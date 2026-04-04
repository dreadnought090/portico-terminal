@echo off
title MyBloomberg Terminal
color 0A
echo.
echo  ============================================
echo   MyBloomberg Terminal - Starting...
echo  ============================================
echo.

cd /d "%~dp0"

:: Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python tidak ditemukan!
    echo  Install Python dari https://python.org
    pause
    exit /b 1
)

:: Install dependencies if needed
if not exist "venv" (
    echo  [INFO] Membuat virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo  [INFO] Menginstall dependencies...
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

:: Open browser after 2 seconds
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8000"

echo.
echo  [OK] Server berjalan di http://localhost:8000
echo  [OK] Browser akan terbuka otomatis...
echo  [INFO] Tekan Ctrl+C untuk menghentikan server
echo.

python app.py
