@echo off
setlocal enabledelayedexpansion
:: ================================================================
::  GameCore — OTA Update Script — Windows
::  Called by the backend when "Apply Update" is clicked in Settings.
:: ================================================================

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [update] ERROR: Run as Administrator.
    exit /b 1
)

set "REPO=p4v1c/GamecoreRenew"
set "ASSET=gamecore-ota.tar.gz"
set "TMP_DIR=%TEMP%\gamecore_ota"
if "%GAMECORE_PATH%"=="" set "GAMECORE_PATH=C:\GameCore"

echo [update] Checking latest release...
set "API_URL=https://api.github.com/repos/%REPO%/releases/latest"

for /f "delims=" %%i in ('powershell -NoProfile -Command "(Invoke-RestMethod -Uri '%API_URL%').tag_name"') do set "LATEST_TAG=%%i"
for /f "delims=" %%i in ('powershell -NoProfile -Command "(Invoke-RestMethod -Uri '%API_URL%').assets | Where-Object { $_.name -eq '%ASSET%' } | Select-Object -ExpandProperty browser_download_url"') do set "DOWNLOAD_URL=%%i"

if "%DOWNLOAD_URL%"=="" (
    echo [update] ERROR: Asset '%ASSET%' not found in release %LATEST_TAG%
    exit /b 1
)

echo [update] Latest: %LATEST_TAG%
echo [update] Downloading %ASSET%...

if exist "%TMP_DIR%" rmdir /s /q "%TMP_DIR%"
mkdir "%TMP_DIR%"

powershell -NoProfile -Command "Invoke-WebRequest -Uri '%DOWNLOAD_URL%' -OutFile '%TMP_DIR%\%ASSET%'"
if %errorlevel% neq 0 ( echo [update] ERROR: Download failed. & exit /b 1 )
echo [update] Download complete.

echo [update] Extracting...
tar -xzf "%TMP_DIR%\%ASSET%" -C "%TMP_DIR%"
if %errorlevel% neq 0 ( echo [update] ERROR: Extraction failed. & exit /b 1 )

echo [update] Stopping GameCore processes...
schtasks /end /tn "GameCore-UI" >nul 2>&1
schtasks /end /tn "GameCore-Backend" >nul 2>&1
timeout /t 3 /nobreak >nul
taskkill /f /im electron.exe >nul 2>&1
taskkill /f /im python.exe >nul 2>&1

echo [update] Installing new files...
:: Exclude .venv, emu/ and config/ to preserve user data
robocopy "%TMP_DIR%" "%GAMECORE_PATH%" /E /XD ".venv" "emu" "config" /XF "*.db" >nul
echo [update] Files installed.

echo [update] Updating Python dependencies...
"%GAMECORE_PATH%\.venv\Scripts\pip.exe" install -q -r "%GAMECORE_PATH%\backend\requirements.txt"
if %errorlevel% neq 0 ( echo [update] WARN: pip install failed. )

echo [update] Rebuilding frontend...
cd /d "%GAMECORE_PATH%\frontend"
call npm install --silent
call npm run build
if %errorlevel% neq 0 ( echo [update] ERROR: Frontend build failed. & exit /b 1 )

echo [update] Restarting GameCore...
schtasks /run /tn "GameCore-Backend" >nul 2>&1
timeout /t 5 /nobreak >nul
schtasks /run /tn "GameCore-UI" >nul 2>&1

echo [update] Done! Now running %LATEST_TAG%
