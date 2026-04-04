@echo off
REM daily_scrape.bat - Fully automated daily data pipeline
REM WARNING: This script will FORCE CLOSE Chrome if running.
setlocal enabledelayedexpansion

REM Derive paths from script location (avoids Chinese path encoding issues)
set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."
set "PHASE2_DIR=%PROJECT_DIR%\phase2_overseas"

for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set "DT=%%I"
set "DATESTAMP=!DT:~0,8!"
set "LOG_FILE=%SCRIPT_DIR%logs\daily_scrape_!DATESTAMP!.log"

if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs"

echo ============================================ >> "!LOG_FILE!"
echo   Pop Mart Daily Scrape >> "!LOG_FILE!"
echo   Started: %date% %time% >> "!LOG_FILE!"
echo ============================================ >> "!LOG_FILE!"

echo [%time%] Checking proxy... >> "!LOG_FILE!"
curl -s --socks5 127.0.0.1:10808 --max-time 10 https://www.google.com >NUL 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [%time%] ERROR: Proxy not reachable. Aborting. >> "!LOG_FILE!"
    goto :END
)
echo [%time%] Proxy OK >> "!LOG_FILE!"

echo [%time%] Checking for Chrome processes... >> "!LOG_FILE!"
tasklist /FI "IMAGENAME eq chrome.exe" 2>NUL | find /I "chrome.exe" >NUL
if !ERRORLEVEL!==0 (
    echo [%time%] WARNING: Chrome is running. Closing it... >> "!LOG_FILE!"
    taskkill /IM chrome.exe /F >NUL 2>&1
    timeout /t 5 /nobreak >NUL
)
echo [%time%] Chrome check done >> "!LOG_FILE!"

echo [%time%] === Step 1: TikTok Scraper === >> "!LOG_FILE!"
cd /d "%PHASE2_DIR%"
python -u tiktok_browser.py >> "!LOG_FILE!" 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [%time%] WARNING: TikTok scraper exited with error !ERRORLEVEL! >> "!LOG_FILE!"
) else (
    echo [%time%] TikTok scraper completed OK >> "!LOG_FILE!"
)

echo [%time%] === Step 2: Instagram Scraper === >> "!LOG_FILE!"
cd /d "%PHASE2_DIR%"
python -u instagram_browser.py >> "!LOG_FILE!" 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [%time%] WARNING: Instagram scraper exited with error !ERRORLEVEL! >> "!LOG_FILE!"
) else (
    echo [%time%] Instagram scraper completed OK >> "!LOG_FILE!"
)

echo [%time%] === Step 3: Export JSON === >> "!LOG_FILE!"
cd /d "%PHASE2_DIR%"
python -u export_json.py >> "!LOG_FILE!" 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [%time%] ERROR: Export failed. Skipping git push. >> "!LOG_FILE!"
    goto :END
)
echo [%time%] Export completed OK >> "!LOG_FILE!"

echo [%time%] === Step 4: Git Commit + Push === >> "!LOG_FILE!"
cd /d "%PROJECT_DIR%"
git add website\src\data\ website\public\data\ >> "!LOG_FILE!" 2>&1
git diff --cached --quiet
if !ERRORLEVEL!==0 (
    echo [%time%] No data changes to commit >> "!LOG_FILE!"
) else (
    git commit -m "data: daily update !DT:~0,4!-!DT:~4,2!-!DT:~6,2!" >> "!LOG_FILE!" 2>&1
    git push origin main >> "!LOG_FILE!" 2>&1
    if !ERRORLEVEL! NEQ 0 (
        echo [%time%] WARNING: Git push failed >> "!LOG_FILE!"
    ) else (
        echo [%time%] Git push OK >> "!LOG_FILE!"
    )
)

:END
echo. >> "!LOG_FILE!"
echo [%time%] === Pipeline finished === >> "!LOG_FILE!"
endlocal