import { app, BrowserWindow, ipcMain } from 'electron';
import * as path from 'path';
import { setupDatabase } from './database';
import { setupApiHandlers } from './api/handlers';
import { setupDatabaseHandlers } from './database/handlers';
import { setupPrinterHandlers } from './printer/handlers';
import { setupPythonHandlers } from './python/handlers';
import { startLogReceiver } from './logReceiver';
import * as dns from 'dns';

// 🔥 GLOBALNO ISKLJUČI IPv6 - koristi SAMO IPv4
dns.setDefaultResultOrder('ipv4first');

let mainWindow: BrowserWindow | null = null;

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 768,
    backgroundColor: '#0a0a0a',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
    autoHideMenuBar: true,
    icon: path.join(__dirname, '../../assets/icon.png'),
  });

  // Load the app
  if (process.env.NODE_ENV === 'development') {
    mainWindow.loadURL('http://localhost:3000');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(async () => {
  // Initialize database
  await setupDatabase();

  // Setup IPC handlers
  setupApiHandlers();
  setupDatabaseHandlers();
  setupPrinterHandlers();
  setupPythonHandlers();

  // Start log receiver server for RPI
  startLogReceiver();

  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// Handle app errors
process.on('uncaughtException', (error) => {
  console.error('Uncaught Exception:', error);
});

process.on('unhandledRejection', (reason, promise) => {
  console.error('Unhandled Rejection at:', promise, 'reason:', reason);
});
