@echo off
TITLE Toplik Smart Reception - Setup Card Reader
echo ====================================================
echo  POSTAVLJANJE CITACA KARTICA - TOPLIK RECEPTION
echo ====================================================
echo.

:: Provjera da li je Python instaliran
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [GRESKA] Python nije pronadjen na sistemu!
    echo Molim vas instalirajte Python 3 sa https://www.python.org/
    echo OBAVEZNO oznacite 'Add Python to PATH' tokom instalacije.
    pause
    exit /b
)

echo [OK] Python je pronadjen.
echo Instalacija biblioteka za citac kartica...
echo.

:: Instalacija requirements.txt
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo [GRESKA] Doslo je do greske pri instalaciji biblioteka.
    echo Provjerite internet konekciju i pokusajte ponovo.
    pause
    exit /b
)

echo.
echo ====================================================
echo  USPJESNO! Citac kartica je spreman za rad.
echo  Mozete zatvoriti ovaj prozor i pokrenuti aplikaciju.
echo ====================================================
pause
