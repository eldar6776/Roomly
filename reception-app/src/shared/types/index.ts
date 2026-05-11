// Room Types
export interface Room {
  room_number: string;
  name: string;
  online: boolean;
  current_temp: number | null;
  setpoint_temp: number | null;
  card_inserted: boolean;
  active_pin: string;
  guest_pin: string;
  pin_expiry: string | null;
  guest_in_temp: number | null;
  guest_out_temp: number | null;
  thermostat_mode: string | null;
  thermostat_on: boolean;
  target_temp: number | null;
  occupied: boolean;
  last_seen?: string | null;
  sos_active: boolean;
  sos_timestamp: string | null;
}

export type RoomStatus = 'online' | 'occupied' | 'offline' | 'checked-in';

// Guest Types
export interface Guest {
  id: number;
  room_number: string;
  check_in_date: string;
  check_out_date: string;
  check_out_time: string;
  language: 'srb' | 'eng' | 'ger';
  status: 'ACTIVE' | 'CHECKED_OUT';
  created_at: string;
  updated_at: string;
}

// Log Types
export interface Log {
  id: number;
  timestamp: string;
  room_number: string;
  device_id: number;
  event_code: string;
  event_type: string;
  description: string;
  card_id: string | null;
  created_at: string;
}

export type EventType = 
  | 'GUEST_CARD' 
  | 'GUEST_OUT' 
  | 'MAID_CARD' 
  | 'SERVICE_CARD' 
  | 'SOS' 
  | 'DOOR_OPEN';

// Settings Types
export interface Settings {
  reception_pin: string;
  manager_pin: string;
  maid_pin: string;
  service_pin: string;
  checkout_time: string;
  guest_in_temp: number;
  guest_out_temp: number;
  default_language: 'srb' | 'eng' | 'ger';
}

// API Types
export interface ApiResponse<T = any> {
  status: 'success' | 'error' | 'partial';
  message: string;
  data?: T;
}

export interface SetPinRequest {
  pin: string;
  expiry_date: string;
  expiry_time: string;
  language: 'srb' | 'eng' | 'ger';
  day_temp?: number;
  night_temp?: number;
}

export interface SetPinResponse {
  room_number: string;
  pin: string;
  expiry: string;
  verified: boolean;
}

export interface SetTemperatureRequest {
  setpoint: number;
}

export interface SetGuestTempsRequest {
  guest_in_temp: number;
  guest_out_temp: number;
}

export interface ThermostatRequest {
  action: 'on' | 'off' | 'heating' | 'cooling';
}

export interface ChangePinRequest {
  old_pin: string;
  new_pin: string;
}

export interface GlobalPinUpdateResponse {
  updated: number;
  failed: number;
  total: number;
}

// SOS Alert Type
export interface SOSAlert {
  room_number: string;
  timestamp: string;
  title: string;
  message: string;
}
