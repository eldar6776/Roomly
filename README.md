# Roomly

Roomly je centralni dio šireg sistema za **smart recepciju** i **smart room kontrolu apartmana**.

Ovaj repozitorij trenutno objedinjuje tri glavne cjeline:

1. **Windows 11 desktop aplikaciju za recepciju**
2. **Python server za Raspberry Pi 3B**
3. **Windows razvojnu kopiju servera za localhost testiranje**

Pored toga, projekat je direktno povezan sa mojim **HTTPBridge ESP32** projektom, a dio je i većeg ekosistema koji uključuje:

- dodatne **STM32 projekte**
- **Android aplikaciju**
- više uređaja i kontrolera koji zajedno čine kompletan sistem za upravljanje recepcijom i sobama / apartmanima

Ovaj README je početna dokumentacija za strukturu repo-a i način rada sistema. Linkovi prema povezanim projektima biće dodani naknadno.

---

## Pregled repozitorija

```text
Roomly/
├── reception-app/   # Windows 11 desktop aplikacija (Electron + React + TypeScript)
├── server-rpi/      # produkcijski Python server za Raspberry Pi 3B
├── server-win/      # lokalna Windows razvojna kopija servera za localhost
└── README.md
```

### Folderi i njihova namjena

#### `reception-app`
Desktop aplikacija za recepciju na Windows 11 računaru.

Koristi se za:
- rad recepcije
- upravljanje procesima prijema / evidencije / kontrole
- komunikaciju sa backend dijelom sistema
- integraciju sa dodatnim lokalnim uređajima poput printera i čitača kartica

Tehnologije koje se vide iz projekta:
- Electron
- React
- TypeScript
- Webpack
- Tailwind CSS
- SQLite (`better-sqlite3`)
- Python pomoćne skripte

Važni fajlovi:
- `reception-app/package.json`
- `reception-app/electron_main.js`
- `reception-app/src/`
- `reception-app/printer.py`
- `reception-app/SETUP_NEW_PC.ps1`
- `reception-app/cardrw/`

#### `server-rpi`
Produkcijska verzija Python servera koja radi na **Raspberry Pi 3B** uređaju.

Ovaj folder predstavlja remote / deploy varijantu backend-a.

Tehnologije:
- Python
- Flask
- Waitress
- Requests
- PyJWT

Važni fajlovi:
- `server-rpi/server.py`
- `server-rpi/log_transfer_manager.py`
- `server-rpi/templates/`
- `server-rpi/static/`
- `server-rpi/requirements.txt`

#### `server-win`
Lokalna razvojna kopija backend servera za Windows okruženje.

Ona služi za:
- razvoj novih funkcionalnosti
- testiranje na `localhost`
- debug prije deploy-a
- pripremu izmjena koje se kasnije prenose na Raspberry Pi server

Važni fajlovi:
- `server-win/server.py`
- `server-win/instaliraj_biblioteke.bat`
- `server-win/pokreni_server.bat`
- `server-win/templates/`
- `server-win/static/`

---

## Kako je sistem organizovan

Roomly nije izolovan projekat, nego dio većeg operativnog sistema.

### Logička povezanost

```text
                         +----------------------+
                         |   Android aplikacija |
                         +----------+-----------+
                                    |
                                    v
+------------------+      +----------------------+      +----------------------+
| Reception PC     | ---> | Roomly backend       | ---> | HTTPBridge ESP32     |
| Windows 11 app   |      | (server-win/rpi)     |      | bridge projekat      |
+---------+--------+      +----------+-----------+      +----------+-----------+
          |                          |                             |
          |                          v                             v
          |               +----------------------+       +----------------------+
          |               | Raspberry Pi 3B      |       | ESP32 uređaji        |
          |               | produkcijski server  |       | i periferija         |
          |               +----------------------+       +----------------------+
          |
          v
+----------------------+
| Lokalni uređaji      |
| printer / card reader|
+----------------------+
```

### Šira slika sistema

Pored komponenti u ovom repo-u, kompletan sistem uključuje i:

- **HTTPBridge ESP32** projekat
- **4 potpuno operativna STM32 projekta**
- **Android aplikaciju**
- Raspberry Pi infrastrukturu
- desktop recepcijsku aplikaciju
- lokalne i udaljene uređaje za automatizaciju

To znači da je `Roomly` jedan od glavnih softverskih slojeva unutar šire platforme za:

- smart recepciju
- kontrolu soba / apartmana
- komunikaciju sa mikrokontrolerima i perifernim uređajima
- automatizaciju procesa na objektu

---

## Razvojni workflow

U ovom repo-u postoje dvije verzije backend logike zato što imaju različitu ulogu:

### 1. Lokalni razvoj
Za razvoj i testiranje koristi se:

- `server-win`

Tu se:
- razvijaju nove funkcije
- testira ponašanje servera na `localhost`
- radi debug
- priprema verzija prije deploy-a

### 2. Produkcija
Za produkcijski rad koristi se:

- `server-rpi`

To je verzija servera koja radi na udaljenom Raspberry Pi 3B uređaju.

### 3. Korisnički interfejs
Za operatera / recepciju koristi se:

- `reception-app`

To je glavna desktop aplikacija preko koje korisnik upravlja sistemom.

### Tipičan tok rada

```text
Razvoj funkcije -> test u server-win -> validacija na localhost -> kopiranje / deploy na server-rpi -> rad u produkciji
```

---

## Pokretanje projekta

## 1) `reception-app`

### Zahtjevi
- Windows 11
- Node.js LTS
- Python 3
- Visual Studio Build Tools
- npm

### Automatizovani setup novog računara
U folderu `reception-app` postoji skripta:

- `SETUP_NEW_PC.ps1`

Ona instalira:
- Node.js
- Python
- C++ Build Tools
- npm pakete
- Python dependencies za card reader
- osnovnu lokalnu konfiguraciju

### Development
```bash
cd reception-app
npm install
npm run dev
```

### Build / paketiranje
```bash
cd reception-app
npm run build
npm run package:win
```

---

## 2) `server-win`

### Instalacija biblioteka
```bat
cd server-win
instaliraj_biblioteke.bat
```

ili ručno:

```bash
cd server-win
pip install -r requirements.txt
```

### Pokretanje
```bat
cd server-win
pokreni_server.bat
```

ili ručno:

```bash
cd server-win
python server.py
```

---

## 3) `server-rpi`

### Instalacija
```bash
cd server-rpi
pip install -r requirements.txt
```

### Pokretanje
```bash
cd server-rpi
python server.py
```

> Po potrebi se u produkciji može koristiti `waitress`, systemd servis ili drugi način automatskog pokretanja.

---

## Tehnologije

### Desktop dio
- Electron
- React
- TypeScript
- Tailwind CSS
- Webpack
- SQLite

### Backend dio
- Python
- Flask
- Waitress
- Requests
- PyJWT

### Ciljne platforme
- Windows 11
- Raspberry Pi 3B
- ESP32 integracija
- STM32 integracija
- Android aplikacija

---

## Namjena foldera

| Folder | Namjena |
|---|---|
| `reception-app` | Desktop aplikacija za recepciju |
| `server-win` | Lokalni Windows razvoj i localhost testiranje backend-a |
| `server-rpi` | Produkcijski Python server za Raspberry Pi 3B |

---

## Trenutni status dokumentacije

Ovaj README trenutno dokumentuje:
- osnovnu strukturu repo-a
- ulogu pojedinih foldera
- osnovni razvojni tok
- širu povezanost sistema

Planirano za naredne verzije:
- linkovi prema povezanim repozitorijima
- detaljan arhitekturni dijagram
- opis komunikacije između komponenti
- deployment koraci Windows -> Raspberry Pi
- `.env` dokumentacija
- API pregled
- opis svih STM32 i Android modula
- hardware mapa kompletnog sistema

---

## Napomena

Roomly je dio većeg zatvorenog / internog sistema i trenutno README služi prvenstveno kao:

- pregled strukture projekta
- vodič za razvojno okruženje
- osnovna arhitekturna dokumentacija

Kako se budu dodavali i ostali povezani repozitoriji, README može biti proširen u centralnu dokumentaciju kompletnog smart reception / smart room ekosistema.
