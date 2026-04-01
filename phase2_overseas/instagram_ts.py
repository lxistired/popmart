"""
instagram_ts.py — Instagram 时序评论采集器 (Phase 2)
用途: 采集 @popmart/@lalalalisa_m/@davidbeckham 等账号帖子和评论时间戳，
     写入 instagram_posts + instagram_comments 表，构建时序热度指标。

运行: python -u instagram_ts.py [username1] [username2] ...
     默认: 采集 instagram_targets.json 中所有账号
"""

import os
import sys
import json
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Path setup — ensure shared modules are importable when run from any cwd
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from shared.db import init_db, batch_insert, get_latest_date
from shared.log import get_logger
from shared.rate import sleep_jitter
from shared.checkpoint import load_checkpoint, save_checkpoint

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SESSION_FILE = os.path.join(BASE_DIR, 'instagram_session.json')
CONFIG_FILE = os.path.join(BASE_DIR, 'config', 'instagram_targets.json')
API_LIMIT = 800   # Conservative limit to avoid ChallengeRequired

# Lazy import instagrapi — keep at top level so tests can mock it
try:
    from instagrapi import Client
    from instagrapi.exceptions import (
        ChallengeRequired,
        LoginRequired,
        ClientThrottledError,
        PleaseWaitFewMinutes,
        UserNotFound,
        PrivateAccount,
        MediaNotFound,
        ClientForbiddenError,
    )
    # Some versions use ClientLoginRequired instead of LoginRequired
    try:
        from instagrapi.exceptions import ClientLoginRequired
    except ImportError:
        ClientLoginRequired = LoginRequired

    try:
        from instagrapi.exceptions import RateLimitError
    except ImportError:
        RateLimitError = ClientThrottledError

except ImportError:
    # Allow import in test environments where instagrapi is mocked
    Client = None
    ChallengeRequired = Exception
    LoginRequired = Exception
    ClientLoginRequired = Exception
    ClientThrottledError = Exception
    PleaseWaitFewMinutes = Exception
    RateLimitError = Exception
    UserNotFound = Exception
    PrivateAccount = Exception
    MediaNotFound = Exception
    ClientForbiddenError = Exception


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------
def load_config(config_file=None):
    """Load instagram_targets.json config. Returns dict with accounts, since_date, etc."""
    path = config_file or CONFIG_FILE
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# init_client
# ---------------------------------------------------------------------------
def init_client(session_file=None):
    """
    Create instagrapi Client, load session file (NO login() call), set proxy + delay_range.
    Returns configured Client instance ready for API calls.
    """
    path = session_file or SESSION_FILE
    cl = Client()
    cl.delay_range = [3, 6]                        # IG-04: 3-6s between private API calls (conservative)
    cl.set_proxy('socks5://127.0.0.1:10808')       # v2rayN SOCKS5 proxy
    cl.load_settings(path)                          # Sets user_id + device UUIDs (no network call)
    # Call login() to refresh session tokens — when user_id is already set from
    # load_settings(), login() returns immediately without triggering ChallengeRequired.
    # Without this, session tokens expire and all API calls fail with login_required.
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, '.env'))
    username = os.getenv('IG_USERNAME')
    password = os.getenv('IG_PASSWORD')
    if username and password:
        cl.login(username, password)
        cl.dump_settings(path)  # Save refreshed session
    return cl


# ---------------------------------------------------------------------------
# get_cutoff_date
# ---------------------------------------------------------------------------
def get_cutoff_date(conn, shortcode, config_since_date):
    """
    Return the cutoff date for incremental scraping of a post's comments.
    = max(latest existing comment_date for this shortcode, config since_date).
    Returns None if no cutoff applies.
    """
    existing_latest = get_latest_date(conn, 'instagram_comments', 'comment_date',
                                      'shortcode', shortcode)
    if not existing_latest and not config_since_date:
        return None
    candidates = [d for d in [existing_latest, config_since_date] if d]
    return max(candidates)


# ---------------------------------------------------------------------------
# map_post_row
# ---------------------------------------------------------------------------
def map_post_row(media, username):
    """Map an instagrapi Media object to an instagram_posts row dict."""
    taken_at = getattr(media, 'taken_at', None)
    post_date = taken_at.strftime('%Y-%m-%d') if taken_at else None
    return {
        'shortcode':      media.code,
        'post_url':       f'https://www.instagram.com/p/{media.code}/',
        'account':        username,
        'caption':        media.caption_text or '',
        'likes':          media.like_count,
        'comments_count': media.comment_count,
        'post_date':      post_date,
        'source':         'instagrapi',
        'scraped_at':     datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# map_comment_row
# ---------------------------------------------------------------------------
def map_comment_row(comment, shortcode, username):
    """Map an instagrapi Comment object to an instagram_comments row dict."""
    created = comment.created_at_utc
    return {
        'shortcode':        shortcode,
        'comment_id':       str(comment.pk),
        'comment_text':     comment.text,
        'comment_date':     created.strftime('%Y-%m-%d'),
        'comment_datetime': created.isoformat(),
        'likes':            comment.like_count or 0,
        'author_name':      comment.user.username,
        'is_author_reply':  1 if comment.user.username == username else 0,
        'scraped_at':       datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# upsert_posts
# ---------------------------------------------------------------------------
def upsert_posts(conn, post_rows):
    """
    Upsert instagram_posts rows using INSERT OR REPLACE.
    Ensures existing rows with NULL metadata (post_date, likes, comments_count) get updated.
    This is necessary because 15 rows from the old Playwright scrape have NULL metadata.
    """
    if not post_rows:
        return
    columns = ['shortcode', 'post_url', 'account', 'caption', 'likes',
               'comments_count', 'post_date', 'source', 'scraped_at']
    cols_str = ', '.join(columns)
    placeholders = ', '.join(['?'] * len(columns))
    sql = f"INSERT OR REPLACE INTO instagram_posts ({cols_str}) VALUES ({placeholders})"
    data = [[r[c] for c in columns] for r in post_rows]
    conn.executemany(sql, data)
    conn.commit()


# ---------------------------------------------------------------------------
# scrape_account
# ---------------------------------------------------------------------------
def scrape_account(cl, conn, logger, api_counter, cfg_account, cfg, checkpoint_state):
    """
    Scrape posts and comments for one Instagram account.

    Args:
        cl: instagrapi Client (or mock)
        conn: SQLite connection
        logger: logger from get_logger()
        api_counter: mutable dict {'count': int} — shared across all accounts
        cfg_account: dict with 'username', 'label'
        cfg: full config dict (since_date, max_posts_per_account, max_comments_per_post)
        checkpoint_state: mutable checkpoint dict (updated in-place on API limit)
    """
    username = cfg_account['username']
    logger.info(f'=== Scraping @{username} ===')

    # --- Step 1: Resolve user_id (1 API call) ---
    if api_counter['count'] >= API_LIMIT:
        logger.warning(f'API limit reached before starting @{username}')
        save_checkpoint('instagram', checkpoint_state)
        return

    try:
        # Use private v1 API directly — public GQL endpoint is heavily rate-limited (429)
        user_info = cl.user_info_by_username_v1(username)
        user_id = user_info.pk
        api_counter['count'] += 1
        logger.info(f'@{username} user_id={user_id} (api_calls={api_counter["count"]})')
    except UserNotFound:
        logger.warning(f'@{username} not found, skipping')
        return
    except PrivateAccount:
        logger.warning(f'@{username} is private, skipping')
        return
    except Exception as e:
        logger.warning(f'@{username} user_id lookup failed: {e}, skipping')
        return

    # --- Step 2: Fetch posts with pagination ---
    # Resume from checkpoint: skip already-completed posts for this account
    in_progress = checkpoint_state.get('in_progress') or {}
    completed_shortcodes = set()
    if in_progress.get('account') == username:
        completed_shortcodes = set(in_progress.get('completed_post_shortcodes', []))

    end_cursor = in_progress.get('post_end_cursor', '') if in_progress.get('account') == username else ''
    all_posts = []

    while True:
        if api_counter['count'] >= API_LIMIT:
            logger.warning(f'API limit ({API_LIMIT}) reached during post fetch for @{username}')
            checkpoint_state['in_progress'] = {
                'account': username,
                'completed_post_shortcodes': list(completed_shortcodes),
                'post_end_cursor': end_cursor,
            }
            checkpoint_state['api_calls_today'] = api_counter['count']
            save_checkpoint('instagram', checkpoint_state)
            return

        try:
            medias, end_cursor = cl.user_medias_paginated(user_id, amount=12, end_cursor=end_cursor)
            api_counter['count'] += 1
        except (ChallengeRequired, LoginRequired, ClientLoginRequired) as e:
            logger.error(f'Auth error fetching posts for @{username}: {e}')
            checkpoint_state['in_progress'] = {
                'account': username,
                'completed_post_shortcodes': list(completed_shortcodes),
            }
            save_checkpoint('instagram', checkpoint_state)
            sys.exit(1)
        except (ClientThrottledError, PleaseWaitFewMinutes, RateLimitError) as e:
            logger.error(f'Rate limit fetching posts for @{username}: {e}')
            checkpoint_state['in_progress'] = {
                'account': username,
                'completed_post_shortcodes': list(completed_shortcodes),
            }
            save_checkpoint('instagram', checkpoint_state)
            sys.exit(1)

        all_posts.extend(medias)
        logger.info(f'  Fetched {len(medias)} posts (total={len(all_posts)}, cursor={end_cursor!r})')

        if not end_cursor or len(all_posts) >= cfg['max_posts_per_account']:
            break

        sleep_jitter(5.0)  # 帖子翻页间隔 2.5-7.5s

    # --- Step 3: Upsert posts to DB ---
    post_rows = [map_post_row(m, username) for m in all_posts]
    upsert_posts(conn, post_rows)
    logger.info(f'  Upserted {len(post_rows)} posts for @{username}')

    # --- Step 4: Fetch comments per post ---
    since_date = cfg.get('since_date', '')
    post_shortcodes_done = []

    for media in all_posts:
        shortcode = media.code

        # Skip posts already scraped in this checkpoint run
        if shortcode in completed_shortcodes:
            logger.info(f'  Skipping {shortcode} (already in checkpoint)')
            post_shortcodes_done.append(shortcode)
            continue

        if api_counter['count'] >= API_LIMIT:
            logger.warning(f'API limit ({API_LIMIT}) reached during comment fetch')
            checkpoint_state['in_progress'] = {
                'account': username,
                'completed_post_shortcodes': list(completed_shortcodes) + post_shortcodes_done,
            }
            checkpoint_state['api_calls_today'] = api_counter['count']
            save_checkpoint('instagram', checkpoint_state)
            return

        # Incremental: compute cutoff date for this post
        cutoff = get_cutoff_date(conn, shortcode, since_date)

        try:
            comments = cl.media_comments(media_id=media.pk, amount=cfg['max_comments_per_post'])
            api_counter['count'] += max(1, len(comments) // 20)
        except MediaNotFound:
            logger.warning(f'  Post {shortcode} not found, skipping')
            post_shortcodes_done.append(shortcode)
            continue
        except ClientForbiddenError:
            logger.warning(f'  Post {shortcode} access forbidden, skipping')
            post_shortcodes_done.append(shortcode)
            continue
        except (ChallengeRequired, LoginRequired, ClientLoginRequired) as e:
            logger.error(f'Auth error fetching comments for {shortcode}: {e}')
            checkpoint_state['in_progress'] = {
                'account': username,
                'completed_post_shortcodes': list(completed_shortcodes) + post_shortcodes_done,
            }
            save_checkpoint('instagram', checkpoint_state)
            sys.exit(1)
        except (ClientThrottledError, PleaseWaitFewMinutes, RateLimitError) as e:
            logger.error(f'Rate limit fetching comments for {shortcode}: {e}')
            checkpoint_state['in_progress'] = {
                'account': username,
                'completed_post_shortcodes': list(completed_shortcodes) + post_shortcodes_done,
            }
            save_checkpoint('instagram', checkpoint_state)
            sys.exit(1)

        # Filter by cutoff date and map to row dicts
        if cutoff:
            filtered = [c for c in comments if c.created_at_utc.strftime('%Y-%m-%d') > cutoff]
        else:
            filtered = comments

        if filtered:
            comment_rows = [map_comment_row(c, shortcode, username) for c in filtered]
            batch_insert(conn, 'instagram_comments', comment_rows,
                         ['shortcode', 'comment_id', 'comment_text', 'comment_date',
                          'comment_datetime', 'likes', 'author_name', 'is_author_reply',
                          'scraped_at'])
            logger.info(f'  {shortcode}: inserted {len(comment_rows)}/{len(comments)} comments '
                        f'(filtered={len(comments)-len(filtered)}, cutoff={cutoff})')
        else:
            logger.info(f'  {shortcode}: 0 new comments (cutoff={cutoff})')

        post_shortcodes_done.append(shortcode)
        sleep_jitter(4.0)  # 每个帖子评论采集后等 2-6s

    # Account complete — update checkpoint
    completed_accounts = checkpoint_state.get('completed_accounts', [])
    if username not in completed_accounts:
        completed_accounts.append(username)
    checkpoint_state['completed_accounts'] = completed_accounts
    checkpoint_state['in_progress'] = None
    checkpoint_state['api_calls_today'] = api_counter['count']
    save_checkpoint('instagram', checkpoint_state)
    logger.info(f'=== @{username} complete. Total api_calls={api_counter["count"]} ===')


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    """
    Entry point. Supports optional CLI args for specific accounts.
    Usage: python -u instagram_ts.py [popmart] [lalalalisa_m] [davidbeckham] ...
    Default: all accounts in instagram_targets.json
    """
    logger = get_logger('instagram')
    logger.info('instagram_ts.py starting')

    cfg = load_config()
    today_str = datetime.utcnow().strftime('%Y-%m-%d')

    # Load checkpoint
    checkpoint_state = load_checkpoint('instagram')
    # Reset API counter if this is a new day
    last_run_date = checkpoint_state.get('last_run_date', '')
    if last_run_date != today_str:
        logger.info(f'New day detected ({last_run_date} -> {today_str}), resetting API counter')
        checkpoint_state['api_calls_today'] = 0
        checkpoint_state['last_run_date'] = today_str
    api_counter = {'count': checkpoint_state.get('api_calls_today', 0)}
    logger.info(f'API calls today so far: {api_counter["count"]}')

    # Filter accounts based on CLI args (if any)
    requested = set(sys.argv[1:]) if len(sys.argv) > 1 else set()
    all_accounts = cfg.get('accounts', [])
    if requested:
        accounts = [a for a in all_accounts if a['username'] in requested]
        logger.info(f'Running specified accounts: {[a["username"] for a in accounts]}')
    else:
        accounts = all_accounts
        logger.info(f'Running all {len(accounts)} accounts from config')

    # Skip already-completed accounts (from checkpoint)
    completed = set(checkpoint_state.get('completed_accounts', []))
    in_progress_account = (checkpoint_state.get('in_progress') or {}).get('account')

    # Sort: process in-progress account first, then remaining by order in config
    def account_order(a):
        if a['username'] == in_progress_account:
            return 0
        if a['username'] in completed:
            return 2
        return 1

    accounts_sorted = sorted(accounts, key=account_order)

    # Init DB and client
    conn = init_db()
    try:
        cl = init_client()
        logger.info(f'Session loaded. user_id={cl.user_id}')

        for cfg_account in accounts_sorted:
            username = cfg_account['username']
            if username in completed and username != in_progress_account:
                logger.info(f'Skipping @{username} (already completed in checkpoint)')
                continue

            if api_counter['count'] >= API_LIMIT:
                logger.warning(f'API limit ({API_LIMIT}) reached. Stopping.')
                break

            try:
                scrape_account(cl, conn, logger, api_counter, cfg_account, cfg, checkpoint_state)
            except SystemExit:
                raise
            except Exception as e:
                logger.error(f'Unexpected error for @{username}: {e}')
                checkpoint_state['in_progress'] = {
                    'account': username,
                    'completed_post_shortcodes': [],
                }
                save_checkpoint('instagram', checkpoint_state)
                continue

        logger.info(f'instagram_ts.py finished. Total API calls: {api_counter["count"]}')

    finally:
        conn.close()


if __name__ == '__main__':
    main()
