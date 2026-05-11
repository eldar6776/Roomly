import express from 'express';
import { getDatabase } from './database';
import axios from 'axios';
import { RPI_CONFIG, LOCAL_IP } from './config';
import * as os from 'os';

const app = express();
app.use(express.json());

// Convert DD.MM.YYYY HH:MM:SS to ISO format YYYY-MM-DD HH:MM:SS
function convertToISO(timestamp: string): string {
  // Format: "22.01.2026 15:10:40"
  const [datePart, timePart] = timestamp.split(' ');
  const [day, month, year] = datePart.split('.');
  return `${year}-${month}-${day} ${timePart}`;
}

app.post('/api/logs/receive', async (req, res) => {
  const { log } = req.body;
  if (!log) {
    return res.status(400).json({ status: 'error', message: 'No log provided' });
  }
  try {
    console.log('[LogReceiver] Primljen log:', log);
    const db = getDatabase();
    
    // Convert timestamp to ISO format
    let timestamp = log.timestamp || (log.date && log.time ? `${log.date} ${log.time}` : null);
    if (timestamp) {
      timestamp = convertToISO(timestamp);
    }
    
    const eventName = log.event_name || '';
    const roomNumber = log.room_number || String(log.device_id || ''); // RPI šalje room_number
    
    // Classify log type
    const accessEvents = ['PASSWORD_VALID', 'GUEST_CARD', 'MAID_CARD', 'MANAGER_CARD', 'SERVICE_CARD'];
    const systemEvents = ['POWER_ON_RESET', 'SOFTWARE_RESET', 'WATCHDOG_RESET', 'BROWNOUT_RESET'];
    const errorEvents = ['INVALID_CARD', 'INVALID_PASSWORD', 'EXPIRED_PASSWORD', 'TAMPER_ALERT', 'LOW_BATTERY'];
    
    if (accessEvents.includes(eventName)) {
      // ACCESS LOG
      let accessMethod = 'UNKNOWN';
      let pinType = null;
      
      if (eventName === 'PASSWORD_VALID' || log.event_description?.includes('PIN')) {
        accessMethod = 'PIN';
        // Determine PIN type based on group field
        // group: 71 = Guest PIN, 72 = Maid PIN, 77 = Manager/Service PIN
        if (log.group === 71) {
          pinType = 'GUEST';
        } else if (log.group === 72) {
          pinType = 'MAID';
        } else if (log.group === 77) {
          pinType = 'MANAGER';
        }
      } else if (eventName.includes('CARD') || log.event_description?.includes('karticom')) {
        accessMethod = 'CARD';
      }
      
      db.prepare(`
        INSERT INTO access_logs 
        (room_number, timestamp, device_id, access_type, access_method, card_id, pin_type, event_code, description)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      `).run(
        roomNumber,
        timestamp,
        log.device_id || null,
        log.event_name || null,
        accessMethod,
        log.card_id || null,
        pinType,
        log.event_code || null,
        log.event_description || null
      );
    } else if (systemEvents.includes(eventName) || eventName.includes('RESET')) {
      // SYSTEM LOG
      db.prepare(`
        INSERT INTO system_logs 
        (timestamp, room_number, event_type, event_code, description)
        VALUES (?, ?, ?, ?, ?)
      `).run(
        timestamp,
        roomNumber,
        log.event_name || null,
        log.event_code || null,
        log.event_description || null
      );
    } else if (errorEvents.includes(eventName) || eventName.includes('INVALID') || eventName.includes('ERROR')) {
      // ERROR LOG
      let severity = 'WARNING';
      if (eventName.includes('TAMPER') || eventName.includes('ALERT')) {
        severity = 'CRITICAL';
      } else if (eventName.includes('ERROR')) {
        severity = 'ERROR';
      }
      
      db.prepare(`
        INSERT INTO error_logs 
        (timestamp, room_number, error_type, error_code, severity, message, details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
      `).run(
        timestamp,
        roomNumber,
        log.event_name || 'UNKNOWN',
        log.event_code || null,
        severity,
        log.event_description || 'Unknown error',
        JSON.stringify({ card_id: log.card_id, type: log.type, group: log.group })
      );
    } else {
      // FALLBACK - unknown events go to system_logs
      db.prepare(`
        INSERT INTO system_logs 
        (timestamp, room_number, event_type, event_code, description)
        VALUES (?, ?, ?, ?, ?)
      `).run(
        timestamp,
        roomNumber,
        log.event_name || 'UNKNOWN',
        log.event_code || null,
        log.event_description || 'Unknown event'
      );
    }
    
    return res.json({ status: 'success' });
  } catch (e) {
    console.error('[LogReceiver] Failed to insert log:', e);
    return res.status(500).json({ status: 'error', message: 'DB insert failed' });
  }
});

/**
 * Dohvata lokalnu IP adresu mašine na LAN mreži
 * 
 * Prioritet:
 * 1. Ako postoji LOCAL_IP u .env fajlu, koristi to (manual override)
 * 2. Automatska detekcija sa pametnim filterima:
 *    - Ignoriši APIPA adrese (169.254.x.x)
 *    - Ignoriši VPN/Tailscale/Docker adaptere
 *    - Preferiraj adaptere sa default gateway
 * 3. Fallback na localhost
 */
function getLocalIPAddress(): string {
  // 1. Manual override iz .env fajla
  const manualIP = LOCAL_IP;
  if (manualIP && manualIP.trim() !== '') {
    console.log('[LogReceiver] Using manual IP from .env:', manualIP);
    return manualIP.trim();
  }
  
  // 2. Automatska detekcija
  const interfaces = os.networkInterfaces();
  const candidates: Array<{name: string, address: string, hasGateway: boolean}> = [];
  
  // Blacklist imena adaptera koje treba ignorisati
  const ignoreNames = ['tailscale', 'virtualbox', 'vmware', 'docker', 'vethernet', 'hyper-v'];
  
  for (const name of Object.keys(interfaces)) {
    // Skip ako je adapter na blacklist-i
    const nameLower = name.toLowerCase();
    if (ignoreNames.some(ignore => nameLower.includes(ignore))) {
      continue;
    }
    
    const iface = interfaces[name];
    if (!iface) continue;
    
    for (const alias of iface) {
      // Traži IPv4 adresu koja nije internal (loopback)
      if (alias.family === 'IPv4' && !alias.internal) {
        const ip = alias.address;
        
        // Ignoriši APIPA adrese (169.254.x.x)
        if (ip.startsWith('169.254.')) {
          console.log(`[LogReceiver] Skipping APIPA address: ${ip} on ${name}`);
          continue;
        }
        
        // Ignoriši Docker/VirtualBox range
        if (ip.startsWith('172.17.') || ip.startsWith('172.18.')) {
          continue;
        }
        
        // Ovo je validan kandidat
        // Heuristika: ako je WiFi ili Ethernet i u 192.168.x.x rangu, verovatno ima gateway
        const hasGateway = ip.startsWith('192.168.') || ip.startsWith('10.');
        
        candidates.push({
          name,
          address: ip,
          hasGateway
        });
      }
    }
  }
  
  // Sortiraj: prvo oni sa gateway-em
  candidates.sort((a, b) => {
    if (a.hasGateway && !b.hasGateway) return -1;
    if (!a.hasGateway && b.hasGateway) return 1;
    return 0;
  });
  
  // Vrati prvi najbolji kandidat
  if (candidates.length > 0) {
    const best = candidates[0];
    console.log(`[LogReceiver] Auto-detected IP: ${best.address} on ${best.name}`);
    if (candidates.length > 1) {
      console.log('[LogReceiver] TIP: Postoji više mrežnih adaptera. Možeš eksplicitno postaviti LOCAL_IP u .env fajlu.');
      console.log('[LogReceiver] Ostali adapteri:', candidates.slice(1).map(c => `${c.address} (${c.name})`).join(', '));
    }
    return best.address;
  }
  
  // 3. Fallback na localhost ako ne može naći pravu IP
  console.log('[LogReceiver] WARNING: Nisam mogao pronaći validnu IP adresu. Koristim localhost.');
  console.log('[LogReceiver] TIP: Postavi LOCAL_IP u .env fajlu sa tvojom IP adresom (npr. LOCAL_IP=192.168.88.58)');
  return 'localhost';
}

async function registerWithRPI() {
  try {
    const rpiUrl = RPI_CONFIG.baseURL;
    const localIP = getLocalIPAddress();
    const appUrl = `http://${localIP}:3000`;
    
    console.log(`[LogReceiver] Registering with RPI using IP: ${localIP}`);
    
    await axios.post(`${rpiUrl}/api/log_transfer/register_app`, {
      app_url: appUrl
    }, { timeout: 5000 });
    
    console.log(`[LogReceiver] Successfully registered with RPI: ${appUrl}`);
  } catch (error) {
    console.log('[LogReceiver] RPI registration failed (will retry on next start)');
  }
}

export function startLogReceiver() {
  app.listen(3000, () => {
    console.log('📡 Log receiver listening on port 3000');
    setTimeout(() => registerWithRPI(), 2000);
  });
}
