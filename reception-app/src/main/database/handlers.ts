import { ipcMain } from 'electron';
import { getDatabase } from './index';
import { generateUniquePin, checkPinCollision } from '../utils/pinGenerator';

export function setupDatabaseHandlers(): void {
  const db = getDatabase();

  // Guests handlers
  ipcMain.handle('db:guests:create', async (_event, data) => {
    const stmt = db.prepare(`
      INSERT INTO guests (room_number, check_in_date, check_out_date, language, status)
      VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?)
    `);
    const result = stmt.run(
      data.room_number,
      data.check_out_date,
      data.language ?? 'srb',
      'ACTIVE'
    );
    return { id: result.lastInsertRowid };
  });

  ipcMain.handle('db:guests:getAll', async () => {
    const stmt = db.prepare('SELECT * FROM guests ORDER BY created_at DESC');
    return stmt.all();
  });

  ipcMain.handle('db:guests:getActive', async () => {
    const stmt = db.prepare("SELECT * FROM guests WHERE status = 'ACTIVE' ORDER BY room_number");
    return stmt.all();
  });

  ipcMain.handle('db:guests:update', async (_event, id: number, data) => {
    const fields = [];
    const values = [];
    
    if (data.room_number !== undefined) {
      fields.push('room_number = ?');
      values.push(data.room_number);
    }
    if (data.check_in !== undefined) {
      fields.push('check_in_date = ?');
      values.push(data.check_in);
    }
    if (data.check_out !== undefined) {
      fields.push('check_out_date = ?');
      values.push(data.check_out);
    }
    if (data.status !== undefined) {
      fields.push('status = ?');
      values.push(data.status);
    }
    
    fields.push('updated_at = CURRENT_TIMESTAMP');
    values.push(id);
    
    const stmt = db.prepare(`
      UPDATE guests 
      SET ${fields.join(', ')}
      WHERE id = ?
    `);
    stmt.run(...values);
    return { success: true };
  });

  ipcMain.handle('db:guests:checkOut', async (_event, roomNumber: string) => {
    const stmt = db.prepare(`
      UPDATE guests 
      SET status = 'CHECKED_OUT', updated_at = CURRENT_TIMESTAMP
      WHERE room_number = ? AND status = 'ACTIVE'
    `);
    stmt.run(roomNumber);
    return { success: true };
  });

  // Logs handlers
  ipcMain.handle('db:logs:create', async (_event, data) => {
    const stmt = db.prepare(`
      INSERT INTO logs (timestamp, room_number, device_id, event_code, event_type, description, card_id)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `);
    const result = stmt.run(
      data.timestamp || new Date().toISOString(),  // Auto-generate if missing
      data.room_number || '',
      data.device_id || 0,
      data.event_code || '',
      data.event_type || 'UNKNOWN',
      data.description || '',
      data.card_id || null
    );
    return { id: result.lastInsertRowid };
  });

  // System Logs handlers
  ipcMain.handle('db:systemLogs:create', async (_event, data) => {
    const stmt = db.prepare(`
      INSERT INTO system_logs (timestamp, room_number, event_type, event_code, description, user_role)
      VALUES (?, ?, ?, ?, ?, ?)
    `);
    const result = stmt.run(
      data.timestamp || new Date().toISOString(),
      data.room_number || null,
      data.event_type,
      data.event_code || null,
      data.description,
      data.user_role || 'SYSTEM'
    );
    return { id: result.lastInsertRowid };
  });

  ipcMain.handle('db:systemLogs:getAll', async (_event, filters) => {
    let query = 'SELECT * FROM system_logs WHERE 1=1';
    const params: any[] = [];

    if (filters?.room_number) {
      query += ' AND room_number = ?';
      params.push(filters.room_number);
    }

    if (filters?.start_date) {
      query += ' AND timestamp >= ?';
      params.push(filters.start_date);
    }

    if (filters?.end_date) {
      query += ' AND timestamp <= ?';
      params.push(filters.end_date);
    }

    if (filters?.event_type) {
      query += ' AND event_type = ?';
      params.push(filters.event_type);
    }

    query += ' ORDER BY timestamp DESC';

    if (filters?.limit) {
      query += ' LIMIT ?';
      params.push(filters.limit);
    }

    const stmt = db.prepare(query);
    return stmt.all(...params);
  });

  // Access Logs handlers
  ipcMain.handle('db:accessLogs:create', async (_event, data) => {
    const stmt = db.prepare(`
      INSERT INTO access_logs (timestamp, room_number, device_id, access_type, access_method, card_id, pin_type, event_code, description)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);
    const result = stmt.run(
      data.timestamp,
      data.room_number,
      data.device_id,
      data.access_type,
      data.access_method,
      data.card_id || null,
      data.pin_type || null,
      data.event_code || null,
      data.description || null
    );
    return { id: result.lastInsertRowid };
  });

  ipcMain.handle('db:accessLogs:getAll', async (_event, filters) => {
    let query = 'SELECT * FROM access_logs WHERE 1=1';
    const params: any[] = [];

    // Isključi stare logove sa invalidnim podacima
    query += ' AND access_method IN (?, ?)';
    params.push('PIN', 'CARD');

    if (filters?.room_number) {
      query += ' AND room_number = ?';
      params.push(filters.room_number);
    }

    if (filters?.start_date) {
      query += ' AND timestamp >= ?';
      params.push(filters.start_date);
    }

    if (filters?.end_date) {
      query += ' AND timestamp <= ?';
      params.push(filters.end_date);
    }

    if (filters?.access_method) {
      query += ' AND access_method = ?';
      params.push(filters.access_method);
    }

    if (filters?.pin_type) {
      query += ' AND pin_type = ?';
      params.push(filters.pin_type);
    }

    query += ' ORDER BY timestamp DESC';

    if (filters?.limit) {
      query += ' LIMIT ?';
      params.push(filters.limit);
    }

    const stmt = db.prepare(query);
    return stmt.all(...params);
  });

  // Error Logs handlers
  ipcMain.handle('db:errorLogs:create', async (_event, data) => {
    const stmt = db.prepare(`
      INSERT INTO error_logs (timestamp, room_number, error_type, error_code, severity, message, details, resolved)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `);
    const result = stmt.run(
      data.timestamp || new Date().toISOString(),
      data.room_number || null,
      data.error_type,
      data.error_code || null,
      data.severity || 'ERROR',
      data.message,
      data.details || null,
      data.resolved || 0
    );
    return { id: result.lastInsertRowid };
  });

  ipcMain.handle('db:errorLogs:getAll', async (_event, filters) => {
    let query = 'SELECT * FROM error_logs WHERE 1=1';
    const params: any[] = [];

    if (filters?.room_number) {
      query += ' AND room_number = ?';
      params.push(filters.room_number);
    }

    if (filters?.start_date) {
      query += ' AND timestamp >= ?';
      params.push(filters.start_date);
    }

    if (filters?.end_date) {
      query += ' AND timestamp <= ?';
      params.push(filters.end_date);
    }

    if (filters?.error_type) {
      query += ' AND error_type = ?';
      params.push(filters.error_type);
    }

    if (filters?.severity) {
      query += ' AND severity = ?';
      params.push(filters.severity);
    }

    if (filters?.resolved !== undefined) {
      query += ' AND resolved = ?';
      params.push(filters.resolved ? 1 : 0);
    }

    query += ' ORDER BY timestamp DESC';

    if (filters?.limit) {
      query += ' LIMIT ?';
      params.push(filters.limit);
    }

    const stmt = db.prepare(query);
    return stmt.all(...params);
  });

  ipcMain.handle('db:errorLogs:resolve', async (_event, id: number) => {
    const stmt = db.prepare('UPDATE error_logs SET resolved = 1 WHERE id = ?');
    stmt.run(id);
    return { success: true };
  });

  ipcMain.handle('db:logs:getAll', async (_event, filters) => {
    let query = 'SELECT * FROM logs WHERE 1=1';
    const params: any[] = [];

    if (filters?.room_number) {
      query += ' AND room_number = ?';
      params.push(filters.room_number);
    }

    if (filters?.start_date) {
      query += ' AND timestamp >= ?';
      params.push(filters.start_date);
    }

    if (filters?.end_date) {
      query += ' AND timestamp <= ?';
      params.push(filters.end_date);
    }

    if (filters?.event_type) {
      query += ' AND event_type = ?';
      params.push(filters.event_type);
    }

    query += ' ORDER BY timestamp DESC';

    if (filters?.limit) {
      query += ' LIMIT ?';
      params.push(filters.limit);
    }

    const stmt = db.prepare(query);
    return stmt.all(...params);
  });

  // Settings handlers
  ipcMain.handle('settings:get', async (_event, key: string) => {
    const stmt = db.prepare('SELECT value FROM settings WHERE key = ?');
    const result = stmt.get(key) as { value: string } | undefined;
    return result?.value || null;
  });

  ipcMain.handle('settings:set', async (_event, key: string, value: string) => {
    const stmt = db.prepare(`
      INSERT INTO settings (key, value, updated_at) 
      VALUES (?, ?, CURRENT_TIMESTAMP)
      ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = CURRENT_TIMESTAMP
    `);
    stmt.run(key, value, value);
    return { success: true };
  });

  // Utils handlers
  ipcMain.handle('utils:generatePin', async () => {
    return generateUniquePin();
  });

  ipcMain.handle('utils:checkPinCollision', async (_event, pin: string) => {
    return checkPinCollision(pin);
  });

  console.log('✅ Database handlers registered');
}
