@echo off
setlocal enabledelayedexpansion
:: ================================================================
::  GameCore — Installation Script — Windows 10/11
::  Requires: winget, PowerShell 5+, run as Administrator
:: ================================================================

:: ── Check admin ──────────────────────────────────────────────────
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Run this script as Administrator.
    pause
    exit /b 1
)

echo.
echo  ╔══════════════════════════════════════╗
echo  ║   GameCore — Installer (Windows)     ║
echo  ╚══════════════════════════════════════╝
echo.

:: ── Prompts ──────────────────────────────────────────────────────
set /p "GAMECORE_PATH=  Install path [default: C:\GameCore] : "
if "%GAMECORE_PATH%"=="" set "GAMECORE_PATH=C:\GameCore"

set /p "WEB_PORT=  Backend port [default: 8765] : "
if "%WEB_PORT%"=="" set "WEB_PORT=8765"

echo.
echo   Install path : %GAMECORE_PATH%
echo   API port     : %WEB_PORT%
echo.
set /p "CONFIRM=  Continue? (y/N) : "
if /i not "%CONFIRM%"=="y" ( echo Aborted. & exit /b 0 )

:: ── Python 3.11 ──────────────────────────────────────────────────
echo.
echo [*] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Installing Python 3.11 via winget...
    winget install -e --id Python.Python.3.11 --silent --accept-source-agreements --accept-package-agreements
    if %errorlevel% neq 0 ( echo [ERROR] Python install failed. & pause & exit /b 1 )
    echo [OK] Python installed.
) else (
    echo [OK] Python already present.
)

:: ── Node.js 20 ───────────────────────────────────────────────────
echo.
echo [*] Checking Node.js...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Installing Node.js 20 via winget...
    winget install -e --id OpenJS.NodeJS.LTS --silent --accept-source-agreements --accept-package-agreements
    if %errorlevel% neq 0 ( echo [ERROR] Node.js install failed. & pause & exit /b 1 )
    echo [OK] Node.js installed.
) else (
    echo [OK] Node.js already present.
)

:: Refresh PATH after winget installs
call refreshenv >nul 2>&1

:: ── Copy files ───────────────────────────────────────────────────
echo.
echo [*] Setting up %GAMECORE_PATH%...
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

if /i not "%SCRIPT_DIR%"=="%GAMECORE_PATH%" (
    xcopy /E /I /Y "%SCRIPT_DIR%" "%GAMECORE_PATH%" >nul
    echo [OK] Copied to %GAMECORE_PATH%
) else (
    echo [OK] Already in place.
)

:: ── ROM directories ──────────────────────────────────────────────
echo.
echo [*] Creating ROM directories...
for %%d in (azahar cemu ryujinx dolphin duckstation gopher64 melonds mgba pcsx2 ppsspp rpcs3 covers) do (
    mkdir "%GAMECORE_PATH%\emu\%%d" >nul 2>&1
)
echo [OK] ROM directories ready.

:: ── Python venv + dependencies ───────────────────────────────────
echo.
echo [*] Setting up Python virtual environment...
python -m venv "%GAMECORE_PATH%\.venv"
if %errorlevel% neq 0 ( echo [ERROR] venv creation failed. & pause & exit /b 1 )
"%GAMECORE_PATH%\.venv\Scripts\pip" install -q -r "%GAMECORE_PATH%\backend\requirements.txt"
if %errorlevel% neq 0 ( echo [ERROR] pip install failed. & pause & exit /b 1 )
echo [OK] Python dependencies installed.

:: ── Frontend build ───────────────────────────────────────────────
echo.
echo [*] Building frontend...
cd /d "%GAMECORE_PATH%\frontend"
call npm install --silent
if %errorlevel% neq 0 ( echo [ERROR] npm install failed. & pause & exit /b 1 )
call npm run build
if %errorlevel% neq 0 ( echo [ERROR] frontend build failed. & pause & exit /b 1 )
echo [OK] Frontend built.

:: ── Electron dependencies ────────────────────────────────────────
echo.
echo [*] Installing Electron dependencies...
cd /d "%GAMECORE_PATH%\electron"
call npm install --silent
if %errorlevel% neq 0 ( echo [ERROR] Electron npm install failed. & pause & exit /b 1 )
echo [OK] Electron ready.

:: ── Startup scripts ──────────────────────────────────────────────
echo.
echo [*] Creating startup scripts...

:: Backend launcher
(
echo @echo off
echo set GAMECORE_PATH=%GAMECORE_PATH%
echo set GAMECORE_BACKEND_PORT=%WEB_PORT%
echo cd /d "%GAMECORE_PATH%"
echo "%GAMECORE_PATH%\.venv\Scripts\python.exe" -m uvicorn backend.main:app --host 0.0.0.0 --port %WEB_PORT% --log-level warning
) > "%GAMECORE_PATH%\start-backend.bat"

:: UI launcher (waits 5s for backend)
(
echo @echo off
echo timeout /t 5 /nobreak ^>nul
echo cd /d "%GAMECORE_PATH%\electron"
echo "%GAMECORE_PATH%\electron\node_modules\.bin\electron.cmd" "%GAMECORE_PATH%\electron\main.js"
) > "%GAMECORE_PATH%\start-ui.bat"

echo [OK] Startup scripts created.

:: ── Task Scheduler — autostart at login ──────────────────────────
echo.
echo [*] Registering autostart tasks...

schtasks /delete /tn "GameCore-Backend" /f >nul 2>&1
schtasks /create /tn "GameCore-Backend" /tr "\"%GAMECORE_PATH%\start-backend.bat\"" ^
  /sc onlogon /rl highest /f >nul
if %errorlevel% neq 0 ( echo [WARN] Could not create Backend task. & goto :skip_ui_task )

schtasks /delete /tn "GameCore-UI" /f >nul 2>&1
schtasks /create /tn "GameCore-UI" /tr "\"%GAMECORE_PATH%\start-ui.bat\"" ^
  /sc onlogon /rl highest /delay 0000:10 /f >nul
if %errorlevel% neq 0 ( echo [WARN] Could not create UI task. )

:skip_ui_task
echo [OK] Tasks registered — GameCore will start at next login.

:: ── Windows auto-login (optional) ────────────────────────────────
echo.
echo [?] Configure Windows auto-login (no password at boot)?
set /p "AUTOLOGIN=  Enable auto-login? (y/N) : "
if /i "%AUTOLOGIN%"=="y" (
    set /p "WIN_USER=  Windows username : "
    set /p "WIN_PASS=  Windows password (leave blank if none) : "
    reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v AutoAdminLogon /t REG_SZ /d 1 /f >nul
    reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultUserName /t REG_SZ /d "!WIN_USER!" /f >nul
    reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultPassword /t REG_SZ /d "!WIN_PASS!" /f >nul
    echo [OK] Auto-login configured for !WIN_USER!.
)

:: ── Final summary ────────────────────────────────────────────────
echo.
echo  ╔══════════════════════════════════════╗
echo  ║     Installation complete!           ║
echo  ╚══════════════════════════════════════╝
echo.
echo   Backend API  -^> http://localhost:%WEB_PORT%
echo   ROM Manager  -^> http://localhost:%WEB_PORT%/roms
echo.
echo   NOTE: Flatpak emulators are not available on Windows.
echo   Install emulators manually (Dolphin, PCSX2, RPCS3, etc.)
echo   and configure their paths in GameCore settings.
echo.
echo   Next steps:
echo   1. Reboot — GameCore starts automatically at login.
echo   2. Upload ROMs at http://localhost:%WEB_PORT%/roms
echo   3. Install firmware for DS/3DS/PS1/PS2/Wii U/PS3.
echo.
pause
