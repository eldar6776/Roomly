import { contextBridge, ipcRenderer } from 'electron';

// API Interface za renderer process
const api = {
  // Room API
  rooms: {
    getAll: () => ipcRenderer.invoke('rooms:getAll'),
    rediscover: () => ipcRenderer.invoke('rooms:rediscover'),
    setPin: (roomNumber: string, data: any) => 
      ipcRenderer.invoke('rooms:setPin', roomNumber, data),
    deletePin: (roomNumber: string) => 
      ipcRenderer.invoke('rooms:deletePin', roomNumber),
    setTemperature: (roomNumber: string, setpoint: number) =>
      ipcRenderer.invoke('rooms:setTemperature', roomNumber, setpoint),
    setGuestTemps: (roomNumber: string, data: any) =>
      ipcRenderer.invoke('rooms:setGuestTemps', roomNumber, data),
    controlThermostat: (roomNumber: string, action: string) =>
      ipcRenderer.invoke('rooms:controlThermostat', roomNumber, action),
    setLanguage: (roomNumber: string, language: string) =>
      ipcRenderer.invoke('rooms:setLanguage', roomNumber, language),
    resetSos: (roomNumber: string) =>
      ipcRenderer.invoke('rooms:resetSos', roomNumber),
  },

  // Logs API
  logs: {
    getAll: (filters?: any) => ipcRenderer.invoke('logs:getAll', filters),
  },

  // Settings API
  settings: {
    get: (key: string) => ipcRenderer.invoke('settings:get', key),
    set: (key: string, value: string) => ipcRenderer.invoke('settings:set', key, value),
    getStaffPins: () => ipcRenderer.invoke('settings:getStaffPins'),
    changeReceptionPin: (oldPin: string, newPin: string) =>
      ipcRenderer.invoke('settings:changeReceptionPin', oldPin, newPin),
    changeManagerPin: (oldPin: string, newPin: string) =>
      ipcRenderer.invoke('settings:changeManagerPin', oldPin, newPin),
    changeMaidPin: (oldPin: string, newPin: string) =>
      ipcRenderer.invoke('settings:changeMaidPin', oldPin, newPin),
    changeServicePin: (oldPin: string, newPin: string) =>
      ipcRenderer.invoke('settings:changeServicePin', oldPin, newPin),
  },

  // Database API
  database: {
    guests: {
      create: (data: any) => ipcRenderer.invoke('db:guests:create', data),
      getAll: () => ipcRenderer.invoke('db:guests:getAll'),
      getActive: () => ipcRenderer.invoke('db:guests:getActive'),
      update: (id: number, data: any) => ipcRenderer.invoke('db:guests:update', id, data),
      checkOut: (roomNumber: string) => ipcRenderer.invoke('db:guests:checkOut', roomNumber),
    },
    logs: {
      create: (data: any) => ipcRenderer.invoke('db:logs:create', data),
      getAll: (filters?: any) => ipcRenderer.invoke('db:logs:getAll', filters),
    },
    systemLogs: {
      create: (data: any) => ipcRenderer.invoke('db:systemLogs:create', data),
      getAll: (filters?: any) => ipcRenderer.invoke('db:systemLogs:getAll', filters),
    },
    accessLogs: {
      create: (data: any) => ipcRenderer.invoke('db:accessLogs:create', data),
      getAll: (filters?: any) => ipcRenderer.invoke('db:accessLogs:getAll', filters),
    },
    errorLogs: {
      create: (data: any) => ipcRenderer.invoke('db:errorLogs:create', data),
      getAll: (filters?: any) => ipcRenderer.invoke('db:errorLogs:getAll', filters),
      resolve: (id: number) => ipcRenderer.invoke('db:errorLogs:resolve', id),
    },
  },

  // Printer API
  printer: {
    checkStatus: () => ipcRenderer.invoke('printer:checkStatus'),
    print: (data: any) => ipcRenderer.invoke('printer:print', data),
    reprint: (data: { roomNumber: string; pin: string; checkoutDate: string; language?: string }) =>
      ipcRenderer.invoke('printer:reprint', data),
    test: () => ipcRenderer.invoke('printer:test'),
  },

  // Utility
  utils: {
    generatePin: () => ipcRenderer.invoke('utils:generatePin'),
    checkPinCollision: (pin: string) => ipcRenderer.invoke('utils:checkPinCollision', pin),
  },

  // Card reader API
  cards: {
    checkAvailability: () => ipcRenderer.invoke('cards:checkAvailability'),
    writeGuestCard: (data: {
      roomNumber: string;
      checkOutDate: string;
      checkOutTime: string;
      language?: 'srb' | 'eng' | 'ger';
    }) => ipcRenderer.invoke('cards:writeGuestCard', data),
    writeStaffCard: (data: {
      cardType: 'H' | 'M';
      checkOutDate: string;
      checkOutTime?: string;
    }) => ipcRenderer.invoke('cards:writeStaffCard', data),
  },

  // SOS Listener
  sos: {
    onAlert: (callback: (alert: any) => void) => {
      ipcRenderer.on('sos:alert', (_event, alert) => callback(alert));
    },
    removeListener: () => {
      ipcRenderer.removeAllListeners('sos:alert');
    },
  },

  // Python / dependency check
  python: {
    checkAndInstall: () => ipcRenderer.invoke('python:checkAndInstall'),
    openDownload: () => ipcRenderer.invoke('python:openDownload'),
  },
};

// Expose protected methods that allow the renderer process to use ipcRenderer
contextBridge.exposeInMainWorld('electronAPI', api);

// TypeScript declaration
declare global {
  interface Window {
    electronAPI: typeof api;
  }
}
