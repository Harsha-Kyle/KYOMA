@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
title KYOMA AI - Future Gadget Laboratory
color 06

echo ========================================================
echo                        KYOMA AI
echo ========================================================
echo Backend Server : http://localhost:8000
echo Web Frontend   : http://localhost:5173
echo ========================================================
echo.

echo [1/3] Launching Web Frontend (Vite dev server)...
start "KYOMA Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo [2/3] Opening Browser Interface...
timeout /t 2 /nobreak >nul
start http://localhost:5173

echo [3/3] Starting Backend Server...
start "KYOMA Backend" cmd /k "cd /d %~dp0backend && ..\..\venv\Scripts\python.exe server.py"

echo.
echo Waiting for KYOMA Backend to become healthy...
:health_loop
timeout /t 2 /nobreak >nul
curl -s -f http://localhost:8000/api/status >nul 2>&1
if errorlevel 1 (
    echo ... waiting for backend initialization ...
    goto health_loop
)

echo.
echo ========================================================
echo               *** KYOMA SYSTEM READY ***
echo ========================================================
echo Input Mode   : wake_word (Say "Hey Kyoma" or "Kyoma")
echo Desktop UI   : http://localhost:5173
echo API Health   : http://localhost:8000/health
echo NOTE: Gemma model warms up in background (first query may take a few extra seconds)
echo ========================================================
echo.
pause

