# ==============================================================================
# TOPLIK SMART RECEPTION - FULL SYSTEM INSTALLER
# ==============================================================================
# Ova skripta instalira: Node.js, Python, C++ Build Tools i sve ovisnosti.
# Pokrenite ovo kao Administrator na novom racunaru.
# ==============================================================================

Write-Host ">>> Pokrecem instalaciju sistema za Toplik Reception..." -ForegroundColor Cyan

# 1. Provjera Administratorskih prava
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Warning "MOLIM POKRENITE OVU SKRIPTU KAO ADMINISTRATOR!"
    Write-Warning "Desni klik na fajl -> Run with PowerShell (Administrator)"
    Pause
    exit
}

# 2. Instalacija sistemskih programa preko Winget-a
Write-Host "`n[1/5] Instalacija Node.js, Python i VS Build Tools (ovo traje)..." -ForegroundColor Yellow

# Node.js LTS
Write-Host "Instaliram Node.js..."
winget install -e --id OpenJS.NodeJS.LTS --silent --accept-package-agreements --accept-source-agreements

# Python 3
Write-Host "Instaliram Python..."
winget install -e --id Python.Python.3 --silent --accept-package-agreements

# Visual Studio Build Tools (Kljucno za SQLITE bazu!)
Write-Host "Instaliram C++ Build Tools (potrebno za rad baze podataka)..."
winget install --id Microsoft.VisualStudio.2022.BuildTools --override "--passive --config .vsconfig --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended" --silent --accept-package-agreements

# Osvjezi Environment varijable da sistem vidi nove programe
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# 3. Instalacija Node modula
Write-Host "`n[2/5] Instalacija NPM modula..." -ForegroundColor Yellow
npm install --no-audit

# 4. Popravka baze (Electron Rebuild)
Write-Host "`n[3/5] Kompajliranje baze podataka za ovaj racunar..." -ForegroundColor Yellow
npx electron-rebuild

# 5. Podizanje citaca kartica (Python)
Write-Host "`n[4/5] Podizanje servisa za citac kartica..." -ForegroundColor Yellow
if (Test-Path "cardrw") {
    cd cardrw
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    cd ..
}

# 6. Konfiguracija (.env)
Write-Host "`n[5/5] Finalizacija..." -ForegroundColor Yellow
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[!] Kreiran je .env fajl. OBAVEZNO unesite API KEY i ime PRINTERA!" -ForegroundColor Red
}

# Kreiranje Desktop precice (Opcionalno)
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$Home\Desktop\Toplik Reception.lnk")
$Shortcut.TargetPath = "$PSScriptRoot
ode_modules\.bin\electron.cmd"
$Shortcut.Arguments = "$PSScriptRoot"
$Shortcut.WorkingDirectory = "$PSScriptRoot"
$Shortcut.IconLocation = "$PSScriptRoot\assets\icon.ico"
$Shortcut.Save()

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "   INSTALACIJA ZAVRSENA! MOZETE POKRENUTI APLIKACIJU." -ForegroundColor Green
Write-Host "   Precica je na Desktopu: 'Toplik Reception'"
Write-Host "============================================================" -ForegroundColor Green
Pause
