@echo off
rem Smart Farm - installs everything it needs on Windows 10/11, sets it up and starts it.
rem Installs (with winget): Python 3.12, Node.js LTS, PostgreSQL 16. Click "Yes" when Windows asks.
setlocal
cd /d "%~dp0"

echo.
echo ============================================================
echo   Smart Farm installer
echo   This installs Python 3.12, Node.js and PostgreSQL 16,
echo   then sets up Smart Farm. It can take 10-20 minutes.
echo   Click "Yes" if Windows asks for permission.
echo ============================================================
echo.

where winget >nul 2>nul
if errorlevel 1 (
  echo winget was not found on this computer.
  echo Install "App Installer" from the Microsoft Store, then run this file again:
  echo   https://apps.microsoft.com/detail/9NBLGGH4NNS1
  goto :fail
)

set "WG=winget install --exact --silent --accept-package-agreements --accept-source-agreements"

echo [1/3] Installing Python 3.12...
py -3.12 --version >nul 2>nul
if errorlevel 1 (
  %WG% --id Python.Python.3.12
) else (
  echo       Already installed.
)

echo.
echo [2/3] Installing Node.js LTS...
where node >nul 2>nul
if errorlevel 1 (
  %WG% --id OpenJS.NodeJS.LTS
) else (
  echo       Already installed.
)

echo.
echo [3/3] Installing PostgreSQL 16...
sc query state= all | findstr /i "postgresql" >nul
if errorlevel 1 (
  rem New install: give it a random password and pass it straight to the setup step.
  set "SF_PG_PASSWORD=SmartFarm%RANDOM%%RANDOM%%RANDOM%"
  call :install_postgres
  if errorlevel 1 goto :fail
) else (
  echo       PostgreSQL is already installed. Setup will ask for its password.
)

echo.
echo === Programs installed. Setting up Smart Farm... ===
set "SF_NO_PAUSE=1"
call windows-setup.bat
if errorlevel 1 goto :fail

echo.
echo === All done. Starting Smart Farm... ===
call windows-start.bat
exit /b 0

:install_postgres
%WG% --id PostgreSQL.PostgreSQL.16 --override "--mode unattended --unattendedmodeui minimal --superpassword %SF_PG_PASSWORD% --serverport 5432 --disable-components stackbuilder"
sc query state= all | findstr /i "postgresql" >nul
if errorlevel 1 (
  echo PostgreSQL did not install. Install it by hand from
  echo   https://www.postgresql.org/download/windows/
  echo then run windows-setup.bat.
  exit /b 1
)
exit /b 0

:fail
echo.
echo *** The installer stopped. Take a photo of this window and send it for help. ***
pause
exit /b 1
