@echo off
title Building MyBloomberg Terminal EXE
color 0E
echo.
echo  ============================================
echo   Building MyBloomberg Terminal EXE...
echo  ============================================
echo.

cd /d "%~dp0"

:: Check PyInstaller
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo  [INFO] Installing PyInstaller...
    pip install pyinstaller
)

echo  [INFO] Building executable...
pyinstaller --noconfirm --onedir --console ^
    --name "MyBloomberg" ^
    --add-data "templates;templates" ^
    --add-data "frontend;frontend" ^
    --add-data "backend;backend" ^
    --hidden-import uvicorn.logging ^
    --hidden-import uvicorn.loops ^
    --hidden-import uvicorn.loops.auto ^
    --hidden-import uvicorn.protocols ^
    --hidden-import uvicorn.protocols.http ^
    --hidden-import uvicorn.protocols.http.auto ^
    --hidden-import uvicorn.protocols.websockets ^
    --hidden-import uvicorn.protocols.websockets.auto ^
    --hidden-import uvicorn.lifespan ^
    --hidden-import uvicorn.lifespan.on ^
    --hidden-import uvicorn.lifespan.off ^
    --hidden-import sqlalchemy.dialects.sqlite ^
    --collect-all yfinance ^
    --collect-all feedparser ^
    app.py

if errorlevel 1 (
    echo.
    echo  [ERROR] Build gagal!
    pause
    exit /b 1
)

:: Copy run script into dist folder
echo @echo off > "dist\MyBloomberg\start.bat"
echo title MyBloomberg Terminal >> "dist\MyBloomberg\start.bat"
echo cd /d "%%~dp0" >> "dist\MyBloomberg\start.bat"
echo start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8000" >> "dist\MyBloomberg\start.bat"
echo MyBloomberg.exe >> "dist\MyBloomberg\start.bat"

echo.
echo  ============================================
echo   BUILD SELESAI!
echo   Folder: dist\MyBloomberg\
echo   Jalankan: dist\MyBloomberg\start.bat
echo  ============================================
echo.
pause
