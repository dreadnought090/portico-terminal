@echo off
title Portico Terminal
color 0A
echo.
echo  ======================================
echo       PORTICO TERMINAL - Starting...
echo  ======================================
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
    if errorlevel 1 (
        echo  [ERROR] Gagal membuat venv!
        pause
        exit /b 1
    )
    call venv\Scripts\activate.bat
    echo  [SETUP] Menginstall dependencies...
    pip install -r requirements.txt
    echo.
) else (
    call venv\Scripts\activate.bat
)

:: Check if dependencies installed
python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo  [SETUP] Installing missing dependencies...
    pip install -r requirements.txt
)

:: Open browser after 3 seconds
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:8000"

echo  [OK] Server berjalan di http://localhost:8000
echo  [OK] Browser akan terbuka otomatis...
echo.
echo  Tekan Ctrl+C untuk stop server
echo  ──────────────────────────────────────────
echo.

python app.py

:: If server exits with error, don't close window
if errorlevel 1 (
    echo.
    echo  [ERROR] Server berhenti! Lihat error di atas.
    echo.
    pause
)
