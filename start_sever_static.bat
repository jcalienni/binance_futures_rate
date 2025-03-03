@echo off
cd /d C:\Projects\binance_futures_rate

:: Start the Python HTTP server in a new minimized window
start /min cmd /c "python -m http.server 8000"

:: Wait a few seconds to ensure the server starts
timeout /t 3 /nobreak >nul

:: Open in Google Chrome
start chrome http://localhost:8000/graph2.html