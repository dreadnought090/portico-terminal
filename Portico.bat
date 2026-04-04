@echo off
title Portico Terminal
color 0A
echo.
echo  ╔══════════════════════════════════════════╗
echo  ║       PORTICO TERMINAL - Starting...     ║
echo  ╚══════════════════════════════════════════╝
echo.

cd /d "%~dp0"

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python tidak ditemukan!
    echo  Install Python dari https://python.org
    echo.
    pause
    exit /b 1
)

:: Auto-setup venv + dependencies on first run
if not exist "venv" (
    echo  [SETUP] Pertama kali — membuat virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo  [SETUP] Menginstall dependencies...
    pip install -r requirements.txt
    echo.
) else (
    call venv\Scripts\activate.bat
)

:: Open browser after 2 seconds
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8000"

echo  [OK] Server berjalan di http://localhost:8000
echo  [OK] Browser akan terbuka otomatis...
echo  [OK] Akses dari HP: http://192.168.1.74:8000
echo.
echo  Tekan Ctrl+C untuk stop server
echo  ──────────────────────────────────────────
echo.

python app.py
