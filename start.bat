@echo off
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
cd /d %~dp0backend
..\..\venv\Scripts\python.exe server.py

pause

