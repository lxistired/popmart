@echo off
REM scripts/daily_update.bat — Launch Claude Code for daily data update
REM Schedule via Windows Task Scheduler at 08:00 daily

echo [%date% %time%] Launching Claude Code for daily update >> "%~dp0daily_update.log"

cd /d "C:\Users\lxxxxxx\Desktop\个人项目\popmart"

REM Launch Claude Code with update prompt
claude -p "执行每日海外数据更新：1) cd phase2_overseas 2) python -u tiktok_browser.py 采集新视频和评论 3) python -u instagram_browser.py 检查新帖子 4) python -u export_json.py 导出网站数据 5) git add website/src/data/ website/public/data/ && git commit -m 'data: daily update' && git push origin main。每步完成后报告结果，如遇到登录态过期等问题请记录并跳过。" --dangerously-skip-permissions

echo [%date% %time%] Claude Code session finished >> "%~dp0daily_update.log"
