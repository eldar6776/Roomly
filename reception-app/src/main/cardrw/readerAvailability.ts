import { spawn } from 'child_process';
import * as path from 'path';
import { app } from 'electron';

export interface CardWriterPayload {
  room_number: string;
  check_out_date: string;
  check_out_time: string;
  sys_id: number;
  first_name: string;
  last_name: string;
  gender: 'M' | 'Z';
  language: 'srb' | 'eng' | 'ger';
}

export interface StaffCardPayload {
  card_type: 'H' | 'M';
  check_out_date: string;
  check_out_time: string;
  sys_id: number;
}

export interface CardReaderAvailability {
  available: boolean;
  message: string;
}

interface BridgeResponse {
  ok: boolean;
  message: string;
  available?: boolean;
  room_number?: string;
  valid_until?: string;
  sys_id?: number;
  card_type?: string;
}

function resolveBridgeScriptPath(): string {
  // Kada je aplikacija zapakovana (.exe), resursi se nalaze u 'resources' folderu
  const baseDir = app.isPackaged 
    ? path.join(process.resourcesPath, 'cardrw') 
    : path.join(process.cwd(), 'cardrw');
    
  return path.join(baseDir, 'cardrw_bridge.py');
}

function runBridgeCommand(command: string, action: string, payload?: unknown): Promise<BridgeResponse> {
  return new Promise((resolve, reject) => {
    const scriptPath = resolveBridgeScriptPath();
    const args = command === 'py' ? ['-3', scriptPath, action] : [scriptPath, action];

    const child = spawn(command, args, {
      windowsHide: true,
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    let stdout = '';
    let stderr = '';

    const timeout = setTimeout(() => {
      child.kill();
      reject(new Error('Card reader check timeout'));
    }, 5000);

    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString();
    });

    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });

    if (payload) {
      child.stdin.write(JSON.stringify(payload));
    }
    child.stdin.end();

    child.on('error', (error) => {
      clearTimeout(timeout);
      reject(error);
    });

    child.on('close', () => {
      clearTimeout(timeout);

      const output = stdout.trim();
      if (!output) {
        resolve({
          ok: false,
          message: stderr.trim() || 'No response from probe script',
        });
        return;
      }

      try {
        const parsed = JSON.parse(output) as BridgeResponse;
        resolve(parsed);
      } catch {
        resolve({
          ok: false,
          message: output,
        });
      }
    });
  });
}

export async function checkCardReaderAvailability(): Promise<CardReaderAvailability> {
  const attempts = ['python', 'py'];

  for (const attempt of attempts) {
    try {
      const response = await runBridgeCommand(attempt, 'check');
      return {
        available: Boolean(response.available),
        message: response.message,
      };
    } catch {
      continue;
    }
  }

  return {
    available: false,
    message: 'Python runtime not found (python/py)',
  };
}

export async function writeGuestCard(payload: CardWriterPayload): Promise<BridgeResponse> {
  const attempts = ['python', 'py'];

  for (const attempt of attempts) {
    try {
      return await runBridgeCommand(attempt, 'write_guest', payload);
    } catch {
      continue;
    }
  }

  return {
    ok: false,
    message: 'Python runtime not found (python/py)',
  };
}

export async function writeStaffCard(payload: StaffCardPayload): Promise<BridgeResponse> {
  const attempts = ['python', 'py'];

  for (const attempt of attempts) {
    try {
      return await runBridgeCommand(attempt, 'write_staff', payload);
    } catch {
      continue;
    }
  }

  return {
    ok: false,
    message: 'Python runtime not found (python/py)',
  };
}
