import { ipcMain, app } from 'electron';
import { spawnSync } from 'child_process';
import * as path from 'path';
import { PRINTER_CONFIG } from '../config';
import { getDatabase } from '../database/index';

/**
 * Apsolutna putanja do printer.py.
 * U pakovanoj aplikaciji nalazi se u resources/ folderu (extraResources).
 * U dev modu nalazi se u root folderu projekta.
 */
const PRINTER_SCRIPT = app.isPackaged
  ? path.join(process.resourcesPath, 'printer.py')
  : path.join(__dirname, '../../printer.py');

/**
 * Poziva printer.py sinhronim spawnom.
 * Vraća { success, stdout, stderr }.
 */
function callPrinterScript(args: string[]): { success: boolean; stdout: string; stderr: string } {
  const result = spawnSync('python', [PRINTER_SCRIPT, ...args], {
    encoding: 'utf-8',
    timeout: 15000, // 15s max za print job
  });
  const stdout = result.stdout?.toString() ?? '';
  const stderr = result.stderr?.toString() ?? '';
  const success = result.status === 0 && !stderr.includes('[GRESKA]');
  return { success, stdout, stderr };
}

export function setupPrinterHandlers(): void {
  /**
   * printer:checkStatus
   * Pita Windows spooler da li printer iz .env postoji i nije Offline.
   * Renderer koristi ovo za show/hide checkboxa i ikonice na kartici.
   */
  ipcMain.handle('printer:checkStatus', async () => {
    try {
      const ps = spawnSync(
        'powershell',
        [
          '-NonInteractive', '-NoProfile', '-Command',
          `(Get-Printer -Name '${PRINTER_CONFIG.name}' -ErrorAction Stop).PrinterStatus`,
        ],
        { encoding: 'utf-8', timeout: 5000 }
      );
      if (ps.status !== 0) return { available: false };
      const status = ps.stdout?.trim().toLowerCase();
      // PrinterStatus: Normal=3, Idle=3, Printing=4 — sve osim 'error','offline' je dostupno
      const available = Boolean(status) && !status.includes('error') && !status.includes('offline') && status !== '';
      return { available };
    } catch (e) {
      console.error('[printer:checkStatus]', e);
      return { available: false };
    }
  });

  /**
   * printer:print
   * Poziva se automatski nakon uspješnog check-in.
   * data: { roomNumber, pin, checkoutDate, language }
   */
  ipcMain.handle('printer:print', async (_event, data) => {
    const { roomNumber, pin, checkoutDate, language = 'srb' } = data?.data ?? data ?? {};
    if (!roomNumber || !pin || !checkoutDate) {
      console.error('[printer:print] Nedostaju obavezni podaci:', data);
      return { success: false, error: 'Nedostaju obavezni podaci (roomNumber, pin, checkoutDate)' };
    }
    const args = [
      '--soba',   String(roomNumber),
      '--pin',    String(pin),
      '--istice', String(checkoutDate),
      '--lang',   String(language),
    ];
    console.log('[printer:print] Pozivam script:', args.join(' '));
    const result = callPrinterScript(args);
    if (!result.success) {
      console.error('[printer:print] GREŠKA:', result.stderr);
    } else {
      console.log('[printer:print] OK:', result.stdout.trim());
    }
    return { success: result.success, stderr: result.stderr };
  });

  /**
   * printer:reprint
   * Poziva se s RoomCard ikonице za re-štampanje slipa zauzete sobe.
   * Jezik se automatski čita iz lokalne DB (guests tabela).
   * data: { roomNumber, pin, checkoutDate }
   */
  ipcMain.handle('printer:reprint', async (_event, data) => {
    const { roomNumber, pin, checkoutDate } = data ?? {};
    if (!roomNumber || !pin) {
      return { success: false, error: 'Nedostaju roomNumber ili pin' };
    }
    // Pokušaj da učitamo jezik iz lokalne baze
    let language = 'srb';
    try {
      const db = getDatabase();
      const guest = db.prepare(
        "SELECT language FROM guests WHERE room_number = ? AND status = 'ACTIVE' ORDER BY created_at DESC LIMIT 1"
      ).get(roomNumber) as any;
      if (guest?.language) language = guest.language;
    } catch (e) {
      console.warn('[printer:reprint] Ne mogu pročitati jezik iz DB:', e);
    }
    const args = [
      '--soba',   String(roomNumber),
      '--pin',    String(pin),
      '--istice', String(checkoutDate ?? ''),
      '--lang',   language,
    ];
    console.log('[printer:reprint] Pozivam script:', args.join(' '));
    const result = callPrinterScript(args);
    return { success: result.success, stderr: result.stderr };
  });

  /**
   * printer:test
   * Test štampa — šalje testni slip sa fiksnim podacima.
   */
  ipcMain.handle('printer:test', async () => {
    const args = [
      '--soba',   'TEST',
      '--pin',    '0000',
      '--istice', 'TEST PRINT',
      '--lang',   'srb',
    ];
    const result = callPrinterScript(args);
    return { success: result.success, stderr: result.stderr };
  });

  console.log('✅ Printer handlers registered | script:', PRINTER_SCRIPT);
}
