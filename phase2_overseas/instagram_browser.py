"""
instagram_browser.py — Instagram 浏览器采集器 (DrissionPage)
绕过 API 限制，用 Chrome 真实登录态直接抓取 Instagram 网页版。

两种采集模式:
  1. 话题标签模式 — 从 #labubu #popmart 等标签页发现帖子，保证数据相关性
  2. 账号模式 — 采集指定账号（如 @popmart 官方号）的帖子

运行前: 确保 Chrome 浏览器已登录 Instagram，然后关闭所有 Chrome 窗口。
用法: python -u instagram_browser.py [--tags] [--accounts] [popmart] ...
     默认: 先采集话题标签，再采集账号
"""

import os
import sys
import json
import time
import random
import re
import sqlite3
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from shared.db import init_db, batch_insert, get_latest_date, upsert_post_metadata
from shared.log import get_logger
from shared.rate import sleep_jitter
from shared.checkpoint import load_checkpoint, save_checkpoint

CONFIG_FILE = os.path.join(BASE_DIR, 'config', 'instagram_targets.json')

# ---------------------------------------------------------------------------
# Browser setup
# ---------------------------------------------------------------------------
def create_browser():
    """Create DrissionPage browser using real Chrome profile (has IG login cookies)."""
    from DrissionPage import ChromiumPage, ChromiumOptions

    co = ChromiumOptions()
    # Use default Chrome user data dir (already logged into Instagram)
    local = os.environ.get('LOCALAPPDATA', '')
    chrome_user_data = os.path.join(local, 'Google', 'Chrome', 'User Data')
    if os.path.isdir(chrome_user_data):
        co.set_user_data_path(chrome_user_data)
    co.set_argument('--profile-directory', 'Default')

    # Proxy — v2rayN SOCKS5 via Chrome's native --proxy-server flag
    co.set_argument('--proxy-server', 'socks5://127.0.0.1:10808')

    co.set_argument('--window-size', '1400,900')
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.auto_port()  # Avoid port conflict

    page = ChromiumPage(co)
    return page


# ---------------------------------------------------------------------------
# Extract posts from hashtag / topic page
# ---------------------------------------------------------------------------
def scrape_hashtag_posts(page, hashtag, max_posts=60, logger=None):
    """Navigate to IG hashtag/topic page, scroll to load posts, extract shortcodes."""
    url = f'https://www.instagram.com/explore/tags/{hashtag}/'
    page.get(url)
    sleep_jitter(5.0)  # IG redirects /explore/tags/ → /popular/ (needs time)

    # Wait for redirect to settle — IG sends to /popular/{hashtag}/ which is fine
    final_url = (page.url or '').lower()
    if 'login' in final_url and 'popular' not in final_url:
        # Retry with /popular/ URL directly
        page.get(f'https://www.instagram.com/popular/{hashtag}/')
        sleep_jitter(4.0)
        final_url = (page.url or '').lower()
        if 'login' in final_url:
            if logger:
                logger.warning(f'#{hashtag}: redirected to login, skipping')
            return []

    posts = []
    seen_codes = set()
    no_new_count = 0

    for scroll_i in range(max_posts // 4 + 5):
        links = page.eles('xpath://a[contains(@href, "/p/") or contains(@href, "/reel/")]')
        for link in links:
            href = link.attr('href') or ''
            m = re.search(r'/(?:p|reel)/([A-Za-z0-9_-]+)', href)
            if m:
                code = m.group(1)
                if code not in seen_codes:
                    seen_codes.add(code)
                    posts.append(code)

        if len(posts) >= max_posts:
            break

        try:
            page.scroll.down(800)
        except Exception:
            # JS timeout on scroll — stop loading more, use what we have
            break
        sleep_jitter(2.0)

        if len(posts) == len(seen_codes) and scroll_i > 2:
            no_new_count += 1
            if no_new_count >= 3:
                break
        else:
            no_new_count = 0

    posts = posts[:max_posts]
    if logger:
        logger.info(f'#{hashtag}: found {len(posts)} posts')
    return posts


# ---------------------------------------------------------------------------
# Extract posts from account page
# ---------------------------------------------------------------------------
def scrape_account_posts(page, username, max_posts=50, logger=None):
    """Navigate to IG profile, scroll to load posts, extract shortcodes + metadata."""
    url = f'https://www.instagram.com/{username}/'
    page.get(url)
    sleep_jitter(3.0)

    # Check if page loaded
    if 'Page Not Found' in (page.title or '') or "Sorry, this page isn't available" in (page.html or ''):
        logger.warning(f'@{username} page not found or unavailable')
        return []

    # Scroll to load posts
    posts = []
    seen_codes = set()
    no_new_count = 0

    for scroll_i in range(max_posts // 4 + 5):  # rough estimate: ~12 posts per scroll
        # Extract post links from current page
        links = page.eles('xpath://a[contains(@href, "/p/") or contains(@href, "/reel/")]')
        for link in links:
            href = link.attr('href') or ''
            m = re.search(r'/(?:p|reel)/([A-Za-z0-9_-]+)', href)
            if m:
                code = m.group(1)
                if code not in seen_codes:
                    seen_codes.add(code)
                    posts.append(code)

        if len(posts) >= max_posts:
            break

        # Scroll down
        try:
            page.scroll.down(800)
        except Exception:
            break
        sleep_jitter(2.0)

        # Check if new posts loaded
        if len(posts) == len(seen_codes) and scroll_i > 2:
            no_new_count += 1
            if no_new_count >= 3:
                break
        else:
            no_new_count = 0

    posts = posts[:max_posts]
    if logger:
        logger.info(f'@{username}: found {len(posts)} posts')
    return posts


# ---------------------------------------------------------------------------
# Extract comments from a single post page
# ---------------------------------------------------------------------------
def _extract_comments_js(page):
    """Run JS to extract comments from Instagram post page DOM.
    Instagram uses nested <div>s (no <ul>/<li>) with <time datetime> markers.
    """
    return page.run_js(r'''
    const times = document.querySelectorAll('time[datetime]');
    const results = [];
    times.forEach((t, idx) => {
        const dt = t.getAttribute('datetime');
        // Walk up to L3 (3 levels up from <time>) = row with "username  timestamp"
        let L3 = t;
        for (let j = 0; j < 3; j++) L3 = L3 ? L3.parentElement : null;
        // Walk up to L4 (4 levels up) = row with "username  timestamp  comment_text"
        let L4 = L3 ? L3.parentElement : null;
        // Walk up to L6 (6 levels up) = full comment container with "赞 回复"
        let L6 = L4 ? L4.parentElement?.parentElement : null;
        if (!L4) return;

        // Find username from <a> with profile link pattern
        const links = (L6 || L4).querySelectorAll('a[href]');
        let username = '';
        for (const a of links) {
            const href = a.getAttribute('href') || '';
            if (/^\/[a-zA-Z0-9_.]+\/$/.test(href)
                && !href.includes('/explore/')
                && !href.includes('/p/')
                && !href.includes('/reel/')
                && !href.includes('/accounts/')) {
                username = href.replace(/\//g, '');
                break;
            }
        }
        if (!username) return;

        // Comment text = L4.textContent minus L3.textContent
        const l3Text = L3 ? L3.textContent : '';
        const l4Text = L4 ? L4.textContent : '';
        let commentText = l4Text;
        if (l3Text && l4Text.startsWith(l3Text)) {
            commentText = l4Text.slice(l3Text.length);
        }
        // Also remove trailing UI text (赞, 回复, like, reply, etc.)
        commentText = commentText.replace(/[\s]*(赞|回复|like|reply|likes|replies)[\s]*$/gi, '').trim();

        results.push({
            index: idx,
            datetime: dt,
            username: username,
            text: commentText.substring(0, 1000)
        });
    });
    return JSON.stringify(results);
    ''')


def scrape_post_comments(page, shortcode, username, max_comments=500, logger=None):
    """
    Open post page, load comments via scrolling/clicking, extract via JS.
    Instagram modern DOM uses nested divs (not ul/li) with <time> markers.
    Returns (post_info, comments_list).
    """
    import hashlib

    url = f'https://www.instagram.com/p/{shortcode}/'
    page.get(url)
    sleep_jitter(3.0)

    now = datetime.now(timezone.utc)
    scraped_at = now.isoformat()

    # --- Extract post metadata ---
    post_info = {
        'shortcode': shortcode,
        'post_url': url,
        'account': username,
        'caption': '',
        'likes': 0,
        'comments_count': 0,
        'post_date': None,
        'source': 'drissionpage',
        'scraped_at': scraped_at,
    }

    # Post date from first <time> element (the caption's timestamp)
    try:
        time_el = page.ele('xpath://time[@datetime]', timeout=5)
        if time_el:
            dt_str = time_el.attr('datetime')
            if dt_str:
                post_info['post_date'] = dt_str[:10]
    except:
        pass

    # --- Load more comments by clicking + scrolling the comment container ---
    prev_count = 0
    no_new_rounds = 0

    for load_round in range(max_comments // 5 + 10):
        # Click "load more" buttons (Chinese + English patterns)
        try:
            load_btn = page.ele(
                'xpath://button[contains(text(), "加载更多") or contains(text(), "查看") '
                'or contains(text(), "View") or contains(text(), "more") '
                'or contains(text(), "Load")]',
                timeout=2
            )
            if load_btn:
                load_btn.click()
                sleep_jitter(2.0)
        except:
            pass

        # Scroll the comment container (not the whole page)
        # Find the scrollable div containing <time> elements
        try:
            page.run_js('''
                const divs = document.querySelectorAll('div');
                for (const d of divs) {
                    const style = window.getComputedStyle(d);
                    if ((style.overflowY === 'scroll' || style.overflowY === 'auto')
                        && d.scrollHeight > d.clientHeight + 50
                        && d.querySelector('time[datetime]')) {
                        d.scrollTop += 600;
                        break;
                    }
                }
            ''')
        except Exception:
            pass  # JS timeout — stop scrolling this round
        sleep_jitter(1.5)

        # Check how many <time> elements are loaded
        cur_count = len(page.eles('tag:time'))
        if cur_count <= prev_count:
            no_new_rounds += 1
            if no_new_rounds >= 4:
                break
        else:
            no_new_rounds = 0
        prev_count = cur_count

        if cur_count >= max_comments:
            break

    # --- Extract all comments via JS ---
    try:
        raw = _extract_comments_js(page)
    except Exception:
        raw = None
    import json as _json
    try:
        entries = _json.loads(raw) if raw else []
    except:
        entries = []

    # First entry (index=0) is usually the caption if posted by the account owner
    comments = []
    seen_ids = set()
    for entry in entries:
        author = entry.get('username', '')
        text = entry.get('text', '').strip()
        dt = entry.get('datetime', '')
        idx = entry.get('index', -1)

        # Skip the caption (first entry by the account owner)
        if idx == 0 and author == username:
            post_info['caption'] = text[:500]
            continue

        if not text or not author:
            continue

        comment_date = dt[:10] if dt else None
        comment_datetime = dt if dt else None

        raw_id = f"{shortcode}_{author}_{text[:50]}_{comment_date or ''}"
        comment_id = 'web_' + hashlib.sha256(raw_id.encode()).hexdigest()[:16]

        if comment_id in seen_ids:
            continue
        seen_ids.add(comment_id)

        comments.append({
            'shortcode': shortcode,
            'comment_id': comment_id,
            'comment_text': text[:1000],
            'comment_date': comment_date,
            'comment_datetime': comment_datetime,
            'likes': 0,
            'author_name': author,
            'is_author_reply': 1 if author == username else 0,
            'scraped_at': scraped_at,
        })

        if len(comments) >= max_comments:
            break

    post_info['comments_count'] = len(comments)

    if logger:
        logger.info(f'  {shortcode}: {len(comments)} comments, post_date={post_info["post_date"]}')

    return post_info, comments


# ---------------------------------------------------------------------------
# Comment refresh logic
# ---------------------------------------------------------------------------
def _needs_comment_refresh(conn, shortcode):
    """Check if post needs comment re-scraping.
    Returns True for: new posts, never-scraped-comments posts, stale recent posts."""
    row = conn.execute(
        'SELECT last_comment_scraped_at, post_date FROM instagram_posts WHERE shortcode=?',
        (shortcode,)
    ).fetchone()
    if not row:
        return True  # new post
    last_scraped, post_date = row
    if last_scraped is None:
        return True  # never scraped comments
    # Re-scrape if post is recent (within 90 days) and last scrape > 7 days ago
    try:
        last_dt = datetime.fromisoformat(last_scraped)
        if post_date:
            post_dt = datetime.fromisoformat(post_date + 'T00:00:00+00:00') if len(post_date) == 10 else datetime.fromisoformat(post_date)
            now = datetime.now(timezone.utc)
            if (now - post_dt).days <= 90 and (now - last_dt).days > 7:
                return True
    except (ValueError, TypeError):
        pass
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _scrape_posts_batch(page, conn, post_codes, source_label, cfg, logger):
    """Scrape comments for a list of shortcodes. Returns count of posts done.
    Layer 2 fix: existing posts with NULL/stale last_comment_scraped_at get re-visited."""
    max_comments = cfg.get('max_comments_per_post', 500)
    comment_cols = ['shortcode', 'comment_id', 'comment_text', 'comment_date',
                    'comment_datetime', 'likes', 'author_name', 'is_author_reply', 'scraped_at']
    posts_done = 0

    for i, shortcode in enumerate(post_codes):
        # Check if already in DB
        existing = conn.execute(
            'SELECT 1 FROM instagram_posts WHERE shortcode=?', (shortcode,)
        ).fetchone()

        if existing and not _needs_comment_refresh(conn, shortcode):
            logger.info(f'  [{i+1}/{len(post_codes)}] {shortcode} comments fresh, skip')
            continue

        label = 'NEW' if not existing else 'REFRESH'
        logger.info(f'  [{i+1}/{len(post_codes)}] Opening {shortcode}... ({label})')

        try:
            post_info, comments = scrape_post_comments(
                page, shortcode, source_label,
                max_comments=max_comments, logger=logger
            )
            upsert_post_metadata(conn, post_info)
            if comments:
                batch_insert(conn, 'instagram_comments', comments, comment_cols)
            # Update last_comment_scraped_at
            conn.execute(
                "UPDATE instagram_posts SET last_comment_scraped_at=? WHERE shortcode=?",
                (datetime.now(timezone.utc).isoformat(), shortcode)
            )
            conn.commit()
            posts_done += 1
        except Exception as e:
            logger.warning(f'  {shortcode}: error: {e}')
            continue

        sleep_jitter(4.0)

    return posts_done


def backfill_comments(page, conn, cfg, logger=None):
    """
    Backfill comments for posts with last_comment_scraped_at IS NULL.
    Targets historically zero-comment posts (SCRP-01: 60 posts).
    Returns total comments saved.
    """
    posts_needing = conn.execute("""
        SELECT shortcode, account
        FROM instagram_posts
        WHERE last_comment_scraped_at IS NULL
        ORDER BY post_date DESC
        LIMIT 50
    """).fetchall()

    if not posts_needing:
        if logger:
            logger.info('backfill: no posts need comments')
        return 0

    if logger:
        logger.info(f'backfill: {len(posts_needing)} posts need comments')

    max_comments = cfg.get('max_comments_per_post', 500)
    comment_cols = ['shortcode', 'comment_id', 'comment_text', 'comment_date',
                    'comment_datetime', 'likes', 'author_name', 'is_author_reply', 'scraped_at']
    total_saved = 0

    for i, (shortcode, account) in enumerate(posts_needing):
        try:
            post_info, comments = scrape_post_comments(
                page, shortcode, account,
                max_comments=max_comments, logger=logger
            )
            upsert_post_metadata(conn, post_info)
            if comments:
                batch_insert(conn, 'instagram_comments', comments, comment_cols)
                total_saved += len(comments)
            # Update last_comment_scraped_at
            conn.execute(
                "UPDATE instagram_posts SET last_comment_scraped_at=? WHERE shortcode=?",
                (datetime.now(timezone.utc).isoformat(), shortcode)
            )
            conn.commit()
            if logger:
                logger.info(f'  backfill [{i+1}/{len(posts_needing)}] {shortcode}: {len(comments)} comments')
        except Exception as e:
            if logger:
                logger.warning(f'  backfill {shortcode}: error: {e}')
            continue

        sleep_jitter(4.0)

    return total_saved


def main():
    logger = get_logger('instagram_browser')
    logger.info('instagram_browser.py starting')

    # Load config
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        cfg = json.load(f)

    # Parse CLI args
    args = sys.argv[1:]
    run_tags = '--tags' in args or not any(a.startswith('--') for a in args)
    run_accounts = '--accounts' in args or not any(a.startswith('--') for a in args)
    explicit_names = [a for a in args if not a.startswith('--')]

    # Load checkpoint (for crash recovery only)
    checkpoint = load_checkpoint('instagram_browser')
    # Session-scoped: reset so all tags/accounts are re-scanned each run
    completed_tags = set()
    completed_accounts = set()

    # Init DB
    conn = init_db()

    # Create browser
    logger.info('Launching Chrome via DrissionPage...')
    try:
        page = create_browser()
    except Exception as e:
        logger.error(f'Failed to launch browser: {e}')
        logger.error('Make sure ALL Chrome windows are closed before running this script!')
        sys.exit(1)

    # Quick login check
    logger.info('Checking Instagram login status...')
    page.get('https://www.instagram.com/')
    sleep_jitter(3.0)

    if 'login' in (page.url or '').lower():
        logger.error('Not logged into Instagram! Please log in via Chrome first, then close Chrome and re-run.')
        page.quit()
        sys.exit(1)

    logger.info('Instagram login confirmed')

    try:
        # ===== Phase A: Hashtag discovery =====
        if run_tags:
            hashtags = cfg.get('hashtags', [])
            max_per_tag = cfg.get('max_posts_per_tag', 60)
            logger.info(f'=== Hashtag mode: {len(hashtags)} tags ===')

            for tag in hashtags:
                if tag in completed_tags:
                    logger.info(f'Skipping #{tag} (completed)')
                    continue

                logger.info(f'--- #{tag} ---')
                try:
                    post_codes = scrape_hashtag_posts(page, tag, max_posts=max_per_tag, logger=logger)
                except Exception as e:
                    logger.warning(f'#{tag}: browser error during discovery: {e}')
                    logger.info('Reconnecting browser...')
                    try:
                        page.quit()
                    except:
                        pass
                    page = create_browser()
                    page.get('https://www.instagram.com/')
                    sleep_jitter(5.0)
                    try:
                        post_codes = scrape_hashtag_posts(page, tag, max_posts=max_per_tag, logger=logger)
                    except Exception as e2:
                        logger.error(f'#{tag}: still failing after reconnect: {e2}')
                        continue

                if not post_codes:
                    logger.warning(f'#{tag}: no posts found')
                    completed_tags.add(tag)
                    continue

                done = _scrape_posts_batch(page, conn, post_codes, f'hashtag:{tag}', cfg, logger)
                completed_tags.add(tag)
                save_checkpoint('instagram_browser', {
                    'completed_tags': list(completed_tags),
                    'completed_accounts': list(completed_accounts),
                })
                logger.info(f'#{tag} complete: {done} new posts scraped')
                sleep_jitter(5.0)

        # ===== Phase B: Account scraping =====
        if run_accounts:
            accounts = cfg.get('accounts', [])
            if explicit_names:
                accounts = [a for a in accounts if a['username'] in explicit_names]

            for acct in accounts:
                username = acct['username']
                if username in completed_accounts:
                    logger.info(f'Skipping @{username} (completed)')
                    continue

                logger.info(f'=== Scraping @{username} ===')
                post_codes = scrape_account_posts(
                    page, username,
                    max_posts=cfg.get('max_posts_per_account', 50),
                    logger=logger
                )

                if not post_codes:
                    logger.warning(f'@{username}: no posts found, skipping')
                    completed_accounts.add(username)
                    continue

                done = _scrape_posts_batch(page, conn, post_codes, username, cfg, logger)
                completed_accounts.add(username)
                save_checkpoint('instagram_browser', {
                    'completed_tags': list(completed_tags),
                    'completed_accounts': list(completed_accounts),
                })
                logger.info(f'@{username} complete: {done} posts scraped')
                sleep_jitter(5.0)

        # ===== Phase C: Backfill comments for posts with no comment data =====
        logger.info('=== Backfilling comments for zero-comment posts ===')
        backfilled = backfill_comments(page, conn, cfg, logger=logger)
        logger.info(f'Backfill complete: {backfilled} comments saved')

    except KeyboardInterrupt:
        logger.info('Interrupted by user — saving progress')
        save_checkpoint('instagram_browser', {
            'completed_tags': list(completed_tags),
            'completed_accounts': list(completed_accounts),
        })
    except Exception as e:
        logger.error(f'Unexpected error: {e}')
        import traceback
        traceback.print_exc()
    finally:
        try:
            page.quit()
        except:
            pass
        conn.close()

    # Final stats
    conn2 = sqlite3.connect(os.path.join(BASE_DIR, 'overseas_data.db'))
    posts_total = conn2.execute('SELECT COUNT(*) FROM instagram_posts').fetchone()[0]
    comments_total = conn2.execute("SELECT COUNT(*) FROM instagram_comments WHERE comment_id NOT LIKE 'synth_%'").fetchone()[0]
    conn2.close()
    logger.info(f'Done. DB totals: {posts_total} posts, {comments_total} real comments')


if __name__ == '__main__':
    main()
