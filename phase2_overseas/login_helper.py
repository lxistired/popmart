"""
login_helper.py - 用 ChromePW profile 打开浏览器，登录 Amazon / TikTok / Instagram
登录完成后按 Enter，session 自动保存到 ChromePW，之后每次跑 ts_pw.py 都有效。
"""
import os, sys
CHROME_PROFILE = os.path.join(os.path.expanduser("~"), "AppData", "Local", "ChromePW")

print("启动 Chrome (ChromePW profile + stealth)...")
print("请在浏览器里：")
print("  1. 登录 Amazon  (https://www.amazon.com)")
print("  2. 登录 TikTok  (https://www.tiktok.com/login)")
print("  3. 登录 Instagram (https://www.instagram.com)")
print()
print("登录完成后回到这里按 Enter，session 会自动保存。")

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

with Stealth().use_sync(sync_playwright()) as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=CHROME_PROFILE,
        channel="chrome",
        headless=False,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        viewport={"width": 1400, "height": 900}
    )
    page = ctx.new_page()
    page.goto("https://www.amazon.com/ap/signin", wait_until="domcontentloaded")

    page2 = ctx.new_page()
    page2.goto("https://www.tiktok.com/login", wait_until="domcontentloaded")

    page3 = ctx.new_page()
    page3.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded")

    print("\nChrome 已打开，请在三个标签页里分别登录：")
    print("  Tab 1: Amazon")
    print("  Tab 2: TikTok")
    print("  Tab 3: Instagram")
    print("\n登录完成后告诉 Claude，会自动关闭浏览器并保存 session。")
    print("浏览器将保持打开 10 分钟...")
    import time
    time.sleep(600)
    ctx.close()

print("\n✅ Session 已保存到 ChromePW。现在可以运行 ts_pw.py 了。")
