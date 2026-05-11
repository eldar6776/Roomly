import Database from 'better-sqlite3';
import * as path from 'path';
import { app } from 'electron';

let db: Database.Database | null = null;

export function getDatabase(): Database.Database {
  if (!db) {
    const dbPath = path.join(app.getPath('userData'), 'hotel.db');
    db = new Database(dbPath);
    db.pragma('journal_mode = WAL');
  }
  return db;
}

export async function setupDatabase(): Promise<void> {
  const database = getDatabase();

  // Check if we need to migrate (remove guest_pin column)
  try {
    const tableInfo = database.prepare("PRAGMA table_info(guests)").all() as any[];
    const hasPinColumn = tableInfo.some((col: any) => col.name === 'guest_pin');
    
    if (hasPinColumn) {
      console.log('🔄 Migrating database: Removing guest_pin column...');
      
      // SQLite doesn't support DROP COLUMN, so we need to recreate the table
      database.exec(`
        -- Create new table without guest_pin
        CREATE TABLE IF NOT EXISTS guests_new (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          room_number TEXT NOT NULL,
          check_in_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          check_out_date TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'ACTIVE',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Copy data from old table (excluding guest_pin)
        INSERT INTO guests_new (id, room_number, check_in_date, check_out_date, status, created_at, updated_at)
        SELECT id, room_number, 
               COALESCE(check_in_date, created_at) as check_in_date,
               check_out_date, status, created_at, updated_at
        FROM guests;
        
        -- Drop old table
        DROP TABLE guests;
        
        -- Rename new table
        ALTER TABLE guests_new RENAME TO guests;
        
        -- Recreate indexes
        CREATE INDEX IF NOT EXISTS idx_guests_room ON guests(room_number);
        CREATE INDEX IF NOT EXISTS idx_guests_status ON guests(status);
      `);
      
      console.log('✅ Database migration completed: guest_pin column removed');
    }
  } catch (error: any) {
    // Table doesn't exist yet, will be created below
    if (!error.message.includes('no such table')) {
      console.error('Migration error:', error);
    }
  }

  // Migracija: dodaj language kolonu ako ne postoji (nezavisno od ostalih migracija)
  try {
    const cols = database.prepare('PRAGMA table_info(guests)').all() as any[];
    const hasLanguage = cols.some((col: any) => col.name === 'language');
    if (!hasLanguage && cols.length > 0) {
      database.exec("ALTER TABLE guests ADD COLUMN language TEXT NOT NULL DEFAULT 'srb'");
      console.log('✅ DB migracija: language kolona dodana u guests tabelu');
    }
  } catch (e: any) {
    if (!e.message?.includes('no such table')) {
      console.error('Migracija language kolone:', e);
    }
  }

  // Create tables (will only create if they don't exist)
  database.exec(`
    CREATE TABLE IF NOT EXISTS guests (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      room_number TEXT NOT NULL,
      check_in_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      check_out_date TEXT NOT NULL,
      language TEXT NOT NULL DEFAULT 'srb',
      status TEXT NOT NULL DEFAULT 'ACTIVE',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_guests_room ON guests(room_number);
    CREATE INDEX IF NOT EXISTS idx_guests_status ON guests(status);

    -- SYSTEM LOGS: App actions (check-in, check-out, PIN changes)
    CREATE TABLE IF NOT EXISTS system_logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      room_number TEXT,
      event_type TEXT NOT NULL,
      event_code TEXT,
      description TEXT NOT NULL,
      user_role TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_system_logs_room ON system_logs(room_number);
    CREATE INDEX IF NOT EXISTS idx_system_logs_timestamp ON system_logs(timestamp);
    CREATE INDEX IF NOT EXISTS idx_system_logs_event_type ON system_logs(event_type);

    -- ACCESS LOGS: UL controller logs (who entered the room)
    CREATE TABLE IF NOT EXISTS access_logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      timestamp TEXT NOT NULL,
      room_number TEXT NOT NULL,
      device_id INTEGER NOT NULL,
      access_type TEXT NOT NULL,
      access_method TEXT NOT NULL,
      card_id TEXT,
      pin_type TEXT,
      event_code TEXT,
      description TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_access_logs_room ON access_logs(room_number);
    CREATE INDEX IF NOT EXISTS idx_access_logs_timestamp ON access_logs(timestamp);
    CREATE INDEX IF NOT EXISTS idx_access_logs_type ON access_logs(access_type);
    CREATE INDEX IF NOT EXISTS idx_access_logs_method ON access_logs(access_method);

    -- ERROR LOGS: System errors (offline controllers, failed commands)
    CREATE TABLE IF NOT EXISTS error_logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      room_number TEXT,
      error_type TEXT NOT NULL,
      error_code TEXT,
      severity TEXT NOT NULL,
      message TEXT NOT NULL,
      details TEXT,
      resolved BOOLEAN DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_error_logs_room ON error_logs(room_number);
    CREATE INDEX IF NOT EXISTS idx_error_logs_timestamp ON error_logs(timestamp);
    CREATE INDEX IF NOT EXISTS idx_error_logs_type ON error_logs(error_type);
    CREATE INDEX IF NOT EXISTS idx_error_logs_severity ON error_logs(severity);
    CREATE INDEX IF NOT EXISTS idx_error_logs_resolved ON error_logs(resolved);

    -- Legacy logs table (keep for backward compatibility, will be migrated)
    CREATE TABLE IF NOT EXISTS logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      timestamp TEXT NOT NULL,
      room_number TEXT NOT NULL,
      device_id INTEGER NOT NULL,
      event_code TEXT NOT NULL,
      event_type TEXT NOT NULL,
      description TEXT,
      card_id TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_logs_room ON logs(room_number);
    CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp);
    CREATE INDEX IF NOT EXISTS idx_logs_event_type ON logs(event_type);

    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
  `);

  // Migracija: ukloni zastarjele maid_pin i service_pin iz baze
  // Ovi PIN-ovi su stari ostatak - APP ih više ne čuva lokalno (RPI je jedini izvor istine)
  const stalePinKeys = database.prepare("SELECT key FROM settings WHERE key IN ('maid_pin', 'service_pin')").all() as any[];
  if (stalePinKeys.length > 0) {
    database.prepare("DELETE FROM settings WHERE key IN ('maid_pin', 'service_pin')").run();
    console.log('🧹 Migracija: Uklonjeni zastarjeli maid_pin i service_pin iz SQLite baze');
  }

  // Insert default settings if not exist
  // Import vrednosti iz centralnog configa
  const { DEFAULT_PINS, DEFAULT_SETTINGS } = require('../config');

  // Provjeri WRITE_DEFAULT_PINS flag - ako je postavljen, PREPIŠI reception i manager PIN
  const writeDefaultPins = process.env.WRITE_DEFAULT_PINS === 'true';
  if (writeDefaultPins) {
    console.log('⚠️  WRITE_DEFAULT_PINS=true: Prepisujem reception_pin i manager_pin u SQLite sa .env default-ima!');
    database.prepare('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)').run('reception_pin', DEFAULT_PINS.reception);
    database.prepare('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)').run('manager_pin', DEFAULT_PINS.manager);
    console.log(`✅  reception_pin → ${DEFAULT_PINS.reception}, manager_pin → ${DEFAULT_PINS.manager}`);
  }
  
  const defaultSettings = [
    { key: 'reception_pin', value: DEFAULT_PINS.reception },
    { key: 'manager_pin', value: DEFAULT_PINS.manager },
    // Maid i Service PIN-ovi se NE čuvaju u APP bazi - RPI je jedini izvor istine
    // APP dobija ove PIN-ove od RPI-a preko API-ja
    { key: 'checkout_time', value: DEFAULT_SETTINGS.checkoutTime },
    { key: 'guest_in_temp', value: DEFAULT_SETTINGS.guestInTemp.toString() },
    { key: 'guest_out_temp', value: DEFAULT_SETTINGS.guestOutTemp.toString() },
    { key: 'default_language', value: DEFAULT_SETTINGS.language },
  ];

  // INSERT OR IGNORE - ne dira postojeće vrijednosti (osim ako je writeDefaultPins=true, gore je već urađeno)
  const insertSetting = database.prepare(
    'INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)'
  );

  for (const setting of defaultSettings) {
    insertSetting.run(setting.key, setting.value);
  }

  console.log('✅ Database initialized successfully');
}

export function closeDatabase(): void {
  if (db) {
    db.close();
    db = null;
  }
}
