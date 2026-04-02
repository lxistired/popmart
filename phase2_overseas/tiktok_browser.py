"""
tiktok_browser.py — TikTok 视频元数据采集器 (DrissionPage)

使用 DrissionPage 采集 TikTok 话题标签下的视频元数据（create_time, views, likes等），
构建内容发布热度时序。不需要登录。

原理：
  1. 访问 /tag/{hashtag} 页面，滚动加载，从 DOM 提取视频 ID 列表
  2. 逐个访问 /video/{id} 页面，从 __UNIVERSAL_DATA_FOR_REHYDRATION__ JSON 提取详情
  3. 写入 tiktok_videos 表

用法: python -u tiktok_browser.py [hashtag1 hashtag2 ...]
     默认: 采集 config/tiktok_targets.json 中所有关键词
"""

import os, sys, json, re, time, random
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from shared.db import init_db, batch_insert, upsert_video_metadata
from shared.log import get_logger
from shared.rate import sleep_jitter
from shared.checkpoint import load_checkpoint, save_checkpoint

CONFIG_FILE = os.path.join(BASE_DIR, 'config', 'tiktok_targets.json')
TIKTOK_COOKIES_FILE = os.path.join(BASE_DIR, 'tiktok_cookies.json')

# TikTok login cookies that matter
TIKTOK_COOKIE_NAMES = {
    'sessionid', 'sid_tt', 'sid_guard', 'uid_tt', 'passport_csrf_token',
    'passport_csrf_token_default', 'tt-target-idc', 'tt-target-idc-sign',
    'odin_tt', 'msToken', 'ttwid', 's_v_web_id',
}


def save_tiktok_cookies(page, logger=None):
    """Save TikTok cookies to JSON file for persistence across sessions."""
    try:
        cookies = page.cookies(all_domains=False)
        if not cookies:
            cookies = page.cookies()
        tiktok_cookies = []
        for c in cookies:
            name = c.get('name', '')
            if name in TIKTOK_COOKIE_NAMES or '.tiktok.com' in c.get('domain', ''):
                tiktok_cookies.append(c)
        if tiktok_cookies:
            data = {'saved_at': datetime.now().isoformat(), 'cookies': tiktok_cookies}
            with open(TIKTOK_COOKIES_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            if logger:
                logger.info(f'Saved {len(tiktok_cookies)} TikTok cookies to {TIKTOK_COOKIES_FILE}')
    except Exception as e:
        if logger:
            logger.warning(f'Failed to save cookies: {e}')


def load_tiktok_cookies(page, logger=None):
    """Load TikTok cookies from JSON file and inject into browser via CDP."""
    if not os.path.exists(TIKTOK_COOKIES_FILE):
        if logger:
            logger.info('No saved TikTok cookies found')
        return False
    try:
        with open(TIKTOK_COOKIES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cookies = data.get('cookies', [])
        if not cookies:
            return False
        # Navigate to TikTok first
        page.get('https://www.tiktok.com/')
        time.sleep(2)
        # Use CDP to set cookies — more reliable than page.set.cookies()
        injected = 0
        for c in cookies:
            try:
                params = {
                    'name': c['name'],
                    'value': c['value'],
                    'domain': c.get('domain', '.tiktok.com'),
                    'path': c.get('path', '/'),
                }
                if c.get('secure'):
                    params['secure'] = True
                if c.get('httpOnly'):
                    params['httpOnly'] = True
                if c.get('expires') or c.get('expirationDate'):
                    exp = c.get('expires') or c.get('expirationDate')
                    if isinstance(exp, (int, float)) and exp > 0:
                        params['expires'] = exp
                page.run_cdp('Network.setCookie', **params)
                injected += 1
            except:
                pass
        if logger:
            logger.info(f'Injected {injected}/{len(cookies)} cookies via CDP')
        # Refresh to apply
        page.get('https://www.tiktok.com/')
        time.sleep(3)
        return injected > 0
    except Exception as e:
        if logger:
            logger.warning(f'Failed to load cookies: {e}')
        return False


def wait_for_manual_login(page, logger=None):
    """Navigate to TikTok login and wait for user to complete login manually."""
    if logger:
        logger.info('Opening TikTok login page — please log in manually in the browser window...')
    page.get('https://www.tiktok.com/login')
    time.sleep(2)

    for i in range(120):  # max 30 minutes
        time.sleep(15)
        try:
            url = page.url or ''
            cookies = page.cookies()
            cookie_names = {c.get('name', '') for c in cookies} if cookies else set()
            has_session = bool(cookie_names & {'sessionid', 'sid_tt'})
            if has_session:
                if logger:
                    logger.info('Login detected! Session cookie found.')
                save_tiktok_cookies(page, logger=logger)
                return True
            if i % 4 == 0 and logger:
                logger.info(f'  Waiting for login... ({i*15}s)')
        except:
            pass
    return False


def check_tiktok_login(page, logger=None):
    """
    Check if TikTok is logged in. Try in order:
    1. Current cookies (Chrome Profile)
    2. Saved cookie JSON
    3. Manual login
    Returns True if logged in, False if user gave up.
    """
    # Check 1: already logged in via Chrome Profile
    page.get('https://www.tiktok.com/')
    time.sleep(3)
    url = page.url or ''
    cookies = page.cookies()
    cookie_names = {c.get('name', '') for c in cookies} if cookies else set()
    if bool(cookie_names & {'sessionid', 'sid_tt'}) and 'login' not in url.lower():
        if logger:
            logger.info('TikTok login confirmed (Chrome Profile)')
        save_tiktok_cookies(page, logger=logger)  # backup to JSON
        return True

    # Check 2: inject saved cookies
    if logger:
        logger.info('No login in Chrome Profile, trying saved cookies...')
    if load_tiktok_cookies(page, logger=logger):
        url = page.url or ''
        cookies = page.cookies()
        cookie_names = {c.get('name', '') for c in cookies} if cookies else set()
        if bool(cookie_names & {'sessionid', 'sid_tt'}) and 'login' not in url.lower():
            if logger:
                logger.info('TikTok login confirmed (from saved cookies)')
            return True

    # Check 3: manual login
    if logger:
        logger.info('Saved cookies expired or missing. Need manual login.')
    return wait_for_manual_login(page, logger=logger)

# 毒品相关过滤词（#molly 搜索结果可能包含毒品内容）
DRUG_KEYWORDS = re.compile(
    r'\b(mdma|ecstasy|xtc|rolling|drug|pill|trippy|psychedelic|molly\s+water|'
    r'molly\s+capsule|lsd|cocaine|weed)\b', re.IGNORECASE
)


def create_browser():
    """Create DrissionPage browser using real Chrome profile (has TikTok login cookies)."""
    from DrissionPage import ChromiumPage, ChromiumOptions
    co = ChromiumOptions()
    # Use default Chrome user data dir (already logged into TikTok)
    local = os.environ.get('LOCALAPPDATA', '')
    chrome_user_data = os.path.join(local, 'Google', 'Chrome', 'User Data')
    if os.path.isdir(chrome_user_data):
        co.set_user_data_path(chrome_user_data)
    co.set_argument('--profile-directory', 'Default')
    co.set_argument('--proxy-server', 'socks5://127.0.0.1:10808')
    co.set_argument('--window-size', '1400,900')
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.auto_port()
    return ChromiumPage(co)


def collect_video_ids(page, hashtag, max_scrolls=8, logger=None):
    """访问 /tag/{hashtag} 页面，滚动加载，提取视频 ID 列表。"""
    # hashtag 不能有空格，用于 URL
    tag_slug = hashtag.replace(' ', '')
    url = f'https://www.tiktok.com/tag/{tag_slug}'

    if logger:
        logger.info(f'  Loading /tag/{tag_slug}...')
    page.get(url)
    sleep_jitter(8.0)

    # 滚动加载更多视频
    for i in range(max_scrolls):
        try:
            page.scroll.down(random.randint(800, 1200))
        except:
            pass
        time.sleep(random.uniform(1.5, 3.0))

    # 从 DOM 提取视频 ID
    video_ids = page.run_js(r'''
        const seen = new Set();
        document.querySelectorAll('a[href*="/video/"]').forEach(a => {
            const m = a.href.match(/\/video\/(\d+)/);
            if (m) seen.add(m[1]);
        });
        return JSON.stringify([...seen]);
    ''')
    ids = json.loads(video_ids)
    if logger:
        logger.info(f'  /tag/{tag_slug}: {len(ids)} video IDs found')
    return ids


def fetch_video_detail(page, video_id, logger=None):
    """访问视频页面，提取完整元数据（createTime, stats 等）。"""
    url = f'https://www.tiktok.com/@_/video/{video_id}'
    page.get(url)
    sleep_jitter(random.uniform(4, 7))

    html = page.html or ''
    m = re.search(
        r'<script[^>]*id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
        html, re.S
    )
    if not m:
        return None

    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None

    scope = data.get('__DEFAULT_SCOPE__', {})
    detail = scope.get('webapp.video-detail', {})
    item = detail.get('itemInfo', {}).get('itemStruct', {})
    if not item or not item.get('createTime'):
        return None

    stats = item.get('stats', {})
    author_info = item.get('author', {})

    return {
        'video_id': str(video_id),
        'author': author_info.get('uniqueId', ''),
        'title': (item.get('desc', '') or '')[:500],
        'views': stats.get('playCount', 0),
        'likes': stats.get('diggCount', 0),
        'comments_count': stats.get('commentCount', 0),
        'shares': stats.get('shareCount', 0),
        'create_time': str(int(item.get('createTime', 0))),
    }


def fetch_video_comments(page, video_id, max_comments=500, logger=None):
    """
    Collect all comments for a video by intercepting TikTok's /api/comment/list/ API.
    Must click the comment icon first to open the comment panel, then scroll to paginate.
    Returns list of dicts ready for tiktok_comments table.
    """
    url = f'https://www.tiktok.com/@_/video/{video_id}'

    # Start listening for comment API responses before page load
    page.listen.start('api/comment/list')
    page.get(url)
    sleep_jitter(random.uniform(4, 7))

    # Click the comment icon to open comment panel — this triggers the first API call
    try:
        page.run_js('''
            const el = document.querySelector('[data-e2e="comment-icon"]');
            if (el) el.click();
        ''')
    except:
        pass
    sleep_jitter(random.uniform(2, 3))

    now_str = datetime.now(timezone.utc).isoformat()
    comments = []
    seen_ids = set()
    no_new_rounds = 0

    for attempt in range(max_comments // 20 + 10):
        # Scroll comment panel to trigger next page
        try:
            page.run_js('''
                const divs = document.querySelectorAll('div');
                for (const d of divs) {
                    const style = window.getComputedStyle(d);
                    if ((style.overflowY === "scroll" || style.overflowY === "auto")
                        && d.scrollHeight > d.clientHeight + 50) {
                        d.scrollTop += 600;
                        break;
                    }
                }
            ''')
        except:
            pass
        sleep_jitter(1.5)

        # Collect any intercepted responses
        prev_count = len(comments)
        for resp in page.listen.steps(timeout=3):
            try:
                data = resp.response.body
                if not isinstance(data, dict):
                    import json as _json
                    data = _json.loads(data)
                raw_comments = data.get('comments') or []
                for c in raw_comments:
                    cid = str(c.get('cid', ''))
                    if not cid or cid in seen_ids:
                        continue
                    seen_ids.add(cid)
                    create_ts = int(c.get('create_time', 0))
                    comment_datetime = datetime.fromtimestamp(create_ts, tz=timezone.utc).isoformat() if create_ts else None
                    comment_date = comment_datetime[:10] if comment_datetime else None
                    comments.append({
                        'video_id': str(video_id),
                        'comment_id': cid,
                        'comment_text': (c.get('text') or '')[:1000],
                        'comment_date': comment_date,
                        'comment_datetime': comment_datetime,
                        'likes': c.get('digg_count', 0),
                        'author_name': (c.get('user') or {}).get('unique_id', ''),
                        'scraped_at': now_str,
                    })
                has_more = data.get('has_more', 0)
                if not has_more:
                    page.listen.stop()
                    return comments
            except:
                pass

        if len(comments) == prev_count:
            no_new_rounds += 1
            if no_new_rounds >= 4:
                break
        else:
            no_new_rounds = 0

        if len(comments) >= max_comments:
            break

    page.listen.stop()
    return comments


def is_drug_content(title):
    """检查标题是否包含毒品相关内容。"""
    return bool(DRUG_KEYWORDS.search(title or ''))


def _needs_comment_refresh(conn, video_id):
    """Check if a video needs comment re-scraping.
    Returns True if:
      - last_comment_scraped_at IS NULL (never scraped)
      - create_time is within 90 days AND last_comment_scraped_at is older than 7 days
    """
    row = conn.execute(
        'SELECT last_comment_scraped_at, create_time FROM tiktok_videos WHERE video_id=?',
        (video_id,)
    ).fetchone()
    if not row:
        return True
    last_scraped, create_time = row
    if last_scraped is None:
        return True
    # Check if recent video with stale comment scrape
    try:
        now = datetime.now(timezone.utc)
        ninety_days_ago_ts = int((now - timedelta(days=90)).timestamp())
        if int(create_time) > ninety_days_ago_ts:
            seven_days_ago = (now - timedelta(days=7)).isoformat()
            if last_scraped < seven_days_ago:
                return True
    except (ValueError, TypeError):
        pass
    return False


def scrape_hashtag(page, conn, keyword, max_videos=50, since_date=None, logger=None):
    """采集一个话题标签的视频元数据并写入数据库。返回 (new_count, skip_count)。

    Rebuilt with three-layer fix:
      - Processes ALL discovered videos (not just new ones)
      - Uses upsert_video_metadata for each video (refreshes views/likes/comments_count/shares)
      - Selectively fetches comments based on _needs_comment_refresh()
    """
    if logger:
        logger.info(f'=== #{keyword} ===')

    # 收集视频 ID
    video_ids = collect_video_ids(page, keyword, logger=logger)
    if not video_ids:
        if logger:
            logger.info(f'  No videos found for #{keyword}')
        return 0, 0

    # 限制数量
    if len(video_ids) > max_videos:
        video_ids = video_ids[:max_videos]

    # 查询已有数据 (for logging only — we process ALL videos)
    existing = set()
    rows = conn.execute('SELECT video_id FROM tiktok_videos').fetchall()
    for r in rows:
        existing.add(r[0])

    new_count = len([vid for vid in video_ids if vid not in existing])
    if logger:
        logger.info(f'  {new_count} new / {len(video_ids) - new_count} existing — processing ALL')

    now_str = datetime.now(timezone.utc).isoformat()
    drug_filtered = 0
    upserted = 0
    comments_fetched = 0

    fail_streak = 0
    for i, vid_id in enumerate(video_ids):
        try:
            detail = fetch_video_detail(page, vid_id, logger)
            fail_streak = 0  # reset on success (even if no data)
            if not detail:
                if logger:
                    logger.info(f'  [{i+1}/{len(video_ids)}] {vid_id}: no data (private/deleted?)')
                continue

            # 毒品过滤
            if is_drug_content(detail['title']):
                drug_filtered += 1
                if logger:
                    logger.info(f'  [{i+1}/{len(video_ids)}] {vid_id}: FILTERED (drug content)')
                continue

            # since_date 过滤
            if since_date and detail['create_time']:
                video_date = datetime.fromtimestamp(int(detail['create_time']))
                if video_date < since_date:
                    continue

            detail['source'] = f'tag/{keyword}'
            detail['scraped_at'] = now_str

            # Layer 3: upsert metadata (insert new or refresh views/likes/comments_count/shares)
            upsert_video_metadata(conn, detail)
            upserted += 1

            is_new = vid_id not in existing
            # Layer 2: selective comment fetch
            needs_comments = is_new or _needs_comment_refresh(conn, vid_id)
            tag = 'NEW' if is_new else ('REFRESH' if needs_comments else 'meta-only')

            if needs_comments:
                try:
                    vid_comments = fetch_video_comments(page, vid_id, logger=logger)
                    if vid_comments:
                        _save_comments(conn, vid_comments)
                        comments_fetched += len(vid_comments)
                        if logger:
                            logger.info(f'    -> {len(vid_comments)} comments saved')
                    # Update last_comment_scraped_at after successful comment scrape
                    conn.execute(
                        'UPDATE tiktok_videos SET last_comment_scraped_at=? WHERE video_id=?',
                        (datetime.now(timezone.utc).isoformat(), vid_id)
                    )
                    conn.commit()
                except Exception as e:
                    if logger:
                        logger.warning(f'    comments error: {e}')

            ct_str = datetime.fromtimestamp(int(detail['create_time'])).strftime('%Y-%m-%d')
            if logger:
                logger.info(
                    f'  [{i+1}/{len(video_ids)}] {vid_id} | {ct_str} | '
                    f'views={detail["views"]:,} | @{detail["author"]} | {tag}'
                )

            # Mark as existing for subsequent iterations in this run
            existing.add(vid_id)

        except Exception as e:
            fail_streak += 1
            if logger:
                logger.warning(f'  [{i+1}/{len(video_ids)}] {vid_id}: error: {e}')
            if fail_streak >= 3:
                if logger:
                    logger.warning(f'  3 consecutive failures — browser may be disconnected, stopping #{keyword}')
                break
            continue

        # 每 10 个视频休息更久，避免触发 TikTok 反爬
        if (i + 1) % 10 == 0:
            delay = random.uniform(15, 25)
            if logger:
                logger.info(f'  Anti-detection pause: {delay:.0f}s')
            sleep_jitter(delay)
        else:
            sleep_jitter(random.uniform(5, 9))

    if logger:
        logger.info(f'  #{keyword}: {upserted} upserted, {comments_fetched} comments, {drug_filtered} drug-filtered')
    return upserted, drug_filtered


def _save_videos(conn, videos):
    """Save videos using upsert (Layer 3 fix). Used by scrape_user_videos."""
    for v in videos:
        upsert_video_metadata(conn, v)


def _save_comments(conn, comments):
    cols = ['video_id', 'comment_id', 'comment_text', 'comment_date',
            'comment_datetime', 'likes', 'author_name', 'scraped_at']
    batch_insert(conn, 'tiktok_comments', comments, cols)


def scrape_user_videos(page, conn, username, max_videos=30, logger=None):
    """采集用户的视频列表。Processes ALL discovered videos via upsert."""
    if logger:
        logger.info(f'=== @{username} ===')

    url = f'https://www.tiktok.com/@{username}'
    page.get(url)
    sleep_jitter(8.0)

    # 滚动加载
    for _ in range(6):
        try:
            page.scroll.down(random.randint(800, 1200))
        except:
            pass
        time.sleep(random.uniform(1.5, 2.5))

    # 提取视频 ID
    video_ids_json = page.run_js(r'''
        const seen = new Set();
        document.querySelectorAll('a[href*="/video/"]').forEach(a => {
            const m = a.href.match(/\/video\/(\d+)/);
            if (m) seen.add(m[1]);
        });
        return JSON.stringify([...seen]);
    ''')
    video_ids = json.loads(video_ids_json)[:max_videos]
    if logger:
        logger.info(f'  @{username}: {len(video_ids)} video IDs')

    # Query existing for logging (process ALL, not just new)
    existing = set(r[0] for r in conn.execute('SELECT video_id FROM tiktok_videos').fetchall())
    new_count = len([vid for vid in video_ids if vid not in existing])
    if logger:
        logger.info(f'  {new_count} new / {len(video_ids) - new_count} existing — processing ALL')

    now_str = datetime.now(timezone.utc).isoformat()
    upserted = 0

    for i, vid_id in enumerate(video_ids):
        try:
            detail = fetch_video_detail(page, vid_id, logger)
            if not detail:
                continue
            detail['source'] = f'user/{username}'
            detail['scraped_at'] = now_str

            # Upsert metadata
            upsert_video_metadata(conn, detail)
            upserted += 1

            is_new = vid_id not in existing
            needs_comments = is_new or _needs_comment_refresh(conn, vid_id)
            tag = 'NEW' if is_new else ('REFRESH' if needs_comments else 'meta-only')

            if needs_comments:
                try:
                    vid_comments = fetch_video_comments(page, vid_id, logger=logger)
                    if vid_comments:
                        _save_comments(conn, vid_comments)
                        if logger:
                            logger.info(f'    -> {len(vid_comments)} comments saved')
                    conn.execute(
                        'UPDATE tiktok_videos SET last_comment_scraped_at=? WHERE video_id=?',
                        (datetime.now(timezone.utc).isoformat(), vid_id)
                    )
                    conn.commit()
                except Exception as e:
                    if logger:
                        logger.warning(f'    comments error: {e}')

            existing.add(vid_id)

            ct_str = datetime.fromtimestamp(int(detail['create_time'])).strftime('%Y-%m-%d')
            if logger:
                logger.info(f'  [{i+1}/{len(video_ids)}] {vid_id} | {ct_str} | views={detail["views"]:,} | {tag}')
        except Exception as e:
            if logger:
                logger.warning(f'  [{i+1}/{len(video_ids)}] {vid_id}: error: {e}')
            continue

        sleep_jitter(random.uniform(3, 6))

    return upserted


def _ensure_browser_global(page, logger=None):
    """如果浏览器断连则重建。可在 main() 之外调用。"""
    try:
        _ = page.url
        return page
    except:
        if logger:
            logger.info('Browser disconnected — relaunching...')
        try:
            page.quit()
        except:
            pass
        time.sleep(5)
        return create_browser()


def backfill_comments(page, conn, logger=None):
    """
    Backfill comments for videos with last_comment_scraped_at IS NULL.
    Catches both zero-comment videos AND videos that were never comment-scraped.
    Returns total comments saved.
    """
    videos_needing_comments = conn.execute("""
        SELECT v.video_id, v.author, v.comments_count
        FROM tiktok_videos v
        WHERE v.last_comment_scraped_at IS NULL
        ORDER BY v.create_time DESC
        LIMIT 50
    """).fetchall()

    if not videos_needing_comments:
        if logger:
            logger.info('backfill: no videos need comments')
        return 0

    if logger:
        logger.info(f'backfill: {len(videos_needing_comments)} videos need comments')

    total_saved = 0
    for i, (vid_id, author, expected_count) in enumerate(videos_needing_comments):
        page = _ensure_browser_global(page, logger=logger)
        try:
            comments = fetch_video_comments(page, vid_id, logger=logger)
            if comments:
                _save_comments(conn, comments)
                total_saved += len(comments)
            # Update last_comment_scraped_at after successful scrape
            conn.execute(
                'UPDATE tiktok_videos SET last_comment_scraped_at=? WHERE video_id=?',
                (datetime.now(timezone.utc).isoformat(), vid_id)
            )
            conn.commit()
            if logger:
                logger.info(
                    f'  backfill [{i+1}/{len(videos_needing_comments)}] '
                    f'{vid_id} @{author}: {len(comments)} comments saved'
                )
        except Exception as e:
            if logger:
                logger.warning(f'  backfill {vid_id}: error: {e}')
            continue

        # Pacing: every 10 videos rest longer
        if (i + 1) % 10 == 0:
            delay = random.uniform(20, 35)
            if logger:
                logger.info(f'  backfill pause: {delay:.0f}s')
            sleep_jitter(delay)
        else:
            sleep_jitter(random.uniform(6, 10))

    return total_saved


def main():
    logger = get_logger('tiktok_browser')
    logger.info('tiktok_browser.py starting')

    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        cfg = json.load(f)

    queries = cfg.get('queries', [])
    accounts = cfg.get('accounts', [])
    max_videos = cfg.get('max_videos_per_query', 50)
    since_str = cfg.get('since_date', '2024-01-01')
    since_date = datetime.strptime(since_str, '%Y-%m-%d')

    # CLI override
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    run_backfill = '--backfill' in sys.argv
    if args:
        queries = [q for q in queries if q['keyword'] in args]

    # Checkpoint — session-scoped: reset completed set so all keywords are re-scanned
    checkpoint = load_checkpoint('tiktok_browser')
    completed = set()  # Layer 1 fix: never skip keywords across runs

    # DB
    conn = init_db()
    total_in_db = conn.execute('SELECT COUNT(*) FROM tiktok_videos').fetchone()[0]
    logger.info(f'Videos already in DB: {total_in_db}')

    # Browser
    logger.info('Launching Chrome...')
    try:
        page = create_browser()
    except Exception as e:
        logger.error(f'Failed to launch browser: {e}')
        logger.error('Make sure ALL Chrome windows are closed before running this script!')
        sys.exit(1)

    # Login check — tries Chrome Profile → saved cookies → manual login
    logger.info('Checking TikTok login status...')
    if not check_tiktok_login(page, logger=logger):
        logger.error('TikTok login failed. Exiting.')
        page.quit()
        sys.exit(1)

    total_new = 0

    try:
        # --backfill: skip hashtag/account collection, go straight to comment backfill
        if run_backfill:
            logger.info('=== Backfilling comments for existing videos ===')
            page = _ensure_browser_global(page, logger=logger)
            backfilled = backfill_comments(page, conn, logger=logger)
            logger.info(f'Backfill complete: {backfilled} comments saved')
        else:
            # Hashtag queries
            for i, q in enumerate(queries):
                keyword = q['keyword']
                if keyword in completed:
                    logger.info(f'[{i+1}/{len(queries)}] #{keyword} — skipped (completed)')
                    continue

                page = _ensure_browser_global(page, logger=logger)

                logger.info(f'[{i+1}/{len(queries)}]')
                new, filtered = scrape_hashtag(
                    page, conn, keyword,
                    max_videos=max_videos, since_date=since_date, logger=logger
                )
                total_new += new

                completed.add(keyword)
                save_checkpoint('tiktok_browser', {
                    'completed': list(completed), 'total_new': total_new
                })

                if i < len(queries) - 1:
                    delay = random.uniform(40, 70)
                    logger.info(f'  Waiting {delay:.0f}s between hashtags...')
                    sleep_jitter(delay)

            # User accounts
            for acc in accounts:
                username = acc['username']
                if f'@{username}' in completed:
                    logger.info(f'@{username} — skipped (completed)')
                    continue

                page = _ensure_browser_global(page, logger=logger)
                new = scrape_user_videos(page, conn, username, logger=logger)
                total_new += new
                completed.add(f'@{username}')
                save_checkpoint('tiktok_browser', {
                    'completed': list(completed), 'total_new': total_new
                })

            # Also backfill comments after hashtag collection
            logger.info('=== Backfilling comments for existing videos ===')
            page = _ensure_browser_global(page, logger=logger)
            backfilled = backfill_comments(page, conn, logger=logger)
            logger.info(f'Backfill complete: {backfilled} comments saved')

    except KeyboardInterrupt:
        logger.info('Interrupted — saving checkpoint')
        save_checkpoint('tiktok_browser', {
            'completed': list(completed), 'total_new': total_new
        })
    finally:
        try:
            page.quit()
        except:
            pass
        conn.close()

    # Final stats
    import sqlite3
    conn2 = sqlite3.connect(os.path.join(BASE_DIR, 'overseas_data.db'))
    total = conn2.execute('SELECT COUNT(*) FROM tiktok_videos').fetchone()[0]
    by_source = conn2.execute(
        'SELECT source, COUNT(*) FROM tiktok_videos GROUP BY source ORDER BY COUNT(*) DESC'
    ).fetchall()
    conn2.close()

    logger.info(f'Done. Total videos in DB: {total} (+{total_new} new)')
    for src, cnt in by_source:
        logger.info(f'  {src}: {cnt}')


if __name__ == '__main__':
    main()
