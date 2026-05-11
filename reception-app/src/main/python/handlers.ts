import { ipcMain, shell } from 'electron';
import { spawnSync } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';
import { app } from 'electron';

function getPythonCmd(): string | null {
  for (const cmd of ['python', 'py']) {
    const r = spawnSync(cmd, ['--version'], { encoding: 'utf-8', timeout: 5000 });
    if (r.status === 0) return cmd;
  }
  return null;
}

function getRequirementsPath(): string {
  return app.isPackaged
    ? path.join(process.resourcesPath, 'requirements.txt')
    : path.join(process.cwd(), 'requirements.txt');
}

export function setupPythonHandlers(): void {
  /**
   * python:checkAndInstall
   * 1. Provjeri je li Python instaliran.
   * 2. Ako jest, pokušaj instalirati sve iz requirements.txt.
   * Vraća: { pythonFound, pythonVersion, pipOk, pipOutput }
   */
  ipcMain.handle('python:checkAndInstall', async () => {
    const cmd = getPythonCmd();

    if (!cmd) {
      return { pythonFound: false, pythonVersion: null, pipOk: false, pipOutput: '' };
    }

    // Dohvati verziju
    const verResult = spawnSync(cmd, ['--version'], { encoding: 'utf-8', timeout: 5000 });
    const pythonVersion = (verResult.stdout || verResult.stderr || '').trim();

    // Provjeri postoji li requirements.txt
    const reqPath = getRequirementsPath();
    if (!fs.existsSync(reqPath)) {
      return { pythonFound: true, pythonVersion, pipOk: false, pipOutput: `requirements.txt not found at: ${reqPath}` };
    }

    // Instaliraj što nedostaje
    const pipResult = spawnSync(
      cmd,
      ['-m', 'pip', 'install', '--quiet', '-r', reqPath],
      { encoding: 'utf-8', timeout: 60000 }
    );

    const pipOutput = ((pipResult.stdout || '') + (pipResult.stderr || '')).trim();
    const pipOk = pipResult.status === 0;

    return { pythonFound: true, pythonVersion, pipOk, pipOutput };
  });

  /**
   * python:openDownload — otvara browser sa stranicom za download Pythona
   */
  ipcMain.handle('python:openDownload', async () => {
    await shell.openExternal('https://www.python.org/downloads/windows/');
  });
}
