@echo off
title MyBloomberg Terminal
cd /d "%~dp0"
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8000"
python app.py
