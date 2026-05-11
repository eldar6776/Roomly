import axios, { AxiosInstance, AxiosError } from 'axios';
import http from 'http';
import type { 
  Room, 
  ApiResponse, 
  SetPinRequest, 
  SetPinResponse,
  SetTemperatureRequest,
  SetGuestTempsRequest,
  ThermostatRequest,
  ChangePinRequest,
  GlobalPinUpdateResponse,
  Log
} from '@shared/types';
import { RPI_CONFIG } from '../config';

class RPIClient {
  private client: AxiosInstance;
  private baseURL: string;
  private apiKey: string;

  constructor() {
    // Load from central config
    this.baseURL = RPI_CONFIG.baseURL;
    this.apiKey = RPI_CONFIG.apiKey;

    // HTTP Agent sa SAMO IPv4 podrškom
    const httpAgent = new http.Agent({
      family: 4  // 🔥 FORSIRA IPv4, ISKLJUČUJE IPv6
    });

    this.client = axios.create({
      baseURL: this.baseURL,
      timeout: RPI_CONFIG.timeout,
      httpAgent: httpAgent,  // Koristi IPv4-only agent
      headers: {
        'X-API-Key': this.apiKey,  // OBAVEZNO za /api/rooms/* i /api/settings/* rute
        'Content-Type': 'application/json',
      },
    });

    // Add response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        console.error('RPI API Error:', error.message);
        throw error;
      }
    );
  }

  // Room Endpoints
  async getRooms(): Promise<Room[]> {
    const response = await this.client.get<ApiResponse<{ rooms: Room[] }>>('/api/rooms');
    return response.data.data?.rooms || [];
  }

  async rediscover(): Promise<{ triggered: number; already_resolving: number; rooms: string[] }> {
    const response = await this.client.post<ApiResponse<{ triggered: number; already_resolving: number; rooms: string[] }>>(
      '/api/rooms/rediscover'
    );
    return response.data.data || { triggered: 0, already_resolving: 0, rooms: [] };
  }

  async setPin(roomNumber: string, data: SetPinRequest): Promise<SetPinResponse> {
    const response = await this.client.post<ApiResponse>(
      `/api/rooms/${roomNumber}/set_pin`,
      {
        pin: data.pin,
        expiry_date: data.expiry_date,
        expiry_time: data.expiry_time,
        language: data.language || 'srb',
        day_temp: data.day_temp || 22,
        night_temp: data.night_temp || 18,
      }
    );
    if (response.data.status !== 'success') {
      throw new Error(response.data.message);
    }
    return {
      room_number: roomNumber,
      pin: data.pin,
      expiry: `${data.expiry_date} ${data.expiry_time}`,
      verified: true,
    };
  }

  async deletePin(roomNumber: string): Promise<void> {
    const response = await this.client.post<ApiResponse>(
      `/api/rooms/${roomNumber}/delete_pin`
    );
    if (response.data.status !== 'success') {
      throw new Error(response.data.message);
    }
  }

  async setTemperature(roomNumber: string, setpoint: number): Promise<void> {
    const response = await this.client.post<ApiResponse>(
      `/api/rooms/${roomNumber}/set_temperature`,
      { setpoint } as SetTemperatureRequest
    );
    if (response.data.status !== 'success') {
      throw new Error(response.data.message);
    }
  }

  async setGuestTemps(roomNumber: string, data: SetGuestTempsRequest): Promise<void> {
    const response = await this.client.post<ApiResponse>(
      `/api/rooms/${roomNumber}/set_guest_temps`,
      data
    );
    if (response.data.status !== 'success') {
      throw new Error(response.data.message);
    }
  }

  async controlThermostat(roomNumber: string, action: 'on' | 'off' | 'heating' | 'cooling'): Promise<void> {
    const response = await this.client.post<ApiResponse>(
      `/api/rooms/${roomNumber}/thermostat`,
      { action } as ThermostatRequest
    );
    if (response.data.status !== 'success') {
      throw new Error(response.data.message);
    }
  }

  async setLanguage(roomNumber: string, language: string): Promise<void> {
    const response = await this.client.post<ApiResponse>(
      `/api/rooms/${roomNumber}/set_language`,
      { language }
    );
    if (response.data.status !== 'success') {
      throw new Error(response.data.message);
    }
  }

  async resetSos(roomNumber: string): Promise<void> {
    const response = await this.client.post<ApiResponse>(
      `/api/rooms/${roomNumber}/sos_reset`
    );
    if (response.data.status !== 'success') {
      throw new Error(response.data.message);
    }
  }

  // Logs
  async getLogs(filters?: {
    room_number?: string;
    start_date?: string;
    end_date?: string;
    event_type?: string;
    limit?: number;
    offset?: number;
  }): Promise<{ logs: Log[]; total: number }> {
    const response = await this.client.get<ApiResponse<{ logs: Log[]; total: number }>>(
      '/api/logs',
      { params: filters }
    );
    return response.data.data || { logs: [], total: 0 };
  }

  // Settings
  async getStaffPins(): Promise<{ maid: string; service: string; reception: string; manager: string }> {
    const response = await this.client.get<ApiResponse<{ maid: string; service: string; reception: string; manager: string }>>(
      '/api/settings/staff_pins'
    );
    if (response.data.status !== 'success') {
      throw new Error(response.data.message);
    }
    return response.data.data!;
  }

  async changeReceptionPin(oldPin: string, newPin: string): Promise<void> {
    const response = await this.client.post<ApiResponse>(
      '/api/settings/reception_pin',
      { old_pin: oldPin, new_pin: newPin } as ChangePinRequest
    );
    if (response.data.status !== 'success') {
      throw new Error(response.data.message);
    }
  }

  async changeManagerPin(oldPin: string, newPin: string): Promise<GlobalPinUpdateResponse> {
    const response = await this.client.post<ApiResponse<GlobalPinUpdateResponse>>(
      '/api/settings/manager_pin',
      { old_pin: oldPin, new_pin: newPin } as ChangePinRequest
    );
    if (response.data.status === 'error') {
      throw new Error(response.data.message);
    }
    return response.data.data!;
  }

  async changeMaidPin(oldPin: string, newPin: string): Promise<GlobalPinUpdateResponse> {
    const response = await this.client.post<ApiResponse<GlobalPinUpdateResponse>>(
      '/api/settings/maid_pin',
      { old_pin: oldPin, new_pin: newPin } as ChangePinRequest
    );
    if (response.data.status === 'error') {
      throw new Error(response.data.message);
    }
    return response.data.data!;
  }

  async changeServicePin(oldPin: string, newPin: string): Promise<GlobalPinUpdateResponse> {
    const response = await this.client.post<ApiResponse<GlobalPinUpdateResponse>>(
      '/api/settings/service_pin',
      { old_pin: oldPin, new_pin: newPin } as ChangePinRequest
    );
    if (response.data.status === 'error') {
      throw new Error(response.data.message);
    }
    return response.data.data!;
  }

  // Health Check
  async checkHealth(): Promise<boolean> {
    try {
      const response = await this.client.get<ApiResponse>('/api/health');
      return response.data.status === 'success';
    } catch {
      return false;
    }
  }
}

// Singleton instance
export const rpiClient = new RPIClient();
