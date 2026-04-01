"""
setup_instagram_session.py — Interactive script to create instagram_session.json.
Run once before Phase 2. May require SMS/email challenge response.
Usage: cd phase2_overseas && python -u setup_instagram_session.py
"""
import os
import sys
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

load_dotenv(os.path.join(BASE_DIR, '.env'))

SESSION_FILE = os.path.join(BASE_DIR, 'instagram_session.json')


def main():
    username = os.getenv('IG_USERNAME')
    password = os.getenv('IG_PASSWORD')

    if not username or not password:
        print("[ERROR] IG_USERNAME or IG_PASSWORD not set in .env file")
        print("  Edit phase2_overseas/.env and add your Instagram credentials, then re-run.")
        sys.exit(1)

    if username == 'your_instagram_username':
        print("[ERROR] .env still contains placeholder values — edit .env with real credentials")
        sys.exit(1)

    print(f"[INFO] Setting up Instagram session for @{username}")
    print(f"[INFO] Session file: {SESSION_FILE}")
    print("[WARN] This may trigger an SMS/email challenge. Have your phone/inbox ready.")
    print()

    try:
        from instagrapi import Client
    except ImportError:
        print("[ERROR] instagrapi not installed. Run: pip install instagrapi==2.3.0")
        sys.exit(1)

    cl = Client()
    cl.delay_range = [1, 3]

    if os.path.exists(SESSION_FILE):
        print(f"[INFO] Existing session file found at {SESSION_FILE}. Loading...")
        try:
            cl.load_settings(SESSION_FILE)
            cl.login(username, password)
            print("[OK] Session re-used successfully (no new device UUID generated)")
        except Exception as e:
            print(f"[WARN] Load_settings failed: {e}")
            print("[INFO] Falling back to fresh login...")
            cl2 = Client()
            cl2.delay_range = [1, 3]
            cl2.login(username, password)
            cl2.dump_settings(SESSION_FILE)
            print(f"[OK] New session saved to {SESSION_FILE}")
    else:
        print("[INFO] No existing session. Starting fresh login...")
        print("[WARN] Instagram may send a challenge code. Watch for SMS or email.")
        try:
            cl.login(username, password)
            cl.dump_settings(SESSION_FILE)
            print(f"[OK] Session saved to {SESSION_FILE}")
        except Exception as e:
            print(f"[ERROR] Login failed: {e}")
            print("  If you see ChallengeRequired, Instagram sent a code to your SMS/email.")
            print("  Retry after confirming your account identity via Instagram app.")
            sys.exit(1)

    # Verify session is usable
    try:
        user_id = cl.user_id_from_username(username)
        print(f"[OK] Session verified — @{username} user_id={user_id}")
        print(f"[OK] instagram_session.json ready for Phase 2")
    except Exception as e:
        print(f"[WARN] Session verification failed: {e}")
        print("  Session file was saved but could not be verified. Check manually.")


if __name__ == "__main__":
    main()
