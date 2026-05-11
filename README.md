# Roomly

**Roomly** is a modular software platform for **smart reception operations** and **smart apartment / room control**.

This repository is not a single standalone app. It contains multiple connected components that together support reception workflows, backend services, device communication, and on-site automation.

At this stage, this repository includes:

- a **Windows 11 desktop reception application**
- a **Python backend for Raspberry Pi 3B**
- a **Windows localhost development copy of the backend**

It is also directly connected to the **HTTPBridge ESP32** project and is part of a larger ecosystem that includes:

- **4 production STM32 projects**
- an **Android application**
- additional on-site devices, controllers, and smart room automation components

This README is written as a **promotion and architecture overview** of the project.

---

## Overview

Roomly is designed as a practical operational platform for hospitality-oriented environments where reception workflows, embedded hardware, and room automation need to work together as one system.

The project combines desktop software, backend services, microcontroller-based device layers, and mobile control into a single smart environment.

### Main goals

- support reception and front-desk operations
- provide a backend layer for operational logic
- integrate local devices such as printers and card readers
- connect to Raspberry Pi infrastructure for deployment
- communicate with ESP32- and STM32-based hardware modules
- serve as part of a broader smart reception and smart room ecosystem

---

## Repository structure

```text
Roomly/
├── reception-app/   # Windows 11 desktop application
├── server-rpi/      # Raspberry Pi production backend
├── server-win/      # Windows localhost backend for development
└── README.md
```

---

## Components

### 1. `reception-app`

`reception-app` is the Windows desktop application used by the reception operator.

It is built with modern desktop web technologies and packaged as a native desktop app.

### Technology stack

- Electron
- React
- TypeScript
- Webpack
- Tailwind CSS
- SQLite via `better-sqlite3`
- Python helper scripts for selected local integrations

### Purpose

This application is intended to provide the main operator-facing interface for:

- front-desk workflows
- reservation or guest-related processes
- local operational control
- communication with backend services
- integration with devices such as printers and card readers

### Important files

- `reception-app/package.json`
- `reception-app/electron_main.js`
- `reception-app/src/`
- `reception-app/printer.py`
- `reception-app/SETUP_NEW_PC.ps1`
- `reception-app/cardrw/`

### Desktop application setup

A setup script is already included for preparing a new Windows machine:

- `reception-app/SETUP_NEW_PC.ps1`

Based on the project files, this script installs and prepares:

- Node.js
- Python
- Visual Studio Build Tools
- npm dependencies
- Python dependencies for card reader integration
- local environment preparation

### Development

```bash
cd reception-app
npm install
npm run dev
```

### Build

```bash
cd reception-app
npm run build
npm run package:win
```

---

### 2. `server-rpi`

`server-rpi` is the production backend designed to run on a **Raspberry Pi 3B**.

This folder represents the remote or deployed runtime version of the backend service.

### Technology stack

- Python
- Flask
- Waitress
- Requests
- PyJWT

### Purpose

This service is intended to:

- host backend business logic
- serve templates and static resources
- provide APIs and operational endpoints
- run in the on-site Raspberry Pi environment
- coordinate logic used by the wider Roomly platform

### Important files

- `server-rpi/server.py`
- `server-rpi/log_transfer_manager.py`
- `server-rpi/templates/`
- `server-rpi/static/`
- `server-rpi/requirements.txt`

### Installation

```bash
cd server-rpi
pip install -r requirements.txt
```

### Run

```bash
cd server-rpi
python server.py
```

> In production, this service can also be managed through `waitress`, `systemd`, or another deployment/runtime supervisor.

---

### 3. `server-win`

`server-win` is the Windows development copy of the backend.

It is used for local development, localhost testing, debugging, and preparing backend changes before those changes are copied or deployed to the Raspberry Pi environment.

### Purpose

This folder exists to make backend development faster and more practical on a Windows workstation.

Typical use cases:

- local backend development
- localhost testing
- debugging before deployment
- validating backend behavior before copying to the production Raspberry Pi environment

### Important files

- `server-win/server.py`
- `server-win/instaliraj_biblioteke.bat`
- `server-win/pokreni_server.bat`
- `server-win/templates/`
- `server-win/static/`

### Install dependencies

```bat
cd server-win
instaliraj_biblioteke.bat
```

or manually:

```bash
cd server-win
pip install -r requirements.txt
```

### Run locally

```bat
cd server-win
pokreni_server.bat
```

or manually:

```bash
cd server-win
python server.py
```

---

## Development and deployment workflow

One of the most important things to understand about this repository is the difference between `server-win` and `server-rpi`.

They represent two environments with different roles.

### Local development flow

`server-win` is used for:

- writing new backend logic
- testing locally on `localhost`
- debugging behavior in a convenient desktop environment
- validating changes before deployment

### Production flow

`server-rpi` is used for:

- deployed backend execution
- on-device Raspberry Pi runtime
- production or near-production operational use

### Typical workflow

```text
Feature development
    -> local implementation in server-win
    -> localhost testing and debugging
    -> validation
    -> copy / deploy to server-rpi
    -> production runtime on Raspberry Pi 3B
```

### Application flow

```text
Reception operator
    -> uses reception-app on Windows 11
    -> communicates with backend services
    -> backend runs locally during development or on Raspberry Pi in production
    -> system exchanges data with hardware bridge and embedded controllers
```

---

## System architecture

Roomly is part of a larger technical ecosystem.

The repository itself contains only part of the complete platform, but it already shows the core software layers used in the smart reception and smart room environment.

### High-level architecture

```text
+------------------------+
|   Reception Operator   |
+-----------+------------+
            |
            v
+------------------------+
|  Roomly Reception App  |
|  Windows 11 / Electron |
+-----------+------------+
            |
            v
+------------------------+
|    Roomly Backend      |
| server-win / server-rpi|
+-----+-------------+----+
      |             |
      |             v
      |      +------------------+
      |      | Raspberry Pi 3B  |
      |      | Production Host  |
      |      +------------------+
      |
      v
+------------------------+
| Local integrations     |
| printer / card reader  |
+------------------------+
```

### Extended ecosystem view

```text
                               +----------------------+
                               |   Android App        |
                               +----------+-----------+
                                          |
                                          v
+----------------------+      +----------------------+      +----------------------+
| Reception PC         | ---> | Roomly Backend       | ---> | HTTPBridge ESP32     |
| Windows 11 App       |      | Win dev / RPi prod   |      | Communication layer  |
+----------+-----------+      +----------+-----------+      +----------+-----------+
           |                             |                             |
           |                             v                             v
           |                  +----------------------+      +----------------------+
           |                  | Raspberry Pi 3B      |      | ESP32 devices        |
           |                  | Production runtime   |      | and field hardware   |
           |                  +----------------------+      +----------------------+
           |
           v
+----------------------+
| Local peripherals    |
| Printer / Card reader|
+----------------------+


                      +----------------------------------------------+
                      |     Additional embedded system layer         |
                      |        4 separate production STM32 projects  |
                      +----------------------------------------------+
```

---

## Ecosystem positioning

Roomly should be viewed as one software layer within a broader integrated platform.

### The broader ecosystem includes

- **Roomly** desktop and backend software
- **HTTPBridge ESP32** for device-facing HTTP communication
- **4 fully operational STM32 projects**
- **Android mobile application**
- **Raspberry Pi deployment environment**
- **local operator hardware and peripherals**

Together, these components form a complete operational solution for:

- smart reception
- smart room / apartment control
- hardware-assisted workflows
- on-site automation
- hybrid desktop + embedded + mobile coordination

---

## Related projects

This repository is part of a larger multi-project platform.

At the moment, the following related components are known:

- HTTPBridge ESP32 project
- 4 STM32 embedded projects
- Android mobile application

> Links to related repositories will be added later.

---

## Technology summary

### Desktop

- Electron
- React
- TypeScript
- Tailwind CSS
- Webpack
- SQLite

### Backend

- Python
- Flask
- Waitress
- Requests
- PyJWT

### Infrastructure and device ecosystem

- Windows 11
- Raspberry Pi 3B
- ESP32-based integration
- STM32-based integration
- Android mobile client

---

## Why this repository structure exists

This repository may look unusual at first because it contains both a Raspberry Pi backend and a Windows backend copy.

That structure exists for practical reasons:

- backend development is easier and faster on a Windows workstation
- local testing on `localhost` speeds up iteration
- the Raspberry Pi folder represents the deployment target
- the desktop application is a separate operational layer used by the reception operator

This makes the repository suitable both for development and for real operational deployment.

---

## Promotional summary

Roomly is more than a desktop app or a backend service.

It is part of a broader smart hospitality platform that combines:

- operator-facing software
- backend logic
- Raspberry Pi deployment
- ESP32 communication layers
- STM32 embedded modules
- Android mobile access
- physical device integration

The result is a modular, real-world system for building a connected **smart reception** and **smart room control** environment.

---

## Current documentation scope

This README currently provides:

- an English-only project overview
- repository structure explanation
- component descriptions
- development and deployment flow
- architecture diagrams
- ecosystem context for promotion

Future improvements may include:

- links to all related repositories
- screenshots of the desktop application
- API overview
- deployment guide
- environment configuration details
- hardware topology map
- communication protocol overview
- detailed documentation for Android and STM32 integration
