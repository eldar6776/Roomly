# Roomly

![Platform](https://img.shields.io/badge/platform-Windows%2011-0078D6?style=for-the-badge&logo=windows&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi%203B-C51A4A?style=for-the-badge&logo=raspberrypi&logoColor=white)
![Desktop](https://img.shields.io/badge/app-Electron%20Desktop-47848F?style=for-the-badge&logo=electron&logoColor=white)
![Frontend](https://img.shields.io/badge/frontend-React%20%2B%20TypeScript-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
![Backend](https://img.shields.io/badge/backend-Python%20%2B%20Flask-3776AB?style=for-the-badge&logo=python&logoColor=white)
![System](https://img.shields.io/badge/system-Smart%20Reception-111827?style=for-the-badge)
![System](https://img.shields.io/badge/system-Smart%20Room%20Control-0F766E?style=for-the-badge)
![Version](https://img.shields.io/badge/version-1.0.0-orange?style=for-the-badge)
![Status](https://img.shields.io/badge/status-Active%20Development-16A34A?style=for-the-badge)

**Roomly** is a smart hospitality control platform centered around a reception desktop application and a Raspberry Pi backend that drive room access, room control, guest-facing interfaces, and operational management.

This repository contains the actual working software layers used for:

- reception workstation operations on Windows 11
- local backend development on Windows
- production backend runtime on Raspberry Pi 3B
- room control pages for guests
- manager and admin web interfaces
- printer-based guest slip generation
- card reader / card writer integration
- communication with external smart-device infrastructure

The code in this repository shows a real multi-part system rather than a demo project.

---

## What Roomly does

From the code currently in this repository, Roomly provides a practical software stack for a hospitality environment branded in the project as **Toplik Smart Hotel / Toplik Reception / Toplik Village Resort**.

The project combines:

- a **desktop reception application** built with Electron, React, and TypeScript
- a **Python backend** built with Flask and Waitress
- a **guest room control interface** with multilingual UI
- a **manager heating control panel**
- an **admin dashboard and admin login flow**
- **thermal printer slip generation** with QR code output
- **MIFARE/card-reader related setup and Windows integration**
- configuration for **Raspberry Pi-hosted smart room access**

The repository structure and code clearly indicate that the system is designed for real on-site use, not just local UI prototyping.

---

## Repository structure

```text
Roomly/
├── reception-app/   # Windows 11 desktop reception application
├── server-rpi/      # Production backend for Raspberry Pi 3B
├── server-win/      # Windows localhost backend used for development/testing
└── README.md
```

---

## Component breakdown

### `reception-app`

This is the reception workstation application.

It is an Electron desktop app with a React + TypeScript frontend and local Windows-oriented integrations.

### Confirmed stack from the project files

- Electron
- React
- TypeScript
- Webpack
- Tailwind CSS
- SQLite via `better-sqlite3`
- `electron-store`
- Python helper scripts

### What the reception app is used for

Based on the code and configuration, the desktop app is intended for:

- PIN-based reception and manager login
- hotel configuration and local settings
- communication with the Raspberry Pi backend
- local printer integration
- local card-reader / card-writer support
- Windows-based front desk operation

### Evidence from the code

- `reception-app/package.json` identifies the app as **Toplik Smart Hotel - Reception Desktop Application**
- `reception-app/src/renderer/pages/Login.tsx` shows PIN-based login for **reception** and **manager** roles
- `reception-app/src/main/config.ts` defines hotel name, WiFi SSID, printer name, ntfy alerts, and Raspberry Pi connection settings
- `reception-app/printer.py` prints multilingual thermal slips containing room, PIN, WiFi info, and a QR URL pointing to the Raspberry Pi backend
- `reception-app/cardrw/setup_reader.bat` installs Python dependencies for card reader setup
- `reception-app/SETUP_NEW_PC.ps1` prepares a full Windows machine for operation

### Reception app structure

```text
reception-app/
├── src/main/        # Electron/main-process logic and config
├── src/renderer/    # React frontend
├── src/shared/      # shared code
├── cardrw/          # card reader / writer support
├── printer.py       # thermal printer integration
└── SETUP_NEW_PC.ps1 # full new-PC setup
```

### Reception workstation setup

The repository already includes an installation script for a new PC:

- `reception-app/SETUP_NEW_PC.ps1`

From the script content, it prepares:

- Node.js
- Python 3
- Visual Studio Build Tools
- npm dependencies
- Electron native rebuild
- card reader Python dependencies
- `.env` bootstrap
- a desktop shortcut for the application

### Development commands

```bash
cd reception-app
npm install
npm run dev
```

### Packaging

```bash
cd reception-app
npm run build
npm run package:win
```

---

### `server-rpi`

This is the Raspberry Pi production backend.

It contains the deployed Python server, templates, static assets, authentication pages, control endpoints, and room-facing pages.

### Confirmed stack from the project files

- Python
- Flask
- Waitress
- Requests
- PyJWT

### What the Raspberry Pi backend does

Based strictly on the files present in this repository, `server-rpi` is responsible for:

- serving guest room control pages
- serving admin and manager login pages
- providing backend APIs for room control
- handling manager heating control
- communicating with device-control layers
- producing current device and thermostat state for the frontend
- running on Raspberry Pi as the production host

### Templates currently present

```text
server-rpi/templates/
├── admin.html
├── admin_login.html
├── login.html
├── manager.html
├── manager_heating.html
├── manager_login.html
└── soba.html
```

These are not placeholders. They show that the backend already includes multiple real operational UIs:

- **`soba.html`** — guest-facing room control page
- **`manager_heating.html`** — manager-facing heating/pump control page
- **`admin_login.html`** — admin authentication
- **`manager_login.html`** — manager authentication
- **`admin.html` / `manager.html`** — dashboard-level pages

### Guest room control features visible in `soba.html`

The room control page already includes:

- thermostat setpoint control
- thermostat ON/OFF switch
- control of multiple lighting zones:
  - main light
  - ambient light
  - bed light
  - WC light
  - mirror light
- open door action
- multilingual switching:
  - BHS
  - English
  - German
- Alexa instructions overlay for voice-command guidance
- polling of real status from backend APIs

This means the backend is not just exposing data — it is already serving a complete guest control experience.

### Manager heating features visible in `manager_heating.html`

The manager heating page includes control and status for:

- thermostat temperature setpoint
- thermostat ON/OFF
- fancoil pump mode
- fancoil pump manual ON/OFF
- floor-heating pump mode
- floor-heating pump manual ON/OFF
- real RUN/STOP pump status indicators

The backend code in `server-rpi/server.py` also confirms HVAC / thermostat / pump status handling and command synchronization.

### Raspberry Pi backend commands

```bash
cd server-rpi
pip install -r requirements.txt
python server.py
```

---

### `server-win`

This folder is the Windows localhost development copy of the backend.

It mirrors the server-side application structure used on Raspberry Pi, but exists specifically to make development, localhost testing, and debugging easier on a Windows machine.

### Why this folder exists

The repository makes this workflow clear:

- backend changes are easier to build and debug on Windows
- the same functional backend is then prepared for the Raspberry Pi runtime
- templates and operational pages can be tested locally before deployment

### Confirmed from the files

`server-win` contains:

- `server.py`
- `templates/`
- `static/`
- `instaliraj_biblioteke.bat`
- `pokreni_server.bat`

The templates present in `server-win/templates` match the operational pages found in `server-rpi/templates`, which confirms that the Windows backend is a real development environment for the same application logic.

### Local install and run

```bat
cd server-win
instaliraj_biblioteke.bat
pokreni_server.bat
```

Or manually:

```bash
cd server-win
pip install -r requirements.txt
python server.py
```

---

## Confirmed functional areas from the codebase

This README is intentionally based on the actual repository contents. The following capabilities are visible directly in the files.

### 1. Reception login and role separation

The Electron app login flow supports role-based PIN access for at least:

- reception
- manager

The renderer login page checks locally stored role PINs and routes the user accordingly.

### 2. Hotel and infrastructure configuration

The Electron configuration file includes runtime settings for:

- hotel name
- WiFi SSID
- QR URL generation
- Raspberry Pi host and port
- printer configuration
- SOS notification topic via `ntfy.sh`
- default temperatures
- checkout time
- application dimensions and identity

### 3. Guest thermal slip printing

`reception-app/printer.py` generates a real guest slip containing:

- hotel name
- room number
- guest PIN
- WiFi network name
- QR code for smart room control
- checkout time
- multilingual output:
  - Serbian/BHS
  - English
  - German

The script uses **Windows spooler printing** with ESC/POS commands, which shows this is intended for an actual thermal-printer workflow at reception.

### 4. Guest room control UI

The guest page in `server-rpi/templates/soba.html` provides direct control over:

- room temperature
- thermostat power
- multiple lighting circuits
- door opening
- guest language switching
- Alexa usage instructions

### 5. Manager heating control

The manager heating page and backend logic expose:

- thermostat state and setpoint
- HVAC pump mode switching
- manual/automatic control behavior
- live RUN/STOP feedback

### 6. Admin and manager authentication

Separate login pages exist for:

- admin access
- manager access

This indicates the system already has distinct operational roles on the web/backend side in addition to the desktop app roles.

---

## Architecture

The repository shows three practical software layers:

1. **Reception workstation layer** on Windows 11
2. **Backend service layer** for local testing and Raspberry Pi production runtime
3. **Guest / manager / admin web interfaces** served by the backend

### Core structure

```text
+-----------------------------+
| Reception Workstation       |
| Electron + React desktop UI |
+-------------+---------------+
              |
              | local integrations
              v
+-----------------------------+
| Windows device integrations |
| printer.py / cardrw         |
+-------------+---------------+
              |
              | backend communication
              v
+-----------------------------+
| Roomly backend              |
| server-win or server-rpi    |
+-------------+---------------+
              |
              +------------------------------+
              |                              |
              v                              v
+-----------------------------+   +-----------------------------+
| Guest room web UI           |   | Manager / Admin web UI      |
| soba.html                   |   | manager/admin pages         |
+-----------------------------+   +-----------------------------+
```

### Operational environment view

```text
+----------------------+        +----------------------+        +----------------------+
| Reception PC         | -----> | Roomly Backend       | -----> | Device / control     |
| Windows 11 app       |        | Flask on Win / RPi   |        | infrastructure       |
+----------+-----------+        +----------+-----------+        +----------------------+
           |                               |
           |                               |
           v                               v
+----------------------+        +----------------------+
| Thermal printer      |        | Guest / Manager /    |
| Card reader/writer   |        | Admin web interfaces |
+----------------------+        +----------------------+
```

### Guest access flow visible in the code

The printed slip generated by `printer.py` contains:

- room number
- guest PIN
- WiFi details
- a QR URL derived from Raspberry Pi host and port

That establishes a concrete operational flow:

```text
Reception creates / prints guest slip
        -> guest receives room number + PIN
        -> guest scans QR code
        -> guest opens room control page served by Raspberry Pi backend
        -> guest controls room temperature, lights, and door-related actions
```

This is one of the most important real-world flows visible in the repository.

---

## Development workflow

The codebase itself makes the intended workflow clear.

### Backend workflow

```text
Develop locally in server-win
    -> test on localhost
    -> validate templates, APIs, and control logic
    -> copy / deploy to server-rpi
    -> run in production on Raspberry Pi 3B
```

### Desktop workflow

```text
Prepare Windows workstation
    -> run SETUP_NEW_PC.ps1
    -> install Node.js / Python / Build Tools
    -> install card reader dependencies
    -> build/package reception desktop app
    -> run on reception PC
```

### Hospitality control workflow

```text
Reception operator uses desktop app
    -> system prepares guest access data
    -> thermal printer prints access slip with QR code
    -> guest opens room-control page
    -> backend serves live room control and operational interfaces
```

---

## Technology summary

### Desktop layer

- Electron
- React
- TypeScript
- Webpack
- Tailwind CSS
- better-sqlite3
- electron-store

### Backend layer

- Python
- Flask
- Waitress
- Requests
- PyJWT

### Windows-specific integrations

- Python-based ESC/POS thermal printing through `win32print`
- card reader / card writer setup with Python dependencies
- batch and PowerShell automation scripts

---

## Why the repository is structured this way

This repository has a very practical layout because it reflects how the software is actually operated.

- `reception-app` is the operator-facing application used on a Windows reception PC
- `server-win` is the development and localhost testing backend
- `server-rpi` is the production backend intended for Raspberry Pi deployment

This separation is not generic architecture styling — it matches the real workflow already visible in the code:

- Windows workstation setup scripts
- production Raspberry Pi configuration
- locally testable backend templates
- printer and card-related local integrations
- guest room control served from the backend

---

## Project identity visible in the code

Names and branding currently visible in the repository include:

- **Roomly**
- **Toplik Smart Hotel**
- **Toplik Smart Reception**
- **Toplik Village Resort**
- **Toplik Reception**

That branding appears in the desktop app metadata, UI text, configuration defaults, and printer output.

---

## Summary

Roomly is a real hospitality-control software stack that already combines:

- a Windows reception desktop application
- Raspberry Pi backend deployment
- guest room control pages
- manager heating control
- admin and manager authentication
- thermal printer guest-slip generation
- card reader / card-writer support
- multilingual guest-facing interaction

This repository does not just describe the platform — it already contains the active software layers that make the reception and room-control workflow possible.
