@echo off
rem Smart Farm - start on Windows without Docker. Run windows-setup.bat once first.
setlocal
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
  echo Run windows-setup.bat first.
  pause
  exit /b 1
)

echo Starting the Smart Farm API (port 8010) and web app (port 5180)...
start "Smart Farm API - keep open" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\python.exe manage.py migrate --noinput && .venv\Scripts\python.exe manage.py runserver 8010"
start "Smart Farm web - keep open" cmd /k "cd /d "%~dp0frontend" && npm.cmd run dev"

echo Waiting for the app to start...
timeout /t 12 /nobreak >nul
start "" http://localhost:5180
echo.
echo Smart Farm is opening in your browser: http://localhost:5180
echo To stop it, close the two "keep open" windows.
pause
