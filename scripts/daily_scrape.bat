@echo off
REM scripts/daily_scrape.bat — Fully automated daily data pipeline (no user interaction)
REM WARNING: This script will FORCE CLOSE Chrome if it's running.
REM Schedule at a time when you won't be using Chrome (e.g., 06:00).
setlocal enabledelayedexpansion

set "PROJECT_DIR=C:\Users\lxxxxxx\Desktop\个人项目\popmart"
set "PHASE2_DIR=%PROJECT_DIR%\phase2_overseas"
set "LOG_FILE=%PROJECT_DIR%\scripts\logs\daily_scrape_%date:~0,4%%date:~5,2%%date:~8,2%.log"

REM Ensure log directory exists
if not exist "%PROJECT_DIR%\scripts\logs" mkdir "%PROJECT_DIR%\scripts\logs"

echo ============================================ >> "%LOG_FILE%"
echo   Pop Mart Daily Scrape >> "%LOG_FILE%"
echo   Started: %date% %time% >> "%LOG_FILE%"
echo ============================================ >> "%LOG_FILE%"

REM --- Check proxy ---
echo [%time%] Checking proxy... >> "%LOG_FILE%"
curl -s --socks5 127.0.0.1:10808 --max-time 10 https://www.google.com >NUL 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [%time%] ERROR: Proxy not reachable. Aborting. >> "%LOG_FILE%"
    goto :END
)
echo [%time%] Proxy OK >> "%LOG_FILE%"

REM --- Check and close Chrome ---
echo [%time%] Checking for Chrome processes... >> "%LOG_FILE%"
tasklist /FI "IMAGENAME eq chrome.exe" 2>NUL | find /I "chrome.exe" >NUL
if !ERRORLEVEL!==0 (
    echo [%time%] WARNING: Chrome is running. Closing it for scraping... >> "%LOG_FILE%"
    taskkill /IM chrome.exe /F >NUL 2>&1
    timeout /t 5 /nobreak >NUL
)
echo [%time%] Chrome check done >> "%LOG_FILE%"

REM --- Step 1: TikTok Scraper ---
echo [%time%] === Step 1: TikTok Scraper === >> "%LOG_FILE%"
cd /d "%PHASE2_DIR%"
python -u tiktok_browser.py >> "%LOG_FILE%" 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [%time%] WARNING: TikTok scraper exited with error !ERRORLEVEL! >> "%LOG_FILE%"
) else (
    echo [%time%] TikTok scraper completed OK >> "%LOG_FILE%"
)

REM --- Step 2: Instagram Scraper ---
echo [%time%] === Step 2: Instagram Scraper === >> "%LOG_FILE%"
cd /d "%PHASE2_DIR%"
python -u instagram_browser.py >> "%LOG_FILE%" 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [%time%] WARNING: Instagram scraper exited with error !ERRORLEVEL! >> "%LOG_FILE%"
) else (
    echo [%time%] Instagram scraper completed OK >> "%LOG_FILE%"
)

REM --- Step 3: Export JSON ---
echo [%time%] === Step 3: Export JSON === >> "%LOG_FILE%"
cd /d "%PHASE2_DIR%"
python -u export_json.py >> "%LOG_FILE%" 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [%time%] ERROR: Export failed. Skipping git push. >> "%LOG_FILE%"
    goto :END
)
echo [%time%] Export completed OK >> "%LOG_FILE%"

REM --- Step 4: Git Commit + Push ---
echo [%time%] === Step 4: Git Commit + Push === >> "%LOG_FILE%"
cd /d "%PROJECT_DIR%"
git add website/src/data/ website/public/data/ >> "%LOG_FILE%" 2>&1
git diff --cached --quiet
if !ERRORLEVEL!==0 (
    echo [%time%] No data changes to commit >> "%LOG_FILE%"
) else (
    git commit -m "data: daily update %date:~0,4%-%date:~5,2%-%date:~8,2%" >> "%LOG_FILE%" 2>&1
    git push origin main >> "%LOG_FILE%" 2>&1
    if !ERRORLEVEL! NEQ 0 (
        echo [%time%] WARNING: Git push failed >> "%LOG_FILE%"
    ) else (
        echo [%time%] Git push OK >> "%LOG_FILE%"
    )
)

:END
echo. >> "%LOG_FILE%"
echo [%time%] === Pipeline finished === >> "%LOG_FILE%"
endlocal
