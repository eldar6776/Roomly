#!/usr/bin/env python3
"""
Toplik Smart Hotel - Termalni printer slip
Koristi Windows spooler (win32print) s ESC/POS komandama.

Dinamički prima podatke o sobi via CLI argumenti.
Statičku konfiguraciju (hotel, WiFi, printer, RPI) čita iz .env fajla.

Upotreba:
  python printer.py --soba 505 --pin 4210 --istice "2026-03-04 13:00" --lang srb

Dostupni jezici: srb (default) | eng | ger

Instalacija: pip install pywin32
"""

import argparse
import os
import sys
import win32print

# ── Čitanje .env fajla ────────────────────────────────────────────────────────
def _load_env() -> dict:
    """Čita .env fajl pored printer.py i vraća dict s varijablama."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    result = {}
    if not os.path.exists(env_path):
        return result
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, _, value = line.partition('=')
                result[key.strip()] = value.strip()
    return result

_ENV = _load_env()

def _env(key: str, default: str = '') -> str:
    return _ENV.get(key, os.environ.get(key, default))

# ── Konfiguracija iz .env ─────────────────────────────────────────────────────
PRINTER_NAME = _env('PRINTER_NAME',  'TM-T20II')
HOTEL_NAME_1 = _env('HOTEL_NAME_1',  'Toplik')
HOTEL_NAME_2 = _env('HOTEL_NAME_2',  'Village Resort')
WIFI_SSID    = _env('WIFI_SSID',     'Toplik')
RPI_HOST     = _env('RPI_HOST',      '192.168.88.70')
RPI_PORT     = _env('RPI_PORT',      '5000')
QR_URL       = f"http://{RPI_HOST}:{RPI_PORT}"

# ── ESC/POS konstante ─────────────────────────────────────────────────────────
ESC = b'\x1b'
GS  = b'\x1d'
LF  = b'\x0a'

INIT         = ESC + b'@'
FEED         = lambda n: ESC + b'd' + bytes([n])
ALIGN_CENTER = ESC + b'a\x01'
BOLD_ON      = ESC + b'E\x01'
BOLD_OFF     = ESC + b'E\x00'
SIZE_NORMAL  = GS  + b'!\x00'
SIZE_2X      = GS  + b'!\x11'

# ── Višejezični tekstovi ──────────────────────────────────────────────────────
TRANSLATIONS = {
    'srb': {
        'room_label':     'SOBA',
        'pin_label':      'PIN:',
        'wifi_title':     'WiFi pristup',
        'wifi_network':   'Mreza:',
        'wifi_open':      '(Otvorena mreza, bez lozinke)',
        'qr_title':       'Smart kontrola sobe',
        'qr_scan':        'Skenirajte za upravljanje:',
        'keep_slip':      'Molimo cuvajte ovaj slip.',
        'pin_needed_1':   'PIN je potreban za pristup',
        'pin_needed_2':   'smart kontroli sobe.',
        'checkout_label': 'Odjava:',
        'farewell':       'Zelimo Vam ugodan boravak!',
    },
    'eng': {
        'room_label':     'ROOM',
        'pin_label':      'PIN:',
        'wifi_title':     'WiFi Access',
        'wifi_network':   'Network:',
        'wifi_open':      '(Open network, no password)',
        'qr_title':       'Smart Room Control',
        'qr_scan':        'Scan to manage your room:',
        'keep_slip':      'Please keep this slip.',
        'pin_needed_1':   'PIN is required to access',
        'pin_needed_2':   'smart room control.',
        'checkout_label': 'Check-out:',
        'farewell':       'We wish you a pleasant stay!',
    },
    'ger': {
        'room_label':     'ZIMMER',
        'pin_label':      'PIN:',
        'wifi_title':     'WLAN-Zugang',
        'wifi_network':   'Netzwerk:',
        'wifi_open':      '(Offenes Netzwerk, kein Passwort)',
        'qr_title':       'Smarte Zimmersteuerung',
        'qr_scan':        'Scannen zum Steuern:',
        'keep_slip':      'Bitte bewahren Sie diesen Slip.',
        'pin_needed_1':   'PIN benoetigt fuer den Zugriff',
        'pin_needed_2':   'auf die Zimmersteuerung.',
        'checkout_label': 'Abreise:',
        'farewell':       'Angenehmen Aufenthalt!',
    },
}

# ── ESC/POS helper funkcije ───────────────────────────────────────────────────
def ln(s: str = "", encoding: str = "cp1250") -> bytes:
    return s.encode(encoding, errors="replace") + LF

def separator(char: str = "-", width: int = 32) -> bytes:
    return ln(char * width)

def qr_block(url: str, dot_size: int = 8) -> bytes:
    """Generiše QR kod direktno na printeru (max dot_size=8 za TM-T20II)."""
    data = url.encode("ascii")
    store_len = len(data) + 3
    pL = store_len & 0xFF
    pH = (store_len >> 8) & 0xFF
    return (
        GS + b'(k\x04\x001\x41\x32\x00'
        + GS + b'(k\x03\x001\x43' + bytes([dot_size])
        + GS + b'(k\x03\x001\x45\x31'
        + GS + b'(k' + bytes([pL, pH]) + b'\x31\x50\x30' + data
        + GS + b'(k\x03\x001\x51\x30'
    )

# ── Gradnja slipa ─────────────────────────────────────────────────────────────
def napravi_slip(soba: str, pin: str, istice: str, lang: str = 'srb') -> bytes:
    t = TRANSLATIONS.get(lang, TRANSLATIONS['srb'])
    buf = bytearray()
    buf += INIT

    # ─ Header: naziv hotela ─
    buf += ALIGN_CENTER + BOLD_ON + SIZE_2X
    buf += ln(HOTEL_NAME_1)
    buf += ln(HOTEL_NAME_2)
    buf += SIZE_NORMAL + BOLD_OFF
    buf += separator("=")

    # ─ Ključni podaci: soba i PIN ─
    buf += ALIGN_CENTER + BOLD_ON + SIZE_2X
    buf += ln(f"{t['room_label']}  {soba}")
    buf += ln("")
    buf += ln(f"{t['pin_label']}  {pin}")
    buf += SIZE_NORMAL + BOLD_OFF
    buf += separator("=")

    # ─ WiFi sekcija ─
    buf += ALIGN_CENTER + BOLD_ON
    buf += ln(t['wifi_title'])
    buf += BOLD_OFF
    buf += ln(f"{t['wifi_network']} {WIFI_SSID}")
    buf += ln(t['wifi_open'])
    buf += separator("-")

    # ─ QR kod sekcija ─
    buf += ALIGN_CENTER + BOLD_ON
    buf += ln(t['qr_title'])
    buf += BOLD_OFF
    buf += ln(t['qr_scan'])
    buf += qr_block(QR_URL, dot_size=8)
    buf += ln(QR_URL)
    buf += separator("-")

    # ─ Footer ─
    buf += ALIGN_CENTER
    buf += ln(t['keep_slip'])
    buf += ln(t['pin_needed_1'])
    buf += ln(t['pin_needed_2'])
    buf += ln("")
    buf += BOLD_ON
    buf += ln(f"{t['checkout_label']} {istice}")
    buf += BOLD_OFF
    buf += ln("")
    buf += ln(t['farewell'])
    buf += separator("=")
    buf += FEED(9)  # izvuci papir za ručno rezanje

    return bytes(buf)

# ── Štampa via Windows spooler (RAW) ─────────────────────────────────────────
def stampa(soba: str, pin: str, istice: str, lang: str = 'srb') -> None:
    try:
        hprinter = win32print.OpenPrinter(PRINTER_NAME)
    except Exception as e:
        print(f"[GRESKA] Printer '{PRINTER_NAME}' nije pronadjen: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        win32print.StartDocPrinter(hprinter, 1, ("Toplik PIN Slip", None, "RAW"))
        win32print.StartPagePrinter(hprinter)
        win32print.WritePrinter(hprinter, napravi_slip(soba, pin, istice, lang))
        win32print.EndPagePrinter(hprinter)
        win32print.EndDocPrinter(hprinter)
        print(f"[OK] Slip poslan printeru '{PRINTER_NAME}' | soba={soba} lang={lang}")
    except Exception as e:
        print(f"[GRESKA] Tokom stampanja: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        win32print.ClosePrinter(hprinter)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Toplik Smart Hotel - Termalni printer slip'
    )
    parser.add_argument('--soba',   required=True,
                        help='Broj sobe (npr. 505)')
    parser.add_argument('--pin',    required=True,
                        help='PIN gosta (4 cifre)')
    parser.add_argument('--istice', required=True,
                        help='Datum i vreme odjave (npr. "2026-03-04 13:00")')
    parser.add_argument('--lang',   choices=['srb', 'eng', 'ger'], default='srb',
                        help='Jezik slipa: srb (default) | eng | ger')
    args = parser.parse_args()
    stampa(args.soba, args.pin, args.istice, args.lang)
