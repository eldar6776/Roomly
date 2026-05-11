/**
 * Centralna konfiguracija aplikacije
 * SVE konfiguracione vrednosti su ovde na JEDNOM mestu
 */

// Učitaj .env fajl ako postoji
import * as path from 'path';
import * as fs from 'fs';
import { app } from 'electron';

// Jednostavno učitavanje .env fajla
function loadEnvFile(): void {
  // U pakovanoj aplikaciji .env je u resources/ folderu (extraResources)
  // U dev modu .env je u root folderu projekta (../../ od dist/main/)
  const envPath = app.isPackaged
    ? path.join(process.resourcesPath, '.env')
    : path.join(__dirname, '../../.env');
  if (fs.existsSync(envPath)) {
    const envContent = fs.readFileSync(envPath, 'utf-8');
    envContent.split('\n').forEach(line => {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) return;
      
      const [key, ...valueParts] = trimmed.split('=');
      if (key && valueParts.length > 0) {
        const value = valueParts.join('=').trim();
        process.env[key.trim()] = value;
      }
    });
  }
}

// Učitaj .env odmah
loadEnvFile();

/**
 * Helper funkcija za obavezne environment varijable
 */
function getRequiredEnv(key: string, defaultValue?: string): string {
  const value = process.env[key];
  if (!value && !defaultValue) {
    throw new Error(`KONFIGURACIJA GREŠKA: ${key} nije postavljen u .env fajlu!`);
  }
  return value || defaultValue!;
}

/**
 * RPI Server konfiguracija
 * NAPOMENA: Sve vrijednosti se MORAJU učitati iz .env fajla
 */
export const RPI_CONFIG = {
  host: getRequiredEnv('RPI_HOST', 'localhost'),
  port: getRequiredEnv('RPI_PORT', '5000'),
  apiKey: getRequiredEnv('RPI_API_KEY'),
  timeout: parseInt(process.env.RPI_TIMEOUT_MS || '10000'),
  
  get baseURL(): string {
    return `http://${this.host}:${this.port}`;
  }
};

/**
 * Default PIN kodovi
 * NAPOMENA: Čitaju se iz .env fajla
 */
export const DEFAULT_PINS = {
  reception: getRequiredEnv('DEFAULT_RECEPTION_PIN', '1234'),
  manager: getRequiredEnv('DEFAULT_MANAGER_PIN', '0000'),
  // Maid i Service PIN-ove APP dobija od RPI-a, ne koristi lokalne defaulte
  maid: null,
  service: null,
};

/**
 * Default hotel podešavanja
 * NAPOMENA: Čitaju se iz .env fajla
 */
export const DEFAULT_SETTINGS = {
  checkoutTime: getRequiredEnv('DEFAULT_CHECKOUT_TIME', '12:00'),
  guestInTemp: parseInt(process.env.DEFAULT_TEMP_DAY || '22'),
  guestOutTemp: parseInt(process.env.DEFAULT_TEMP_NIGHT || '18'),
  language: getRequiredEnv('DEFAULT_LANGUAGE', 'srb'),
};

/**
 * Hotel konfiguracija
 * NAPOMENA: Čitaju se iz .env fajla
 */
export const HOTEL_CONFIG = {
  name1: getRequiredEnv('HOTEL_NAME_1', 'Toplik'),
  name2: getRequiredEnv('HOTEL_NAME_2', 'Village Resort'),
  wifiSsid: getRequiredEnv('WIFI_SSID', 'Toplik'),
  get qrUrl(): string {
    return `http://${RPI_CONFIG.host}:${RPI_CONFIG.port}`;
  },
};

/**
 * Printer konfiguracija
 * NAPOMENA: Čitaju se iz .env fajla
 */
export const PRINTER_CONFIG = {
  name: getRequiredEnv('PRINTER_NAME', 'TM-T20II'),
  type: getRequiredEnv('PRINTER_TYPE', 'ESC/POS'),
};

/**
 * MIFARE Card Writer konfiguracija
 */
export const CARD_WRITER_CONFIG = {
  sysId: parseInt(getRequiredEnv('SYSID', '42444'), 10),
};

/**
 * ntfy.sh konfiguracija za SOS alerts
 * NAPOMENA: Čitaju se iz .env fajla
 */
export const NTFY_CONFIG = {
  topic: getRequiredEnv('NTFY_TOPIC', 'toplik_smart_hotel_sos'),
  baseURL: getRequiredEnv('NTFY_BASE_URL', 'https://ntfy.sh'),
};

/**
 * Aplikacione konstante
 * NAPOMENA: Čitaju se iz .env fajla
 */
export const APP_CONFIG = {
  name: getRequiredEnv('APP_NAME', 'Toplik Smart Reception'),
  version: getRequiredEnv('APP_VERSION', '1.0.0'),
  author: getRequiredEnv('APP_AUTHOR', 'Toplik Smart Hotel'),
  windowWidth: parseInt(process.env.APP_WINDOW_WIDTH || '1280'),
  windowHeight: parseInt(process.env.APP_WINDOW_HEIGHT || '800'),
  minWidth: parseInt(process.env.APP_MIN_WIDTH || '1024'),
  minHeight: parseInt(process.env.APP_MIN_HEIGHT || '768'),
};

/**
 * Lokalna IP adresa za Log Transfer registraciju
 * NAPOMENA: Opciono - ako nije postavljeno, koristi se automatska detekcija
 */
export const LOCAL_IP = process.env.LOCAL_IP || undefined;

/**
 * Export svih vrednosti za lak pristup
 */
export default {
  RPI_CONFIG,
  DEFAULT_PINS,
  DEFAULT_SETTINGS,
  HOTEL_CONFIG,
  PRINTER_CONFIG,
  CARD_WRITER_CONFIG,
  NTFY_CONFIG,
  APP_CONFIG,
  LOCAL_IP,
};
