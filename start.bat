@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
title KYOMA AI - Future Gadget Laboratory
color 06

set "KYOMA_STATUS_FILE=%~dp0startup_status.json"
if exist "%KYOMA_STATUS_FILE%" del /F /Q "%KYOMA_STATUS_FILE%" >nul 2>&1

echo ========================================================
echo                        KYOMA AI
echo ========================================================
echo Backend Server : http://localhost:8000
echo Web Frontend   : http://localhost:5173
echo Status File    : %KYOMA_STATUS_FILE%
echo ========================================================
echo.

echo [1/3] Launching Web Frontend (Vite dev server in background)...
taskkill /F /IM node.exe >nul 2>&1
start /MIN "KYOMA Frontend" cmd /c "cd /d %~dp0frontend && npm run dev"

echo [2/3] Waiting for Web Frontend on port 5173 to open browser immediately...
:vite_loop
timeout /t 1 /nobreak >nul
curl -s -o nul http://localhost:5173
if errorlevel 1 (
    goto vite_loop
)
echo Vite dev server active on port 5173. Opening browser interface now...
start http://localhost:5173

echo [3/3] Launching KYOMA Backend Console Window...
start "KYOMA Backend" cmd /k "cd /d %~dp0backend && ..\..\venv\Scripts\python.exe server.py"

echo.
echo Waiting for KYOMA Backend to become healthy and fully ready...
:health_loop
timeout /t 2 /nobreak >nul
curl -s http://localhost:8000/api/startup/status | findstr /i "\"ready\":true" >nul 2>&1
if errorlevel 1 (
    echo ... waiting for backend initialization and model warmup ...
    goto health_loop
)

echo.
echo ========================================================
echo               *** KYOMA SYSTEM READY ***
echo ========================================================
echo Input Mode   : wake_word (Say "Hey Kyoma" or "Kyoma")
echo Desktop UI   : http://localhost:5173
echo API Health   : http://localhost:8000/health
echo Backend Log  : Visible in the dedicated "KYOMA Backend" window
echo NOTE: Gemma model warms up in background (first query may take a few extra seconds)
echo ========================================================
echo.
pause
