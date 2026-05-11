import { ipcMain } from 'electron';
import { rpiClient } from './rpiClient';
import { checkCardReaderAvailability, writeGuestCard, writeStaffCard } from '../cardrw/readerAvailability';
import { CARD_WRITER_CONFIG } from '../config';

export function setupApiHandlers(): void {
  // Room handlers
  ipcMain.handle('rooms:getAll', async () => {
    try {
      return await rpiClient.getRooms();
    } catch (error: any) {
      console.error('Error getting rooms:', error);
      throw error;
    }
  });

  ipcMain.handle('rooms:rediscover', async () => {
    try {
      return await rpiClient.rediscover();
    } catch (error: any) {
      console.error('Error triggering rediscover:', error);
      throw error;
    }
  });

  ipcMain.handle('rooms:setPin', async (_event, roomNumber: string, data: any) => {
    try {
      return await rpiClient.setPin(roomNumber, data);
    } catch (error: any) {
      console.error('Error setting PIN:', error);
      throw error;
    }
  });

  ipcMain.handle('rooms:deletePin', async (_event, roomNumber: string) => {
    try {
      return await rpiClient.deletePin(roomNumber);
    } catch (error: any) {
      console.error('Error deleting PIN:', error);
      throw error;
    }
  });

  ipcMain.handle('rooms:setTemperature', async (_event, roomNumber: string, setpoint: number) => {
    try {
      return await rpiClient.setTemperature(roomNumber, setpoint);
    } catch (error: any) {
      console.error('Error setting temperature:', error);
      throw error;
    }
  });

  ipcMain.handle('rooms:setGuestTemps', async (_event, roomNumber: string, data: any) => {
    try {
      return await rpiClient.setGuestTemps(roomNumber, data);
    } catch (error: any) {
      console.error('Error setting guest temps:', error);
      throw error;
    }
  });

  ipcMain.handle('rooms:controlThermostat', async (_event, roomNumber: string, action: string) => {
    try {
      return await rpiClient.controlThermostat(roomNumber, action as any);
    } catch (error: any) {
      console.error('Error controlling thermostat:', error);
      throw error;
    }
  });

  ipcMain.handle('rooms:setLanguage', async (_event, roomNumber: string, language: string) => {
    try {
      return await rpiClient.setLanguage(roomNumber, language);
    } catch (error: any) {
      console.error('Error setting language:', error);
      throw error;
    }
  });

  ipcMain.handle('rooms:resetSos', async (_event, roomNumber: string) => {
    try {
      return await rpiClient.resetSos(roomNumber);
    } catch (error: any) {
      console.error('Error resetting SOS:', error);
      throw error;
    }
  });

  ipcMain.handle('cards:checkAvailability', async () => {
    try {
      return await checkCardReaderAvailability();
    } catch (error: any) {
      console.error('Error checking card reader:', error);
      return {
        available: false,
        message: error?.message || 'Card reader check failed',
      };
    }
  });

  ipcMain.handle('cards:writeGuestCard', async (_event, data: {
    roomNumber: string;
    checkOutDate: string;
    checkOutTime: string;
    language?: 'srb' | 'eng' | 'ger';
  }) => {
    try {
      const result = await writeGuestCard({
        room_number: data.roomNumber,
        check_out_date: data.checkOutDate,
        check_out_time: data.checkOutTime,
        sys_id: CARD_WRITER_CONFIG.sysId,
        first_name: '',
        last_name: '',
        gender: 'M',
        language: data.language || 'srb',
      });

      return result;
    } catch (error: any) {
      console.error('Error writing guest card:', error);
      return {
        ok: false,
        message: error?.message || 'Card writing failed',
      };
    }
  });

  ipcMain.handle('cards:writeStaffCard', async (_event, data: {
    cardType: 'H' | 'M';
    checkOutDate: string;
    checkOutTime?: string;
  }) => {
    try {
      const result = await writeStaffCard({
        card_type: data.cardType,
        check_out_date: data.checkOutDate,
        check_out_time: data.checkOutTime || '23:59',
        sys_id: CARD_WRITER_CONFIG.sysId,
      });

      return result;
    } catch (error: any) {
      console.error('Error writing staff card:', error);
      return {
        ok: false,
        message: error?.message || 'Staff card writing failed',
      };
    }
  });

  // Logs handlers
  ipcMain.handle('logs:getAll', async (_event, filters?: any) => {
    try {
      return await rpiClient.getLogs(filters);
    } catch (error: any) {
      console.error('Error getting logs:', error);
      throw error;
    }
  });

  // Settings handlers
  ipcMain.handle('settings:getStaffPins', async () => {
    try {
      return await rpiClient.getStaffPins();
    } catch (error: any) {
      console.error('Error getting staff PINs:', error);
      throw error;
    }
  });

  ipcMain.handle('settings:changeReceptionPin', async (_event, oldPin: string, newPin: string) => {
    try {
      return await rpiClient.changeReceptionPin(oldPin, newPin);
    } catch (error: any) {
      console.error('Error changing reception PIN:', error);
      throw error;
    }
  });

  ipcMain.handle('settings:changeManagerPin', async (_event, oldPin: string, newPin: string) => {
    try {
      return await rpiClient.changeManagerPin(oldPin, newPin);
    } catch (error: any) {
      console.error('Error changing manager PIN:', error);
      throw error;
    }
  });

  ipcMain.handle('settings:changeMaidPin', async (_event, oldPin: string, newPin: string) => {
    try {
      return await rpiClient.changeMaidPin(oldPin, newPin);
    } catch (error: any) {
      console.error('Error changing maid PIN:', error);
      throw error;
    }
  });

  ipcMain.handle('settings:changeServicePin', async (_event, oldPin: string, newPin: string) => {
    try {
      return await rpiClient.changeServicePin(oldPin, newPin);
    } catch (error: any) {
      console.error('Error changing service PIN:', error);
      throw error;
    }
  });

  console.log('✅ API handlers registered');
}
