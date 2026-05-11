# ----------------------------------------------------------------------
#  TOPLIK SERVICE - PYTHON BACKEND SERVER (FAZA 6.3: Admin PIN Change)
# ----------------------------------------------------------------------
import os
import json
import requests  
import jwt 
import subprocess
import sys
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, redirect, make_response, url_for, send_file
from waitress import serve
import re
import threading
import time
import logging
from collections import OrderedDict
import sqlite3

# --- DEBUG FLAG (True = detaljni logovi, False = samo greške) ---
DEBUG = False

# --- TIMEOUTI (sekunde) ---
TIMEOUT_NTFY_POST = 5
TIMEOUT_MDNS_RESOLVE = 5
TIMEOUT_ESP_SHORT = 2
TIMEOUT_ESP_DEFAULT = 3
TIMEOUT_ESP_LONG = 5
TIMEOUT_PROXY_GET = 5
TIMEOUT_PROXY_POST_JSON = 10
TIMEOUT_PROXY_POST_FILES = 30
TIMEOUT_OTA_UPLOAD = 120
TIMEOUT_APP_POST = 2

# SOS retry interval (sekunde)
SOS_RETRY_SECONDS = 600

# --- INICIJALIZACIJA APLIKACIJE ---
app = Flask(__name__)
logging.basicConfig(
    level=logging.INFO,  # INFO za log transfer
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- GLOBALNE VARIJABLE ---
CONFIG = {}
config_lock = threading.Lock()

# Tracking aktivnih update procesa po sobama
# Format: {soba_id: {'active': bool, 'start_time': timestamp, 'last_check': timestamp, 'last_progress': int}}
active_updates = {}
update_lock = threading.Lock()

# Timeout za update proces (90 sekundi - 9× frontend polling interval)
UPDATE_TIMEOUT_SECONDS = 90
# Interval provjere watchdog-a (15 sekundi)
UPDATE_WATCHDOG_INTERVAL = 15
# No-progress timeout (ako progress ne raste 30s)
NO_PROGRESS_TIMEOUT_SECONDS = 30

# Pozadinski taskovi (sekunde)
RESOLVER_INTERVAL_SECONDS = 60
RESOLVER_ROOM_DELAY_SECONDS = 1
LOG_TRANSFER_START_DELAY_SECONDS = 3
STAFF_PIN_SYNC_INTERVAL_SECONDS = 3600
STAFF_PIN_SYNC_START_DELAY_SECONDS = 30

# Tracking SOS notifikacija {soba_id: {'notified': bool, 'last_try': timestamp}}
sos_notification_state = {}

# Autoritativno stanje fitnes termostata za manager UI (postavlja se iz uspješnih komandi)
manager_fitness_state_lock = threading.Lock()
manager_fitness_state = {
    'isThermostatOn': None,
    'setpoint': None
}

def update_watchdog():
    """Background thread koji periodično provjerava zaglavljene update procese."""
    while True:
        time.sleep(UPDATE_WATCHDOG_INTERVAL)
        try:
            with update_lock:
                current_time = time.time()
                stuck_rooms = []
                
                for soba_id, update_info in list(active_updates.items()):
                    if not isinstance(update_info, dict):
                        # Stari format, konvertuj
                        if update_info:  # Ako je True
                            active_updates[soba_id] = {
                                'active': True,
                                'start_time': current_time,
                                'last_check': current_time,
                                'last_progress': 0,
                                'last_progress_time': current_time
                            }
                        else:
                            del active_updates[soba_id]
                        continue
                    
                    if not update_info.get('active', False):
                        continue
                    
                    elapsed = current_time - update_info.get('start_time', current_time)
                    last_check_elapsed = current_time - update_info.get('last_check', current_time)
                    last_progress_elapsed = current_time - update_info.get('last_progress_time', current_time)
                    
                    # Provjeri no-progress timeout (30s bez promjene progresa)
                    if last_progress_elapsed > NO_PROGRESS_TIMEOUT_SECONDS:
                        stuck_rooms.append(soba_id)
                        progress = update_info.get('last_progress', 0)
                        logging.error(
                            f"WATCHDOG: Update za sobu {soba_id} ZAGLAVLJEN - nema progresa {last_progress_elapsed:.0f}s "
                            f"(progress={progress}%) - resetujem lock"
                        )
                        active_updates[soba_id]['active'] = False
                        continue
                    
                    # Provjeri opšti timeout (90s ukupno)
                    if elapsed > UPDATE_TIMEOUT_SECONDS:
                        stuck_rooms.append(soba_id)
                        logging.warning(
                            f"WATCHDOG: Update za sobu {soba_id} prekoračio opšti timeout "
                            f"({elapsed:.0f}s > {UPDATE_TIMEOUT_SECONDS}s) - resetujem lock"
                        )
                        active_updates[soba_id]['active'] = False
                        continue
                    
                    # Provjeri da li je update_status pozivan (last_check)
                    if last_check_elapsed > 30:
                        logging.warning(
                            f"WATCHDOG: Update za sobu {soba_id} - nema update_status poziva {last_check_elapsed:.0f}s "
                            f"(elapsed={elapsed:.0f}s, progress={update_info.get('last_progress', 0)}%)"
                        )
                
                # Očisti neaktivne
                for soba_id in list(active_updates.keys()):
                    if isinstance(active_updates[soba_id], dict) and not active_updates[soba_id].get('active'):
                        del active_updates[soba_id]
                        
        except Exception as e:
            logging.error(f"WATCHDOG: Greška u watchdog thread-u: {e}")

# Pokreni watchdog thread
watchdog_thread = threading.Thread(target=update_watchdog, daemon=True)
watchdog_thread.start()
logging.info("Update watchdog thread pokrenut")

# ----------------------------------------------------------------------
# POSTAVKE
# ----------------------------------------------------------------------
DEFAULT_SECRET_KEY = 'OVDJE-STAVITE-NEKI-VAS-DUGACAK-TAJNI-KLJUC-12345'
app.config['SECRET_KEY'] = DEFAULT_SECRET_KEY

# ----------------------------------------------------------------------
# FUNKCIJE ZA RUKOVANJE KONFIGURACIJOM
# ----------------------------------------------------------------------
def is_update_active(soba_id):
    """Provjerava da li je update aktivan za sobu (thread-safe helper)."""
    with update_lock:
        update_info = active_updates.get(soba_id)
        if update_info is None:
            return False
        if isinstance(update_info, bool):
            return update_info
        if isinstance(update_info, dict):
            return update_info.get('active', False)
        return False

def set_update_active(soba_id, active, log_message=None):
    """Postavlja status update-a za sobu (thread-safe helper)."""
    with update_lock:
        if active:
            active_updates[soba_id] = {
                'active': True,
                'start_time': time.time(),
                'last_check': time.time(),
                'last_progress': 0,
                'last_progress_time': time.time()
            }
            if log_message:
                logging.info(log_message)
        else:
            if soba_id in active_updates:
                active_updates[soba_id] = {'active': False, 'start_time': 0, 'last_check': 0}
                if log_message:
                    logging.info(log_message)
            # Očisti nakon markovanja kao neaktivan
            if soba_id in active_updates and not active_updates[soba_id].get('active'):
                del active_updates[soba_id]

def _get_nested(config, keys, default=None):
    current = config
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current

def _as_number(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def apply_config_settings():
    global DEBUG
    global TIMEOUT_NTFY_POST, TIMEOUT_MDNS_RESOLVE, TIMEOUT_ESP_SHORT, TIMEOUT_ESP_DEFAULT, TIMEOUT_ESP_LONG
    global TIMEOUT_PROXY_GET, TIMEOUT_PROXY_POST_JSON, TIMEOUT_PROXY_POST_FILES, TIMEOUT_OTA_UPLOAD, TIMEOUT_APP_POST
    global SOS_RETRY_SECONDS
    global UPDATE_TIMEOUT_SECONDS, UPDATE_WATCHDOG_INTERVAL, NO_PROGRESS_TIMEOUT_SECONDS
    global RESOLVER_INTERVAL_SECONDS, RESOLVER_ROOM_DELAY_SECONDS, LOG_TRANSFER_START_DELAY_SECONDS
    global STAFF_PIN_SYNC_INTERVAL_SECONDS, STAFF_PIN_SYNC_START_DELAY_SECONDS

    with config_lock:
        cfg = CONFIG

    DEBUG = bool(_get_nested(cfg, ['server', 'debug'], DEBUG))
    app.config['SECRET_KEY'] = str(_get_nested(cfg, ['security', 'secret_key'], app.config.get('SECRET_KEY')))

    timeouts = cfg.get('timeouts', {})
    TIMEOUT_NTFY_POST = _as_number(timeouts.get('ntfy_post_seconds', timeouts.get('ntfy_post', TIMEOUT_NTFY_POST)), TIMEOUT_NTFY_POST)
    TIMEOUT_MDNS_RESOLVE = _as_number(timeouts.get('mdns_resolve_seconds', timeouts.get('mdns_resolve', TIMEOUT_MDNS_RESOLVE)), TIMEOUT_MDNS_RESOLVE)
    TIMEOUT_ESP_SHORT = _as_number(timeouts.get('esp_short_seconds', timeouts.get('esp_short', TIMEOUT_ESP_SHORT)), TIMEOUT_ESP_SHORT)
    TIMEOUT_ESP_DEFAULT = _as_number(timeouts.get('esp_default_seconds', timeouts.get('esp_default', TIMEOUT_ESP_DEFAULT)), TIMEOUT_ESP_DEFAULT)
    TIMEOUT_ESP_LONG = _as_number(timeouts.get('esp_long_seconds', timeouts.get('esp_long', TIMEOUT_ESP_LONG)), TIMEOUT_ESP_LONG)
    TIMEOUT_PROXY_GET = _as_number(timeouts.get('proxy_get_seconds', timeouts.get('proxy_get', TIMEOUT_PROXY_GET)), TIMEOUT_PROXY_GET)
    TIMEOUT_PROXY_POST_JSON = _as_number(timeouts.get('proxy_post_json_seconds', timeouts.get('proxy_post_json', TIMEOUT_PROXY_POST_JSON)), TIMEOUT_PROXY_POST_JSON)
    TIMEOUT_PROXY_POST_FILES = _as_number(timeouts.get('proxy_post_files_seconds', timeouts.get('proxy_post_files', TIMEOUT_PROXY_POST_FILES)), TIMEOUT_PROXY_POST_FILES)
    TIMEOUT_OTA_UPLOAD = _as_number(timeouts.get('ota_upload_seconds', timeouts.get('ota_upload', TIMEOUT_OTA_UPLOAD)), TIMEOUT_OTA_UPLOAD)
    TIMEOUT_APP_POST = _as_number(timeouts.get('app_post_seconds', timeouts.get('app_post', TIMEOUT_APP_POST)), TIMEOUT_APP_POST)

    update_cfg = cfg.get('update', {})
    UPDATE_TIMEOUT_SECONDS = _as_number(update_cfg.get('timeout_seconds', UPDATE_TIMEOUT_SECONDS), UPDATE_TIMEOUT_SECONDS)
    UPDATE_WATCHDOG_INTERVAL = _as_number(update_cfg.get('watchdog_interval', UPDATE_WATCHDOG_INTERVAL), UPDATE_WATCHDOG_INTERVAL)
    NO_PROGRESS_TIMEOUT_SECONDS = _as_number(update_cfg.get('no_progress_timeout_seconds', NO_PROGRESS_TIMEOUT_SECONDS), NO_PROGRESS_TIMEOUT_SECONDS)

    ntfy_cfg = cfg.get('ntfy', {})
    SOS_RETRY_SECONDS = _as_number(ntfy_cfg.get('sos_retry_seconds', ntfy_cfg.get('sos_retry', SOS_RETRY_SECONDS)), SOS_RETRY_SECONDS)

    background_cfg = cfg.get('background', {})
    RESOLVER_INTERVAL_SECONDS = _as_number(
        background_cfg.get('resolver_interval_seconds', RESOLVER_INTERVAL_SECONDS),
        RESOLVER_INTERVAL_SECONDS
    )
    RESOLVER_ROOM_DELAY_SECONDS = _as_number(
        background_cfg.get('resolver_room_delay_seconds', RESOLVER_ROOM_DELAY_SECONDS),
        RESOLVER_ROOM_DELAY_SECONDS
    )
    LOG_TRANSFER_START_DELAY_SECONDS = _as_number(
        background_cfg.get('log_transfer_start_delay_seconds', LOG_TRANSFER_START_DELAY_SECONDS),
        LOG_TRANSFER_START_DELAY_SECONDS
    )
    STAFF_PIN_SYNC_INTERVAL_SECONDS = _as_number(
        background_cfg.get('staff_pin_sync_interval_seconds', STAFF_PIN_SYNC_INTERVAL_SECONDS),
        STAFF_PIN_SYNC_INTERVAL_SECONDS
    )
    STAFF_PIN_SYNC_START_DELAY_SECONDS = _as_number(
        background_cfg.get('staff_pin_sync_start_delay_seconds', STAFF_PIN_SYNC_START_DELAY_SECONDS),
        STAFF_PIN_SYNC_START_DELAY_SECONDS
    )

def load_config():
    global CONFIG
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            original_config = json.load(f, object_pairs_hook=OrderedDict)
            for soba_id, soba_data in original_config.get('sobe', {}).items():
                soba_data['cached_ip'] = None
            
            with config_lock:
                CONFIG = original_config
            apply_config_settings()
            logging.info("Uspješno učitan i inicijaliziran 'config.json'.")
    except Exception as e:
        logging.critical(f"!!! GRESKA pri čitanju 'config.json': {e}")
        exit(1)

def get_service_name():
    with config_lock:
        service_name = _get_nested(CONFIG, ['server', 'service_name'], None)
    return service_name or os.environ.get('TOPLIK_SERVICE_NAME')

def restart_systemd_service(service_name):
    if not service_name:
        logging.error("RESTART: Service name not provided.")
        return False

    cmd = ['systemctl', 'restart', service_name]
    if hasattr(os, 'geteuid') and os.geteuid() != 0:
        cmd.insert(0, 'sudo')

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logging.info(f"RESTART: Service '{service_name}' restarted.")
        return True
    except Exception as e:
        logging.error(f"RESTART: Failed to restart service '{service_name}': {e}")
        return False

def save_config():
    """Sprema trenutni CONFIG u config.json (thread-safe)."""
    with config_lock:
        try:
            # Deep copy via JSON to avoid modifying global state and to strip runtime fields
            config_to_save = json.loads(json.dumps(CONFIG))
            
            # Remove cached_ip from all rooms before saving
            for soba_data in config_to_save.get('sobe', {}).values():
                soba_data.pop('cached_ip', None)

            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(config_to_save, f, indent=2, ensure_ascii=False)
            logging.info("CONFIG: Uspješno spremljen config.json.")
            return True
        except Exception as e:
            logging.error(f"CONFIG: Nije moguće upisati u config.json: {e}")
            return False

# ----------------------------------------------------------------------
#  SOS NOTIFIKACIJA LOGIKA
# ----------------------------------------------------------------------
def check_and_notify_sos(room_id, is_sos_active):
    """
    Provjerava da li treba poslati ntfy notifikaciju za SOS alarm.
    Logika:
    - Ako SOS nije aktivan -> Briše state (reset).
    - Ako je već javljeno -> Ne radi ništa.
    - Ako nije javljeno -> Šalje notifikaciju (uz retry od 10 min).
    """
    global sos_notification_state
    
    state = sos_notification_state.get(room_id, {'notified': False, 'last_try': 0})
    
    # 1. Ako SOS više nije aktivan na uređaju (neko ga je resetovao)
    if not is_sos_active:
        if state['notified']:
            logging.info(f"SOS RESET: Alarm resetovan za sobu {room_id}. Čistim stanje notifikacije.")
            if room_id in sos_notification_state:
                del sos_notification_state[room_id]
        return

    # 2. SOS je aktivan, i već smo uspješno javili
    if state['notified']:
        return # Čekamo manualni reset od recepcionera

    # 3. SOS je aktivan, nismo javili (ili je prošli put puklo)
    now = time.time()
    # Retry interval: 10 minuta
    if (now - state['last_try']) > SOS_RETRY_SECONDS:
        ntfy_topic = _get_nested(CONFIG, ['ntfy', 'topic'], CONFIG.get('ntfy_topic'))
        if not ntfy_topic:
            logging.warning("SOS DETECTED: ntfy_topic nije konfigurisan u config.json!")
            return

        try:
            # Ime sobe za ljepši ispis
            room_name = CONFIG.get('sobe', {}).get(room_id, {}).get('ime', f'Soba {room_id}')
            
            logging.info(f"SOS ALARM: Šaljem notifikaciju za sobu {room_id} ({room_name}) na temu '{ntfy_topic}'...")
            
            headers = {
                "Title": f"SOS ALARM - Soba {room_id}",
                "Priority": "urgent",
                "Tags": "warning,skull"
            }
            data = f"SOS Alarm aktiviran u sobi: {room_name}!"
            
            # Slanje na ntfy.sh
            resp = requests.post(
                f"https://ntfy.sh/{ntfy_topic}",
                data=data.encode('utf-8'),
                headers=headers,
                timeout=TIMEOUT_NTFY_POST
            )
            
            if resp.status_code == 200:
                logging.info(f"SOS NOTIFIKACIJA USPJEŠNO POSLANA za sobu {room_id}")
                state['notified'] = True
            else:
                logging.error(f"SOS NOTIFIKACIJA GREŠKA: {resp.status_code} - {resp.text}")
                # notified ostaje False, probat će opet za 10 min
                
        except Exception as e:
            logging.error(f"SOS NOTIFIKACIJA EXCEPTION: {e}")
        
        state['last_try'] = now
        sos_notification_state[room_id] = state

# ----------------------------------------------------------------------
#  PARSER ZA GET_STATUS (JSON Format)
# ----------------------------------------------------------------------
def parse_get_status_from_json(json_data, room_id=None):
    """
    Mapira JSON odgovor od GET_STATUS na interni format koji frontend očekuje.
    Svi podaci se vraćaju BEZ maskiranja za potpunu kontrolu sistema.
    """
    if not json_data or 'data' not in json_data:
        return {}

    d = json_data['data']

    # --- SOS CHECK ---
    if room_id and 'sos' in d:
        sos_active = d['sos'].get('active', False)
        # Pozivamo logiku za notifikaciju
        check_and_notify_sos(room_id, sos_active)
    # -----------------

    main_data = {}

    # Mapiranje WiFi podataka - BEZ MASKIRANJA PASSWORD-A
    if 'wifi' in d:
        main_data['wifi_ssid'] = d['wifi'].get('ssid')
        main_data['wifi_password'] = d['wifi'].get('password')  # Dodato - bez maskiranja
        main_data['wifi_connected'] = d['wifi'].get('connected')
        main_data['wifi_mdns'] = d['wifi'].get('mdns')
        main_data['wifi_ip'] = d['wifi'].get('ip')
        main_data['wifi_port'] = d['wifi'].get('port')
        main_data['ip_address'] = d['wifi'].get('ip')  # Kompatibilnost
    
    if 'network' in d:
        main_data['ip_address'] = d['network'].get('ip')
        main_data['port'] = d['network'].get('port')
        main_data['mdns'] = d['network'].get('mdns')

    # Vrijeme i zona
    if 'time' in d:
        main_data['current_time'] = d['time'].get('current')
        main_data['utc_time'] = d['time'].get('utc')
        main_data['timezone_offset'] = d['time'].get('timezone_offset')
        main_data['timezone_offset_minutes'] = d['time'].get('timezone_offset_minutes')
        main_data['dst_active'] = d['time'].get('dst_active')

    # Sunce - izlazak i zalazak
    if 'sun' in d:
        main_data['sunrise'] = d['sun'].get('sunrise')
        main_data['sunset'] = d['sun'].get('sunset')

    # Rasvjeta - sve postavke
    if 'light' in d:
        main_data['timer_on'] = d['light'].get('timer_on')
        main_data['timer_off'] = d['light'].get('timer_off')
        main_data['light_relay_state'] = d['light'].get('relay_state')
        main_data['light_control_mode'] = d['light'].get('control_mode')
        main_data['timer_on_type'] = d['light'].get('timer_on_type')
        main_data['timer_off_type'] = d['light'].get('timer_off_type')
        main_data['on_time'] = d['light'].get('on_time')
        main_data['off_time'] = d['light'].get('off_time')
    
    # Ping Watchdog
    if 'watchdog' in d:
        main_data['ping_watchdog'] = "Enabled" if d['watchdog'].get('ping_enabled') else "Disabled"
        main_data['ping_watchdog_enabled'] = d['watchdog'].get('ping_enabled')
    
    # Direktno iz root nivoa ako postoji
    if 'ping_watchdog' in d:
        main_data['ping_watchdog'] = d.get('ping_watchdog')
        main_data['ping_watchdog_enabled'] = d.get('ping_watchdog')

    # Thermostat - svi podaci
    if 'thermostat' in d:
        t = d['thermostat']
        main_data['temperature'] = t.get('temperature')
        main_data['setpoint'] = t.get('setpoint')
        main_data['threshold'] = t.get('threshold')
        main_data['mode'] = t.get('mode')
        main_data['pump_valve'] = t.get('valve')
        main_data['valve'] = t.get('valve')
        main_data['pump'] = t.get('pump')
        main_data['fan'] = t.get('fan')
        main_data['ema_alpha'] = t.get('ema_alpha')
        main_data['fluid_temp'] = t.get('fluid_temp')
        main_data['fluid_available'] = t.get('fluid_available')

    # SOS podaci - VAŽNO za monitoring
    if 'sos' in d:
        main_data['sos_active'] = d['sos'].get('active')
        main_data['sos_timestamp'] = d['sos'].get('timestamp')

    # IR podaci
    if 'ir' in d:
        main_data['ir_received'] = d['ir'].get('received')
        if d['ir'].get('received'):
            main_data['ir_ctrl_mode'] = d['ir'].get('ctrl_mode')
            main_data['ir_state'] = d['ir'].get('state')
            main_data['ir_measured_temp'] = d['ir'].get('measured_temp')
            main_data['ir_setpoint'] = d['ir'].get('setpoint')
    
    # Dodaj i raw podatke za kompletan pristup
    main_data['raw'] = d
    
    return main_data

# ----------------------------------------------------------------------
#  HELPER FUNKCIJE ZA IP RESOLVING I SLANJE
# ----------------------------------------------------------------------
def resolve_and_cache_ip(soba_id):
    """
    (POZADINSKA FUNKCIJA) Pokušava riješiti IP i spremiti ga u CONFIG.
    Koristi JSON parser za ESP32 unificirani format.
    """
    with config_lock:
        if soba_id not in CONFIG['sobe']:
            return None
        soba_config = CONFIG['sobe'][soba_id]
        mdns_name = soba_config['mdns']
        port = soba_config['port']
    mdns_url = f"http://{mdns_name}:{port}/sysctrl.cgi"
    params = {'CMD': 'GET_IP_ADDRESS'}
    try:
        logging.info(f"RESOLVING: Tražim IP za {soba_id} ({mdns_name})...")
        r = requests.get(mdns_url, params=params, timeout=TIMEOUT_MDNS_RESOLVE)
        r.raise_for_status()
        
        # --- JSON PARSING ---
        try:
            data = r.json()
            if data.get('status') == 'success' and 'data' in data and 'ip' in data['data']:
                ip_address = data['data']['ip']
                logging.info(f"RESOLVED: Soba {soba_id} ({mdns_name}) je na IP {ip_address}")
                with config_lock:
                    CONFIG['sobe'][soba_id]['cached_ip'] = ip_address
                return ip_address
            else:
                logging.warning(f"Neuspjelo parsiranje IP adrese za {soba_id}. JSON: {data}")
                return None
        except ValueError:
            logging.error(f"RESOLVE FAILED: Odgovor nije validan JSON. Raw: {r.text[:100]}")
            return None
            
    except requests.exceptions.RequestException as e:
        logging.error(f"RESOLVE FAILED: Neuspješno kontaktiranje {mdns_name}. Greška: {e}")
        with config_lock:
            if soba_id in CONFIG['sobe']:
                CONFIG['sobe'][soba_id]['cached_ip'] = None
        return None

def get_cached_url_only(soba_id):
    """
    (BRZA FUNKCIJA) Vraća URL samo ako je IP keširan. NIKADA ne pokreće resolve.
    """
    with config_lock:
        soba_config = CONFIG['sobe'].get(soba_id)
        if not soba_config:
            return None, "soba_not_found"
        
        cached_ip = soba_config.get('cached_ip')
        port = soba_config['port']

    if cached_ip:
        return f"http://{cached_ip}:{port}/sysctrl.cgi", "ok"
    else:
        return None, "resolving"

def send_esp_command(soba_id, params, timeout=TIMEOUT_ESP_DEFAULT):
    """
    Šalje komandu i validira JSON odgovor.
    Vraća (response_object, message_string, json_data_dict).
    """
    base_url, status = get_cached_url_only(soba_id)
    
    if status == "soba_not_found":
        logging.error(f"FATAL: Pokušaj slanja komande na nepostojeću sobu {soba_id}")
        return None, "Greška: Soba nije pronađena u konfiguraciji.", None
    
    if status == "resolving":
        logging.warning(f"INFO: Komanda za {soba_id} odbijena (cached_ip=None). Pozadinski task traži adresu.")
        threading.Thread(target=resolve_and_cache_ip, args=(soba_id,), daemon=True).start()
        return None, "Uređaj se još traži (mDNS). Pokušajte ponovo za 10 sekundi.", None

    try:
        from urllib.parse import urlencode
        full_url = f"{base_url}?{urlencode(params)}"
        
        # 🔥 UVIJEK loguj punu URL za debugging
        logging.info(f"🌐 [{soba_id}] PUNA URL: {full_url}")
        
        if DEBUG:
            logging.info("=" * 80)
            logging.info(f">>> ŠALJEM KOMANDU NA SOBU {soba_id}")
            logging.info(f">>> PARAMETRI: {params}")
            logging.info(f">>> PUNA URL: {full_url}")
            logging.info("=" * 80)

        r = requests.get(base_url, params=params, timeout=timeout)

        if DEBUG:
            logging.info(f"<<< ODGOVOR: HTTP {r.status_code}")
            logging.info(f"<<< RAW TEXT (prvih 500 chars): {r.text[:500]}")
        
        r.raise_for_status()
        
        # --- JSON PARSING ---
        try:
            json_data = r.json()
            if DEBUG:
                logging.info(f"<<< JSON PARSIRAN: {json_data}")
            
            # Prihvati i "success" i "OK" (READ_LOG koristi "OK")
            status = json_data.get('status', '').lower()
            if status in ['success', 'ok']:
                if DEBUG:
                    logging.info(f"<<< STATUS: {status.upper()} ✓")
                    logging.info(f"<<< MESSAGE: {json_data.get('message', 'Success')}")
                    logging.info("=" * 80)
                return r, "ok", json_data  # USPJEH
            else:
                error_msg = json_data.get('message', 'Unknown error')
                logging.error(f"<<< STATUS: FAILED ✗")
                logging.error(f"<<< ERROR MESSAGE: {error_msg}")
                if DEBUG:
                    logging.error(f"<<< FULL JSON: {json_data}")
                    logging.info("=" * 80)
                return None, f"ESP greška: {error_msg}", json_data
        except ValueError:
            # Fallback za non-JSON odgovore (backward compatibility)
            if DEBUG:
                logging.warning(f"<<< UPOZORENJE: Odgovor NIJE JSON!")
                logging.warning(f"<<< RAW TEXT: {r.text[:200]}")
                logging.info("=" * 80)
            return r, "ok", None
        
    except requests.exceptions.RequestException as e:
        if DEBUG:
            logging.error("=" * 80)
        logging.error(f"!!! GREŠKA KONEKCIJE ZA SOBU {soba_id}")
        logging.error(f"!!! URL BIO: {base_url}")
        logging.error(f"!!! EXCEPTION: {e}")
        if DEBUG:
            logging.error("=" * 80)
        
        with config_lock:
            if soba_id in CONFIG['sobe']:
                CONFIG['sobe'][soba_id]['cached_ip'] = None
        
        threading.Thread(target=resolve_and_cache_ip, args=(soba_id,), daemon=True).start()
        
        return None, "Greška: Konekcija na uređaj nije uspjela. Adresa se osvježava u pozadini. Pokušajte ponovo.", None

def find_soba_id_by_mdns(mdns_name):
    """Helper funkcija za pronalazak soba_id (npr. '505') iz mDNS imena."""
    with config_lock:
        for soba_id, data in CONFIG.get('sobe', {}).items():
            if data.get('mdns') == mdns_name:
                return soba_id
    return None

# ----------------------------------------------------------------------
#  HELPER FUNKCIJA ZA DUAL KONTROLER OPERACIJE (PIN I SYSTEM_ID)
# ----------------------------------------------------------------------
def send_command_to_both_controllers(room_number, command_params, controller_id, secondary_controller_id=None, timeout=TIMEOUT_ESP_LONG):
    """
    Šalje komandu na glavni i sekundarni kontroler (ako postoji).
    Vraća success samo ako oba kontrolera uspješno odgovore.
    
    Args:
        room_number: Broj sobe
        command_params: Dict sa komandom (bez 'ID' parametra)
        controller_id: ID glavnog kontrolera
        secondary_controller_id: ID sekundarnog kontrolera (optional)
        timeout: Timeout za komandu
        
    Returns:
        (success: bool, message: str, primary_json: dict, secondary_json: dict)
    """
    # Komanda za glavni kontroler
    primary_params = command_params.copy()
    primary_params['ID'] = controller_id
    
    logging.info(f"🔑 [{room_number}] Šaljem komandu na GLAVNI kontroler ID={controller_id}")
    _, primary_msg, primary_json = send_esp_command(room_number, primary_params, timeout=timeout)
    
    if primary_json is None or primary_json.get('status') != 'success':
        logging.error(f"❌ [{room_number}] GLAVNI kontroler FAILED: {primary_msg}")
        return False, f"Glavni kontroler neuspješan: {primary_msg}", primary_json, None
    
    logging.info(f"✅ [{room_number}] GLAVNI kontroler SUCCESS")
    
    # Ako postoji sekundarni kontroler, šalji i na njega
    if secondary_controller_id:
        secondary_params = command_params.copy()
        secondary_params['ID'] = secondary_controller_id
        
        logging.info(f"🔑 [{room_number}] Šaljem komandu na SEKUNDARNI kontroler ID={secondary_controller_id}")
        _, secondary_msg, secondary_json = send_esp_command(room_number, secondary_params, timeout=timeout)
        
        if secondary_json is None or secondary_json.get('status') != 'success':
            logging.error(f"❌ [{room_number}] SEKUNDARNI kontroler FAILED: {secondary_msg}")
            return False, f"Sekundarni kontroler neuspješan: {secondary_msg}", primary_json, secondary_json
        
        logging.info(f"✅ [{room_number}] SEKUNDARNI kontroler SUCCESS")
        return True, "Oba kontrolera uspješna", primary_json, secondary_json
    else:
        # Nema sekundarnog kontrolera, samo glavni je uspješan
        return True, "Glavni kontroler uspješan", primary_json, None

# ----------------------------------------------------------------------
#  DECORATOR ZA API KEY AUTENTIFIKACIJU (Windows APP)
# ----------------------------------------------------------------------
def require_api_key(f):
    """Dekorator koji provjerava X-API-Key header za Windows APP endpointe."""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        with config_lock:
            expected_key = _get_nested(
                CONFIG,
                ['security', 'external_api_key'],
                CONFIG.get('external_api_key', 'KLJUC-ZA-HOTELSKI-SOFTVER-98765')
            )
        
        if api_key != expected_key:
            logging.warning(f"API KEY ODBIJEN: {api_key}")
            return jsonify({'status': 'error', 'message': 'Neispravan API ključ'}), 401
        
        return f(*args, **kwargs)
    return decorated_function

# ----------------------------------------------------------------------
#  KORISNIČKE (GOST) RUTE
# ----------------------------------------------------------------------
@app.route('/')
def login_page():
    return render_template('login.html')

@app.route('/soba')
def soba_page():
    return render_template('soba.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    pin = data.get('pin') 
    if not pin:
        return jsonify({'success': False, 'message': 'PIN nije poslan'}), 400
    
    try:
        with config_lock:
            for soba_id, soba_data in CONFIG.get('sobe', {}).items():
                if soba_data.get('guest_pin') == pin:
                    token_payload = {
                        'soba_id': soba_id, 
                        'guest_pin': pin, # Spremi PIN u token
                        'mdns': soba_data['mdns'],
                        'port': soba_data['port'],
                        'tip': 'gost',
                        'exp': datetime.utcnow() + timedelta(hours=24)
                    }
                    token = jwt.encode(token_payload, app.config['SECRET_KEY'], algorithm='HS256')
                    response = make_response(jsonify({'success': True}))
                    response.set_cookie('token', token, httponly=True, samesite='Strict', max_age=86400)
                    logging.info(f"USPJEŠAN LOGIN: Gost se prijavio za sobu {soba_id} (Ime: {soba_data['ime']})")
                    return response

        logging.warning(f"NEUSPJEŠAN LOGIN: Pogrešan PIN unesen: {pin}")
        return jsonify({'success': False, 'message': 'Pogrešan PIN'}), 401
            
    except Exception as e:
        logging.error(f"Greška u /api/login: {e}")
        return jsonify({'success': False, 'message': 'Greška servera'}), 500

@app.route('/api/control', methods=['POST'])
def api_control():
    token = request.cookies.get('token')
    if not token:
        return jsonify({'success': False, 'message': 'Niste prijavljeni'}), 401
    try:
        soba_data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        if soba_data.get('tip') != 'gost':
             return jsonify({'success': False, 'message': 'Neispravan token'}), 401
        
        # --- SIGURNOSNI BLOK (Faza 6.2) ---
        soba_id = soba_data.get('soba_id')
        pin_iz_tokena = soba_data.get('guest_pin')
        is_manager_access = soba_data.get('is_manager_access', False)
        if not pin_iz_tokena and not is_manager_access:
            return jsonify({'success': False, 'message': 'Neispravan token (nedostaje pin). Prijavite se ponovo.'}), 401

        with config_lock:
            if not soba_id or soba_id not in CONFIG['sobe']:
                return jsonify({'success': False, 'message': 'Konfiguracija sobe nije pronađena.'}), 500
            trenutni_guest_pin = CONFIG['sobe'][soba_id].get('guest_pin')
            if not is_manager_access and trenutni_guest_pin != pin_iz_tokena:
                logging.warning(f"ODBIJENO: Token za sobu {soba_id} je nevažeći (PIN promijenjen). Korisnik izbačen.")
                return jsonify({'success': False, 'message': 'PIN za sobu je promijenjen. Molimo prijavite se ponovo.'}), 401
        # --- KRAJ SIGURNOSNOG BLOKA ---

        data = request.json
        uredjaj = data.get('uredjaj'); vrijednost = data.get('vrijednost')
        logging.info(f"[DEBUG] Primljen zahtjev: soba={soba_id}, uredjaj={uredjaj}, vrijednost={vrijednost}")

        with config_lock:
            soba_config = CONFIG['sobe'][soba_id]
            logging.info(f"[DEBUG] Cached IP za {soba_id}: {soba_config.get('cached_ip')}")
            
            # Specijalna obrada za thermostat_power i open_door
            if uredjaj == 'thermostat_power':
                termostat_id = soba_config.get('uredjaji', {}).get('termostat_set', {}).get('ID')
                if not termostat_id:
                    return jsonify({'success': False, 'message': 'ID termostata nije definiran'}), 400
                params = {'CMD': 'SET_THST_ON' if vrijednost else 'SET_THST_OFF', 'ID': termostat_id}
            elif uredjaj == 'open_door':
                pin_controller_id = soba_config.get('uredjaji', {}).get('pin_controller', {}).get('ID')
                if not pin_controller_id:
                    return jsonify({'success': False, 'message': 'ID pin kontrolera nije definiran'}), 400
                params = {'CMD': 'OPEN_DOOR', 'ID': pin_controller_id}
            else:
                # Standardna obrada uređaja iz config-a
                if not uredjaj or uredjaj not in soba_config.get('uredjaji', {}):
                    logging.error(f"[DEBUG] Uređaj '{uredjaj}' NIJE u config! Dostupni: {list(soba_config.get('uredjaji', {}).keys())}")
                    return jsonify({'success': False, 'message': f'Uređaj "{uredjaj}" nije definiran'}), 400
                device_config = soba_config['uredjaji'][uredjaj]
                logging.info(f"[DEBUG] Device config: {device_config}")
                
                params = device_config.copy()
                komanda = params.get('CMD')
                
                if komanda == 'SET_PIN': params['VALUE'] = '1' if vrijednost else '0'
                elif komanda == 'SET_ROOM_TEMP': params['VALUE'] = str(int(vrijednost))
                elif komanda in ['SET_THST_ON', 'SET_THST_OFF', 'SET_THST_HEATING', 'SET_THST_COOLING']: pass
                else: return jsonify({'success': False, 'message': f'Komanda {komanda} nije podržana'}), 500

        logging.info(f"GOST KONTROLA ({soba_id}): Uređaj '{uredjaj}' -> {params}")
        response, message, json_resp = send_esp_command(soba_id, params)
        
        logging.info(f"[DEBUG] Odgovor send_esp_command: response={'OK' if response else 'None'}, message='{message}'")
        
        if response and response.ok:
            return jsonify({'success': True, 'message': 'Komanda poslana'})
        else:
            logging.error(f"[DEBUG] KOMANDA NIJE USPJELA! Message: {message}")
            return jsonify({'success': False, 'message': message}), 500
            
    except jwt.ExpiredSignatureError:
        logging.info("GOST KONTROLA: Sesija istekla (ExpiredSignatureError)")
        return jsonify({'success': False, 'message': 'Sesija istekla, prijavite se ponovo'}), 401
    except Exception as e:
        logging.error(f"Greška u /api/control: {e}")
        return jsonify({'success': False, 'message': 'Greška servera'}), 500

# ----------------------------------------------------------------------
#  ADMIN RUTE
# ----------------------------------------------------------------------
def provjeri_admin_token(token):
    if not token: return False
    try:
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        return data.get('tip') == 'admin'
    except: return False

def provjeri_manager_token(token):
    if not token: return False
    try:
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        return data.get('tip') == 'manager'
    except: return False

@app.route('/admin')
def admin_login_page():
    return render_template('admin_login.html')

# AŽURIRANO: /admin/dashboard (Ispravno šalje 'guest_pin')
@app.route('/admin/dashboard')
def admin_dashboard():
    if not provjeri_admin_token(request.cookies.get('admin_token')):
        return redirect(url_for('admin_login_page'))
    
    with config_lock:
        sobe_za_admina = {}
        # AŽURIRANO: Ključ je 'soba_id' (fiksni) a ne 'pin'
        for soba_id, data in CONFIG.get('sobe', {}).items(): 
            uredjaji = data.get('uredjaji', {})
            sobe_za_admina[soba_id] = { # Koristi fiksni soba_id kao ključ
                "ime": data.get('ime'),
                "mdns": data.get('mdns'),
                "port": data.get('port'),
                "guest_pin": data.get('guest_pin', 'N/A'), # Šaljemo stvarni PIN
                "termostat_id": uredjaji.get('termostat_set', {}).get('ID', 'N/A'),
                "pin_controller_id": uredjaji.get('pin_controller', {}).get('ID', 'N/A'),
                "secondary_pin_controller_id": uredjaji.get('secondary_pin_controller', {}).get('ID', 'N/A'),
                "scene_controller_id": uredjaji.get('scene_controller', {}).get('ID', 'N/A')
            }
    return render_template('admin.html', sobe=sobe_za_admina)

@app.route('/api/admin/login', methods=['POST'])
def api_admin_login():
    data = request.json
    password = data.get('password')
    if not password:
        return jsonify({'success': False, 'message': 'Lozinka nije poslana'}), 400
    if password == _get_nested(CONFIG, ['security', 'admin_password'], CONFIG.get('admin_password')):
        token_payload = { 'tip': 'admin', 'exp': datetime.utcnow() + timedelta(hours=8) }
        token = jwt.encode(token_payload, app.config['SECRET_KEY'], algorithm='HS256')
        response = make_response(jsonify({'success': True}))
        response.set_cookie('admin_token', token, httponly=True, samesite='Strict', max_age=28800)
        logging.info("USPJEŠAN LOGIN: Administrator se prijavio.")
        return response
    else:
        logging.warning("NEUSPJEŠAN LOGIN: Pogrešna admin lozinka.")
        return jsonify({'success': False, 'message': 'Pogrešna lozinka'}), 401

@app.route('/api/admin/proxy', methods=['POST'])
def api_admin_proxy():
    if not provjeri_admin_token(request.cookies.get('admin_token')):
        return jsonify({'success': False, 'message': 'Niste prijavljeni'}), 401
    
    data = request.json
    soba_id = data.get('soba_id')
    params = data.get('params')
    
    if not soba_id or not params:
        return jsonify({'success': False, 'message': 'Missing soba_id or params'}), 400

    # Validacija za SET_SYSID (očekuje decimalni VALUE u rasponu 10000-65000)
    if params.get('CMD') == 'SET_SYSID':
        if 'ID' not in params:
            return jsonify({'success': False, 'message': 'Missing ID for SET_SYSID'}), 400

        raw_value = params.get('VALUE')
        normalized_value = None

        if isinstance(raw_value, list) and len(raw_value) == 2:
            try:
                b0 = int(raw_value[0])
                b1 = int(raw_value[1])
                if 0 <= b0 <= 255 and 0 <= b1 <= 255:
                    normalized_value = (b0 << 8) | b1
            except (TypeError, ValueError):
                normalized_value = None
        elif isinstance(raw_value, (int, float)):
            normalized_value = int(raw_value)
        elif isinstance(raw_value, str) and raw_value.isdigit():
            normalized_value = int(raw_value)

        if normalized_value is None:
            return jsonify({'success': False, 'message': 'Invalid VALUE for SET_SYSID'}), 400

        if normalized_value < 10000 or normalized_value > 65000:
            return jsonify({'success': False, 'message': 'System ID mora biti u rasponu 10000-65000'}), 400

        params['VALUE'] = str(normalized_value)
    
    # Proveri da li je update aktivan za ovu sobu
    if is_update_active(soba_id):
        logging.warning(f"ADMIN PROXY: Blokirano za sobu {soba_id} - update u toku")
        return jsonify({'success': False, 'message': 'Firmware update u toku, molimo sačekajte'}), 503
        
    logging.info(f"ADMIN PROXY ({soba_id}): {params}")
    response, message, json_resp = send_esp_command(soba_id, params)
    
    # --- SOS CHECK FIX ---
    # Ako je komanda GET_STATUS, moramo provući kroz parser da bi okinuli SOS notifikaciju
    if response and response.ok and params.get('CMD') == 'GET_STATUS':
        try:
            parse_get_status_from_json(json_resp, room_id=soba_id)
        except Exception as e:
            logging.error(f"ADMIN PROXY: Greška u SOS check-u: {e}")
    # ---------------------

    if response and response.ok:
        return jsonify({'success': True, 'data': json_resp, 'message': message})
    else:
        # Vraćamo i data ako postoji (može sadržavati error detalje)
        return jsonify({'success': False, 'message': message, 'data': json_resp}), 500

@app.route('/api/admin/esp_proxy/<soba_id>/<path:endpoint>', methods=['GET', 'POST'])
def api_admin_esp_proxy(soba_id, endpoint):
    """Proxy za direktne ESP32 HTTP endpointe (npr. /slots, /update_status, /upload)"""
    if not provjeri_admin_token(request.cookies.get('admin_token')):
        return jsonify({'success': False, 'message': 'Niste prijavljeni'}), 401
    
    # Proveri da li je update aktivan za ovu sobu
    if is_update_active(soba_id) and endpoint != 'update_status':
        logging.warning(f"ESP Proxy: Blokirano {endpoint} za sobu {soba_id} - update u toku")
        return jsonify({'success': False, 'message': 'Firmware update u toku, molimo sačekajte'}), 503
    
    with config_lock:
        soba_data = CONFIG.get('sobe', {}).get(soba_id)
    
    if not soba_data:
        return jsonify({'success': False, 'message': f'Soba {soba_id} ne postoji'}), 404
    
    ip = soba_data.get('cached_ip')
    if not ip:
        return jsonify({'success': False, 'message': f'IP adresa za sobu {soba_id} nije dostupna'}), 503
    
    port = soba_data.get('port', '8020')
    url = f"http://{ip}:{port}/{endpoint}"
    
    try:
        if request.method == 'GET':
            # Proslijedi query parametre (slot, addr, itd.)
            resp = requests.get(url, params=request.args, timeout=TIMEOUT_PROXY_GET)
        else:
            # Ako je multipart/form-data (upload), proslijedi files i data
            if request.files:
                files = {}
                for key, file in request.files.items():
                    files[key] = (file.filename, file.stream, file.content_type)
                resp = requests.post(url, data=request.form, files=files, timeout=TIMEOUT_PROXY_POST_FILES)
            else:
                resp = requests.post(url, json=request.json, timeout=TIMEOUT_PROXY_POST_JSON)
        
        result = resp.json()
        
        # Ako je start_update i uspješno, markiraj kao aktivan
        if endpoint == 'start_update' and result.get('status') == 'success':
            set_update_active(soba_id, True, f"Update pokrenut za sobu {soba_id} - blokiranje ostalih komandi")
        
        # Ako je start_update ali neuspješan, osiguraj da lock nije setovan
        elif endpoint == 'start_update' and result.get('status') != 'success':
            set_update_active(soba_id, False, f"Update za sobu {soba_id} nije uspješno pokrenut - osiguravam otključavanje")
        
        # Ako je update_status, proveri da li je završen
        if endpoint == 'update_status':
            state = result.get('state', 0)
            active = result.get('active', False)
            progress = result.get('progress', 0)
            was_locked = is_update_active(soba_id)
            
            # Ažuriraj timestamp posljednje provjere i progresa
            if was_locked:
                with update_lock:
                    if soba_id in active_updates and isinstance(active_updates[soba_id], dict):
                        active_updates[soba_id]['last_check'] = time.time()
                        
                        # Ako se progress promenio, ažuriraj progress tracking
                        old_progress = active_updates[soba_id].get('last_progress', 0)
                        if progress != old_progress:
                            active_updates[soba_id]['last_progress'] = progress
                            active_updates[soba_id]['last_progress_time'] = time.time()
                            logging.info(f"Update progress za sobu {soba_id}: {old_progress}% → {progress}%")
            
            # State 0 = IDLE, State 7 = FAILED, State 8 = SUCCESS
            # Resetuj lock ako je update neaktivan ILI u završnom stanju
            if not active or state in [0, 7, 8]:
                if was_locked:
                    set_update_active(soba_id, False, 
                        f"Update završen za sobu {soba_id} (state={state}, active={active}, progress={progress}%) - otključavanje komandi")
            # Ako je ESP32 vratio active=True ali naš flag nije setovan, sinhronizuj
            elif active and not was_locked:
                set_update_active(soba_id, True, f"Update detektovan za sobu {soba_id} - sinhronizacija flaga (progress={progress}%)")
        
        return jsonify(result), resp.status_code
    except Exception as e:
        logging.error(f"ESP Proxy greška za {soba_id}/{endpoint}: {e}")
        
        # KRITIČNO: Ako je greška na start_update, resetuj lock da ne zaglavimo sistem
        if endpoint == 'start_update':
            set_update_active(soba_id, False, 
                f"EXCEPTION na start_update za sobu {soba_id} - resetujem lock: {e}")
        
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/reset_update_lock/<soba_id>', methods=['POST'])
def api_admin_reset_update_lock(soba_id):
    """Ručni reset update lock-a ako zaglavi"""
    if not provjeri_admin_token(request.cookies.get('admin_token')):
        return jsonify({'success': False, 'message': 'Niste prijavljeni'}), 401
    
    was_active = is_update_active(soba_id)
    if was_active:
        with update_lock:
            update_info = active_updates.get(soba_id, {})
            if isinstance(update_info, dict):
                elapsed = time.time() - update_info.get('start_time', 0)
                logging.warning(f"RUČNI RESET update lock-a za sobu {soba_id} (trajao {elapsed:.0f}s)")
            else:
                logging.warning(f"RUČNI RESET update lock-a za sobu {soba_id}")
        
        set_update_active(soba_id, False)
        return jsonify({'success': True, 'message': 'Update lock resetovan'})
    else:
        return jsonify({'success': False, 'message': 'Update nije bio aktivan'}), 400

@app.route('/api/admin/update_locks', methods=['GET'])
def api_admin_get_update_locks():
    """Vraća status svih aktivnih update lock-ova (za debugging)"""
    if not provjeri_admin_token(request.cookies.get('admin_token')):
        return jsonify({'success': False, 'message': 'Niste prijavljeni'}), 401
    
    with update_lock:
        locks_info = {}
        current_time = time.time()
        for soba_id, update_info in active_updates.items():
            if isinstance(update_info, dict) and update_info.get('active'):
                elapsed = current_time - update_info.get('start_time', current_time)
                last_check_ago = current_time - update_info.get('last_check', current_time)
                last_progress_ago = current_time - update_info.get('last_progress_time', current_time)
                progress = update_info.get('last_progress', 0)
                locks_info[soba_id] = {
                    'active': True,
                    'elapsed_seconds': round(elapsed, 1),
                    'last_check_ago': round(last_check_ago, 1),
                    'last_progress_change_ago': round(last_progress_ago, 1),
                    'current_progress': progress,
                    'timeout_in': round(UPDATE_TIMEOUT_SECONDS - elapsed, 1),
                    'no_progress_timeout_in': round(NO_PROGRESS_TIMEOUT_SECONDS - last_progress_ago, 1)
                }
    
    return jsonify({
        'success': True, 
        'active_locks': locks_info, 
        'timeout_seconds': UPDATE_TIMEOUT_SECONDS,
        'no_progress_timeout_seconds': NO_PROGRESS_TIMEOUT_SECONDS
    })

# ----------------------------------------------------------------------
#  MANAGER RUTE
# ----------------------------------------------------------------------
@app.route('/manager')
def manager_login_page():
    return render_template('manager_login.html')

@app.route('/api/manager/login', methods=['POST'])
def api_manager_login():
    data = request.json
    pin = data.get('pin')
    if not pin:
        return jsonify({'success': False, 'message': 'PIN nije poslan'}), 400
    
    with config_lock:
        manager_pin = _get_nested(CONFIG, ['staff_pins', 'manager'], CONFIG.get('manager_pin'))

    if pin == manager_pin:
        token_payload = { 'tip': 'manager', 'exp': datetime.utcnow() + timedelta(hours=8) }
        token = jwt.encode(token_payload, app.config['SECRET_KEY'], algorithm='HS256')
        response = make_response(jsonify({'success': True}))
        response.set_cookie('manager_token', token, httponly=True, samesite='Strict', max_age=28800)
        logging.info("USPJEŠAN LOGIN: Manager se prijavio.")
        return response
    else:
        logging.warning("NEUSPJEŠAN LOGIN: Pogrešan manager PIN.")
        return jsonify({'success': False, 'message': 'Pogrešan PIN'}), 401

@app.route('/manager/dashboard')
def manager_dashboard():
    if not provjeri_manager_token(request.cookies.get('manager_token')):
        return redirect(url_for('manager_login_page'))
    
    with config_lock:
        # Prikazuj samo standardne sobe (3xx, 5xx), sakrij specijalne uređaje ('hvac', '101')
        sobe_za_managera = {
            soba_id: data for soba_id, data in CONFIG.get('sobe', {}).items()
            if soba_id.isdigit() and len(soba_id) == 3 and (soba_id.startswith('3') or soba_id.startswith('5'))
        }
    return render_template('manager.html', sobe=sobe_za_managera)

@app.route('/manager/soba/<soba_id>')
def manager_soba_redirect(soba_id):
    if not provjeri_manager_token(request.cookies.get('manager_token')):
        return redirect(url_for('manager_login_page'))

    with config_lock:
        if soba_id not in CONFIG['sobe']:
            return jsonify({'success': False, 'message': 'Soba nije pronađena'}), 404
        soba_config = CONFIG['sobe'][soba_id]
        
        token_payload = {
            'soba_id': soba_id, 
            'guest_pin': soba_config['guest_pin'], 
            'mdns': soba_config['mdns'],
            'port': soba_config['port'],
            'tip': 'gost',
            'is_manager_access': True, # Oznaka za managerski pristup
            'exp': datetime.utcnow() + timedelta(minutes=30) # Kratkotrajni token
        }
        token = jwt.encode(token_payload, app.config['SECRET_KEY'], algorithm='HS256')
        
        response = make_response(redirect(url_for('soba_page')))
        response.set_cookie('token', token, httponly=True, samesite='Strict', max_age=1800) # 30 min
        logging.info(f"MANAGER PRISTUP: Manager dobio token za sobu {soba_id}")
        return response

@app.route('/api/admin/get_status', methods=['POST'])
def api_admin_get_status():
    if not provjeri_admin_token(request.cookies.get('admin_token')):
        return jsonify({'success': False, 'message': 'Niste prijavljeni'}), 401
    
    data = request.json
    mdns_name = data.get('mdns')
    if not mdns_name:
        logging.error("ADMIN GRESKA: /api/admin/get_status pozvan bez 'mdns' parametra.")
        return jsonify({'success': False, 'message': 'Greška: Nedostaje mdns u zahtjevu.'}), 400

    soba_id = find_soba_id_by_mdns(mdns_name)
    
    if not soba_id:
        logging.warning(f"ADMIN: Primljen zahtjev za nepoznat mDNS: {mdns_name}")
        return jsonify({'success': False, 'message': f'Greška: mDNS ime {mdns_name} nije pronađeno u config.json.'}), 400
    
    params = {'CMD': 'GET_STATUS'}
    logging.info(f"ADMIN: Tražim GET_STATUS za {soba_id} (mDNS: {mdns_name})") 
    
    response, message, json_data = send_esp_command(soba_id, params, timeout=TIMEOUT_ESP_LONG)
    
    if response and response.ok:
        parsed_data = parse_get_status_from_json(json_data, room_id=soba_id)
        logging.info(f"ADMIN: Uspješno parsiran status za {soba_id}")
        return jsonify({'success': True, 'status': parsed_data})
    else:
        logging.error(f"ADMIN GRESKA: Dohvaćanje statusa za {soba_id} nije uspjelo.")
        return jsonify({'success': False, 'message': message}), 500

@app.route('/api/admin/set_settings', methods=['POST'])
def api_admin_set_settings():
    if not provjeri_admin_token(request.cookies.get('admin_token')):
        return jsonify({'success': False, 'message': 'Niste prijavljeni'}), 401
    
    data = request.json
    mdns_name = data.get('mdns')
    termostat_id = data.get('termostat_id')
    settings = data.get('settings')
    
    if not mdns_name:
         return jsonify({'success': False, 'message': 'Greška: Nedostaje mdns.'}), 400
         
    soba_id = find_soba_id_by_mdns(mdns_name)
    
    if not all([soba_id, settings]):
        logging.error(f"ADMIN SET GRESKA: Poziv bez 'settings' ili 'soba_id' nije pronađen (mdns: {mdns_name})")
        return jsonify({'success': False, 'message': 'Nedostaju ključni podaci (settings) ili mDNS nije pronađen.'}), 400

    commands_to_send = []
    
    if 'mode' in settings:
        mode = settings['mode'].upper()
        if mode == 'HEATING': commands_to_send.append({'CMD': 'TH_HEATING'})
        elif mode == 'COOLING': commands_to_send.append({'CMD': 'TH_COOLING'})
        elif mode == 'ON': commands_to_send.append({'CMD': 'TH_ON'})
        elif mode == 'OFF': commands_to_send.append({'CMD': 'TH_OFF'})
    if 'mdns' in settings:
        commands_to_send.append({'CMD': 'SET_MDNS_NAME', 'MDNS': settings['mdns']})
    if 'port' in settings:
        commands_to_send.append({'CMD': 'SET_TCPIP_PORT', 'PORT': settings['port']})
    if termostat_id and termostat_id != 'N/A' and 'setpoint' in settings:
        commands_to_send.append({'CMD': 'SET_ROOM_TEMP', 'ID': termostat_id, 'VALUE': settings['setpoint']})
    if 'wifi_ssid' in settings and 'wifi_password' in settings:
        cmd = {'CMD': 'SET_SSID_PSWRD', 'SSID': settings['wifi_ssid']}
        if settings['wifi_password']: cmd['PSWRD'] = settings['wifi_password']
        commands_to_send.append(cmd)
    if 'ping_watchdog' in settings:
        if settings['ping_watchdog']: commands_to_send.append({'CMD': 'PINGWDG_ON'})
        else: commands_to_send.append({'CMD': 'PINGWDG_OFF'})
    if 'diff' in settings and settings['diff']:
        try:
            diff_value = int(float(settings['diff']) * 10)
            commands_to_send.append({'CMD': 'TH_DIFF', 'VALUE': diff_value})
        except ValueError:
            logging.warning(f"ADMIN SET: Pogrešna 'diff' vrijednost: {settings['diff']}")
    if 'ema_filter' in settings and settings['ema_filter']:
        try:
            ema_value = int(float(settings['ema_filter']) * 10)
            commands_to_send.append({'CMD': 'TH_EMA', 'VALUE': ema_value})
        except ValueError:
             logging.warning(f"ADMIN SET: Pogrešna 'ema_filter' vrijednost: {settings['ema_filter']}")
    if 'timer_on' in settings and 'timer_off' in settings:
         commands_to_send.append({'CMD': 'SET_TIMER', 'TIMERON': settings['timer_on'], 'TIMEROFF': settings['timer_off']})

    
    success_count = 0
    errors = []
    logging.info(f"ADMIN SET: Soba {soba_id} - Počinjem slanje {len(commands_to_send)} komandi...")
    for params in commands_to_send:
        logging.info(f"ADMIN SET ({soba_id}): Šaljem {params}...")
        response, message, json_resp = send_esp_command(soba_id, params)
        if response and response.ok:
            success_count += 1
        else:
            errors.append(f"Komanda {params.get('CMD')} nije uspjela: {message}")
            
    if success_count == len(commands_to_send):
        logging.info(f"ADMIN SET ({soba_id}): Uspješno poslane sve komande.")
        return jsonify({'success': True, 'message': f'Sve postavke ({success_count}) uspješno poslane.'})
    else:
        logging.warning(f"ADMIN SET ({soba_id}): Neke komande nisu uspjele. Poslano {success_count}/{len(commands_to_send)}.")
        return jsonify({'success': False, 'message': f'Neke komande nisu uspjele. Poslano {success_count}/{len(commands_to_send)}. Prva greška: {errors[0]}'})

# ----------------------------------------------------------------------
# CONFIG EDITOR ENDPOINTS
# ----------------------------------------------------------------------

@app.route('/api/admin/config', methods=['GET'])
def api_admin_get_config():
    """Vraća trenutni config.json"""
    if not provjeri_admin_token(request.cookies.get('admin_token')):
        return jsonify({'success': False, 'message': 'Niste prijavljeni'}), 401
    
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        return jsonify({'success': True, 'config': config_data})
    except Exception as e:
        logging.error(f"ADMIN CONFIG: Greška pri čitanju config.json: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/config', methods=['POST'])
def api_admin_save_config():
    """Čuva novi config.json"""
    if not provjeri_admin_token(request.cookies.get('admin_token')):
        return jsonify({'success': False, 'message': 'Niste prijavljeni'}), 401
    
    try:
        new_config = request.json.get('config')
        if not new_config:
            return jsonify({'success': False, 'message': 'Nedostaje config u zahtjevu'}), 400
        
        # Backup postojećeg fajla
        import shutil
        from datetime import datetime
        backup_name = f"config_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        shutil.copy('config.json', backup_name)
        logging.info(f"ADMIN CONFIG: Kreiran backup: {backup_name}")
        
        # Sačuvaj novi config
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(new_config, f, indent=2, ensure_ascii=False)
        
        # Reload config u memoriju
        load_config()
        
        logging.info("ADMIN CONFIG: Novi config.json uspješno sačuvan i učitan")
        return jsonify({'success': True, 'message': 'Config uspješno sačuvan. Backup kreiran.'})
    except Exception as e:
        logging.error(f"ADMIN CONFIG: Greška pri čuvanju config.json: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/config/download', methods=['GET'])
def api_admin_download_config():
    """Download config.json fajla"""
    if not provjeri_admin_token(request.cookies.get('admin_token')):
        return "Unauthorized", 401
    
    try:
        return send_file('config.json', as_attachment=True, download_name='config.json', mimetype='application/json')
    except Exception as e:
        logging.error(f"ADMIN CONFIG: Greška pri download-u: {e}")
        return str(e), 500

@app.route('/api/admin/restart', methods=['POST'])
def api_admin_restart_service():
    if not provjeri_admin_token(request.cookies.get('admin_token')):
        return jsonify({'success': False, 'message': 'Niste prijavljeni'}), 401

    if not sys.platform.startswith('linux'):
        return jsonify({'success': False, 'message': 'Restart je podrzan samo na Linux (systemd)'}), 400

    service_name = get_service_name()
    if not service_name:
        return jsonify({'success': False, 'message': 'Service name nije konfigurisan (server.service_name)'}), 400

    def delayed_restart():
        time.sleep(1)
        restart_systemd_service(service_name)

    threading.Thread(target=delayed_restart, daemon=True).start()
    return jsonify({'success': True, 'message': f'Restart zakazan za servis: {service_name}'}), 200

# ----------------------------------------------------------------------
#  IFTTT / ALEXA WEBHOOK RUTA
# ----------------------------------------------------------------------
@app.route('/api/ifttt/control', methods=['POST'])
def api_ifttt_control():
    data = request.json
    
    # 1. Sigurnosna Provjera Ključa
    secret_key = data.get('api_key')
    with config_lock:
        expected_key = _get_nested(CONFIG, ['security', 'external_api_key'])
        if secret_key != expected_key:
            logging.warning("IFTTT: Odbijen neispravan API ključ.")
            return jsonify({'success': False, 'message': 'Neispravan API ključ'}), 401
    
    # 2. Dohvat Komande (IFTTT šalje soba_id, uredjaj_key i vrijednost)
    room_id = data.get('room_id')
    uredjaj = data.get('uredjaj')
    vrijednost_str = str(data.get('vrijednost', 'off')).lower() # 'on'/'off'
    
    # 3. Validacija Komande
    if not all([room_id, uredjaj]):
        return jsonify({'success': False, 'message': 'Nedostaje room_id ili uredjaj.'}), 400

    # Pretvori string 'on'/'off' u boolean True/False
    if vrijednost_str == 'on':
        vrijednost = True
    elif vrijednost_str == 'off':
        vrijednost = False
    else:
        # Podrška za setpoint ako se šalje
        try:
             vrijednost = float(vrijednost_str)
        except ValueError:
             return jsonify({'success': False, 'message': 'Vrijednost nije valjana (očekivano on/off/broj).'}), 400

    # 4. Izvrši Komandu (Koristi se logika iz /api/control)
    try:
        with config_lock:
            soba_config = CONFIG['sobe'].get(room_id)
            if not soba_config or uredjaj not in soba_config.get('uredjaji', {}):
                return jsonify({'success': False, 'message': f'Uređaj "{uredjaj}" nije definiran za sobu {room_id}.'}), 400
            
            device_config = soba_config['uredjaji'][uredjaj]
            params = device_config.copy()
            komanda = params.get('CMD')
        
        # Prilagodi parametre za ESP32
        if komanda == 'SET_PIN': 
            params['VALUE'] = '1' if vrijednost else '0'
        elif komanda == 'SET_ROOM_TEMP':
            try:
                # Vrijednost (procenat) stiže od Alexe kao broj. Tretiramo ga kao temperaturu.
                temp_trazena = float(vrijednost) 
                
                # --- OVDJE JE OGRANIČAVANJE (Clamping) ---
                MIN_TEMP = 18  # Minimalna dozvoljena temperatura
                MAX_TEMP = 30  # Maksimalna dozvoljena temperatura
                
                final_value = int(round(temp_trazena))
                
                if final_value < MIN_TEMP:
                    final_value = MIN_TEMP
                    logging.info(f"IFTTT/ALEXA: Vrijednost {temp_trazena} je ISPOD minimuma. Postavljam na {final_value}°C")
                elif final_value > MAX_TEMP:
                    final_value = MAX_TEMP
                    logging.info(f"IFTTT/ALEXA: Vrijednost {temp_trazena} je IZNAD maksimuma. Postavljam na {final_value}°C")
                else:
                    logging.info(f"IFTTT/ALEXA: Postavljam temperaturu na {final_value}°C")
                    
                params['VALUE'] = str(final_value)
                
            except ValueError:
                logging.error(f"IFTTT: Nije moguće pretvoriti vrijednost '{vrijednost}' u broj za termostat.")
                params['VALUE'] = str(MIN_TEMP) # Vrati na minimum ako je greška
        else: 
            return jsonify({'success': False, 'message': f'Komanda {komanda} nije podržana preko IFTTT.'}), 500

        logging.info(f"IFTTT KONTROLA ({room_id}): Uređaj '{uredjaj}' -> {params}")
        
        # Šaljemo komandu ESP32 uređaju (koristimo isti send_esp_command)
        response, message, _ = send_esp_command(room_id, params, timeout=TIMEOUT_ESP_DEFAULT)
        
        if response and response.ok:
            return jsonify({'success': True, 'message': 'Komanda poslana IFTTT-om'})
        else:
            return jsonify({'success': False, 'message': message}), 500
            
    except Exception as e:
        logging.error(f"Greška u /api/ifttt/control: {e}")
        return jsonify({'success': False, 'message': 'Greška servera'}), 500
        
# ----------------------------------------------------------------------
#  API RUTA ZA DOHVAT STATUSA ZA GOSTA (Verzija 7.3 - Finalni Sigurni Sync)
# ----------------------------------------------------------------------
def parse_get_pins_response(response_text):
    """Parsira binarni odgovor GET_PINS i vraća string pinova ('00100...')."""
    match = re.search(r'Pins States = ([\d]+)', response_text)
    if match:
        # Odgovor je npr. '00100000'
        return match.group(1).strip() 
    return None

@app.route('/api/status')
def api_get_guest_status():
    token = request.cookies.get('token')
    if not token:
        return jsonify({'success': False, 'message': 'Niste prijavljeni'}), 401
    try:
        soba_data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        if soba_data.get('tip') != 'gost':
             return jsonify({'success': False, 'message': 'Neispravan token'}), 401

        soba_id = soba_data.get('soba_id')
        pin_iz_tokena = soba_data.get('guest_pin')
        is_manager_access = soba_data.get('is_manager_access', False)
        if not pin_iz_tokena and not is_manager_access:
            return jsonify({'success': False, 'message': 'Neispravan token (nedostaje pin). Prijavite se ponovo.'}), 401

        with config_lock:
            if not soba_id or soba_id not in CONFIG['sobe']:
                return jsonify({'success': False, 'message': 'Konfiguracija sobe nije pronađena.'}), 500
            trenutni_guest_pin = CONFIG['sobe'][soba_id].get('guest_pin')
            if not is_manager_access and trenutni_guest_pin != pin_iz_tokena:
                logging.warning(f"ODBIJENO (STATUS): Token za sobu {soba_id} je nevažeći (PIN promijenjen). Korisnik izbačen.")
                return jsonify({'success': False, 'message': 'PIN za sobu je promijenjen. Molimo prijavite se ponovo.'}), 401
            
            # Dohvat pin-to-device mape i termostat ID-a
            soba_config = CONFIG['sobe'][soba_id]
            termostat_id = soba_config.get('uredjaji', {}).get('termostat_set', {}).get('ID')
            uredjaji_config = soba_config.get('uredjaji', {})
            
            # Mapiranje kontrolera i pinova (npr. { '212': {'1':'light_luster', '2':'light_ambient', ...} })
            controller_to_pins = {}
            for device_name, device_data in uredjaji_config.items():
                if device_name.startswith('light_') and 'ID' in device_data and 'PIN' in device_data:
                    ctrl_id = device_data['ID']
                    pin_broj = device_data['PIN']
                    if ctrl_id not in controller_to_pins:
                        controller_to_pins[ctrl_id] = {}
                    controller_to_pins[ctrl_id][pin_broj] = device_name
        
        if not termostat_id:
            return jsonify({'success': False, 'message': 'ID termostata nije definiran'}), 500

        current_temp, setpoint = 22.0, 22.0
        is_thermostat_on = False
        light_states = {}
        
        # 1. DOHVAT TERMOSTATA I TEMPERATURE (GET_ROOM_TEMP)
        logging.info(f"GOST STATUS ({soba_id}): Tražim GET_ROOM_TEMP (ID: {termostat_id})...")
        params_temp = {'CMD': 'GET_ROOM_TEMP', 'ID': termostat_id}
        r_temp, msg_temp, json_temp = send_esp_command(soba_id, params_temp)
        
        if r_temp and r_temp.ok and json_temp:
            # JSON format: {"status":"success","message":"...","data":{"room_temperature":26,"setpoint_temperature":24,"thermostat_control_mode":2,...}}
            if 'data' in json_temp:
                data = json_temp['data']
                current_temp = data.get('room_temperature', 22.0)
                setpoint = data.get('setpoint_temperature', 22.0)
                
                # thermostat_control_mode: 0=OFF, 1=HEATING, 2=COOLING
                control_mode = data.get('thermostat_control_mode', 0)
                is_thermostat_on = (control_mode == 1 or control_mode == 2)
                logging.info(f"GOST STATUS ({soba_id}): Termostat mode={control_mode}, ON={is_thermostat_on}")
        
        # 3. DOHVAT STANJA SVJETALA (GET_PINS)
        # Šaljemo JEDAN zahtjev za SVAKI podređeni kontroler
        for ctrl_id, pin_map in controller_to_pins.items():
            logging.info(f"GOST STATUS ({soba_id}): Tražim GET_PINS za kontroler {ctrl_id}...")
            params_pins = {'CMD': 'GET_PINS', 'ID': ctrl_id}
            r_pins, msg_pins, json_pins = send_esp_command(soba_id, params_pins)
            
            if r_pins and r_pins.ok and json_pins:
                # JSON format: {"status":"success","data":{"pin_states":"00100000"}}
                pins_states_str = json_pins.get('data', {}).get('pin_states', '')
                
                if pins_states_str:
                    # Mapiramo pinove: PIN '1' je prvi karakter, PIN '2' je drugi, itd.
                    # String je 8 karaktera. Pinovi su 1-based (1-8).
                    for pin_str, device_name in pin_map.items():
                        try:
                            pin_index = int(pin_str) - 1 # Pin '1' je indeks 0
                            if pin_index >= 0 and pin_index < len(pins_states_str):
                                # '1' = ON (True), '0' = OFF (False)
                                light_states[device_name] = (pins_states_str[pin_index] == '1')
                            else:
                                logging.warning(f"Mapiranje: Neispravan PIN {pin_str} za {device_name}.")
                        except ValueError:
                            logging.error(f"Mapiranje: Greška konverzije PIN-a za {device_name}.")
            else:
                 logging.warning(f"Nije uspjelo dohvaćanje GET_PINS za kontroler {ctrl_id}.")
        
        
        final_status = {
            'currentTemp': current_temp,
            'setpoint': setpoint,
            'isThermostatOn': is_thermostat_on,
            'lights': light_states
        }

        logging.info(f"GOST STATUS ({soba_id}): Vraćam Temp={current_temp}, Setpoint={setpoint}, On={is_thermostat_on}, Svjetla={len(light_states)}.")
        return jsonify({'success': True, 'status': final_status})

    except jwt.ExpiredSignatureError:
        return jsonify({'success': False, 'message': 'Sesija istekla'}), 401
    except Exception as e:
        logging.error(f"Greška u /api/status (Sigurni Sync): {e}")
        return jsonify({'success': False, 'message': 'Greška servera'}), 500
# ----------------------------------------------------------------------
#  FUNKCIJE ZA EKSTERNI API (PIN SYNC)
# ----------------------------------------------------------------------
@app.route('/api/manager/heating_control', methods=['POST'])
def api_manager_heating_control():
    if not provjeri_manager_token(request.cookies.get('manager_token')):
        return jsonify({'success': False, 'message': 'Niste prijavljeni'}), 401
    
    data = request.json
    uredjaj = data.get('uredjaj')
    vrijednost = data.get('vrijednost')

    # Kontrola termostata u fitnesu
    if uredjaj.startswith('fitness_thermostat'):
        with config_lock:
            config = CONFIG.get('manager_devices', {}).get('fitness_thermostat', {})
            soba_id = config.get('mdns_soba_id')
        
        if not soba_id:
            return jsonify({'success': False, 'message': 'Fitnes termostat nije konfigurisan.'}), 500

        params = None
        if uredjaj == 'fitness_thermostat_setpoint':
            params = {'CMD': 'TH_SETPOINT', 'VALUE': str(int(vrijednost))}
        elif uredjaj == 'fitness_thermostat_on_off':
            params = {'CMD': 'TH_ON' if vrijednost else 'TH_OFF'}
        elif uredjaj == 'fitness_thermostat_mode':
            params = {'CMD': 'TH_HEATING' if vrijednost else 'TH_COOLING'}
        
        if not params:
            return jsonify({'success': False, 'message': f'Komanda za {uredjaj} nije definisana.'}), 500

        response, message, json_resp = send_esp_command(soba_id, params)

        # Ako je prvi pokušaj pao jer uređaj nema cached IP, pokušaj sync resolve + retry.
        if response is None and isinstance(message, str) and 'mDNS' in message:
            resolved_ip = resolve_and_cache_ip(soba_id)
            if resolved_ip:
                response, message, json_resp = send_esp_command(soba_id, params)

        success = response is not None and response.ok
        result = {
            'success': success,
            'message': message,
            'command': params.get('CMD'),
            'response_data': (json_resp or {}).get('data', {}) if isinstance(json_resp, dict) else {}
        }

        if uredjaj == 'fitness_thermostat_on_off':
            applied_on = None
            if success:
                response_data = result.get('response_data', {})
                mode_text = str(response_data.get('mode', '')).upper()
                if mode_text:
                    applied_on = (mode_text != 'OFF')
                else:
                    applied_on = bool(vrijednost)

                with manager_fitness_state_lock:
                    manager_fitness_state['isThermostatOn'] = applied_on

            result['applied_on'] = applied_on
        elif uredjaj == 'fitness_thermostat_setpoint':
            applied_setpoint = int(vrijednost) if success else None
            if success:
                with manager_fitness_state_lock:
                    manager_fitness_state['setpoint'] = applied_setpoint
            result['applied_setpoint'] = applied_setpoint

        return jsonify(result)

    # Kontrola pumpi (HVAC kontroler)
    elif uredjaj in ['pumpa_fancoil', 'pumpa_podno']:
        soba_id = 'hvac'
        pump_id = 2 if uredjaj == 'pumpa_fancoil' else 1

        if vrijednost: # ON -> MANUAL ON
            # 1. Set mode to MANUAL
            _, msg1, _ = send_esp_command(soba_id, {'CMD': 'SET_PUMP_MODE', 'PUMP': pump_id, 'MODE': 'MANUAL'})
            # 2. Set manual output to ON
            _, msg2, _ = send_esp_command(soba_id, {'CMD': 'SET_PUMP_MANUAL', 'PUMP': pump_id, 'VALUE': 1})
            return jsonify({'success': True, 'message': f'Pumpa {pump_id} postavljena na MANUAL ON. ({msg1}, {msg2})'})
        else: # OFF -> AUTO OFF
            # 1. Set mode to AUTO
            _, msg1, _ = send_esp_command(soba_id, {'CMD': 'SET_PUMP_MODE', 'PUMP': pump_id, 'MODE': 'AUTO'})
            # 2. Set manual output to OFF (za svaki slučaj)
            _, msg2, _ = send_esp_command(soba_id, {'CMD': 'SET_PUMP_MANUAL', 'PUMP': pump_id, 'VALUE': 0})
            return jsonify({'success': True, 'message': f'Pumpa {pump_id} vraćena na AUTO. ({msg1}, {msg2})'})
    
    # NOVO: Granularna kontrola pumpi
    elif uredjaj == 'pumpa_fancoil_mode' or uredjaj == 'pumpa_podno_mode':
        soba_id = 'hvac'
        pump_id = 2 if 'fancoil' in uredjaj else 1
        mode = str(vrijednost).upper() # MANUAL ili AUTO
        if mode not in ['MANUAL', 'AUTO']:
            return jsonify({'success': False, 'message': 'Mode mora biti MANUAL ili AUTO'}), 400
        
        _, msg, _ = send_esp_command(soba_id, {'CMD': 'SET_PUMP_MODE', 'PUMP': pump_id, 'MODE': mode})
        return jsonify({'success': True, 'message': f'Mod pumpe {pump_id} postavljen na {mode}. ({msg})'})

    elif uredjaj == 'pumpa_fancoil_manual' or uredjaj == 'pumpa_podno_manual':
        soba_id = 'hvac'
        pump_id = 2 if 'fancoil' in uredjaj else 1
        value = 1 if vrijednost else 0

        _, msg, _ = send_esp_command(soba_id, {'CMD': 'SET_PUMP_MANUAL', 'PUMP': pump_id, 'VALUE': value})
        return jsonify({'success': True, 'message': f'Ručna komanda za pumpu {pump_id} postavljena na {value}. ({msg})'})


    return jsonify({'success': False, 'message': f'Uređaj "{uredjaj}" nije podržan.'}), 400

    if not soba_id:
        return jsonify({'success': False, 'message': f'Soba ID za uređaj "{uredjaj}" nije definiran u konfiguraciji.'}), 500
    if not params:
        return jsonify({'success': False, 'message': f'Komanda za uređaj "{uredjaj}" nije ispravno formirana.'}), 500
    
    response, message, _ = send_esp_command(soba_id, params)
    
    if response and response.ok:
        return jsonify({'success': True, 'message': 'Komanda poslana'})
    else:
        return jsonify({'success': False, 'message': message}), 500

def sync_pin_on_server_and_device(room_id, new_pin):
    with config_lock:
        if room_id not in CONFIG['sobe']:
             return False, f'Greška: Room ID {room_id} nije pronađen u konfiguraciji.'
        soba_config = CONFIG['sobe'][room_id]
        if 'pin_controller' not in soba_config.get('uredjaji', {}):
            return False, f'Greška: Soba {room_id} nema definiran "pin_controller" u config.json.'
        pin_ctrl_config = soba_config['uredjaji']['pin_controller']
        controller_id = pin_ctrl_config.get('ID')
        if not controller_id:
             return False, f'Greška: "pin_controller" za sobu {room_id} nema definiran ID.'

    validity = '1200010130'  # Format: HHMMDDMMYY
    params = {
        'CMD': 'SET_PASSWORD', 
        'ID': controller_id, 
        'TYPE': 'GUEST',
        'GUEST_ID': '1',
        'PASSWORD': new_pin,
        'EXPIRY': validity
    }
    
    response, message, _ = send_esp_command(room_id, params, timeout=TIMEOUT_ESP_LONG)
    
    if response and response.ok:
        with config_lock:
            CONFIG['sobe'][room_id]['guest_pin'] = new_pin
        
        if save_config():
            logging.info(f"PIN SYNC: Soba {room_id} uspješno sinkronizirana na PIN {new_pin}.")
            return True, f'PIN sobe {room_id} uspješno sinkroniziran na {new_pin} (Uređaj & Server).'
        else:
            logging.critical(f"PIN SYNC GREŠKA: PIN promijenjen na uređaju, ali NE I u config.json! Soba: {room_id}.")
            return False, f'PIN je promijenjen na uređaju, ali ne i na serveru (greška pri upisu)!'
    else:
        logging.error(f"PIN SYNC GREŠKA: ESP32 ({room_id}) nije prihvatio PIN. Poruka: {message}")
        return False, f'Greška: ESP32 nije prihvatio PIN. ({message})'


@app.route('/api/external/sync_pin', methods=['POST'])
def api_external_sync_pin():
    data = request.json
    external_key = data.get('api_key'); room_id = data.get('room_id'); new_pin = data.get('new_pin')
    
    with config_lock:
        config_api_key = _get_nested(CONFIG, ['security', 'external_api_key'], CONFIG.get('external_api_key'))
    
    if not config_api_key or external_key != config_api_key:
        logging.warning(f"AUTH: Odbijen eksterni API poziv (pogrešan ključ).")
        return jsonify({'success': False, 'message': 'Neispravan eksterni API ključ.'}), 401

    with config_lock:
        soba_postoji = room_id in CONFIG['sobe']
        
    if not all([room_id, new_pin]) or not soba_postoji:
        logging.warning(f"API SYNC: Neispravan zahtjev (Room ID: {room_id}, Novi PIN: {new_pin}).")
        return jsonify({'success': False, 'message': 'Nedostaje room_id, new_pin ili room_id nije pronađen.'}), 400

    success, message = sync_pin_on_server_and_device(room_id, new_pin)

    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'success': False, 'message': message}), 500

@app.route('/api/external/delete_pin', methods=['POST'])
def api_external_delete_pin():
    data = request.json
    external_key = data.get('api_key'); room_id = data.get('room_id')
    
    with config_lock:
        config_api_key = _get_nested(CONFIG, ['security', 'external_api_key'], CONFIG.get('external_api_key'))
    
    if not config_api_key or external_key != config_api_key:
        logging.warning(f"AUTH: Odbijen eksterni API poziv (pogrešan ključ).")
        return jsonify({'success': False, 'message': 'Neispravan eksterni API ključ.'}), 401

    with config_lock:
        if room_id not in CONFIG['sobe']:
            return jsonify({'success': False, 'message': f'Room ID {room_id} nije pronađen.'}), 400
        soba_config = CONFIG['sobe'][room_id]
        if 'pin_controller' not in soba_config.get('uredjaji', {}):
            return jsonify({'success': False, 'message': f'Soba {room_id} nema "pin_controller".'}), 400
        controller_id = soba_config['uredjaji']['pin_controller'].get('ID')
        if not controller_id:
            return jsonify({'success': False, 'message': f'Soba {room_id} "pin_controller" nema ID.'}), 400

    logging.info(f"PIN DELETE: Brišem PIN za sobu {room_id} (ID: {controller_id})")
    params = {'CMD': 'SET_PASSWORD', 'ID': controller_id, 'TYPE': 'DELETE_GUEST', 'GUEST_ID': '1', 'PASSWORD': '0000'}
    response, message, _ = send_esp_command(room_id, params, timeout=TIMEOUT_ESP_LONG)

    if response and response.ok:
        with config_lock:
            CONFIG['sobe'][room_id]['guest_pin'] = ""
        
        if save_config():
            logging.info(f"PIN DELETE: PIN za sobu {room_id} uspješno obrisan (Uređaj & Server).")
            return jsonify({'success': True, 'message': f'PIN za sobu {room_id} uspješno obrisan.'})
        else:
            logging.critical(f"PIN DELETE GREŠKA: PIN obrisan na uređaju, ali NE I u config.json! Soba: {room_id}.")
            return jsonify({'success': False, 'message': 'PIN je obrisan na uređaju, ali ne i na serveru!'})
    else:
        logging.error(f"PIN DELETE GREŠKA: ESP32 ({room_id}) nije prihvatio G1X. Poruka: {message}")
        return jsonify({'success': False, 'message': f'Greška: ESP32 nije prihvatio komandu za brisanje. ({message})'})

# ----------------------------------------------------------------------
#  DODATNE ADMIN API RUTE
# ----------------------------------------------------------------------
@app.route('/api/admin/restart_esp', methods=['POST'])
def api_admin_restart_esp():
    if not provjeri_admin_token(request.cookies.get('admin_token')):
        return jsonify({'success': False, 'message': 'Niste prijavljeni'}), 401
    
    data = request.json
    mdns_name = data.get('mdns')
    soba_id = find_soba_id_by_mdns(mdns_name)
    if not soba_id:
        return jsonify({'success': False, 'message': 'mDNS nije pronađen.'}), 400

    logging.info(f"ADMIN RESTART: Pokrećem restart za {soba_id} ({mdns_name})")
    response, message, json_data = send_esp_command(soba_id, {'CMD': 'RESTART'}, timeout=TIMEOUT_ESP_LONG)
    
    if response and response.ok:
        return jsonify({'success': True, 'message': 'Komanda za restart poslana. Uređaj se restartuje.'})
    else:
        return jsonify({'success': False, 'message': message})

@app.route('/api/admin/set_esp_time', methods=['POST'])
def api_admin_set_esp_time():
    if not provjeri_admin_token(request.cookies.get('admin_token')):
        return jsonify({'success': False, 'message': 'Niste prijavljeni'}), 401
    
    data = request.json
    mdns_name = data.get('mdns')
    date_str = data.get('date') # Očekuje DDMMYY
    time_str = data.get('time') # Očekuje HHMMSS
    
    soba_id = find_soba_id_by_mdns(mdns_name)
    if not soba_id:
        return jsonify({'success': False, 'message': 'mDNS nije pronađen.'}), 400
    if not date_str or not time_str:
        return jsonify({'success': False, 'message': 'Nedostaje datum ili vrijeme.'}), 400

    logging.info(f"ADMIN SET TIME: Šaljem vrijeme {date_str} {time_str} na {soba_id}")
    params = {'CMD': 'SET_TIME', 'DATE': date_str, 'TIME': time_str}
    response, message, json_data = send_esp_command(soba_id, params, timeout=TIMEOUT_ESP_LONG)
    
    if response and response.ok:
        return jsonify({'success': True, 'message': 'Vrijeme na uređaju uspješno postavljeno.'})
    else:
        return jsonify({'success': False, 'message': message})

@app.route('/api/admin/esp_pin_control', methods=['POST'])
def api_admin_esp_pin_control():
    if not provjeri_admin_token(request.cookies.get('admin_token')):
        return jsonify({'success': False, 'message': 'Niste prijavljeni'}), 401
    
    data = request.json
    mdns_name = data.get('mdns')
    pin = data.get('pin')
    state = data.get('state')
    
    soba_id = find_soba_id_by_mdns(mdns_name)
    if not soba_id:
        return jsonify({'success': False, 'message': 'mDNS nije pronađen.'}), 400
    if not pin:
        return jsonify({'success': False, 'message': 'Nedostaje PIN.'}), 400

    komanda = 'ESP_SET_PIN' if state else 'ESP_RESET_PIN'
    
    logging.info(f"ADMIN PIN CONTROL: Soba {soba_id}, PIN {pin}, Stanje {state}, Komanda {komanda}")
    params = {'CMD': komanda, 'PIN': pin}
    
    response, message, json_data = send_esp_command(soba_id, params, timeout=TIMEOUT_ESP_LONG)
    
    if response and response.ok:
        return jsonify({'success': True, 'message': f'PIN {pin} postavljen.'})
    else:
        return jsonify({'success': False, 'message': message})

@app.route('/api/admin/esp_ota_update', methods=['POST'])
def api_admin_esp_ota_update():
    """Proxy endpoint za ESP32 OTA firmware update"""
    if not provjeri_admin_token(request.cookies.get('admin_token')):
        return jsonify({'success': False, 'message': 'Niste prijavljeni'}), 401
    
    mdns_name = request.form.get('mdns')
    if not mdns_name:
        return jsonify({'success': False, 'message': 'Nedostaje mDNS parametar.'}), 400
    
    if 'firmware' not in request.files:
        return jsonify({'success': False, 'message': 'Nedostaje firmware fajl.'}), 400
    
    firmware_file = request.files['firmware']
    
    soba_id = find_soba_id_by_mdns(mdns_name)
    if not soba_id:
        return jsonify({'success': False, 'message': 'mDNS nije pronađen u konfiguraciji.'}), 400
    
    # Koristi cached_ip iz resolvera (kao send_esp_command)
    with config_lock:
        soba = CONFIG['sobe'].get(soba_id)
        if not soba:
            return jsonify({'success': False, 'message': f'Soba {soba_id} nije pronađena u konfiguraciji.'}), 400
        cached_ip = soba.get('cached_ip')
        port = soba.get('port', 8020)
    
    if not cached_ip:
        return jsonify({'success': False, 'message': 'IP adresa nije resolvovana. Pokušajte ponovo za 10 sekundi.'}), 400
    
    url = f"http://{cached_ip}:{port}/update"
    
    try:
        logging.info(f"ADMIN OTA: Proxy upload firmware na {url} (soba {soba_id})")
        
        # Pripremi fajl za upload
        files = {'update': (firmware_file.filename, firmware_file.stream, 'application/octet-stream')}
        
        # Pošalji POST request sa fajlom
        response = requests.post(url, files=files, timeout=TIMEOUT_OTA_UPLOAD)
        
        if response.status_code == 200:
            logging.info(f"ADMIN OTA: Upload uspješan za sobu {soba_id}")
            return jsonify({'success': True, 'message': 'Firmware uspješno uploadovan. ESP32 se restartuje.'})
        else:
            logging.error(f"ADMIN OTA: Greška {response.status_code} - {response.text}")
            return jsonify({'success': False, 'message': f'ESP32 odgovorio sa greškom: {response.status_code}'}), 500
    
    except requests.exceptions.Timeout:
        # Timeout može biti OK ako se ESP32 restartovao
        logging.warning(f"ADMIN OTA: Timeout tokom upload-a (moguće uspješan ako je ESP32 restartovan)")
        return jsonify({'success': True, 'message': 'Upload završen, ESP32 se restartuje (timeout očekivan).', 'timeout': True})
    except Exception as e:
        logging.error(f"ADMIN OTA: Greška tokom upload-a: {str(e)}")
        return jsonify({'success': False, 'message': f'Greška tokom upload-a: {str(e)}'}), 500


@app.route('/api/admin/hvac_ota_update', methods=['POST'])
def api_admin_hvac_ota_update():
    """Proxy endpoint za HVAC kontroler OTA firmware update"""
    if not provjeri_admin_token(request.cookies.get('admin_token')):
        return jsonify({'success': False, 'message': 'Niste prijavljeni'}), 401

    if 'firmware' not in request.files:
        return jsonify({'success': False, 'message': 'Nedostaje firmware fajl.'}), 400

    firmware_file = request.files['firmware']

    with config_lock:
        soba = CONFIG['sobe'].get('hvac')
        if not soba:
            return jsonify({'success': False, 'message': 'HVAC kontroler nije pronađen u konfiguraciji.'}), 400
        cached_ip = soba.get('cached_ip')
        port = soba.get('port', 80)

    if not cached_ip:
        return jsonify({'success': False, 'message': 'IP adresa HVAC kontrolera nije resolvovana. Pokušajte ponovo za 10 sekundi.'}), 400

    url = f"http://{cached_ip}:{port}/update"

    try:
        logging.info(f"ADMIN HVAC OTA: Proxy upload firmware na {url}")

        files = {'update': (firmware_file.filename, firmware_file.stream, 'application/octet-stream')}
        response = requests.post(url, files=files, timeout=TIMEOUT_OTA_UPLOAD)

        if response.status_code == 200:
            logging.info("ADMIN HVAC OTA: Upload uspješan")
            return jsonify({'success': True, 'message': 'Firmware uspješno uploadovan. HVAC kontroler se restartuje.'})
        else:
            logging.error(f"ADMIN HVAC OTA: Greška {response.status_code} - {response.text}")
            return jsonify({'success': False, 'message': f'HVAC kontroler odgovorio sa greškom: {response.status_code}'}), 500

    except requests.exceptions.Timeout:
        logging.warning("ADMIN HVAC OTA: Timeout tokom upload-a (moguće uspješan ako se HVAC restartovao)")
        return jsonify({'success': True, 'message': 'Upload završen, HVAC kontroler se restartuje (timeout očekivan).', 'timeout': True})
    except requests.exceptions.ConnectionError as e:
        # HVAC OTA handler ne šalje HTTP response prije restarta - veza se prekida odmah
        # To je očekivano ponašanje: Update.end(true) triggera restart bez slanja odgovora
        logging.warning(f"ADMIN HVAC OTA: Veza prekinuta tokom upload-a - ovo je normalno ponašanje HVAC OTA ({str(e)})")
        return jsonify({'success': True, 'message': 'Upload završen, HVAC kontroler se restartuje (veza prekinuta - očekivano).', 'timeout': True})
    except Exception as e:
        logging.error(f"ADMIN HVAC OTA: Greška tokom upload-a: {str(e)}")
        return jsonify({'success': False, 'message': f'Greška tokom upload-a: {str(e)}'}), 500


# ----------------------------------------------------------------------
#  MANAGER API RUTE
# ----------------------------------------------------------------------
@app.route('/api/manager/outdoor_light_status')
def api_manager_outdoor_light_status():
    if not provjeri_manager_token(request.cookies.get('manager_token')):
        return jsonify({'success': False, 'message': 'Niste prijavljeni'}), 401

    outdoor_light_on = False
    with config_lock:
        outdoor_config = CONFIG.get('manager_devices', {}).get('vanjska_rasvjeta', {})
        soba_ids = outdoor_config.get('mdns_soba_ids', [])
        
    for soba_id in soba_ids:
        # Prvo provjeravamo da li soba ID postoji
        with config_lock:
            if soba_id not in CONFIG['sobe']:
                logging.warning(f"MANAGER OUTDOOR: Soba ID {soba_id} za vanjsku rasvjetu nije u CONFIG-u.")
                continue

        # Dohvaćanje statusa
        params = {'CMD': 'GET_STATUS'}
        response, message, json_data = send_esp_command(soba_id, params, timeout=TIMEOUT_ESP_SHORT) # Kraći timeout za status

        if response and response.ok:
            parsed_data = parse_get_status_from_json(json_data, room_id=soba_id)
            if parsed_data.get('light_relay_state') == 'ON':
                outdoor_light_on = True
                break # Ako je jedno upaljeno, cijela rasvjeta je "ON"
        else:
            logging.warning(f"MANAGER OUTDOOR: Nije uspjelo dohvaćanje statusa za sobu {soba_id}. Greška: {message}")
            
    return jsonify({'success': True, 'status': 'on' if outdoor_light_on else 'off'})

@app.route('/api/manager/toggle_outdoor_light', methods=['POST'])
def api_manager_toggle_outdoor_light():
    if not provjeri_manager_token(request.cookies.get('manager_token')):
        return jsonify({'success': False, 'message': 'Niste prijavljeni'}), 401
    
    data = request.json
    state = data.get('state') # 'on' or 'off'

    if state not in ['on', 'off']:
        return jsonify({'success': False, 'message': 'Neispravno stanje (očekuje se "on" ili "off")'}), 400

    with config_lock:
        # Šalji komandu na SVE definisane uređaje
        soba_ids = list(CONFIG.get('sobe', {}).keys())
        outdoor_config = CONFIG.get('manager_devices', {}).get('vanjska_rasvjeta', {})
        command_params = outdoor_config.get(f'command_{state}')

    if not command_params:
        return jsonify({'success': False, 'message': f'Komanda za stanje "{state}" nije definirana u config.json'}), 500

    successful_commands = []
    failed_commands = []

    for soba_id in soba_ids:
        # Provjeri da li je uređaj online prije slanja
        with config_lock:
            is_online = CONFIG.get('sobe', {}).get(soba_id, {}).get('cached_ip') is not None
        
        if not is_online:
            logging.warning(f"MANAGER OUTDOOR TOGGLE: Preskačem offline uređaj {soba_id}.")
            continue # Ne šalji na offline uređaje

        response, message, _ = send_esp_command(soba_id, command_params, timeout=TIMEOUT_ESP_DEFAULT)
        if response and response.ok:
            successful_commands.append(soba_id)
        else:
            failed_commands.append(f"Soba {soba_id}: {message}")
            logging.error(f"MANAGER OUTDOOR TOGGLE: Neuspjela komanda za sobu {soba_id}. Greška: {message}")

    if not failed_commands:
        return jsonify({'success': True, 'message': f'Uspješno poslana komanda "{state}" na {len(successful_commands)} uređaja.'})
    elif len(successful_commands) > 0:
        return jsonify({'success': False, 'message': f'Komanda poslana na {len(successful_commands)} uređaja, ali neuspjela na {len(failed_commands)}. Detalji: {"; ".join(failed_commands)}'}), 500
    else:
        return jsonify({'success': False, 'message': f'Komanda "{state}" nije uspjela ni na jednom uređaju. Detalji: {"; ".join(failed_commands)}'}), 500

@app.route('/api/manager/global_mode_status')
def api_manager_global_mode_status():
    """Dohvaća status globalnog moda sa HVAC kontrolera kao referentnog uređaja."""
    if not provjeri_manager_token(request.cookies.get('manager_token')):
        return jsonify({'success': False, 'message': 'Niste prijavljeni'}), 401

    hvac_soba_id = 'hvac'
    params_hvac = {'CMD': 'GET_STATUS'}
    _, _, json_hvac = send_esp_command(hvac_soba_id, params_hvac, timeout=TIMEOUT_ESP_DEFAULT)

    if json_hvac and json_hvac.get('status') == 'success':
        mode = json_hvac.get('data', {}).get('mode_control', {}).get('mode', 'OFF').lower()
        # Vraćamo 'heating' ako je HEATING, inače 'cooling' (za sve ostalo, uključujući OFF)
        return jsonify({'success': True, 'status': 'heating' if mode == 'heating' else 'cooling'})
    
    return jsonify({'success': False, 'message': 'HVAC kontroler nije dostupan.'})

@app.route('/api/manager/toggle_global_mode', methods=['POST'])
def api_manager_toggle_global_mode():
    """Postavlja globalni mod (HEATING/COOLING) na sve uređaje."""
    if not provjeri_manager_token(request.cookies.get('manager_token')):
        return jsonify({'success': False, 'message': 'Niste prijavljeni'}), 401
    
    data = request.json
    mode = data.get('mode') # 'heating' or 'cooling'

    if mode not in ['heating', 'cooling']:
        return jsonify({'success': False, 'message': 'Neispravan mod (očekuje se "heating" ili "cooling")'}), 400

    # Komanda 1: ESP32 lokalni termostat (TH_HEATING / TH_COOLING)
    esp_command = 'TH_HEATING' if mode == 'heating' else 'TH_COOLING'
    esp_command_params = {'CMD': esp_command}

    # Komanda 2: RS485 IC sobni termostat (SET_THST_HEATING / SET_THST_COOLING)
    rs485_command = 'SET_THST_HEATING' if mode == 'heating' else 'SET_THST_COOLING'

    with config_lock:
        soba_ids = list(CONFIG.get('sobe', {}).keys())

    successful_commands = []
    failed_commands = []

    for soba_id in soba_ids:
        with config_lock:
            soba_cfg = CONFIG.get('sobe', {}).get(soba_id, {})
            is_online = soba_cfg.get('cached_ip') is not None
            termostat_id = soba_cfg.get('uredjaji', {}).get('termostat_controller', {}).get('ID')

        if not is_online:
            logging.warning(f"MANAGER GLOBAL MODE: Preskačem offline uređaj {soba_id}.")
            continue

        # Korak 1: Pošalji TH_ komandu ESP32 lokalnom termostatu
        response, message, _ = send_esp_command(soba_id, esp_command_params, timeout=TIMEOUT_ESP_DEFAULT)
        if response and response.ok:
            successful_commands.append(soba_id)
        else:
            failed_commands.append(f"Soba {soba_id} (ESP): {message}")
            logging.error(f"MANAGER GLOBAL MODE: Neuspjela ESP komanda '{esp_command}' za sobu {soba_id}. Greška: {message}")

        # Korak 2: Ako soba ima definisan termostat_controller, pošalji SET_THST_ na RS485 IC kontroler
        if termostat_id:
            rs485_params = {'CMD': rs485_command, 'ID': termostat_id}
            response2, message2, _ = send_esp_command(soba_id, rs485_params, timeout=TIMEOUT_ESP_DEFAULT)
            if response2 and response2.ok:
                logging.info(f"MANAGER GLOBAL MODE: RS485 komanda '{rs485_command}' ID={termostat_id} uspješna za sobu {soba_id}.")
            else:
                failed_commands.append(f"Soba {soba_id} (RS485 ID={termostat_id}): {message2}")
                logging.error(f"MANAGER GLOBAL MODE: Neuspjela RS485 komanda '{rs485_command}' ID={termostat_id} za sobu {soba_id}. Greška: {message2}")

    if not failed_commands:
        return jsonify({'success': True, 'message': f'Uspješno poslana komanda "{esp_command}" + RS485 "{rs485_command}" na {len(successful_commands)} uređaja.'})
    else:
        return jsonify({'success': False, 'message': f'Neke komande nisu uspjele. Detalji: {"; ".join(failed_commands)}'}), 500

@app.route('/manager/heating')
def manager_heating_page():
    if not provjeri_manager_token(request.cookies.get('manager_token')):
        return redirect(url_for('manager_login_page'))
    return render_template('manager_heating.html')

@app.route('/api/manager/heating_status')
def api_manager_heating_status():
    if not provjeri_manager_token(request.cookies.get('manager_token')):
        return jsonify({'success': False, 'message': 'Niste prijavljeni'}), 401

    def _as_bool(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in ('1', 'true', 'on', 'yes', 'run', 'manual')
        return False

    final_status = {
        'currentTemp': None,
        'setpoint': None,
        'isThermostatOn': None,
        'pumpaFancoilOn': False,
        'pumpaPodnoOn': False,
        'pumpaFancoilModeIsManual': False,
        'pumpaFancoilManualIsOn': False,
        'pumpaPodnoModeIsManual': False,
        'pumpaPodnoManualIsOn': False,
        'pumpaFancoilStvarniStatus': False,
        'pumpaPodnoStvarniStatus': False
    }

    with config_lock:
        manager_devices = CONFIG.get('manager_devices', {})
        fitness_thermostat_config = manager_devices.get('fitness_thermostat', {})

    thermostat_soba_id = fitness_thermostat_config.get('mdns_soba_id') or '101'

    # Status termostata (ESP32 lokalni termostat - koristimo samo GET_STATUS)
    thermostat_packet_valid = False
    if thermostat_soba_id:
        # GET_STATUS daje thermostat blok direktno sa ESP32 termostata
        r_status_all, _, json_status_all = send_esp_command(thermostat_soba_id, {'CMD': 'GET_STATUS'}, timeout=TIMEOUT_ESP_DEFAULT)
        if r_status_all and r_status_all.ok and json_status_all:
            thermostat_data = json_status_all.get('data', {}).get('thermostat', {})
            current_temp = thermostat_data.get('temperature')
            setpoint = thermostat_data.get('setpoint')
            mode = (thermostat_data.get('mode') or '').upper()

            if current_temp is not None and setpoint is not None and mode:
                final_status['currentTemp'] = current_temp
                final_status['setpoint'] = setpoint
                final_status['isThermostatOn'] = (mode != 'OFF')
                thermostat_packet_valid = True

    # Autoritativno stanje iz uspješne komande uvijek ima prioritet nad polling statusom
    with manager_fitness_state_lock:
        if manager_fitness_state['isThermostatOn'] is not None:
            final_status['isThermostatOn'] = manager_fitness_state['isThermostatOn']
        if manager_fitness_state['setpoint'] is not None:
            final_status['setpoint'] = manager_fitness_state['setpoint']

    if not thermostat_packet_valid and final_status['isThermostatOn'] is None:
        return jsonify({'success': False, 'message': 'Nevažeći ili nepotpun termostat paket.'}), 503

    # Status pumpi sa HVAC kontrolera (komandno stanje + stvarni RUN/STOP feedback)
    hvac_soba_id = 'hvac'
    _, _, json_hvac = send_esp_command(hvac_soba_id, {'CMD': 'GET_STATUS'}, timeout=TIMEOUT_ESP_DEFAULT)
    if json_hvac and json_hvac.get('status') == 'success':
        data = json_hvac.get('data', {})
        toplik_data = data.get('toplik', {})
        inputs = toplik_data.get('inputs', {})
        outputs = toplik_data.get('outputs', {})

        fancoil_manual_mode = _as_bool(outputs.get('pump_fancoil_mode_auto_manual', False))
        fancoil_manual_on = _as_bool(outputs.get('pump_fancoil_manual_on_off', False))
        podno_manual_mode = _as_bool(outputs.get('pump_podno_mode_auto_manual', False))
        podno_manual_on = _as_bool(outputs.get('pump_podno_manual_on_off', False))
        final_status['pumpaFancoilModeIsManual'] = _as_bool(outputs.get('pump_fancoil_mode_auto_manual'))
        final_status['pumpaFancoilManualIsOn'] = _as_bool(outputs.get('pump_fancoil_manual_on_off'))

        final_status['pumpaFancoilOn'] = fancoil_manual_mode and fancoil_manual_on
        final_status['pumpaPodnoOn'] = podno_manual_mode and podno_manual_on
        final_status['pumpaPodnoModeIsManual'] = _as_bool(outputs.get('pump_podno_mode_auto_manual'))
        final_status['pumpaPodnoManualIsOn'] = _as_bool(outputs.get('pump_podno_manual_on_off'))

        final_status['pumpaFancoilStvarniStatus'] = _as_bool(inputs.get('status_pump_fancoil', False))
        final_status['pumpaPodnoStvarniStatus'] = _as_bool(inputs.get('status_pump_podno', False))
    else:
        logging.warning('MANAGER HEATING STATUS: HVAC GET_STATUS nije dostupan, vraćam podrazumijevani status pumpi.')

    return jsonify({'success': True, 'status': final_status})
    
# ----------------------------------------------------------------------
#  NOVO: API RUTA ZA PROMJENU PINA (ADMIN)
@app.route('/api/admin/change_pin', methods=['POST'])
def api_admin_change_pin():
    """API za promjenu PIN-a pozvan iz Admin Dashboarda."""
    if not provjeri_admin_token(request.cookies.get('admin_token')):
        return jsonify({'success': False, 'message': 'Niste prijavljeni (neispravan token).'}), 401
    
    data = request.json
    room_id = data.get('room_id')
    new_pin = data.get('new_pin')

    if not all([room_id, new_pin]):
        return jsonify({'success': False, 'message': 'Nedostaje ID sobe ili novi PIN.'}), 400

    # Koristimo istu centralnu logiku kao i eksterni API
    logging.info(f"ADMIN PIN CHANGE: Admin mijenja PIN za sobu {room_id} na {new_pin}")
    success, message = sync_pin_on_server_and_device(room_id, new_pin)

    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'success': False, 'message': message}), 500

# ----------------------------------------------------------------------
#  API RUTA ZA PROMJENU SYSTEM ID (Radi sa oba kontrolera)
@app.route('/api/admin/change_system_id', methods=['POST'])
def api_admin_change_system_id():
    """API za promjenu System ID-a na PIN kontroleru(ima) - radi sa primarnim i sekundarnim."""
    if not provjeri_admin_token(request.cookies.get('admin_token')):
        return jsonify({'success': False, 'message': 'Niste prijavljeni (neispravan token).'}), 401
    
    data = request.json
    room_id = data.get('room_id')
    new_system_id = data.get('system_id')

    if not all([room_id, new_system_id]):
        return jsonify({'success': False, 'message': 'Nedostaje ID sobe ili System ID.'}), 400

    try:
        # Validate system_id is numeric
        system_id_value = int(new_system_id)
        
        # Get room config
        with config_lock:
            room_config = CONFIG.get('sobe', {}).get(room_id)
        
        if not room_config:
            return jsonify({'success': False, 'message': 'Soba ne postoji'}), 404
        
        if not room_config.get('cached_ip'):
            return jsonify({'success': False, 'message': f'Soba {room_id} je offline'}), 503
        
        pin_controller_id = room_config['uredjaji']['pin_controller']['ID']
        secondary_pin_controller_id = room_config['uredjaji'].get('secondary_pin_controller', {}).get('ID')
        
        logging.info(f"ADMIN SYSTEM_ID CHANGE: Admin mijenja System ID za sobu {room_id} na {system_id_value}")
        
        # Koristi dual controller funkciju
        success, msg, primary_json, secondary_json = send_command_to_both_controllers(
            room_id,
            {
                'CMD': 'SET_SYSID',
                'VALUE': str(system_id_value)
            },
            pin_controller_id,
            secondary_pin_controller_id,
            timeout=TIMEOUT_ESP_LONG
        )
        
        if success:
            return jsonify({'success': True, 'message': f'System ID postavljen na oba kontrolera: {system_id_value}'})
        else:
            return jsonify({'success': False, 'message': msg}), 500
            
    except ValueError:
        return jsonify({'success': False, 'message': 'System ID mora biti broj'}), 400
    except Exception as e:
        logging.error(f"Greška u change_system_id: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ----------------------------------------------------------------------
#  API ENDPOINT ZA PROMJENU SYSTEM ID (Windows APP)
@app.route('/api/rooms/<room_number>/set_system_id', methods=['POST'])
@require_api_key
def api_windows_set_system_id(room_number):
    """Postavlja System ID na PIN kontroleru(ima) sobe - radi sa primarnim i sekundarnim."""
    try:
        data = request.json
        system_id = data.get('system_id')
        
        if not system_id:
            return jsonify({'status': 'error', 'message': 'System ID nedostaje'}), 400
        
        try:
            system_id_value = int(system_id)
        except ValueError:
            return jsonify({'status': 'error', 'message': 'System ID mora biti broj'}), 400
        
        # Get room config
        with config_lock:
            room_config = CONFIG.get('sobe', {}).get(room_number)
        
        if not room_config:
            return jsonify({'status': 'error', 'message': 'Soba ne postoji'}), 404
        
        if not room_config.get('cached_ip'):
            return jsonify({'status': 'error', 'message': f'Soba {room_number} je offline'}), 503
        
        pin_controller_id = room_config['uredjaji']['pin_controller']['ID']
        secondary_pin_controller_id = room_config['uredjaji'].get('secondary_pin_controller', {}).get('ID')
        
        logging.info(f"🔧 [{room_number}] SET_SYSTEM_ID započet: {system_id_value}")
        
        # Koristi dual controller funkciju
        success, msg, primary_json, secondary_json = send_command_to_both_controllers(
            room_number,
            {
                'CMD': 'SET_SYSID',
                'VALUE': str(system_id_value)
            },
            pin_controller_id,
            secondary_pin_controller_id,
            timeout=TIMEOUT_ESP_LONG
        )
        
        if not success:
            logging.error(f"❌ [{room_number}] SET_SYSTEM_ID NEUSPJEŠAN: {msg}")
            return jsonify({
                'status': 'error',
                'message': 'System ID nije postavljen',
                'details': msg
            }), 500
        
        logging.info(f"✅ [{room_number}] SET_SYSTEM_ID USPJEŠAN na svim kontrolerima: {system_id_value}")
        
        return jsonify({
            'status': 'success',
            'message': 'System ID postavljen na oba kontrolera',
            'data': {
                'room_number': room_number,
                'system_id': system_id_value,
                'controllers_updated': 2 if secondary_pin_controller_id else 1
            }
        }), 200
        
    except Exception as e:
        logging.error(f"❌ [{room_number}] Greška u set_system_id: {e}")
        return jsonify({'status': 'error', 'message': f'Greška: {str(e)}'}), 500
        
# ----------------------------------------------------------------------
#  POZADINSKI PROCES ZA AŽURIRANJE IP ADRESA
# ----------------------------------------------------------------------
def background_resolver_task():
    logging.info("Pokrenut pozadinski IP resolver.")
    while True:
        try:
            time.sleep(RESOLVER_INTERVAL_SECONDS)
            logging.info("PROAKTIVNI RESOLVER: Pokrećem provjeru IP adresa...")
            with config_lock:
                soba_ids = list(CONFIG.get('sobe', {}).keys())
            if not soba_ids:
                logging.info("PROAKTIVNI RESOLVER: Nema soba u config.json.")
                continue
            for soba_id in soba_ids:
                ip_address = resolve_and_cache_ip(soba_id)
                
                # Proaktivni status check (Okida SOS notifikaciju nezavisno od klijenata)
                if ip_address:
                    try:
                        resp, msg, json_status = send_esp_command(soba_id, {'CMD': 'GET_STATUS'}, timeout=TIMEOUT_ESP_LONG)
                        if resp and resp.ok:
                            parse_get_status_from_json(json_status, room_id=soba_id)
                    except Exception as e:
                        logging.warning(f"PROAKTIVNI STATUS: Greška za {soba_id}: {e}")
                        
                time.sleep(RESOLVER_ROOM_DELAY_SECONDS)
            logging.info("PROAKTIVNI RESOLVER: Provjera IP adresa završena.")
        except Exception as e:
            logging.error(f"Greška u pozadinskom resolveru: {e}")
            time.sleep(RESOLVER_INTERVAL_SECONDS)

# ----------------------------------------------------------------------
#  WINDOWS APP API ENDPOINTS
# ----------------------------------------------------------------------

@app.route('/api/rooms', methods=['GET'])
@require_api_key
def api_windows_get_rooms():
    """Vraća listu svih soba sa statusom za Windows aplikaciju.
    
    KRITIČNO: PIN se čita DIREKTNO iz UL EEPROM-a (GET_PASSWORD), 
    NE iz config.json! EEPROM je jedini izvor istine.
    """
    rooms_data = []
    
    with config_lock:
        rooms_config = list(CONFIG.get('sobe', {}).items())
    
    for soba_id, soba_config in rooms_config:
        # Preskoči uređaje koji nisu prave sobe (prazni uredjaji = HVAC, fitnes, itd.)
        if not soba_config.get('uredjaji'):
            continue
        
        room_info = {
            "room_number": soba_id,
            "name": soba_config.get('ime', f"Soba {soba_id}"),
            "online": bool(soba_config.get('cached_ip')),
            "current_temp": None,
            "setpoint_temp": None,
            "card_inserted": False,
            "active_pin": "",  # Biće popunjeno iz EEPROM-a
            "guest_pin": "",  # Biće popunjeno iz EEPROM-a
            "guest_in_temp": None,  # Biće popunjeno sa GET_GUEST_IN_TEMP
            "guest_out_temp": None,  # Biće popunjeno sa GET_GUEST_OUT_TEMP
            "thermostat_mode": "OFF",
            "thermostat_on": False,
            "target_temp": None,
            "occupied": False,
            "sos_active": False,  # SOS alarm status
            "sos_timestamp": None  # SOS alarm timestamp
        }
        
        # Ako je soba online, čitaj PRAVI status iz kontrolera
        if soba_config.get('cached_ip'):
            try:
                # GET_PASSWORD - čitaj PIN iz EEPROM-a (SINGLE SOURCE OF TRUTH)
                pin_controller_id = soba_config['uredjaji']['pin_controller']['ID']
                scene_controller_id = soba_config['uredjaji'].get('scene_controller', {}).get('ID', pin_controller_id)
                _, _, json_pin = send_esp_command(soba_id, {
                    'CMD': 'GET_PASSWORD',
                    'ID': pin_controller_id,
                    'TYPE': 'GUEST',
                    'GUEST_ID': '1'
                }, timeout=TIMEOUT_ESP_SHORT)
                
                if json_pin and json_pin.get('status') == 'success':
                    eeprom_pin = str(json_pin.get('data', {}).get('password', ''))
                    # PIN postoji ako nije prazan, "0000", ili "00000000"
                    if eeprom_pin and eeprom_pin not in ['0', '0000', '00000000', '']:
                        room_info['active_pin'] = eeprom_pin
                        room_info['guest_pin'] = eeprom_pin
                
                # GET_ROOM_TEMP - trenutna i zadana temperatura sa TH uređaja
                thermostat_id = soba_config['uredjaji']['termostat_set']['ID']
                _, _, json_temp = send_esp_command(soba_id, {
                    'CMD': 'GET_ROOM_TEMP',
                    'ID': thermostat_id
                }, timeout=TIMEOUT_ESP_SHORT)
                
                if json_temp and json_temp.get('status') == 'success':
                    temp_data = json_temp.get('data', {})
                    room_temp = temp_data.get('room_temperature')
                    setpoint_temp = temp_data.get('setpoint_temperature')
                    # Prikaži bez decimala ako je cijeli broj (21 umjesto 21.0)
                    room_info['current_temp'] = int(room_temp) if room_temp and room_temp == int(room_temp) else room_temp
                    room_info['setpoint_temp'] = int(setpoint_temp) if setpoint_temp and setpoint_temp == int(setpoint_temp) else setpoint_temp
                    room_info['target_temp'] = room_info['setpoint_temp']
                
                # GET_ROOM_STATUS - card stacker (SC uređaj)
                _, _, json_room = send_esp_command(soba_id, {
                    'CMD': 'GET_ROOM_STATUS',
                    'ID': scene_controller_id
                }, timeout=TIMEOUT_ESP_SHORT)
                
                if json_room and json_room.get('status') == 'success':
                    card_data = json_room.get('data', {})
                    room_info['card_inserted'] = card_data.get('card_inserted', False)
                    room_info['occupied'] = card_data.get('card_inserted', False)
                
                # GET_GUEST_IN_TEMP - temperatura kada gost uđe (SC uređaj)
                _, _, json_guest_in = send_esp_command(soba_id, {
                    'CMD': 'GET_GUEST_IN_TEMP',
                    'ID': scene_controller_id
                }, timeout=TIMEOUT_ESP_SHORT)
                
                if json_guest_in and json_guest_in.get('status') == 'success':
                    guest_in_data = json_guest_in.get('data', {})
                    room_info['guest_in_temp'] = guest_in_data.get('guest_in_temperature')
                
                # GET_GUEST_OUT_TEMP - temperatura kada gost izađe (SC uređaj)
                _, _, json_guest_out = send_esp_command(soba_id, {
                    'CMD': 'GET_GUEST_OUT_TEMP',
                    'ID': scene_controller_id
                }, timeout=TIMEOUT_ESP_SHORT)
                
                if json_guest_out and json_guest_out.get('status') == 'success':
                    guest_out_data = json_guest_out.get('data', {})
                    room_info['guest_out_temp'] = guest_out_data.get('guest_out_temperature')
                
                # GET_STATUS - SOS alarm status
                _, _, json_status = send_esp_command(soba_id, {
                    'CMD': 'GET_STATUS'
                }, timeout=TIMEOUT_ESP_SHORT)
                
                if json_status and json_status.get('status') == 'success':
                    status_data = json_status.get('data', {})
                    sos_data = status_data.get('sos', {})
                    room_info['sos_active'] = sos_data.get('active', False)
                    room_info['sos_timestamp'] = sos_data.get('timestamp')
                    
            except Exception as e:
                logging.error(f"Greška pri čitanju statusa sobe {soba_id}: {e}")
        
        rooms_data.append(room_info)
    
    # Sortiraj po broju sobe
    rooms_data.sort(key=lambda x: x['room_number'])
    
    return jsonify({"status": "success", "data": {"rooms": rooms_data}})


@app.route('/api/rooms/<room_number>/set_pin', methods=['POST'])
@require_api_key
def api_windows_set_pin(room_number):
    """
    Postavlja PIN za sobu - Check-in.
    KRITIČNI FLOW:
    0. Provjera kolizije PINa u config.json (prije svega!)
    1. Prima PIN + expiry od APP
    2. Šalje SET_PASSWORD na UL kontroler
    3. AKO UL vrati success -> UPDATE config.json guest_pin
    4. Tek nakon update-a config.json -> vrati success APP-u
    5. Postavlja guest temperature i jezik
    """
    try:
        data = request.json
        pin = data.get('pin')
        expiry_date = data.get('expiry_date')  # Format: DD.MM.YYYY
        expiry_time = data.get('expiry_time')  # Format: HH:MM
        language = data.get('language', 'srb')
        day_temp = data.get('day_temp', 22)
        night_temp = data.get('night_temp', 18)
        
        # Validacija
        if not pin or len(pin) != 4 or not pin.isdigit():
            pin_len = len(pin) if pin else 0
            logging.warning(f"GUEST PIN: Neispravna duzina PIN-a (len={pin_len}, ocekivano=4)")
            return jsonify({'status': 'error', 'message': 'PIN mora biti 4 cifre'}), 400
        
        if not expiry_date or not expiry_time:
            return jsonify({'status': 'error', 'message': 'Nedostaju expiry_date ili expiry_time'}), 400
        
        # ============================================================
        # KORAK 0: PROVJERA KOLIZIJE - PRIJE BILO KOJE UL OPERACIJE!
        # ============================================================
        logging.info(f"🔍 [{room_number}] Provjeravam koliziju PINa {pin} u config.json")
        with config_lock:
            for room_id, room_data in CONFIG.get('sobe', {}).items():
                # Provjeri sve sobe osim trenutne
                if room_id != room_number:
                    existing_pin = room_data.get('guest_pin', '')
                    if existing_pin == pin:
                        logging.warning(f"❌ [{room_number}] PIN {pin} već postoji u sobi {room_id}!")
                        return jsonify({
                            'status': 'error',
                            'message': f'PIN {pin} je već zauzet u sobi {room_id}',
                            'error_type': 'pin_collision'
                        }), 409  # 409 Conflict
        
        logging.info(f"✅ [{room_number}] PIN {pin} slobodan, nema kolizije")
        
        # Construct EXPIRY parameter: HHMMDDMMYY
        expiry_parts_date = expiry_date.split('.')
        expiry_parts_time = expiry_time.split(':')
        hh = expiry_parts_time[0]
        mm = expiry_parts_time[1]
        dd = expiry_parts_date[0]
        MM = expiry_parts_date[1]
        yy = expiry_parts_date[2][-2:]
        expiry_param = f"{hh}{mm}{dd}{MM}{yy}"
        
        logging.info(f"🔑 [{room_number}] CHECK-IN ZAPOČET: PIN={pin}, Expiry={expiry_date} {expiry_time}")
        
        # Get room config
        with config_lock:
            room_config = CONFIG.get('sobe', {}).get(room_number)
        
        if not room_config:
            return jsonify({'status': 'error', 'message': 'Soba ne postoji'}), 404
        
        # Check online
        if not room_config.get('cached_ip'):
            return jsonify({'status': 'error', 'message': f'Soba {room_number} je offline'}), 503
        
        # Get controller IDs
        pin_controller_id = room_config['uredjaji']['pin_controller']['ID']
        secondary_pin_controller_id = room_config['uredjaji'].get('secondary_pin_controller', {}).get('ID')
        scene_controller_id = room_config['uredjaji'].get('scene_controller', {}).get('ID', pin_controller_id)
        
        # ============================================================
        # KORAK 1: SET_PASSWORD na UL kontroler(e) - NAJVAŽNIJI KORAK!
        # ============================================================
        logging.info(f"🔥 [{room_number}] Šaljem SET_PASSWORD na kontroler(e)")
        
        # Koristi dual controller funkciju
        success, msg, primary_json, secondary_json = send_command_to_both_controllers(
            room_number,
            {
                'CMD': 'SET_PASSWORD',
                'TYPE': 'GUEST',
                'GUEST_ID': '1',
                'PASSWORD': pin,
                'EXPIRY': expiry_param
            },
            pin_controller_id,
            secondary_pin_controller_id,
            timeout=TIMEOUT_ESP_LONG
        )
        
        if not success:
            logging.error(f"❌ [{room_number}] SET_PASSWORD NEUSPJEŠAN: {msg}")
            return jsonify({
                'status': 'error', 
                'message': 'Kontroler(i) nisu prihvatili PIN', 
                'details': msg
            }), 500
        
        logging.info(f"✅ [{room_number}] Svi kontroleri prihvatili PIN={pin}")
        
        # ============================================================
        # KORAK 2: UPDATE config.json - MORA SE DESITI!
        # ============================================================
        with config_lock:
            CONFIG['sobe'][room_number]['guest_pin'] = pin
            CONFIG['sobe'][room_number]['pin_expiry'] = f"{expiry_date} {expiry_time}"
            CONFIG['sobe'][room_number]['language'] = language
        save_config()
        logging.info(f"💾 [{room_number}] config.json ažuriran sa PIN={pin}")
        
        # ============================================================
        # KORAK 3: Verifikacija - čita PIN nazad (opcionalno ali preporučeno)
        # ============================================================
        time.sleep(0.3)
        
        # Verifikuj glavni kontroler
        _, msg_get, json_get = send_esp_command(room_number, {
            'CMD': 'GET_PASSWORD',
            'ID': pin_controller_id,
            'TYPE': 'GUEST',
            'GUEST_ID': '1'
        }, timeout=TIMEOUT_ESP_LONG)
        
        verified_primary = False
        if json_get and json_get.get('status') == 'success':
            returned_pin = str(json_get.get('data', {}).get('password', ''))
            verified_primary = (returned_pin == pin)
            if verified_primary:
                logging.info(f"✅ [{room_number}] PIN verifikovan na GLAVNOM kontroleru: {pin}")
            else:
                logging.warning(f"⚠️ [{room_number}] PIN verifikacija GLAVNOG nepodudaranje: očekivano={pin}, dobijeno={returned_pin}")
        
        # Verifikuj sekundarni kontroler ako postoji
        verified_secondary = True  # Default True ako nema sekundarnog
        if secondary_pin_controller_id:
            _, msg_get_sec, json_get_sec = send_esp_command(room_number, {
                'CMD': 'GET_PASSWORD',
                'ID': secondary_pin_controller_id,
                'TYPE': 'GUEST',
                'GUEST_ID': '1'
            }, timeout=TIMEOUT_ESP_LONG)
            
            if json_get_sec and json_get_sec.get('status') == 'success':
                returned_pin_sec = str(json_get_sec.get('data', {}).get('password', ''))
                verified_secondary = (returned_pin_sec == pin)
                if verified_secondary:
                    logging.info(f"✅ [{room_number}] PIN verifikovan na SEKUNDARNOM kontroleru: {pin}")
                else:
                    logging.warning(f"⚠️ [{room_number}] PIN verifikacija SEKUNDARNOG nepodudaranje: očekivano={pin}, dobijeno={returned_pin_sec}")
        
        verified = verified_primary and verified_secondary
        
        # ============================================================
        # KORAK 4: SET_GUEST_IN_TEMP (Guest prisutan)
        # ============================================================
        logging.info(f"🌡️ [{room_number}] Šaljem SET_GUEST_IN_TEMP={day_temp} na SCENE ID={scene_controller_id}")
        _, msg_temp_in, json_temp_in = send_esp_command(room_number, {
            'CMD': 'SET_GUEST_IN_TEMP',
            'ID': scene_controller_id,
            'VALUE': str(int(day_temp))
        }, timeout=TIMEOUT_ESP_DEFAULT)
        
        if json_temp_in and json_temp_in.get('status') == 'success':
            logging.info(f"✅ [{room_number}] Guest IN temp postavljen: {day_temp}°C")
        else:
            logging.warning(f"⚠️ [{room_number}] Guest IN temp NIJE postavljen: {msg_temp_in}")
        
        # ============================================================
        # KORAK 5: SET_GUEST_OUT_TEMP (Guest odsutan)
        # ============================================================
        logging.info(f"🌡️ [{room_number}] Šaljem SET_GUEST_OUT_TEMP={night_temp} na SCENE ID={scene_controller_id}")
        _, msg_temp_out, json_temp_out = send_esp_command(room_number, {
            'CMD': 'SET_GUEST_OUT_TEMP',
            'ID': scene_controller_id,
            'VALUE': str(int(night_temp))
        }, timeout=TIMEOUT_ESP_DEFAULT)
        
        if json_temp_out and json_temp_out.get('status') == 'success':
            logging.info(f"✅ [{room_number}] Guest OUT temp postavljen: {night_temp}°C")
        else:
            logging.warning(f"⚠️ [{room_number}] Guest OUT temp NIJE postavljen: {msg_temp_out}")
        
        # ============================================================
        # KORAK 6: SET_LANG (Jezik displeja) - SCENE kontroler!
        # ============================================================
        language_map = {'srb': 0, 'eng': 1, 'ger': 2}
        lang_value = language_map.get(language, 0)
        
        logging.info(f"🌍 [{room_number}] Šaljem SET_LANG={lang_value} na SCENE ID={scene_controller_id}")
        _, msg_lang, json_lang = send_esp_command(room_number, {
            'CMD': 'SET_LANG',
            'ID': scene_controller_id,
            'VALUE': str(lang_value)
        }, timeout=TIMEOUT_ESP_DEFAULT)
        
        if json_lang and json_lang.get('status') == 'success':
            logging.info(f"✅ [{room_number}] Jezik displeja postavljen: {language}")
        else:
            logging.warning(f"⚠️ [{room_number}] Jezik displeja NIJE postavljen: {msg_lang}")
        
        # ============================================================
        # KORAK 7: Vraćamo SUCCESS odgovor APP-u
        # ============================================================
        logging.info(f"🎉 [{room_number}] CHECK-IN USPJEŠAN! PIN={pin}")
        return jsonify({
            'status': 'success',
            'message': 'Check-in uspješan',
            'data': {
                'room_number': room_number,
                'pin_set': True,
                'pin_verified': verified,
                'expiry': f"{expiry_date} {expiry_time}",
                'guest_in_temp': day_temp,
                'guest_out_temp': night_temp,
                'language': language
            }
        }), 200
        
    except Exception as e:
        logging.error(f"❌ [{room_number}] Kritična greška u set_pin: {e}")
        return jsonify({'status': 'error', 'message': f'Greška: {str(e)}'}), 500


@app.route('/api/rooms/<room_number>/delete_pin', methods=['POST'])
@require_api_key
def api_windows_delete_pin(room_number):
    """
    Briše PIN za sobu - Check-out.
    KRITIČNI FLOW:
    1. Šalje DELETE_GUEST na UL kontroler
    2. AKO UL vrati success -> UPDATE config.json (guest_pin = None)
    3. Tek nakon update-a config.json -> vrati success APP-u
    """
    try:
        logging.info(f"🚪 [{room_number}] CHECK-OUT ZAPOČET")
        
        # Get room config
        with config_lock:
            room_config = CONFIG.get('sobe', {}).get(room_number)
        
        if not room_config:
            return jsonify({'status': 'error', 'message': 'Soba ne postoji'}), 404
        
        # Check online
        if not room_config.get('cached_ip'):
            return jsonify({'status': 'error', 'message': f'Soba {room_number} je offline'}), 503
        
        # Get PIN controller IDs
        pin_controller_id = room_config['uredjaji']['pin_controller']['ID']
        secondary_pin_controller_id = room_config['uredjaji'].get('secondary_pin_controller', {}).get('ID')
        old_pin = room_config.get('guest_pin')
        
        # ============================================================
        # KORAK 1: DELETE_GUEST na UL kontroler(e) - KRITIČNO!
        # ============================================================
        logging.info(f"🔥 [{room_number}] Šaljem DELETE_GUEST na kontroler(e)")
        
        # Koristi dual controller funkciju
        success, msg, primary_json, secondary_json = send_command_to_both_controllers(
            room_number,
            {
                'CMD': 'SET_PASSWORD',
                'TYPE': 'DELETE_GUEST',
                'GUEST_ID': '1',
                'PASSWORD': '0000'
            },
            pin_controller_id,
            secondary_pin_controller_id,
            timeout=TIMEOUT_ESP_LONG
        )
        
        if not success:
            logging.error(f"❌ [{room_number}] DELETE_GUEST NEUSPJEŠAN: {msg}")
            return jsonify({
                'status': 'error', 
                'message': 'Kontroler(i) nisu obrisali PIN', 
                'details': msg
            }), 500
        
        logging.info(f"✅ [{room_number}] Svi kontroleri obrisali PIN (bio: {old_pin})")
        
        # ============================================================
        # KORAK 2: UPDATE config.json - MORA SE DESITI!
        # ============================================================
        with config_lock:
            CONFIG['sobe'][room_number]['guest_pin'] = None
            CONFIG['sobe'][room_number]['pin_expiry'] = None
        save_config()
        logging.info(f"💾 [{room_number}] config.json ažuriran - PIN obrisan")
        
        # ============================================================
        # KORAK 3: Vraćamo SUCCESS odgovor APP-u
        # ============================================================
        logging.info(f"🎉 [{room_number}] CHECK-OUT USPJEŠAN!")
        return jsonify({
            'status': 'success',
            'message': 'Check-out uspješan',
            'data': {
                'room_number': room_number,
                'pin_deleted': True
            }
        }), 200
        
    except Exception as e:
        logging.error(f"❌ [{room_number}] Kritična greška u delete_pin: {e}")
        return jsonify({'status': 'error', 'message': f'Greška: {str(e)}'}), 500


@app.route('/api/rooms/<room_number>/set_temperature', methods=['POST'])
@require_api_key
def api_windows_set_temperature(room_number):
    """Postavlja trenutni setpoint temperature."""
    try:
        data = request.json
        setpoint = data.get('setpoint')
        
        if setpoint is None:
            return jsonify({'status': 'error', 'message': 'Nedostaje setpoint parametar'}), 400
        
        # Get room config
        with config_lock:
            room_config = CONFIG.get('sobe', {}).get(room_number)
        
        if not room_config:
            return jsonify({'status': 'error', 'message': 'Soba ne postoji'}), 404
        
        # Check online
        if not room_config.get('cached_ip'):
            return jsonify({'status': 'error', 'message': f'Soba {room_number} je offline'}), 503
        
        # Get thermostat device ID
        thermostat_id = room_config['uredjaji']['termostat_set']['ID']
        
        # Send SET_ROOM_TEMP command with detailed logging
        logging.info(f"[{room_number}] Šaljem SET_ROOM_TEMP={setpoint} na ID={thermostat_id}")
        _, msg, json_resp = send_esp_command(room_number, {
            'CMD': 'SET_ROOM_TEMP',
            'ID': thermostat_id,
            'VALUE': str(int(setpoint))
        }, timeout=TIMEOUT_ESP_LONG)
        
        if json_resp is None or json_resp.get('status') != 'success':
            logging.error(f"[{room_number}] SET_ROOM_TEMP NEUSPJEŠAN: {msg}")
            return jsonify({'status': 'error', 'message': f'Postavljanje temperature neuspješno: {msg}'}), 500
        
        logging.info(f"[{room_number}] SET_ROOM_TEMP USPJEŠAN: Setpoint={setpoint}")
        return jsonify({
            'status': 'success',
            'message': 'Temperatura uspješno postavljena',
            'data': {'room_number': room_number, 'setpoint': setpoint}
        }), 200
        
    except Exception as e:
        logging.error(f"Greška u set_temperature: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/rooms/<room_number>/sos_reset', methods=['POST'])
@require_api_key
def api_windows_sos_reset(room_number):
    """Resetuje SOS alarm za sobu."""
    try:
        logging.info(f"🆘 [{room_number}] SOS RESET zahtjev primljen")
        
        # Get room config
        with config_lock:
            room_config = CONFIG.get('sobe', {}).get(room_number)
        
        if not room_config:
            return jsonify({'status': 'error', 'message': 'Soba ne postoji'}), 404
        
        # Check online
        if not room_config.get('cached_ip'):
            return jsonify({'status': 'error', 'message': f'Soba {room_number} je offline'}), 503
        
        # Send SOS_RESET command to ESP32
        logging.info(f"🆘 [{room_number}] Šaljem SOS_RESET komandu na ESP32")
        _, msg, json_resp = send_esp_command(room_number, {
            'CMD': 'SOS_RESET'
        }, timeout=TIMEOUT_ESP_LONG)
        
        if json_resp is None or json_resp.get('status') != 'success':
            logging.error(f"❌ [{room_number}] SOS_RESET NEUSPJEŠAN: {msg}")
            return jsonify({
                'status': 'error',
                'message': f'SOS reset neuspješan: {msg}'
            }), 500
        
        # Clear notification state on server
        global sos_notification_state
        if room_number in sos_notification_state:
            logging.info(f"🆘 [{room_number}] Čistim server-side SOS notification state")
            del sos_notification_state[room_number]
        
        logging.info(f"✅ [{room_number}] SOS ALARM RESETOVAN")
        return jsonify({
            'status': 'success',
            'message': f'SOS alarm za sobu {room_number} uspješno resetovan',
            'data': {'room_number': room_number}
        }), 200
        
    except Exception as e:
        logging.error(f"❌ Greška u sos_reset: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/rooms/<room_number>/set_guest_temps', methods=['POST'])
@require_api_key
def api_windows_set_guest_temps(room_number):
    """Postavlja GUEST_IN i GUEST_OUT temperature."""
    try:
        data = request.json
        guest_in_temp = data.get('guest_in_temp')
        guest_out_temp = data.get('guest_out_temp')
        
        # Get room config
        with config_lock:
            room_config = CONFIG.get('sobe', {}).get(room_number)
        
        if not room_config:
            return jsonify({'status': 'error', 'message': 'Soba ne postoji'}), 404
        
        # Check online
        if not room_config.get('cached_ip'):
            return jsonify({'status': 'error', 'message': f'Soba {room_number} je offline'}), 503
        
        # Get Scene controller ID (manages guest temps)
        pin_controller_id = room_config['uredjaji']['pin_controller']['ID']
        scene_controller_id = room_config['uredjaji'].get('scene_controller', {}).get('ID', pin_controller_id)
        
        # ✅ KRITIČNA PROVJERA: Provjeri rezultat SVAKE komande
        failed_commands = []
        
        # Send commands with result validation
        if guest_in_temp is not None:
            params = {
                'CMD': 'SET_GUEST_IN_TEMP',
                'ID': scene_controller_id,
                'VALUE': str(int(guest_in_temp))
            }
            logging.info(f"[{room_number}] 🔥 Šaljem SET_GUEST_IN_TEMP={guest_in_temp} na SCENE_RS485_ID={scene_controller_id}")
            logging.info(f"[{room_number}] 🔥 Parametri: {params}")
            
            _, msg, json_resp = send_esp_command(room_number, params, timeout=TIMEOUT_ESP_LONG)
            
            logging.info(f"[{room_number}] 🔥 Odgovor JSON: {json_resp}")
            logging.info(f"[{room_number}] 🔥 Odgovor MSG: {msg}")
            
            if json_resp is None or json_resp.get('status') != 'success':
                error_msg = f"SET_GUEST_IN_TEMP NEUSPJEŠAN: {msg}"
                logging.error(f"[{room_number}] ❌ {error_msg}")
                if json_resp:
                    logging.error(f"[{room_number}] ❌ Full JSON: {json_resp}")
                failed_commands.append(f"Guest In Temp: {msg}")
        
        if guest_out_temp is not None:
            params = {
                'CMD': 'SET_GUEST_OUT_TEMP',
                'ID': scene_controller_id,
                'VALUE': str(int(guest_out_temp))
            }
            logging.info(f"[{room_number}] 🔥 Šaljem SET_GUEST_OUT_TEMP={guest_out_temp} na SCENE_RS485_ID={scene_controller_id}")
            logging.info(f"[{room_number}] 🔥 Parametri: {params}")
            
            _, msg, json_resp = send_esp_command(room_number, params, timeout=TIMEOUT_ESP_LONG)
            
            logging.info(f"[{room_number}] 🔥 Odgovor JSON: {json_resp}")
            logging.info(f"[{room_number}] 🔥 Odgovor MSG: {msg}")
            
            if json_resp is None or json_resp.get('status') != 'success':
                error_msg = f"SET_GUEST_OUT_TEMP NEUSPJEŠAN: {msg}"
                logging.error(f"[{room_number}] ❌ {error_msg}")
                if json_resp:
                    logging.error(f"[{room_number}] ❌ Full JSON: {json_resp}")
                failed_commands.append(f"Guest Out Temp: {msg}")
        
        # ✅ Vrati grešku ako BILO KOJA komanda nije uspjela
        if failed_commands:
            return jsonify({
                'status': 'error',
                'message': 'Neke komande nisu uspjele',
                'failed': failed_commands
            }), 500
        
        logging.info(f"[{room_number}] Guest temperature USPJEŠNO postavljene: IN={guest_in_temp}, OUT={guest_out_temp}")
        return jsonify({
            'status': 'success',
            'message': 'Guest temperature uspješno postavljene',
            'data': {
                'room_number': room_number,
                'guest_in_temp': guest_in_temp,
                'guest_out_temp': guest_out_temp
            }
        }), 200
        
    except Exception as e:
        logging.error(f"Greška u set_guest_temps: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/rooms/<room_number>/thermostat', methods=['POST'])
@require_api_key
def api_windows_control_thermostat(room_number):
    """Kontroliše termostat (on/off/heating/cooling)."""
    try:
        data = request.json
        action = data.get('action')
        
        action_map = {
            'on': 'SET_THST_ON',
            'off': 'SET_THST_OFF',
            'heating': 'SET_THST_HEATING',
            'cooling': 'SET_THST_COOLING'
        }
        
        if action not in action_map:
            return jsonify({'status': 'error', 'message': 'Nepoznata akcija'}), 400
        
        # Get room config
        with config_lock:
            room_config = CONFIG.get('sobe', {}).get(room_number)
        
        if not room_config:
            return jsonify({'status': 'error', 'message': 'Soba ne postoji'}), 404
        
        # Check online
        if not room_config.get('cached_ip'):
            return jsonify({'status': 'error', 'message': f'Soba {room_number} je offline'}), 503
        
        # Get thermostat device ID
        thermostat_id = room_config['uredjaji']['termostat_set']['ID']
        
        # Send command with detailed logging
        cmd = action_map[action]
        logging.info(f"[{room_number}] Šaljem {cmd} na ID={thermostat_id}")
        _, msg, json_resp = send_esp_command(room_number, {
            'CMD': cmd,
            'ID': thermostat_id
        }, timeout=TIMEOUT_ESP_LONG)
        
        if json_resp is None or json_resp.get('status') != 'success':
            logging.error(f"[{room_number}] {cmd} NEUSPJEŠAN: {msg}")
            return jsonify({'status': 'error', 'message': f'Termostat kontrola neuspješna: {msg}'}), 500
        
        logging.info(f"[{room_number}] {cmd} USPJEŠAN")
        return jsonify({
            'status': 'success',
            'message': f'Termostat postavljen na {action.upper()}',
            'data': {'room_number': room_number, 'action': action}
        }), 200
        
    except Exception as e:
        logging.error(f"Greška u control_thermostat: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/rooms/<room_number>/set_language', methods=['POST'])
@require_api_key
def api_windows_set_language(room_number):
    """Postavlja jezik displeja u sobi (0=SRB, 1=ENG, 2=GER)."""
    try:
        data = request.json
        language = data.get('language')
        
        if language is None:
            return jsonify({'status': 'error', 'message': 'Nedostaje language parametar'}), 400
        
        # Convert string language codes to numeric values
        lang_map = {
            'srb': '0', '0': '0',
            'eng': '1', '1': '1',
            'ger': '2', '2': '2'
        }
        
        language_value = lang_map.get(language.lower())
        if language_value is None:
            return jsonify({'status': 'error', 'message': 'Nepravilan language parametar (srb/eng/ger ili 0/1/2)'}), 400
        
        # Get room config
        with config_lock:
            room_config = CONFIG.get('sobe', {}).get(room_number)
        
        if not room_config:
            return jsonify({'status': 'error', 'message': 'Soba ne postoji'}), 404
        
        # Check online
        if not room_config.get('cached_ip'):
            return jsonify({'status': 'error', 'message': f'Soba {room_number} je offline'}), 503
        
        # Get Scene controller device ID (for language setting)
        pin_controller_id = room_config['uredjaji']['pin_controller']['ID']
        # Koristi termostat za SET_LANG, a ne scene controller
        thermostat_id = room_config['uredjaji'].get('termostat_set', {}).get('ID', pin_controller_id)
        
        # Send SET_LANG command with detailed logging
        lang_names = {'0': 'Srpski', '1': 'English', '2': 'Deutsch'}
        logging.info(f"[{room_number}] Šaljem SET_LANG={language_value} ({lang_names.get(language_value)}) na TERMOSTAT_ID={thermostat_id}")
        _, msg, json_resp = send_esp_command(room_number, {
            'CMD': 'SET_LANG',
            'ID': thermostat_id,
            'VALUE': language_value
        }, timeout=TIMEOUT_ESP_LONG)
        
        if json_resp is None or json_resp.get('status') != 'success':
            logging.error(f"[{room_number}] SET_LANG NEUSPJEŠAN: {msg}")
            return jsonify({'status': 'error', 'message': f'Postavljanje jezika neuspješno: {msg}'}), 500
        
        logging.info(f"[{room_number}] SET_LANG USPJEŠAN: {lang_names.get(language_value, language_value)}")
        return jsonify({
            'status': 'success',
            'message': f'Jezik displeja postavljen na {lang_names.get(language_value, language_value)}',
            'data': {'room_number': room_number, 'language': language_value}
        }), 200
        
    except Exception as e:
        logging.error(f"Greška u set_language: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/settings/manager_pin', methods=['POST'])
@require_api_key
def api_windows_change_manager_pin():
    """Mijenja manager PIN."""
    try:
        data = request.json
        old_pin = data.get('old_pin')
        new_pin = data.get('new_pin')

        with config_lock:
            current_pin = CONFIG.get('staff_pins', {}).get('manager', '1111')

        if old_pin != current_pin:
            return jsonify({'status': 'error', 'message': 'Stari PIN netačan'}), 403

        if not new_pin or len(new_pin) != 4 or not new_pin.isdigit():
            pin_len = len(new_pin) if new_pin else 0
            logging.warning(f"MANAGER PIN: Neispravna duzina PIN-a (len={pin_len}, ocekivano=4)")
            return jsonify({'status': 'error', 'message': 'Novi PIN mora biti 4 cifre'}), 400

        # ============================================================
        # WRITE-AHEAD: novi PIN + pending=True na sve sobe → save
        # ============================================================
        with config_lock:
            if 'staff_pins' not in CONFIG:
                CONFIG['staff_pins'] = {}
            CONFIG['staff_pins']['manager'] = new_pin
            for room_id, room_cfg in CONFIG.get('sobe', {}).items():
                if 'pin_controller' in room_cfg.get('uredjaji', {}):
                    room_cfg['staff_pin_sync_pending'] = True
        save_config()
        logging.info(f"MANAGER PIN: Write-ahead upisan ({new_pin}), šaljem na kontrolere...")

        # ============================================================
        # Šalji na svaki online kontroler, odmah briši pending ako OK
        # ============================================================
        success_count = 0
        failed_count = 0

        with config_lock:
            rooms = list(CONFIG.get('sobe', {}).items())

        for room_number, room_config in rooms:
            uredjaji = room_config.get('uredjaji', {})
            if 'pin_controller' not in uredjaji:
                continue
            if not room_config.get('cached_ip'):
                failed_count += 1
                logging.warning(f"MANAGER PIN: {room_number} offline, ostaje pending")
                continue
            try:
                pin_controller_id = uredjaji['pin_controller']['ID']
                secondary_pin_controller_id = uredjaji.get('secondary_pin_controller', {}).get('ID')
                success, _, _, _ = send_command_to_both_controllers(
                    room_number,
                    {'CMD': 'SET_PASSWORD', 'TYPE': 'MANAGER', 'PASSWORD': new_pin},
                    pin_controller_id,
                    secondary_pin_controller_id,
                    timeout=TIMEOUT_ESP_LONG
                )
                if success:
                    success_count += 1
                    with config_lock:
                        CONFIG['sobe'][room_number]['staff_pin_sync_pending'] = False
                    save_config()
                else:
                    failed_count += 1
                    logging.warning(f"MANAGER PIN: {room_number} NEUSPJEŠAN, ostaje pending")
            except:
                failed_count += 1

        logging.info(f"MANAGER PIN završen. Uspješno: {success_count}, Pending: {failed_count}")
        return jsonify({
            'status': 'success',
            'message': 'Manager PIN uspješno promijenjen',
            'data': {
                'updated': success_count,
                'failed': failed_count,
                'total': success_count + failed_count
            }
        }), 200

    except Exception as e:
        logging.error(f"Greška u change_manager_pin: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/settings/staff_pins', methods=['GET'])
@require_api_key
def api_get_staff_pins():
    """
    Endpoint za dobijanje trenutnih staff PIN-ova.
    APP poziva ovaj endpoint umjesto korištenja lokalnih defaulta.
    RPI config.json je jedini izvor istine za staff PIN-ove.
    """
    with config_lock:
        staff_pins = CONFIG.get('staff_pins', {})
        return jsonify({
            'status': 'success',
            'data': {
                'maid': staff_pins.get('maid', ''),
                'service': staff_pins.get('service', ''),
                'manager': staff_pins.get('manager', '')
            }
        })


@app.route('/api/settings/maid_pin', methods=['POST'])
@require_api_key
def api_windows_change_maid_pin():
    """Mijenja maid PIN na svim sobama."""
    try:
        data = request.json
        old_pin = data.get('old_pin')
        new_pin = data.get('new_pin')

        with config_lock:
            current_pin = CONFIG.get('staff_pins', {}).get('maid', '2222')

        if old_pin != current_pin:
            return jsonify({'status': 'error', 'message': 'Stari PIN netačan'}), 403

        if not new_pin or len(new_pin) != 4 or not new_pin.isdigit():
            pin_len = len(new_pin) if new_pin else 0
            logging.warning(f"MAID PIN: Neispravna duzina PIN-a (len={pin_len}, ocekivano=4)")
            return jsonify({'status': 'error', 'message': 'Novi PIN mora biti 4 cifre'}), 400

        # ============================================================
        # WRITE-AHEAD: novi PIN + pending=True na sve sobe → save
        # ============================================================
        with config_lock:
            if 'staff_pins' not in CONFIG:
                CONFIG['staff_pins'] = {}
            CONFIG['staff_pins']['maid'] = new_pin
            for room_id, room_cfg in CONFIG.get('sobe', {}).items():
                if 'pin_controller' in room_cfg.get('uredjaji', {}):
                    room_cfg['staff_pin_sync_pending'] = True
        save_config()
        logging.info(f"MAID PIN: Write-ahead upisan ({new_pin}), šaljem na kontrolere...")

        # ============================================================
        # Šalji na svaki online kontroler, odmah briši pending ako OK
        # ============================================================
        success_count = 0
        failed_count = 0

        with config_lock:
            rooms = list(CONFIG.get('sobe', {}).items())

        for room_number, room_config in rooms:
            uredjaji = room_config.get('uredjaji', {})
            if 'pin_controller' not in uredjaji:
                continue
            if not room_config.get('cached_ip'):
                failed_count += 1
                logging.warning(f"MAID PIN: {room_number} offline, ostaje pending")
                continue
            try:
                pin_controller_id = uredjaji['pin_controller']['ID']
                secondary_pin_controller_id = uredjaji.get('secondary_pin_controller', {}).get('ID')
                success, _, _, _ = send_command_to_both_controllers(
                    room_number,
                    {'CMD': 'SET_PASSWORD', 'TYPE': 'MAID', 'PASSWORD': new_pin},
                    pin_controller_id,
                    secondary_pin_controller_id,
                    timeout=TIMEOUT_ESP_LONG
                )
                if success:
                    success_count += 1
                    with config_lock:
                        CONFIG['sobe'][room_number]['staff_pin_sync_pending'] = False
                    save_config()
                else:
                    failed_count += 1
                    logging.warning(f"MAID PIN: {room_number} NEUSPJEŠAN, ostaje pending")
            except:
                failed_count += 1

        logging.info(f"MAID PIN završen. Uspješno: {success_count}, Pending: {failed_count}")
        return jsonify({
            'status': 'success',
            'message': 'Maid PIN promijenjen',
            'data': {
                'updated': success_count,
                'failed': failed_count,
                'total': success_count + failed_count
            }
        }), 200

    except Exception as e:
        logging.error(f"Greška u change_maid_pin: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/settings/service_pin', methods=['POST'])
@require_api_key
def api_windows_change_service_pin():
    """Mijenja service PIN na svim sobama."""
    try:
        data = request.json
        old_pin = data.get('old_pin')
        new_pin = data.get('new_pin')

        with config_lock:
            current_pin = CONFIG.get('staff_pins', {}).get('service', '3333')

        if old_pin != current_pin:
            return jsonify({'status': 'error', 'message': 'Stari PIN netačan'}), 403

        if not new_pin or len(new_pin) != 5 or not new_pin.isdigit():
            pin_len = len(new_pin) if new_pin else 0
            logging.warning(f"SERVICE PIN: Neispravna duzina PIN-a (len={pin_len}, ocekivano=5)")
            return jsonify({'status': 'error', 'message': 'Novi PIN mora biti 5 cifara'}), 400

        # ============================================================
        # WRITE-AHEAD: novi PIN + pending=True na sve sobe → save
        # ============================================================
        with config_lock:
            if 'staff_pins' not in CONFIG:
                CONFIG['staff_pins'] = {}
            CONFIG['staff_pins']['service'] = new_pin
            for room_id, room_cfg in CONFIG.get('sobe', {}).items():
                if 'pin_controller' in room_cfg.get('uredjaji', {}):
                    room_cfg['staff_pin_sync_pending'] = True
        save_config()
        logging.info(f"SERVICE PIN: Write-ahead upisan ({new_pin}), šaljem na kontrolere...")

        # ============================================================
        # Šalji na svaki online kontroler, odmah briši pending ako OK
        # ============================================================
        success_count = 0
        failed_count = 0

        with config_lock:
            rooms = list(CONFIG.get('sobe', {}).items())

        for room_number, room_config in rooms:
            uredjaji = room_config.get('uredjaji', {})
            if 'pin_controller' not in uredjaji:
                continue
            if not room_config.get('cached_ip'):
                failed_count += 1
                logging.warning(f"SERVICE PIN: {room_number} offline, ostaje pending")
                continue
            try:
                pin_controller_id = uredjaji['pin_controller']['ID']
                secondary_pin_controller_id = uredjaji.get('secondary_pin_controller', {}).get('ID')
                success, _, _, _ = send_command_to_both_controllers(
                    room_number,
                    {'CMD': 'SET_PASSWORD', 'TYPE': 'SERVICE', 'PASSWORD': new_pin},
                    pin_controller_id,
                    secondary_pin_controller_id,
                    timeout=TIMEOUT_ESP_LONG
                )
                if success:
                    success_count += 1
                    with config_lock:
                        CONFIG['sobe'][room_number]['staff_pin_sync_pending'] = False
                    save_config()
                else:
                    failed_count += 1
                    logging.warning(f"SERVICE PIN: {room_number} NEUSPJEŠAN, ostaje pending")
            except:
                failed_count += 1

        logging.info(f"SERVICE PIN završen. Uspješno: {success_count}, Pending: {failed_count}")
        return jsonify({
            'status': 'success',
            'message': 'Service PIN promijenjen',
            'data': {
                'updated': success_count,
                'failed': failed_count,
                'total': success_count + failed_count
            }
        }), 200

    except Exception as e:
        logging.error(f"Greška u change_service_pin: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/health', methods=['GET'])
@require_api_key
def api_windows_health():
    """Health check endpoint."""
    return jsonify({
        'status': 'success',
        'message': 'RPI server je aktivan',
        'data': {
            'version': '6.3',
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S')
        }
    })


@app.route('/api/debug/test_room_commands/<room_number>', methods=['GET'])
@require_api_key
def api_debug_test_room_commands(room_number):
    """🔍 DIJAGNOSTIČKI ENDPOINT - testira SVE komande na sobi i vraća detaljne rezultate."""
    try:
        # Get room config
        with config_lock:
            room_config = CONFIG.get('sobe', {}).get(room_number)
        
        if not room_config:
            return jsonify({'status': 'error', 'message': 'Soba ne postoji'}), 404
        
        if not room_config.get('cached_ip'):
            return jsonify({'status': 'error', 'message': f'Soba {room_number} je offline'}), 503
        
        pin_controller_id = room_config['uredjaji']['pin_controller']['ID']
        scene_controller_id = room_config['uredjaji'].get('scene_controller', {}).get('ID', pin_controller_id)
        thermostat_id = room_config['uredjaji']['termostat_set']['ID']
        base_url = get_cached_url_only(room_number)[0]
        
        results = {
            'room_number': room_number,
            'base_url': base_url,
            'pin_controller_id': pin_controller_id,
            'scene_controller_id': scene_controller_id,
            'thermostat_id': thermostat_id,
            'config_check': {
                'has_scene_controller': 'scene_controller' in room_config['uredjaji'],
                'scene_controller_config': room_config['uredjaji'].get('scene_controller')
            },
            'tests': []
        }
        
        # Test 1: GET_GUEST_IN_TEMP (na SCENE kontroleru!)
        logging.info(f"[DEBUG {room_number}] Test 1: GET_GUEST_IN_TEMP na SCENE_ID={scene_controller_id}")
        resp_obj, msg, json_data = send_esp_command(room_number, {
            'CMD': 'GET_GUEST_IN_TEMP',
            'ID': scene_controller_id
        }, timeout=TIMEOUT_ESP_DEFAULT)
        results['tests'].append({
            'command': 'GET_GUEST_IN_TEMP',
            'id': scene_controller_id,
            'success': json_data and json_data.get('status') == 'success',
            'response': json_data,
            'message': msg
        })
        
        # Test 2: GET_GUEST_OUT_TEMP (na SCENE kontroleru!)
        logging.info(f"[DEBUG {room_number}] Test 2: GET_GUEST_OUT_TEMP na SCENE_ID={scene_controller_id}")
        resp_obj, msg, json_data = send_esp_command(room_number, {
            'CMD': 'GET_GUEST_OUT_TEMP',
            'ID': scene_controller_id
        }, timeout=TIMEOUT_ESP_DEFAULT)
        results['tests'].append({
            'command': 'GET_GUEST_OUT_TEMP',
            'id': scene_controller_id,
            'success': json_data and json_data.get('status') == 'success',
            'response': json_data,
            'message': msg
        })
        
        # Test 3: GET_ROOM_TEMP
        logging.info(f"[DEBUG {room_number}] Test 3: GET_ROOM_TEMP")
        resp_obj, msg, json_data = send_esp_command(room_number, {
            'CMD': 'GET_ROOM_TEMP',
            'ID': thermostat_id
        }, timeout=TIMEOUT_ESP_DEFAULT)
        results['tests'].append({
            'command': 'GET_ROOM_TEMP',
            'id': thermostat_id,
            'success': json_data and json_data.get('status') == 'success',
            'response': json_data,
            'message': msg
        })
        
        # Test 4: SET_GUEST_IN_TEMP (probni set na trenutnu vrijednost)
        current_guest_in = results['tests'][0].get('response', {}).get('data', {}).get('guest_in_temperature', 22)
        logging.info(f"[DEBUG {room_number}] Test 4: SET_GUEST_IN_TEMP={current_guest_in}")
        resp_obj, msg, json_data = send_esp_command(room_number, {
            'CMD': 'SET_GUEST_IN_TEMP',
            'ID': pin_controller_id,
            'VALUE': str(int(current_guest_in))
        }, timeout=TIMEOUT_ESP_LONG)
        results['tests'].append({
            'command': f'SET_GUEST_IN_TEMP (VALUE={current_guest_in})',
            'id': pin_controller_id,
            'success': json_data and json_data.get('status') == 'success',
            'response': json_data,
            'message': msg
        })
        
        # Summary
        total_tests = len(results['tests'])
        passed_tests = sum(1 for t in results['tests'] if t['success'])
        results['summary'] = {
            'total': total_tests,
            'passed': passed_tests,
            'failed': total_tests - passed_tests,
            'success_rate': f"{(passed_tests/total_tests*100):.1f}%"
        }
        
        return jsonify({
            'status': 'success',
            'message': 'Dijagnostički test završen',
            'data': results
        }), 200
        
    except Exception as e:
        logging.error(f"Greška u test_room_commands: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500, 200

# ----------------------------------------------------------------------
# STAFF PIN SYNC TASK
# ----------------------------------------------------------------------
def _sync_staff_pins_to_room(room_id, maid_pin, manager_pin, service_pin):
    """Pokušava sinhronizirati sva 3 staff PIN-a na jednoj sobi. Vraća True ako svi OK."""
    with config_lock:
        room_cfg = CONFIG.get('sobe', {}).get(room_id, {})
    uredjaji = room_cfg.get('uredjaji', {})
    if 'pin_controller' not in uredjaji:
        return True
    if not room_cfg.get('cached_ip'):
        return False

    pin_controller_id = uredjaji['pin_controller']['ID']
    secondary_id = uredjaji.get('secondary_pin_controller', {}).get('ID')

    all_ok = True
    for pin_type, pin_value in [('MAID', maid_pin), ('MANAGER', manager_pin), ('SERVICE', service_pin)]:
        if not pin_value:
            continue
        success, _, _, _ = send_command_to_both_controllers(
            room_id,
            {'CMD': 'SET_PASSWORD', 'TYPE': pin_type, 'PASSWORD': pin_value},
            pin_controller_id,
            secondary_id,
            timeout=TIMEOUT_ESP_LONG
        )
        if success:
            logging.info(f"[StaffPinSync] {room_id}: {pin_type} OK")
        else:
            logging.warning(f"[StaffPinSync] {room_id}: {pin_type} NEUSPJEŠAN")
            all_ok = False

    if all_ok:
        with config_lock:
            CONFIG['sobe'][room_id]['staff_pin_sync_pending'] = False
        save_config()
        logging.info(f"[StaffPinSync] {room_id}: sync završen, pending=False")
    return all_ok


def staff_pin_sync_task():
    """Pozadinska petlja koja sinhronizira staff PIN-ove na sobama s pending=True."""
    time.sleep(STAFF_PIN_SYNC_START_DELAY_SECONDS)
    logging.info("[StaffPinSync] Worker started")
    while True:
        try:
            with config_lock:
                maid_pin = CONFIG.get('staff_pins', {}).get('maid', '')
                manager_pin = CONFIG.get('staff_pins', {}).get('manager', '')
                service_pin = CONFIG.get('staff_pins', {}).get('service', '')
                pending_rooms = [
                    room_id for room_id, room_cfg in CONFIG.get('sobe', {}).items()
                    if room_cfg.get('staff_pin_sync_pending', False)
                    and 'pin_controller' in room_cfg.get('uredjaji', {})
                    and room_cfg.get('cached_ip')
                ]

            if pending_rooms:
                logging.info(f"[StaffPinSync] Pronađeno {len(pending_rooms)} soba sa pending sync: {pending_rooms}")
                for room_id in pending_rooms:
                    _sync_staff_pins_to_room(room_id, maid_pin, manager_pin, service_pin)
            else:
                logging.debug("[StaffPinSync] Nema pending soba")

        except Exception as e:
            logging.error(f"[StaffPinSync] Greška: {e}")

        time.sleep(STAFF_PIN_SYNC_INTERVAL_SECONDS)


# ----------------------------------------------------------------------
# LOG TRANSFER WORKER
# ----------------------------------------------------------------------
APP_ENDPOINT_URL = None

def log_transfer_worker():
    """Background worker za transfer logova UL->RPI->APP"""
    global APP_ENDPOINT_URL
    
    # Početni delay prije starta
    time.sleep(LOG_TRANSFER_START_DELAY_SECONDS)
    logging.info("[LogTransfer] Worker started")
    
    while True:
        try:
            if not APP_ENDPOINT_URL:
                logging.debug("[LogTransfer] Waiting for APP registration...")
                time.sleep(5)
                continue
            
            logging.info("[LogTransfer] Starting log pull cycle...")
            
            with config_lock:
                rooms = CONFIG.get('sobe', {})
            
            total_logs = 0
            for room_id, room_data in rooms.items():
                pin_controller = room_data.get('uredjaji', {}).get('pin_controller', {})
                device_id = pin_controller.get('ID')
                
                if not device_id:
                    continue
                
                # Drain loop - sve logove sa jednog UL
                while True:
                    try:
                        # READ_LOG
                        resp, msg, json_data = send_esp_command(
                            room_id,
                            {'CMD': 'READ_LOG', 'ID': device_id},
                            timeout=TIMEOUT_ESP_SHORT
                        )
                        
                        # Provjeri status unutar 'data' (READ_LOG format)
                        if not json_data:
                            break
                        
                        log_data = json_data.get('data', {})
                        log_status = log_data.get('status', '').upper()
                        
                        if log_status != 'OK':
                            break  # Status je EMPTY ili nepoznat - nema logova
                        
                        # DODAJ room_number prije slanja na APP
                        log_data['room_number'] = room_id
                        
                        # Šalji na APP - šalji cijeli log_data sa room_number
                        app_response = requests.post(
                            f'{APP_ENDPOINT_URL}/api/logs/receive',
                            json={'log': log_data},
                            timeout=TIMEOUT_APP_POST
                        )
                        
                        if app_response.status_code == 200:
                            # APP potvrdio, briši sa UL
                            send_esp_command(
                                room_id,
                                {'CMD': 'DELETE_LOG', 'ID': device_id},
                                timeout=TIMEOUT_ESP_SHORT
                            )
                            total_logs += 1
                            logging.info(f"[LogTransfer] Log transferred from room {room_id}")
                            time.sleep(0.1)
                        else:
                            logging.warning(f"[LogTransfer] APP rejected log from {room_id}")
                            break  # APP nije dostupan, idi dalje
                            
                    except Exception as e:
                        logging.debug(f"Log transfer error {room_id}: {e}")
                        break
                
                time.sleep(0.5)
            
            logging.info(f"[LogTransfer] Cycle complete: {total_logs} logs transferred")
            time.sleep(10)
            
        except Exception as e:
            logging.error(f"Log transfer worker error: {e}")
            time.sleep(10)

@app.route('/api/log_transfer/register_app', methods=['POST'])
def register_app():
    """APP se registruje kada se pokrene"""
    global APP_ENDPOINT_URL
    data = request.get_json()
    app_url = data.get('app_url')
    
    if app_url:
        APP_ENDPOINT_URL = app_url.rstrip('/')
        logging.info(f"APP registered: {APP_ENDPOINT_URL}")
        return jsonify({'status': 'success'})
    
    return jsonify({'status': 'error'}), 400

# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
if __name__ == '__main__':
    load_config() 
    
    logging.info("Pokrećem inicijalno mapiranje IP adresa U POZADINI...")
    with config_lock:
        initial_soba_ids = list(CONFIG.get('sobe', {}).keys())
    
    def initial_map():
        for soba_id in initial_soba_ids:
            resolve_and_cache_ip(soba_id)
            time.sleep(0.5)
        logging.info("Inicijalno mapiranje završeno.")
        
    initial_map_thread = threading.Thread(target=initial_map, daemon=True)
    initial_map_thread.start()
    
    resolver_thread = threading.Thread(target=background_resolver_task, daemon=True)
    resolver_thread.start()
    
    log_transfer_thread = threading.Thread(target=log_transfer_worker, daemon=True)
    log_transfer_thread.start()

    staff_pin_sync_thread = threading.Thread(target=staff_pin_sync_task, daemon=True)
    staff_pin_sync_thread.start()

    server_host = _get_nested(CONFIG, ['server', 'host'], '0.0.0.0')
    if server_host == '*':
        server_host = '0.0.0.0'
    server_port = int(_as_number(_get_nested(CONFIG, ['server', 'port'], 8022), 8022))

    logging.info("--- Pokrecem Toplik Service (PRODUKCIJA Faza 6.3) ---")
    logging.info(f"--- Server radi na http://{server_host}:{server_port} ---")
    logging.info("--- Pritisnite CTRL+C za zaustavljanje ---")
    
    try:
        serve(app, host=server_host, port=server_port, threads=10)
    except ImportError:
        logging.critical("!!! GRESKA: 'waitress' nije instaliran.")
        logging.critical("!!! Pokrenite 'instaliraj_biblioteke.bat' ponovo.")