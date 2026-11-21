@echo off
rem Smart Farm - one-time setup on Windows, without Docker.
rem Needs: Python 3.12, Node.js 22 LTS and PostgreSQL 16 installed first (see README).
setlocal
cd /d "%~dp0"

echo.
echo === Smart Farm setup ===
echo.

rem Programs installed a moment ago may not be on PATH yet in this window.
set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Python\Launcher;%ProgramFiles%\nodejs;%APPDATA%\npm"

where py >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.12 from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" on the first installer screen.
  goto :fail
)
py -3.12 --version >nul 2>nul
if errorlevel 1 (
  echo Python 3.12 was not found. Install Python 3.12 from https://www.python.org/downloads/
  goto :fail
)
where node >nul 2>nul
if errorlevel 1 (
  echo Node.js was not found. Install the LTS version from https://nodejs.org/
  goto :fail
)

echo [1/4] Creating the Python environment...
if not exist "backend\.venv\Scripts\python.exe" (
  py -3.12 -m venv "backend\.venv" || goto :fail
)
"backend\.venv\Scripts\python.exe" -m pip install --upgrade pip >nul
"backend\.venv\Scripts\python.exe" -m pip install -r "backend\requirements\dev.txt" || goto :fail

echo.
echo [2/4] Connecting to PostgreSQL and creating the database...
"backend\.venv\Scripts\python.exe" "backend\scripts\setup_local_db.py" || goto :fail

echo.
echo [3/4] Creating the database tables...
pushd backend
".venv\Scripts\python.exe" manage.py migrate --noinput || (popd & goto :fail)
popd

echo.
echo [4/4] Installing the web app (this can take a few minutes)...
pushd frontend
call npm.cmd install --no-audit --no-fund || (popd & goto :fail)
popd

echo.
echo === Setup finished. Double-click windows-start.bat to run Smart Farm. ===
if not defined SF_NO_PAUSE pause
exit /b 0

:fail
echo.
echo *** Setup stopped. Copy the messages above and send them for help. ***
pause
exit /b 1
