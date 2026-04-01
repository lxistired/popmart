"""
amazon_reviews_browser.py — Amazon 评论日期采集器 (DrissionPage)

使用独立 Chrome Profile 采集 12 个 ASIN 的评论日期，构建销量代理时序。
不影响用户自己的 Chrome。首次运行需在弹出的浏览器窗口登录 Amazon，
之后登录态自动保存在 chrome_data/ 目录，无需重复登录。

用法: python -u amazon_reviews_browser.py [ASIN1 ASIN2 ...]
     默认: 采集 config/amazon_targets.json 中所有 ASIN

重要背景（2026-03-29 调试发现）：
  Amazon 已弃用 URL 翻页参数（?pageNumber=N）。翻页机制改为 JavaScript
  无限滚动（medleyReviewsAjaxUrl）。对于被识别为自动化的会话，Amazon 将
  medleyReviewsAjaxUrl 设为空字符串，禁用分页，无论 URL 参数如何变化
  都只返回同样 8 条"安全"评论。因此：
  1. 每次抓取前必须先 warmup（模拟人类浏览行为）
  2. 同一 ASIN 要用多个排序/过滤组合以最大化唯一评论数
  3. check_pagination_enabled() 可检测分页是否真正开放
"""

import os, sys, json, re, time, random
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from shared.db import init_db, batch_insert
from shared.log import get_logger
from shared.rate import sleep_jitter
from shared.checkpoint import load_checkpoint, save_checkpoint

CONFIG_FILE = os.path.join(BASE_DIR, 'config', 'amazon_targets.json')
COOKIES_FILE = os.path.join(BASE_DIR, 'amazon_cookies.json')
SCRIPT_CHROME_PROFILE = os.path.join(BASE_DIR, 'chrome_data')

MONTH_MAP = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12
}

# Amazon 登录态核心 cookie
AMAZON_COOKIE_NAMES = {
    'at-main', 'sess-at-main', 'session-id',
    'session-id-time', 'session-token', 'ubid-main', 'x-main',
}


# ═══════════════════════════════════════════════════════════════════════════
# Browser setup — 独立 Profile，不碰用户 Chrome
# ═══════════════════════════════════════════════════════════════════════════

REAL_CHROME_PROFILE = os.path.join(
    os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'User Data'
)


def create_browser(use_real_profile=False):
    """启动 Chrome。use_real_profile=True 时用用户真实 Profile（需先关 Chrome）。"""
    from DrissionPage import ChromiumPage, ChromiumOptions
    co = ChromiumOptions()
    if use_real_profile:
        if not os.path.isdir(REAL_CHROME_PROFILE):
            raise RuntimeError(f'Chrome profile not found: {REAL_CHROME_PROFILE}')
        co.set_user_data_path(REAL_CHROME_PROFILE)
    else:
        os.makedirs(SCRIPT_CHROME_PROFILE, exist_ok=True)
        co.set_user_data_path(SCRIPT_CHROME_PROFILE)
    co.set_argument('--proxy-server', 'socks5://127.0.0.1:10808')
    co.set_argument('--window-size', '1400,900')
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.auto_port()
    return ChromiumPage(co)


# ═══════════════════════════════════════════════════════════════════════════
# Cookie 持久化 — JSON 备份层（Chrome Profile 是主层）
# ═══════════════════════════════════════════════════════════════════════════

def save_amazon_cookies(page):
    """提取 Amazon 核心 cookie 存到 JSON 文件（备份层）。"""
    try:
        all_cookies = page.cookies(all_domains=False)
        amazon_cookies = [c for c in all_cookies
                          if isinstance(c, dict) and c.get('name') in AMAZON_COOKIE_NAMES]
        data = {
            'saved_at': datetime.now().isoformat(),
            'cookies': amazon_cookies,
        }
        with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except:
        pass


def load_amazon_cookies(page):
    """从 JSON 备份注入 Amazon cookie。返回 True 如果成功注入。"""
    if not os.path.isfile(COOKIES_FILE):
        return False
    age_days = (time.time() - os.path.getmtime(COOKIES_FILE)) / 86400
    if age_days > 30:
        return False
    try:
        with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cookies = data.get('cookies', [])
        if not cookies:
            return False
        page.get('https://www.amazon.com/')
        time.sleep(2)
        for c in cookies:
            try:
                page.set.cookies(c)
            except:
                pass
        return True
    except:
        return False


# ═══════════════════════════════════════════════════════════════════════════
# 登录检测 + 自动/交互登录
# ═══════════════════════════════════════════════════════════════════════════

def _has_reviews(page):
    """安全检测当前页是否有评论内容。"""
    try:
        return bool(page.eles('css:[data-hook="review-date"]', timeout=3))
    except:
        return False


def _is_signin_page(page):
    """检查是否在 Amazon 登录页。"""
    try:
        url = (page.url or '').lower()
        return 'ap/signin' in url or 'ap/mfa' in url
    except:
        return False


def ensure_reviews_access(page, test_asin, logger=None):
    """确保能访问 Amazon 评论页。三步尝试：
    1. 直接访问（靠 Chrome Profile 里的 cookie）
    2. 从 JSON 备份注入 cookie 再试
    3. 弹出登录页让用户手动登录
    成功后保存 cookie 到 JSON 备份。
    """
    reviews_url = f'https://www.amazon.com/product-reviews/{test_asin}/?pageNumber=1&sortBy=recent'

    # --- Step 1: 直接访问（Chrome Profile 可能已有 cookie）---
    if logger:
        logger.info('Checking reviews access (Chrome Profile)...')
    page.get(reviews_url)
    time.sleep(5)
    if _has_reviews(page):
        if logger:
            logger.info('Reviews accessible — Chrome Profile cookies valid')
        save_amazon_cookies(page)
        return True

    # --- Step 2: 从 JSON 备份注入 cookie ---
    if os.path.isfile(COOKIES_FILE):
        if logger:
            logger.info('Profile cookies expired. Trying JSON backup...')
        if load_amazon_cookies(page):
            page.get(reviews_url)
            time.sleep(5)
            if _has_reviews(page):
                if logger:
                    logger.info('Reviews accessible — JSON backup cookies valid')
                return True
        if logger:
            logger.info('JSON backup cookies also expired')

    # --- Step 3: 交互式登录 ---
    if logger:
        logger.info('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
        logger.info('请在弹出的浏览器窗口中登录 Amazon')
        logger.info('登录完成后会自动检测并继续采集')
        logger.info('最多等待 5 分钟')
        logger.info('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')

    # 如果已经在登录页就不用再导航
    if not _is_signin_page(page):
        page.get(reviews_url)
        time.sleep(3)

    for attempt in range(150):  # 5 min = 150 × 2s
        time.sleep(2)
        try:
            # 检查是否已经能看到评论
            if _has_reviews(page):
                if logger:
                    logger.info('Login detected — saving cookies')
                save_amazon_cookies(page)
                return True
            # 检查 URL 是否已离开登录页
            url = page.url or ''
            if 'product-reviews' in url and not _is_signin_page(page):
                time.sleep(3)
                if _has_reviews(page):
                    save_amazon_cookies(page)
                    if logger:
                        logger.info('Login successful — cookies saved')
                    return True
        except:
            pass
        if attempt > 0 and attempt % 15 == 0 and logger:
            logger.info(f'  Still waiting for login... ({attempt*2}s)')

    if logger:
        logger.error('Login timeout (5 min). Please re-run the script.')
    return False


# ═══════════════════════════════════════════════════════════════════════════
# Session warmup — 建立浏览器信任度，让 Amazon 开放分页
# ═══════════════════════════════════════════════════════════════════════════

def warmup_session(page, asins, logger=None):
    """
    在抓取评论前模拟人类浏览行为，提升 Amazon 会话信任度。

    背景：Amazon 对自动化会话禁用评论分页（medleyReviewsAjaxUrl 为空）。
    新建的 chrome_data/ Profile 没有浏览历史，会立刻被识别为 bot。
    Warmup 通过访问主页、搜索页、产品详情页来积累自然行为信号。

    参数:
        asins: 将要抓取的 ASIN 列表（warmup 时先浏览这些产品页）
        返回: True 如果 warmup 后分页已开放，False 如果仍被限制
    """
    if logger:
        logger.info('Starting session warmup (simulating human browsing)...')

    try:
        # Step 1: Homepage
        page.get('https://www.amazon.com/')
        sleep_jitter(random.uniform(4, 6))
        _human_scroll(page, steps=3)

        # Step 2: Search for "pop mart" (mimics how a real user would arrive)
        page.get('https://www.amazon.com/s?k=pop+mart+blind+box')
        sleep_jitter(random.uniform(5, 8))
        _human_scroll(page, steps=4)

        # Step 3: Visit 2-3 product pages (not review pages) from the ASIN list
        warmup_asins = asins[:min(3, len(asins))]
        for asin in warmup_asins:
            page.get(f'https://www.amazon.com/dp/{asin}')
            sleep_jitter(random.uniform(6, 10))
            _human_scroll(page, steps=6)
            # Click on ratings histogram (signals interest in reviews)
            try:
                hist = page.ele('css:[data-hook="rating-histogram-chart-link"]', timeout=3)
                if hist:
                    hist.click()
                    sleep_jitter(3.0)
                    page.scroll.to_bottom()
                    sleep_jitter(2.0)
            except:
                pass
            sleep_jitter(random.uniform(3, 5))

        # Step 4: Check if pagination is now enabled on a test ASIN
        enabled = check_pagination_enabled(page, warmup_asins[0], logger)
        if logger:
            if enabled:
                logger.info('Warmup complete — pagination ENABLED (medleyReviewsAjaxUrl populated)')
            else:
                logger.info('Warmup complete — pagination still LIMITED (medleyReviewsAjaxUrl empty)')
                logger.info('  Will use multi-sort strategy to maximize unique reviews')
        return enabled

    except Exception as e:
        if logger:
            logger.warning(f'Warmup error (non-fatal): {e}')
        return False


def _human_scroll(page, steps=4):
    """Scroll down in natural steps, like a human reading the page."""
    for _ in range(steps):
        try:
            page.scroll.down(random.randint(300, 600))
        except:
            pass
        time.sleep(random.uniform(0.5, 1.5))


def check_pagination_enabled(page, asin, logger=None):
    """
    Check if Amazon's JavaScript pagination is enabled for this session.

    Returns True if medleyReviewsAjaxUrl is populated (pagination works),
    False if it is empty (bot session, only static 8 reviews available).

    Also logs the presence of the "limited selection" warning banner.
    """
    try:
        url = f'https://www.amazon.com/product-reviews/{asin}/?sortBy=recent'
        page.get(url)
        sleep_jitter(5.0)

        html_raw = page.html or ''
        import html as _html_mod
        decoded = _html_mod.unescape(html_raw)

        # Check medleyReviewsAjaxUrl in page config
        m = re.search(r'"medleyReviewsAjaxUrl"\s*:\s*"([^"]*)"', decoded)
        medley_url = m.group(1) if m else ''

        # Check for "limited selection" banner
        limited = 'limited selection of reviews' in html_raw

        if logger:
            logger.info(f'  Pagination check for {asin}:')
            logger.info(f'    medleyReviewsAjaxUrl: {medley_url!r}')
            logger.info(f'    Limited-selection banner: {limited}')

        return bool(medley_url)
    except:
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Date parsing
# ═══════════════════════════════════════════════════════════════════════════

def parse_review_date(raw_text):
    """Parse Amazon review date. Handles US + UK formats."""
    if not raw_text:
        return None
    m = re.search(r'on\s+(\w+)\s+(\d+),\s+(\d{4})', raw_text)
    if m:
        mon = MONTH_MAP.get(m.group(1).lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(2)):02d}"
    m = re.search(r'on\s+(\d+)\s+(\w+)\s+(\d{4})', raw_text)
    if m:
        mon = MONTH_MAP.get(m.group(2).lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}"
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Block/captcha detection
# ═══════════════════════════════════════════════════════════════════════════

def is_blocked(page):
    """检测 captcha/robot 页面。Amazon 评论页可能 URL 显示 ax/claim 但内容正常。"""
    try:
        title = (page.title or '').lower()
        url = (page.url or '').lower()
        if 'robot' in title or 'captcha' in url:
            return True
        if page.eles('css:[data-hook="review-date"]', timeout=2):
            return False
        if 'ap/signin' in url:
            return True
    except:
        pass
    return False


# ═══════════════════════════════════════════════════════════════════════════
# Extract reviews from a single page
# ═══════════════════════════════════════════════════════════════════════════

def extract_reviews_from_page(page, asin, ip, logger=None):
    """Extract review data from the current page (works on both /dp/ and /product-reviews/)."""
    reviews = []
    now_str = datetime.now(timezone.utc).isoformat()

    try:
        review_els = page.eles('css:[data-hook="review"]')
    except:
        return reviews
    if not review_els:
        return reviews

    for rev in review_els:
        try:
            date_el = rev.ele('css:[data-hook="review-date"]', timeout=1)
            raw_date = date_el.text if date_el else ''
            parsed_date = parse_review_date(raw_date)

            rating = None
            try:
                star_el = rev.ele('css:[data-hook="review-star-rating"] .a-icon-alt', timeout=1)
                if star_el:
                    m = re.search(r'([\d.]+)\s+out\s+of', star_el.text or '')
                    if m:
                        rating = float(m.group(1))
            except:
                pass

            title = ''
            try:
                title_el = rev.ele('css:[data-hook="review-title"] span', timeout=1)
                if title_el:
                    title = (title_el.text or '').strip()[:200]
            except:
                pass

            verified = 0
            try:
                if rev.ele('css:[data-hook="avp-badge"]', timeout=1):
                    verified = 1
            except:
                pass

            reviews.append({
                'asin': asin, 'ip': ip,
                'review_date': parsed_date, 'review_date_raw': raw_date[:300],
                'review_title': title, 'rating': rating,
                'verified': verified, 'scraped_at': now_str,
            })
        except:
            continue

    return reviews


# ═══════════════════════════════════════════════════════════════════════════
# Scrape: review listing pages
# ═══════════════════════════════════════════════════════════════════════════

def scrape_asin_filter(page, asin, ip, sort_by='recent', star_filter=None,
                       max_pages=10, logger=None):
    """
    Scrape review listing pages for one ASIN.

    Note on Amazon pagination (2026-03-29): Amazon uses JavaScript infinite
    scroll (medleyReviewsAjaxUrl), not URL pageNumber parameters. For bot
    sessions where medleyReviewsAjaxUrl is empty, only 8 static reviews are
    served regardless of pageNumber. The multi-page loop still runs in case
    the session has earned pagination access (medleyReviewsAjaxUrl populated),
    but will naturally terminate after page 1 via duplicate/empty detection.

    Returns (reviews_list, blocked_flag).
    """
    all_reviews = []
    seen_keys = set()  # (review_date_raw, review_title) to detect when pages stop changing

    for pg in range(1, max_pages + 1):
        url = (f'https://www.amazon.com/product-reviews/{asin}/'
               f'?pageNumber={pg}&sortBy={sort_by}')
        if star_filter:
            url += f'&filterByStar={star_filter}'

        page.get(url)
        sleep_jitter(3.0)

        if is_blocked(page):
            if logger:
                label = f'{sort_by}/{star_filter}' if star_filter else sort_by
                logger.warning(f'  Blocked on {asin} [{label}] page {pg}. Stopping.')
            return all_reviews, True

        try:
            page.scroll.to_bottom()
        except:
            pass
        sleep_jitter(1.5)

        reviews = extract_reviews_from_page(page, asin, ip, logger)
        if not reviews:
            if logger:
                label = f'{sort_by}/{star_filter}' if star_filter else sort_by
                logger.info(f'  {asin} [{label}] page {pg}: 0 reviews (end)')
            break

        # Detect stale pagination: if ALL reviews on this page were already seen,
        # Amazon is serving the same static set (medleyReviewsAjaxUrl is empty).
        page_keys = {(r['review_date_raw'], r['review_title']) for r in reviews}
        new_keys = page_keys - seen_keys
        if pg > 1 and not new_keys:
            if logger:
                label = f'{sort_by}/{star_filter}' if star_filter else sort_by
                logger.info(f'  {asin} [{label}] page {pg}: all {len(reviews)} reviews are duplicates '
                            f'— Amazon pagination not enabled for this session (stale page)')
            break

        seen_keys |= page_keys
        all_reviews.extend(reviews)
        if logger:
            label = f'{sort_by}/{star_filter}' if star_filter else sort_by
            logger.info(f'  {asin} [{label}] p{pg}: {len(reviews)} reviews '
                        f'({len(new_keys)} new, total={len(all_reviews)})')

        if len(reviews) < 8:
            break
        sleep_jitter(random.uniform(6, 10))

    return all_reviews, False


# ═══════════════════════════════════════════════════════════════════════════
# Scrape: product detail page (/dp/)
# ═══════════════════════════════════════════════════════════════════════════

def scrape_product_page_reviews(page, asin, ip, logger=None):
    """Extract reviews from product detail page (no login needed, ~13 reviews)."""
    page.get(f'https://www.amazon.com/dp/{asin}')
    sleep_jitter(4.0)

    for _ in range(8):
        try:
            page.scroll.down(600)
        except:
            pass
        time.sleep(0.8)

    reviews = extract_reviews_from_page(page, asin, ip, logger)
    if logger:
        logger.info(f'  {asin} product page: {len(reviews)} reviews')
    return reviews


# ═══════════════════════════════════════════════════════════════════════════
# Scrape: one ASIN (product page + multi-sort review listing)
# ═══════════════════════════════════════════════════════════════════════════

# Combinations to try when Amazon pagination is limited.
# Each (sort_by, star_filter) combo may expose a different set of 8 reviews.
# When pagination IS enabled, the first combo (recent, None) alone gets all pages.
_LISTING_COMBOS = [
    ('recent',  None),         # Most recent reviews first
    ('helpful', None),         # Top-rated helpfulness order (different selection)
    ('recent',  'five_star'),  # Recent 5-star only
    ('recent',  'one_star'),   # Recent critical reviews
    ('recent',  'four_star'),  # 4-star
    ('recent',  'three_star'), # 3-star + below often omitted
    ('recent',  'two_star'),
]


def scrape_asin(page, conn, asin, ip, use_star_filters=False, max_pages=10, logger=None):
    """
    Scrape all reviews for one ASIN. Returns (count, blocked_flag).

    Strategy:
    - Phase 1: Product detail page (/dp/) — always works, ~13 reviews
    - Phase 2: Review listing pages with multiple sort/filter combos
      * When Amazon pagination IS enabled (medleyReviewsAjaxUrl populated):
        the first combo (recent, None) fetches all pages via infinite scroll.
      * When Amazon pagination is LIMITED (bot session, medleyReviewsAjaxUrl empty):
        each combo yields the same 8 "safe" reviews → multi-sort adds no value;
        scraper detects this after 2 consecutive zero-new-review combos and stops
        early to avoid wasting time.

    The --stars flag now has no effect (multi-sort is always applied).
    """
    all_reviews = []
    blocked = False

    # Phase 1: Product detail page (always works, ~13 reviews)
    dp_reviews = scrape_product_page_reviews(page, asin, ip, logger)
    all_reviews.extend(dp_reviews)
    sleep_jitter(random.uniform(5, 8))

    # Phase 2: Multi-sort review listing with early-stop on gated session
    # Track globally-seen (date_raw, title) pairs across all combos.
    # If 2 consecutive combos yield zero new reviews, Amazon is gating this
    # session and all further combos will be identical — stop early.
    global_seen_keys = set()
    consecutive_zero_combos = 0
    EARLY_STOP_AFTER = 2  # stop after this many zero-new-review combos

    for sort_by, star_filter in _LISTING_COMBOS:
        listing_reviews, blocked = scrape_asin_filter(
            page, asin, ip,
            sort_by=sort_by, star_filter=star_filter,
            max_pages=max_pages, logger=logger,
        )
        all_reviews.extend(listing_reviews)

        # Count how many are new globally
        new_keys = {(r['review_date_raw'], r['review_title']) for r in listing_reviews}
        truly_new = new_keys - global_seen_keys
        global_seen_keys |= new_keys

        if listing_reviews and not truly_new:
            consecutive_zero_combos += 1
            if logger:
                label = f'{sort_by}/{star_filter}' if star_filter else sort_by
                logger.info(f'  {asin} [{label}]: 0 truly new reviews '
                            f'({consecutive_zero_combos}/{EARLY_STOP_AFTER} zero-new combos)')
            if consecutive_zero_combos >= EARLY_STOP_AFTER:
                if logger:
                    logger.info(f'  {asin}: Amazon session gating detected — '
                                f'stopping multi-sort early (all combos return same reviews)')
                break
        else:
            consecutive_zero_combos = 0  # reset if we found new reviews

        if blocked:
            break
        sleep_jitter(random.uniform(8, 15))

    # Save to DB
    if all_reviews:
        cols = ['asin', 'ip', 'review_date', 'review_date_raw',
                'review_title', 'rating', 'verified', 'scraped_at']
        batch_insert(conn, 'amazon_review_dates', all_reviews, cols)
        if logger:
            logger.info(f'  {asin}: inserted {len(all_reviews)} reviews (deduped by DB)')

    return len(all_reviews), blocked


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    logger = get_logger('amazon_reviews')
    logger.info('amazon_reviews_browser.py starting')

    # Load config
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        cfg = json.load(f)

    skus = cfg.get('skus', [])
    max_pages = cfg.get('max_pages', 10)

    # CLI args
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    use_star_filters = '--stars' in sys.argv  # kept for back-compat; now always uses multi-sort
    if args:
        skus = [s for s in skus if s['asin'] in args]

    # Checkpoint
    checkpoint = load_checkpoint('amazon_reviews')
    completed_asins = set(checkpoint.get('completed_asins', []))

    # DB
    conn = init_db()
    for sku in skus:
        cnt = conn.execute('SELECT COUNT(*) FROM amazon_review_dates WHERE asin=?',
                           (sku['asin'],)).fetchone()[0]
        if cnt > 0:
            logger.info(f"  {sku['asin']} ({sku['ip']}): {cnt} reviews already in DB")

    # Launch browser
    use_real = '--real-profile' in sys.argv
    if use_real:
        logger.info('Using REAL Chrome profile — please close Chrome first!')
        logger.info(f'  Profile: {REAL_CHROME_PROFILE}')
    else:
        logger.info('Launching Chrome (dedicated profile, does NOT touch your Chrome)...')

    profile_dir = REAL_CHROME_PROFILE if use_real else SCRIPT_CHROME_PROFILE
    page = None
    try:
        page = create_browser(use_real_profile=use_real)
    except Exception as e:
        err = str(e).lower()
        if 'user folder' in err or 'conflict' in err or 'address' in err:
            if use_real:
                logger.error('Chrome Profile 被锁定 — 请先关闭所有 Chrome 窗口！')
                sys.exit(1)
            logger.error('Chrome Profile 被锁定（上次可能没正常退出）')
            lock_file = os.path.join(profile_dir, 'Default', 'LOCK')
            if os.path.isfile(lock_file):
                os.remove(lock_file)
                logger.info('Removed LOCK file. Retrying...')
                try:
                    page = create_browser(use_real_profile=use_real)
                except Exception as e2:
                    logger.error(f'Still failed: {e2}')
                    logger.error('请手动关闭脚本打开的浏览器窗口后重试')
                    sys.exit(1)
            else:
                logger.error(f'Failed: {e}')
                logger.error('请手动关闭脚本打开的浏览器窗口后重试')
                sys.exit(1)
        else:
            logger.error(f'Failed to launch browser: {e}')
            sys.exit(1)

    # Ensure Amazon reviews access (auto-login or interactive)
    test_asin = skus[0]['asin'] if skus else 'B0DT44TSM2'
    if not ensure_reviews_access(page, test_asin, logger):
        logger.error('Cannot access Amazon reviews. Exiting.')
        page.quit()
        sys.exit(1)

    # Session warmup — not needed for real profile (already trusted by Amazon)
    skip_warmup = '--no-warmup' in sys.argv or use_real
    if not skip_warmup:
        warmup_asins = [s['asin'] for s in skus[:3]]
        warmup_session(page, warmup_asins, logger)
        sleep_jitter(random.uniform(5, 10))
    elif use_real:
        logger.info('Warmup skipped (real Chrome profile is already trusted)')
        # Check if pagination is enabled with real profile
        check_pagination_enabled(page, test_asin, logger)
    else:
        logger.info('Warmup skipped (--no-warmup flag)')

    # Scrape
    total_inserted = 0
    try:
        for i, sku in enumerate(skus):
            asin = sku['asin']
            ip = sku['ip']

            if asin in completed_asins:
                logger.info(f'[{i+1}/{len(skus)}] Skipping {asin} ({ip}) — completed')
                continue

            logger.info(f'[{i+1}/{len(skus)}] === {asin} ({ip}) ===')

            try:
                count, blocked = scrape_asin(page, conn, asin, ip,
                                             max_pages=max_pages, logger=logger)
                total_inserted += count

                if blocked:
                    logger.warning(f'Blocked at {asin}. Saving checkpoint.')
                    save_checkpoint('amazon_reviews', {
                        'completed_asins': list(completed_asins),
                        'total_inserted': total_inserted,
                    })
                    break

            except Exception as e:
                logger.warning(f'{asin}: error: {e}')
                continue

            completed_asins.add(asin)
            save_checkpoint('amazon_reviews', {
                'completed_asins': list(completed_asins),
                'total_inserted': total_inserted,
            })

            if i < len(skus) - 1:
                delay = random.uniform(30, 50)
                logger.info(f'  Waiting {delay:.0f}s before next ASIN...')
                sleep_jitter(delay)

    except KeyboardInterrupt:
        logger.info('Interrupted — saving checkpoint')
        save_checkpoint('amazon_reviews', {
            'completed_asins': list(completed_asins),
            'total_inserted': total_inserted,
        })
    finally:
        # 用真实 Profile 时，采集结束后保存 cookie 到 JSON（给独立 Profile 将来用）
        if use_real:
            try:
                save_amazon_cookies(page)
                logger.info('Saved real Chrome cookies to amazon_cookies.json (backup for future runs)')
            except:
                pass
        try:
            page.quit()
            profile_name = 'real Chrome profile' if use_real else 'chrome_data/'
            logger.info(f'Browser closed gracefully — session saved to {profile_name}')
        except:
            pass
        conn.close()

    # Final stats
    import sqlite3
    conn2 = sqlite3.connect(os.path.join(BASE_DIR, 'overseas_data.db'))
    total = conn2.execute('SELECT COUNT(*) FROM amazon_review_dates').fetchone()[0]
    asin_counts = conn2.execute(
        'SELECT asin, COUNT(*) FROM amazon_review_dates GROUP BY asin'
    ).fetchall()
    conn2.close()

    logger.info(f'Done. Total reviews in DB: {total}')
    for asin, cnt in asin_counts:
        logger.info(f'  {asin}: {cnt}')


if __name__ == '__main__':
    main()
