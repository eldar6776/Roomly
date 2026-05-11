# ----------------------------------------------------------------------
#  LOG TRANSFER MANAGER - Tihi transfer logova UL → RPI → APP
# ----------------------------------------------------------------------
"""
ARHITEKTURA:
1. UL (ESP32 kontroleri) - čuvaju logove u ring bufferu
2. RPI (ovaj modul) - prikuplja logove i drži ih u SQLite queue-u
3. APP (Electron) - prima logove i upisuje u svoju bazu

PRIORITETI:
- NULTI: Korisničke komande (nikada ne blokiraju)
- NIZAK: Ovaj log transfer sistem (radi u pozadini)

WORKFLOW:
1. Background task kontinuirano Pull-uje logove sa UL uređaja
2. Čuva ih lokalno u SQLite queue (ako APP nije dostupan)
3. Kada je APP online, šalje logove jedan po jedan
4. APP potvrđuje uspješan upis, RPI briše log iz queue-a
5. RPI šalje DELETE_LOG na UL da oslobodi buffer
"""

import sqlite3
import threading
import time
import requests
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any
from collections import deque
import json

# ----------------------------------------------------------------------
# KONFIGURACIJA
# ----------------------------------------------------------------------

# Interval za pull logova sa UL uređaja (sekunde)
UL_PULL_INTERVAL = 10  # Svake 10 sekundi provjerava UL uređaje

# Interval za push logova ka APP (sekunde)
APP_PUSH_INTERVAL = 5  # Svake 5 sekundi pokušava slati ka APP

# Retry logika
MAX_RETRIES = 3
RETRY_BACKOFF = [5, 15, 60]  # Sekunde između pokušaja

# Timeout za HTTP zahtjeve (mali da ne blokira)
HTTP_TIMEOUT = 2  # 2 sekunde

# APP endpoints (dinamički se detektuje kada APP startuje)
APP_BASE_URL = None  # Postavljeno od strane main app-a preko set_app_endpoint()
APP_HEARTBEAT_ENDPOINT = '/api/logs/heartbeat'
APP_RECEIVE_ENDPOINT = '/api/logs/receive'

# Database path
LOG_QUEUE_DB = 'log_transfer_queue.db'

# ----------------------------------------------------------------------
# SQLITE QUEUE ZA LOGOVE
# ----------------------------------------------------------------------

class LogQueue:
    """Thread-safe SQLite queue za lokalno skladištenje logova"""
    
    def __init__(self, db_path: str = LOG_QUEUE_DB):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_database()
    
    def _init_database(self):
        """Kreira tabelu ako ne postoji"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS log_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_number TEXT NOT NULL,
                    device_id INTEGER,
                    log_data TEXT NOT NULL,
                    timestamp_received TEXT NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    last_retry_time TEXT,
                    status TEXT DEFAULT 'pending'
                )
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_status 
                ON log_queue(status)
            ''')
            conn.commit()
    
    def enqueue(self, room_number: str, log_data: Dict[str, Any]) -> int:
        """Dodaje log u queue"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    INSERT INTO log_queue 
                    (room_number, device_id, log_data, timestamp_received)
                    VALUES (?, ?, ?, ?)
                ''', (
                    room_number,
                    log_data.get('device_id'),
                    json.dumps(log_data, ensure_ascii=False),
                    datetime.now().isoformat()
                ))
                conn.commit()
                return cursor.lastrowid
    
    def get_pending(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Vraća pending logove za slanje"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute('''
                    SELECT * FROM log_queue 
                    WHERE status = 'pending'
                    ORDER BY id ASC
                    LIMIT ?
                ''', (limit,))
                return [dict(row) for row in cursor.fetchall()]
    
    def mark_sent(self, log_id: int):
        """Označava log kao poslat"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    UPDATE log_queue 
                    SET status = 'sent'
                    WHERE id = ?
                ''', (log_id,))
                conn.commit()
    
    def mark_failed(self, log_id: int):
        """Označava log kao failed nakon max retries"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    UPDATE log_queue 
                    SET status = 'failed', last_retry_time = ?
                    WHERE id = ?
                ''', (datetime.now().isoformat(), log_id))
                conn.commit()
    
    def increment_retry(self, log_id: int):
        """Inkrementuje retry counter"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    UPDATE log_queue 
                    SET retry_count = retry_count + 1,
                        last_retry_time = ?
                    WHERE id = ?
                ''', (datetime.now().isoformat(), log_id))
                conn.commit()
    
    def get_stats(self) -> Dict[str, int]:
        """Vraća statistiku queue-a"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    SELECT 
                        status,
                        COUNT(*) as count
                    FROM log_queue
                    GROUP BY status
                ''')
                stats = {row[0]: row[1] for row in cursor.fetchall()}
                
                # Total count
                cursor = conn.execute('SELECT COUNT(*) FROM log_queue')
                stats['total'] = cursor.fetchone()[0]
                
                return stats
    
    def cleanup_old_logs(self, days: int = 30):
        """Briše stare logove (sent i failed starije od X dana)"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cutoff_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                cutoff_date = cutoff_date.replace(day=cutoff_date.day - days)
                
                conn.execute('''
                    DELETE FROM log_queue
                    WHERE status IN ('sent', 'failed')
                    AND timestamp_received < ?
                ''', (cutoff_date.isoformat(),))
                conn.commit()

# ----------------------------------------------------------------------
# LOG TRANSFER MANAGER
# ----------------------------------------------------------------------

class LogTransferManager:
    """Glavni manager za transfer logova"""
    
    def __init__(self, config: Dict, send_esp_command_func):
        self.config = config
        self.send_esp_command = send_esp_command_func
        self.queue = LogQueue()
        
        # Thread kontrola
        self.running = False
        self.ul_pull_thread = None
        self.app_push_thread = None
        
        # APP status tracking
        self.app_online = False
        self.last_heartbeat_check = None
        
        # Stats
        self.stats = {
            'logs_pulled': 0,
            'logs_pushed': 0,
            'ul_errors': 0,
            'app_errors': 0
        }
        
        logging.info("[LogTransfer] Manager inicijaliziran")
    
    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------
    
    def start(self):
        """Pokreće background threadove"""
        if self.running:
            logging.warning("[LogTransfer] Manager već radi!")
            return
        
        self.running = True
        
        # Thread 1: Pull logova sa UL uređaja
        self.ul_pull_thread = threading.Thread(
            target=self._ul_pull_worker,
            daemon=True,
            name="UL-Log-Puller"
        )
        self.ul_pull_thread.start()
        
        # Thread 2: Push logova ka APP
        self.app_push_thread = threading.Thread(
            target=self._app_push_worker,
            daemon=True,
            name="APP-Log-Pusher"
        )
        self.app_push_thread.start()
        
        logging.info("[LogTransfer] Background workeri pokrenuti")
    
    def stop(self):
        """Zaustavlja background threadove"""
        self.running = False
        logging.info("[LogTransfer] Zaustavljanje workera...")
    
    def get_status(self) -> Dict[str, Any]:
        """Vraća status i statistiku"""
        queue_stats = self.queue.get_stats()
        
        return {
            'running': self.running,
            'app_online': self.app_online,
            'app_endpoint': APP_BASE_URL,
            'last_heartbeat': self.last_heartbeat_check.isoformat() if self.last_heartbeat_check else None,
            'queue': queue_stats,
            'stats': self.stats
        }
    
    # ------------------------------------------------------------------
    # WORKER 1: Pull logova sa UL uređaja
    # ------------------------------------------------------------------
    
    def _ul_pull_worker(self):
        """
        Kontinuirano pull-uje logove sa UL uređaja.
        Radi sa ULTRA LOW priority - nikada ne blokira glavne procese.
        """
        logging.info("[UL-Puller] Worker pokrenut")
        
        while self.running:
            try:
                # Iteriraj kroz sve sobe
                rooms = self.config.get('sobe', {})
                
                for room_number, room_config in rooms.items():
                    if not self.running:
                        break
                    
                    # Ekstraktuj device ID
                    pin_controller = room_config.get('uredjaji', {}).get('pin_controller', {})
                    device_id = pin_controller.get('ID')
                    
                    if not device_id:
                        continue
                    
                    # Pokušaj pull-ovati log
                    self._pull_log_from_ul(room_number, device_id)
                    
                    # Mini pauza između soba (da ne opterećuje mrežu)
                    time.sleep(0.5)
                
                # Pauza između ciklusa
                time.sleep(UL_PULL_INTERVAL)
                
            except Exception as e:
                logging.error(f"[UL-Puller] Greška u worker loop-u: {e}")
                time.sleep(5)
        
        logging.info("[UL-Puller] Worker zaustavljen")
    
    def _pull_log_from_ul(self, room_number: str, device_id: str):
        """
        Pull-uje jedan log sa UL uređaja.
        Ne briše log sa UL - to će se uraditi tek kada APP potvrdi prijem.
        """
        try:
            # Šalje READ_LOG komandu
            resp, msg, json_data = self.send_esp_command(
                room_number,
                {'CMD': 'READ_LOG', 'ID': device_id},
                timeout=HTTP_TIMEOUT
            )
            
            # Provjeri status
            if not json_data:
                return
            
            status = json_data.get('status', '').upper()
            
            if status == 'EMPTY':
                # Nema logova, to je OK
                return
            
            if status != 'OK':
                logging.warning(f"[UL-Puller] Neočekivan status za sobu {room_number}: {status}")
                return
            
            # Log pronađen! Dodaj u queue
            log_id = self.queue.enqueue(room_number, json_data)
            self.stats['logs_pulled'] += 1
            
            logging.info(
                f"[UL-Puller] ✓ Log #{log_id} from soba {room_number} "
                f"(event: {json_data.get('event_name', 'N/A')})"
            )
            
        except Exception as e:
            self.stats['ul_errors'] += 1
            logging.debug(f"[UL-Puller] Greška za sobu {room_number}: {e}")
    
    # ------------------------------------------------------------------
    # WORKER 2: Push logova ka APP
    # ------------------------------------------------------------------
    
    def _app_push_worker(self):
        """
        Kontinuirano šalje logove ka APP-u (ako je online).
        Radi sa LOW priority.
        """
        logging.info("[APP-Pusher] Worker pokrenut")
        
        while self.running:
            try:
                # Provjeri da li je APP online
                if not self._check_app_heartbeat():
                    time.sleep(APP_PUSH_INTERVAL * 2)  # Duža pauza ako APP nije online
                    continue
                
                # Uzmi pending logove
                pending_logs = self.queue.get_pending(limit=10)  # Batch od 10
                
                if not pending_logs:
                    time.sleep(APP_PUSH_INTERVAL)
                    continue
                
                # Šalji logove jedan po jedan
                for log_entry in pending_logs:
                    if not self.running:
                        break
                    
                    success = self._push_log_to_app(log_entry)
                    
                    if success:
                        # Uspješno poslat - obriši sa UL uređaja
                        self._delete_log_from_ul(
                            log_entry['room_number'],
                            log_entry['device_id']
                        )
                    
                    # Mini pauza između slanja
                    time.sleep(0.2)
                
                time.sleep(APP_PUSH_INTERVAL)
                
            except Exception as e:
                logging.error(f"[APP-Pusher] Greška u worker loop-u: {e}")
                time.sleep(5)
        
        logging.info("[APP-Pusher] Worker zaustavljen")
    
    def _check_app_heartbeat(self) -> bool:
        """Provjerava da li je APP online"""
        if not APP_BASE_URL:
            return False
        
        try:
            url = f"{APP_BASE_URL}{APP_HEARTBEAT_ENDPOINT}"
            response = requests.get(url, timeout=HTTP_TIMEOUT)
            
            self.last_heartbeat_check = datetime.now()
            
            if response.status_code == 200:
                if not self.app_online:
                    logging.info("[APP-Pusher] ✓ APP je sada ONLINE!")
                self.app_online = True
                return True
            else:
                if self.app_online:
                    logging.warning("[APP-Pusher] ✗ APP je sada OFFLINE")
                self.app_online = False
                return False
                
        except Exception as e:
            if self.app_online:
                logging.warning(f"[APP-Pusher] ✗ APP nije dostupan: {e}")
            self.app_online = False
            return False
    
    def _push_log_to_app(self, log_entry: Dict[str, Any]) -> bool:
        """
        Šalje log ka APP endpointu.
        Vraća True ako je uspješno poslat i potvrđen od APP-a.
        """
        if not APP_BASE_URL:
            return False
        
        try:
            # Parse log data
            log_data = json.loads(log_entry['log_data'])
            
            # Šalje POST zahtjev
            url = f"{APP_BASE_URL}{APP_RECEIVE_ENDPOINT}"
            response = requests.post(
                url,
                json={'log': log_data},
                timeout=HTTP_TIMEOUT
            )
            
            # Provjeri odgovor
            if response.status_code == 200:
                result = response.json()
                
                if result.get('status') == 'success':
                    # Uspješno primljen!
                    self.queue.mark_sent(log_entry['id'])
                    self.stats['logs_pushed'] += 1
                    
                    logging.info(
                        f"[APP-Pusher] ✓ Log #{log_entry['id']} sent to APP "
                        f"(soba: {log_entry['room_number']})"
                    )
                    return True
                else:
                    # APP odbio log
                    logging.warning(
                        f"[APP-Pusher] APP odbio log #{log_entry['id']}: "
                        f"{result.get('message', 'Unknown error')}"
                    )
                    self.queue.increment_retry(log_entry['id'])
                    
                    if log_entry['retry_count'] >= MAX_RETRIES:
                        self.queue.mark_failed(log_entry['id'])
                    
                    return False
            else:
                # HTTP greška
                logging.warning(
                    f"[APP-Pusher] HTTP {response.status_code} za log #{log_entry['id']}"
                )
                self.queue.increment_retry(log_entry['id'])
                self.stats['app_errors'] += 1
                return False
                
        except Exception as e:
            logging.error(f"[APP-Pusher] Greška slanja log #{log_entry['id']}: {e}")
            self.queue.increment_retry(log_entry['id'])
            self.stats['app_errors'] += 1
            return False
    
    def _delete_log_from_ul(self, room_number: str, device_id: int):
        """
        Briše log sa UL uređaja nakon što je uspješno poslat i potvrđen od APP-a.
        """
        try:
            resp, msg, json_data = self.send_esp_command(
                room_number,
                {'CMD': 'DELETE_LOG', 'ID': str(device_id)},
                timeout=HTTP_TIMEOUT
            )
            
            if json_data and json_data.get('status', '').upper() == 'OK':
                logging.debug(
                    f"[UL-Puller] ✓ Log deleted from UL device (soba: {room_number})"
                )
            else:
                logging.warning(
                    f"[UL-Puller] Nije moguće obrisati log sa UL (soba: {room_number})"
                )
                
        except Exception as e:
            logging.debug(f"[UL-Puller] Greška brisanja loga sa UL: {e}")

# ----------------------------------------------------------------------
# GLOBALNA INSTANCA
# ----------------------------------------------------------------------

_manager_instance: Optional[LogTransferManager] = None

def init_log_transfer_manager(config: Dict, send_esp_command_func):
    """Inicijalizuje global manager instance"""
    global _manager_instance
    _manager_instance = LogTransferManager(config, send_esp_command_func)
    return _manager_instance

def get_log_transfer_manager() -> Optional[LogTransferManager]:
    """Vraća global manager instance"""
    return _manager_instance

def set_app_endpoint(base_url: str):
    """
    Postavlja APP endpoint URL.
    Ovu funkciju poziva glavni server kada primi registraciju od APP-a.
    
    Example: set_app_endpoint("http://192.168.1.100:3000")
    """
    global APP_BASE_URL
    APP_BASE_URL = base_url.rstrip('/')
    logging.info(f"[LogTransfer] APP endpoint postavljen na: {APP_BASE_URL}")

# ----------------------------------------------------------------------
# FLASK API ENDPOINTI (opciono - za status monitoring)
# ----------------------------------------------------------------------

def register_flask_routes(app):
    """Registruje Flask rute za monitoring log transfera"""
    from flask import jsonify
    
    @app.route('/api/log_transfer/status', methods=['GET'])
    def log_transfer_status():
        """Vraća status log transfer sistema"""
        manager = get_log_transfer_manager()
        if not manager:
            return jsonify({
                'status': 'error',
                'message': 'Log Transfer Manager nije inicijaliziran'
            }), 500
        
        return jsonify({
            'status': 'success',
            'data': manager.get_status()
        })
    
    @app.route('/api/log_transfer/register_app', methods=['POST'])
    def register_app_endpoint():
        """
        APP poziva ovaj endpoint kada se pokrene da bi registrovao svoj URL.
        Payload: {"app_url": "http://192.168.1.100:3000"}
        """
        from flask import request
        
        data = request.get_json()
        app_url = data.get('app_url')
        
        if not app_url:
            return jsonify({
                'status': 'error',
                'message': 'app_url is required'
            }), 400
        
        set_app_endpoint(app_url)
        
        manager = get_log_transfer_manager()
        if manager:
            manager.app_online = True
        
        return jsonify({
            'status': 'success',
            'message': 'APP endpoint registered successfully'
        })
