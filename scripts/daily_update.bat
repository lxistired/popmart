@echo off
REM scripts/daily_update.bat — Daily data export + git push
REM Schedule via Windows Task Scheduler at 08:00 daily

cd /d "C:\Users\lxxxxxx\Desktop\个人项目\popmart"

echo [%date% %time%] Starting daily update >> scripts\daily_update.log

REM Export JSON data
cd phase2_overseas
python -u export_json.py ../website/src/data 2>> ..\scripts\daily_update.log
if errorlevel 1 (
    echo [%date% %time%] ERROR: export_json.py failed >> ..\scripts\daily_update.log
    exit /b 1
)

cd ..

REM Stage and commit
git add website/src/data/ website/public/data/
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "data: daily update %date%"
    git push origin main
    echo [%date% %time%] Pushed daily update >> scripts\daily_update.log
) else (
    echo [%date% %time%] No data changes >> scripts\daily_update.log
)
