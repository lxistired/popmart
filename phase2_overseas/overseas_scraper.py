"""
海外另类数据采集器 V2
维度：Amazon产品页（BSR/评论/价格） + SimilarWeb官网流量 + TikTok社媒 + Instagram名人
架构：复用V1 UC Driver，全部落盘SQLite，断点续跑
"""

import json
import sqlite3
import time
import random
import re
import os
import sys
from datetime import datetime, date

# ── 路径配置 ───────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SKU_FILE = os.path.join(BASE_DIR, "amazon_sku_list.json")
DB_FILE  = os.path.join(BASE_DIR, "overseas_data.db")

# ── UC Driver 初始化 ────────────────────────────────────────────────────────
def get_driver():
    import undetected_chromedriver as uc
    import os
    opts = uc.ChromeOptions()
    opts.add_argument("--window-size=1400,900")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    # 固定使用Chrome 146的ChromeDriver，避免版本不匹配
    _cd146 = os.path.expanduser(r"~\.cache\selenium\chromedriver\win64\146.0.7680.165\chromedriver.exe")
    _kwargs = {"driver_executable_path": _cd146, "version_main": 146} if os.path.exists(_cd146) else {}
    driver = uc.Chrome(options=opts, **_kwargs)
    driver.implicitly_wait(8)
    return driver

# ── 数据库初始化 ────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Amazon产品快照
    c.execute("""
    CREATE TABLE IF NOT EXISTS amazon_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scraped_at TEXT NOT NULL,
        asin TEXT NOT NULL,
        ip TEXT NOT NULL,
        title TEXT,
        price_usd REAL,
        rating REAL,
        reviews INTEGER,
        bsr_main INTEGER,
        bsr_category TEXT,
        bsr_rank INTEGER,
        bought_monthly TEXT,
        in_stock INTEGER DEFAULT 1
    )""")

    # SimilarWeb流量数据
    c.execute("""
    CREATE TABLE IF NOT EXISTS similarweb_traffic (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scraped_at TEXT NOT NULL,
        domain TEXT NOT NULL,
        monthly_visits TEXT,
        visit_duration TEXT,
        pages_per_visit TEXT,
        bounce_rate TEXT,
        top_countries TEXT,
        traffic_sources TEXT,
        raw_json TEXT
    )""")

    # TikTok数据
    c.execute("""
    CREATE TABLE IF NOT EXISTS tiktok_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scraped_at TEXT NOT NULL,
        data_type TEXT NOT NULL,  -- 'hashtag'/'search_video'/'account'
        keyword TEXT,
        hashtag_views TEXT,
        hashtag_posts TEXT,
        video_id TEXT,
        video_title TEXT,
        video_views TEXT,
        video_likes TEXT,
        video_comments TEXT,
        video_shares TEXT,
        video_author TEXT,
        video_date TEXT,
        account_followers TEXT,
        account_likes TEXT,
        raw_json TEXT
    )""")

    # Instagram数据
    c.execute("""
    CREATE TABLE IF NOT EXISTS instagram_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scraped_at TEXT NOT NULL,
        data_type TEXT NOT NULL,  -- 'hashtag'/'account'/'celebrity_post'
        keyword TEXT,
        hashtag_posts TEXT,
        account_username TEXT,
        account_followers TEXT,
        account_posts INTEGER,
        post_url TEXT,
        post_likes TEXT,
        post_comments TEXT,
        post_caption TEXT,
        celebrity_name TEXT,
        raw_json TEXT
    )""")

    conn.commit()
    return conn

# ═══════════════════════════════════════════════════════════════════════════
# 维度1：Amazon产品页采集（BSR + 评论 + 价格）
# ═══════════════════════════════════════════════════════════════════════════
def scrape_amazon_product(driver, asin):
    """抓取单个产品详情页，提取BSR/评论/价格/评分"""
    url = f"https://www.amazon.com/dp/{asin}"
    print(f"  Amazon: {url}")
    driver.get(url)
    time.sleep(random.uniform(3, 5))

    result = {"asin": asin, "scraped_at": datetime.now().isoformat()}

    try:
        # 标题
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        try:
            title_el = driver.find_element(By.ID, "productTitle")
            result["title"] = title_el.text.strip()
        except:
            result["title"] = ""

        # 价格
        try:
            price_el = driver.find_element(By.CSS_SELECTOR, ".a-price .a-offscreen")
            result["price_usd"] = float(re.sub(r'[^\d.]', '', price_el.get_attribute("textContent") or "0") or 0)
        except:
            result["price_usd"] = None

        # 评分 & 评论数
        try:
            rating_el = driver.find_element(By.CSS_SELECTOR, "#acrPopover span.a-icon-alt")
            result["rating"] = float(rating_el.text.split()[0])
        except:
            result["rating"] = None

        try:
            reviews_el = driver.find_element(By.ID, "acrCustomerReviewText")
            rev_text = reviews_el.text.replace(",", "").replace(" ratings", "").strip()
            result["reviews"] = int(re.sub(r'[^\d]', '', rev_text) or 0)
        except:
            result["reviews"] = None

        # 月购买量
        try:
            bought_el = driver.find_element(By.ID, "social-proofing-faceout-title-tk_bought")
            result["bought_monthly"] = bought_el.text.strip()
        except:
            try:
                bought_els = driver.find_elements(By.CSS_SELECTOR, "[id*='social-proofing']")
                result["bought_monthly"] = bought_els[0].text.strip() if bought_els else ""
            except:
                result["bought_monthly"] = ""

        # BSR排名 — 在"Product information"或"Best Sellers Rank"部分
        page_text = driver.execute_script("return document.body.innerText")

        bsr_matches = re.findall(r'#([\d,]+)\s+in\s+([^\n\(]+)', page_text)
        if bsr_matches:
            # 第一个是主BSR
            result["bsr_main"] = int(bsr_matches[0][0].replace(",", ""))
            result["bsr_category"] = bsr_matches[0][1].strip()
            # 寻找Toys & Games细分
            toys_bsr = [(int(m[0].replace(",","")), m[1].strip()) for m in bsr_matches if 'toy' in m[1].lower() or 'game' in m[1].lower()]
            if toys_bsr:
                result["bsr_rank"] = toys_bsr[0][0]
            else:
                result["bsr_rank"] = result["bsr_main"]
        else:
            result["bsr_main"] = None
            result["bsr_category"] = None
            result["bsr_rank"] = None

        print(f"    ✓ BSR={result.get('bsr_main')}, Reviews={result.get('reviews')}, Price=${result.get('price_usd')}")
        result["in_stock"] = 1

    except Exception as e:
        print(f"    ✗ Error: {e}")
        result["in_stock"] = 0

    return result


def run_amazon(driver, conn):
    """采集所有SKU的产品详情页"""
    print("\n═══ Amazon产品页采集 ═══")
    with open(SKU_FILE) as f:
        sku_data = json.load(f)

    c = conn.cursor()
    today = date.today().isoformat()

    # 检查今天已采集的ASIN（断点续跑）
    c.execute("SELECT DISTINCT asin FROM amazon_snapshots WHERE scraped_at LIKE ?", (f"{today}%",))
    done = {r[0] for r in c.fetchall()}

    skus = sku_data["skus"]
    total = len(skus)
    for i, sku in enumerate(skus):
        asin = sku["asin"]
        ip = sku["ip"]
        if asin in done:
            print(f"  [{i+1}/{total}] 跳过 {asin}（今日已采集）")
            continue

        print(f"  [{i+1}/{total}] {ip}: {asin}")
        data = scrape_amazon_product(driver, asin)

        c.execute("""
        INSERT INTO amazon_snapshots
          (scraped_at, asin, ip, title, price_usd, rating, reviews,
           bsr_main, bsr_category, bsr_rank, bought_monthly, in_stock)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            data["scraped_at"], asin, ip,
            data.get("title"), data.get("price_usd"), data.get("rating"),
            data.get("reviews"), data.get("bsr_main"), data.get("bsr_category"),
            data.get("bsr_rank"), data.get("bought_monthly"), data.get("in_stock", 1)
        ))
        conn.commit()
        time.sleep(random.uniform(4, 8))

    print(f"Amazon采集完成，共 {total} 个SKU")


# ═══════════════════════════════════════════════════════════════════════════
# 维度2：SimilarWeb流量数据
# ═══════════════════════════════════════════════════════════════════════════
def scrape_similarweb_domain(driver, domain):
    """访问SimilarWeb提取流量数据"""
    url = f"https://www.similarweb.com/website/{domain}/"
    print(f"  SimilarWeb: {url}")
    driver.get(url)
    time.sleep(random.uniform(5, 8))

    result = {"domain": domain, "scraped_at": datetime.now().isoformat()}

    try:
        page_text = driver.execute_script("return document.body.innerText")

        # 月访问量
        visits_match = re.search(r'([\d,.]+[KkMmBb]?)\s*(?:Total\s+)?Visits', page_text)
        result["monthly_visits"] = visits_match.group(1) if visits_match else ""

        # 停留时间
        duration_match = re.search(r'(\d+:\d+)\s*(?:Avg\.\s+)?Visit\s+Duration', page_text)
        result["visit_duration"] = duration_match.group(1) if duration_match else ""

        # 页面数/访问
        pages_match = re.search(r'([\d.]+)\s*Pages?\s+(?:per\s+)?Visit', page_text)
        result["pages_per_visit"] = pages_match.group(1) if pages_match else ""

        # 跳出率
        bounce_match = re.search(r'([\d.]+)%\s*Bounce\s+Rate', page_text)
        result["bounce_rate"] = bounce_match.group(1) + "%" if bounce_match else ""

        # 国家分布
        country_matches = re.findall(r'([A-Z][a-zA-Z\s]+)\s+([\d.]+)%', page_text[:3000])
        known_countries = ['United States', 'China', 'United Kingdom', 'Japan', 'South Korea',
                           'France', 'Germany', 'Australia', 'Canada', 'Thailand', 'Singapore',
                           'Taiwan', 'Hong Kong', 'Malaysia', 'Indonesia']
        countries_found = [(c, p) for c, p in country_matches if any(kc in c for kc in known_countries)]
        result["top_countries"] = json.dumps(countries_found[:8])

        # 流量来源
        sources = {}
        for src in ['Direct', 'Search', 'Social', 'Email', 'Referrals', 'Paid']:
            match = re.search(rf'{src}\s+([\d.]+)%', page_text)
            if match:
                sources[src] = match.group(1) + "%"
        result["traffic_sources"] = json.dumps(sources)

        print(f"    ✓ Visits={result['monthly_visits']}, Duration={result['visit_duration']}, Bounce={result['bounce_rate']}")
        result["raw_json"] = json.dumps(result)

    except Exception as e:
        print(f"    ✗ Error: {e}")

    return result


def run_similarweb(driver, conn):
    """采集2个域名的流量数据"""
    print("\n═══ SimilarWeb流量采集 ═══")
    domains = ["popmart.com", "global.popmart.com"]
    c = conn.cursor()

    for domain in domains:
        data = scrape_similarweb_domain(driver, domain)
        c.execute("""
        INSERT INTO similarweb_traffic
          (scraped_at, domain, monthly_visits, visit_duration, pages_per_visit,
           bounce_rate, top_countries, traffic_sources, raw_json)
        VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            data["scraped_at"], data["domain"],
            data.get("monthly_visits"), data.get("visit_duration"),
            data.get("pages_per_visit"), data.get("bounce_rate"),
            data.get("top_countries"), data.get("traffic_sources"),
            data.get("raw_json", "")
        ))
        conn.commit()
        time.sleep(random.uniform(5, 10))

    print("SimilarWeb采集完成")


# ═══════════════════════════════════════════════════════════════════════════
# 维度3：TikTok社媒热度
# ═══════════════════════════════════════════════════════════════════════════
def scrape_tiktok_hashtag(driver, hashtag):
    """抓取TikTok标签页：视频数+总播放量"""
    url = f"https://www.tiktok.com/tag/{hashtag.lstrip('#')}"
    print(f"  TikTok hashtag: {url}")
    driver.get(url)
    time.sleep(random.uniform(4, 7))

    result = {"data_type": "hashtag", "keyword": hashtag, "scraped_at": datetime.now().isoformat()}

    try:
        page_text = driver.execute_script("return document.body.innerText")

        # 播放量（例：13.8B views 或 13.8亿次观看）
        views_match = re.search(r'([\d,.]+[KkMmBb]?)\s*(?:views|次观看)', page_text, re.IGNORECASE)
        result["hashtag_views"] = views_match.group(1) if views_match else ""

        # 视频数
        posts_match = re.search(r'([\d,.]+[KkMmBb]?)\s*(?:videos?|视频)', page_text, re.IGNORECASE)
        result["hashtag_posts"] = posts_match.group(1) if posts_match else ""

        print(f"    ✓ #{hashtag}: views={result['hashtag_views']}, posts={result['hashtag_posts']}")

    except Exception as e:
        print(f"    ✗ Error: {e}")

    return result


def scrape_tiktok_search(driver, query, max_videos=25):
    """搜索TikTok，提取Top视频列表"""
    url = f"https://www.tiktok.com/search?q={query.replace(' ', '+')}"
    print(f"  TikTok search: {url}")
    driver.get(url)
    time.sleep(random.uniform(5, 8))

    results = []
    try:
        # 滚动加载更多
        for _ in range(3):
            driver.execute_script("window.scrollBy(0, 1200)")
            time.sleep(1.5)

        page_text = driver.execute_script("return document.body.innerText")

        # 从JSON-LD或页面数据提取视频
        script_tags = driver.execute_script("""
            const scripts = document.querySelectorAll('script[type="application/ld+json"]');
            return Array.from(scripts).map(s => s.textContent);
        """)

        # 尝试从script数据中提取
        for script in script_tags:
            try:
                data = json.loads(script)
                if isinstance(data, list):
                    for item in data:
                        if item.get('@type') == 'VideoObject':
                            results.append({
                                "data_type": "search_video",
                                "keyword": query,
                                "scraped_at": datetime.now().isoformat(),
                                "video_title": item.get("name", "")[:100],
                                "video_views": str(item.get("interactionStatistic", [{}])[0].get("userInteractionCount", "")),
                                "video_author": item.get("author", {}).get("name", ""),
                                "video_date": item.get("uploadDate", ""),
                                "raw_json": json.dumps(item)[:500]
                            })
            except:
                pass

        # 如果JSON-LD为空，从页面文本提取
        if not results:
            # 提取视频卡片数据（通过__UNIVERSAL_DATA_FOR_REHYDRATION__）
            universal_data = driver.execute_script("""
                const el = document.querySelector('#SIGI_STATE') || document.querySelector('#__UNIVERSAL_DATA_FOR_REHYDRATION__');
                return el ? el.textContent : '';
            """)
            if universal_data:
                try:
                    data = json.loads(universal_data)
                    # 查找ItemModule或类似的视频列表
                    def find_videos(obj, depth=0):
                        if depth > 6: return []
                        found = []
                        if isinstance(obj, dict):
                            if 'stats' in obj and 'desc' in obj:  # TikTok视频对象
                                stats = obj.get('stats', {})
                                found.append({
                                    "data_type": "search_video",
                                    "keyword": query,
                                    "scraped_at": datetime.now().isoformat(),
                                    "video_title": obj.get('desc', '')[:100],
                                    "video_views": str(stats.get('playCount', '')),
                                    "video_likes": str(stats.get('diggCount', '')),
                                    "video_comments": str(stats.get('commentCount', '')),
                                    "video_shares": str(stats.get('shareCount', '')),
                                    "video_author": obj.get('author', {}).get('nickname', '') if isinstance(obj.get('author'), dict) else str(obj.get('authorId', '')),
                                    "video_date": datetime.fromtimestamp(obj.get('createTime', 0)).isoformat() if obj.get('createTime') else '',
                                    "raw_json": ""
                                })
                            else:
                                for v in obj.values():
                                    found.extend(find_videos(v, depth+1))
                        elif isinstance(obj, list):
                            for item in obj:
                                found.extend(find_videos(item, depth+1))
                        return found
                    results = find_videos(data)
                except Exception as e:
                    print(f"    JSON parse error: {e}")

        print(f"    ✓ '{query}': found {len(results)} videos")
        return results[:max_videos]

    except Exception as e:
        print(f"    ✗ Error: {e}")
        return []


def scrape_tiktok_account(driver, username):
    """抓取TikTok官方账号：粉丝数+互动"""
    url = f"https://www.tiktok.com/@{username}"
    print(f"  TikTok account: {url}")
    driver.get(url)
    time.sleep(random.uniform(4, 7))

    result = {
        "data_type": "account",
        "keyword": username,
        "scraped_at": datetime.now().isoformat()
    }

    try:
        page_text = driver.execute_script("return document.body.innerText")

        # 粉丝数
        follower_match = re.search(r'([\d,.]+[KkMmBb]?)\s*Followers?', page_text, re.IGNORECASE)
        result["account_followers"] = follower_match.group(1) if follower_match else ""

        # 总点赞
        likes_match = re.search(r'([\d,.]+[KkMmBb]?)\s*Likes?', page_text, re.IGNORECASE)
        result["account_likes"] = likes_match.group(1) if likes_match else ""

        print(f"    ✓ @{username}: followers={result['account_followers']}, likes={result['account_likes']}")

    except Exception as e:
        print(f"    ✗ Error: {e}")

    return result


def run_tiktok(driver, conn):
    """TikTok全量采集：标签+搜索+账号"""
    print("\n═══ TikTok采集 ═══")
    c = conn.cursor()
    now = datetime.now().isoformat()

    def save_row(data):
        c.execute("""
        INSERT INTO tiktok_data
          (scraped_at, data_type, keyword, hashtag_views, hashtag_posts,
           video_id, video_title, video_views, video_likes, video_comments,
           video_shares, video_author, video_date, account_followers, account_likes, raw_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            data.get("scraped_at", now),
            data.get("data_type", ""),
            data.get("keyword", ""),
            data.get("hashtag_views", ""),
            data.get("hashtag_posts", ""),
            data.get("video_id", ""),
            data.get("video_title", ""),
            data.get("video_views", ""),
            data.get("video_likes", ""),
            data.get("video_comments", ""),
            data.get("video_shares", ""),
            data.get("video_author", ""),
            data.get("video_date", ""),
            data.get("account_followers", ""),
            data.get("account_likes", ""),
            data.get("raw_json", "")
        ))
        conn.commit()

    # 1) 标签采集：各IP对比
    hashtags = ["labubu", "popmart", "dimoo", "molly", "skullpanda", "themonsters"]
    for tag in hashtags:
        data = scrape_tiktok_hashtag(driver, tag)
        save_row(data)
        time.sleep(random.uniform(3, 5))

    # 2) 搜索采集：Top视频
    search_queries = ["Labubu", "Pop Mart", "Labubu Lisa", "Labubu Beckham"]
    for query in search_queries:
        videos = scrape_tiktok_search(driver, query)
        for v in videos:
            save_row(v)
        time.sleep(random.uniform(4, 7))

    # 3) 官方账号
    for account in ["popmart_official", "popmartglobal"]:
        data = scrape_tiktok_account(driver, account)
        save_row(data)
        time.sleep(random.uniform(3, 5))

    print("TikTok采集完成")


# ═══════════════════════════════════════════════════════════════════════════
# 维度4：Instagram社媒
# ═══════════════════════════════════════════════════════════════════════════
def scrape_instagram_hashtag(driver, tag):
    """抓取Instagram标签帖子数"""
    url = f"https://www.instagram.com/explore/tags/{tag.lstrip('#')}/"
    print(f"  Instagram hashtag: {url}")
    driver.get(url)
    time.sleep(random.uniform(5, 8))

    result = {
        "data_type": "hashtag",
        "keyword": tag,
        "scraped_at": datetime.now().isoformat()
    }

    try:
        page_text = driver.execute_script("return document.body.innerText")

        # 帖子数
        posts_match = re.search(r'([\d,.]+[KkMmBb]?)\s*(?:posts?|帖子)', page_text, re.IGNORECASE)
        result["hashtag_posts"] = posts_match.group(1) if posts_match else ""

        # 也尝试从JSON数据提取
        json_data = driver.execute_script("""
            const el = document.querySelector('script[type="application/json"]');
            return el ? el.textContent.slice(0, 2000) : '';
        """)
        if not result["hashtag_posts"] and json_data:
            count_match = re.search(r'"media_count":\s*(\d+)', json_data)
            if count_match:
                result["hashtag_posts"] = count_match.group(1)

        print(f"    ✓ #{tag}: posts={result['hashtag_posts']}")

    except Exception as e:
        print(f"    ✗ Error: {e}")

    return result


def scrape_instagram_account(driver, username):
    """抓取Instagram账号：粉丝数+帖子数"""
    url = f"https://www.instagram.com/{username}/"
    print(f"  Instagram account: {url}")
    driver.get(url)
    time.sleep(random.uniform(5, 8))

    result = {
        "data_type": "account",
        "keyword": username,
        "account_username": username,
        "scraped_at": datetime.now().isoformat()
    }

    try:
        page_text = driver.execute_script("return document.body.innerText")

        # 粉丝数
        follower_match = re.search(r'([\d,.]+[KkMmBb]?)\s*[Ff]ollowers?', page_text)
        result["account_followers"] = follower_match.group(1) if follower_match else ""

        # 帖子数
        posts_match = re.search(r'([\d,.]+[KkMmBb]?)\s*[Pp]osts?', page_text)
        result["account_posts"] = int(re.sub(r'[^\d]', '', posts_match.group(1)) or 0) if posts_match else 0

        # 也从meta标签提取
        meta_desc = driver.execute_script("""
            const m = document.querySelector('meta[name="description"]');
            return m ? m.content : '';
        """)
        if meta_desc:
            # "1.5M Followers, 450 Following, 2,345 Posts"
            follower_meta = re.search(r'([\d,.]+[KkMm]?)\s*Followers', meta_desc, re.IGNORECASE)
            if follower_meta and not result["account_followers"]:
                result["account_followers"] = follower_meta.group(1)
            posts_meta = re.search(r'([\d,]+)\s*Posts', meta_desc, re.IGNORECASE)
            if posts_meta:
                result["account_posts"] = int(posts_meta.group(1).replace(",","")) or result["account_posts"]

        print(f"    ✓ @{username}: followers={result['account_followers']}, posts={result.get('account_posts')}")

    except Exception as e:
        print(f"    ✗ Error: {e}")

    return result


def run_instagram(driver, conn):
    """Instagram采集：标签+账号+名人帖子"""
    print("\n═══ Instagram采集 ═══")
    c = conn.cursor()
    now = datetime.now().isoformat()

    def save_row(data):
        c.execute("""
        INSERT INTO instagram_data
          (scraped_at, data_type, keyword, hashtag_posts, account_username,
           account_followers, account_posts, post_url, post_likes, post_comments,
           post_caption, celebrity_name, raw_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            data.get("scraped_at", now),
            data.get("data_type", ""),
            data.get("keyword", ""),
            data.get("hashtag_posts", ""),
            data.get("account_username", ""),
            data.get("account_followers", ""),
            data.get("account_posts", 0),
            data.get("post_url", ""),
            data.get("post_likes", ""),
            data.get("post_comments", ""),
            data.get("post_caption", ""),
            data.get("celebrity_name", ""),
            data.get("raw_json", "")
        ))
        conn.commit()

    # 1) 标签帖子数
    tags = ["labubu", "popmart", "dimoo", "molly", "skullpanda"]
    for tag in tags:
        data = scrape_instagram_hashtag(driver, tag)
        save_row(data)
        time.sleep(random.uniform(3, 6))

    # 2) 官方账号
    for acct in ["popmart_global", "popmart_official"]:
        data = scrape_instagram_account(driver, acct)
        save_row(data)
        time.sleep(random.uniform(4, 7))

    # 3) 名人账号（查粉丝数+帖子，分析者手动找帖子）
    celebrities = [
        ("lalalalisa_m", "Lisa BLACKPINK"),
        ("davidbeckham", "David Beckham"),
        ("badgalriri", "Rihanna"),
    ]
    for username, celeb_name in celebrities:
        data = scrape_instagram_account(driver, username)
        data["celebrity_name"] = celeb_name
        data["data_type"] = "celebrity_account"
        save_row(data)
        time.sleep(random.uniform(5, 8))

    print("Instagram采集完成")


# ═══════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════
def main():
    modules = sys.argv[1:] if len(sys.argv) > 1 else ["amazon", "similarweb", "tiktok", "instagram"]
    print(f"运行模块: {modules}")
    print(f"数据库: {DB_FILE}")

    conn = init_db()
    driver = None

    try:
        driver = get_driver()

        if "amazon" in modules:
            run_amazon(driver, conn)

        if "similarweb" in modules:
            run_similarweb(driver, conn)

        if "tiktok" in modules:
            run_tiktok(driver, conn)

        if "instagram" in modules:
            run_instagram(driver, conn)

        print("\n✅ 全部采集完成")
        print(f"数据落盘: {DB_FILE}")

    except KeyboardInterrupt:
        print("\n⚠️ 用户中断，数据已落盘")
    except Exception as e:
        import traceback
        print(f"\n✗ 错误: {e}")
        traceback.print_exc()
    finally:
        if driver:
            driver.quit()
        conn.close()


if __name__ == "__main__":
    main()
