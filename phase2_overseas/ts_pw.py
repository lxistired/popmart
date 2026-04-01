"""timeseries_playwright.py - Playwright version, inherits Chrome login state"""
import sqlite3, time, random, json, re, os, sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB       = os.path.join(BASE_DIR, "overseas_data.db")
CHROME_PROFILE = os.path.join(os.path.expanduser("~"), "AppData", "Local", "ChromePW")

AMAZON_TARGETS = [
    ("B0DT44TSM2", "Labubu"),
    ("B0FJFV4PQN", "Labubu"),
    ("B0BG8QHZV5", "Skullpanda"),
    ("B0D2D7MRRL", "Skullpanda"),
    ("B0D3T2QJ1W", "Molly"),
    ("B0DT95S945", "Dimoo"),
]
TIKTOK_QUERIES     = ["Labubu", "Labubu Lisa", "Pop Mart Labubu", "Labubu Beckham"]
INSTAGRAM_ACCOUNTS = ["lalalalisa_m", "davidbeckham", "popmart"]

MONTH_MAP = {'January':1,'February':2,'March':3,'April':4,'May':5,'June':6,
             'July':7,'August':8,'September':9,'October':10,'November':11,'December':12}

def init_db(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS amazon_review_dates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asin TEXT, ip TEXT, review_date TEXT, review_date_raw TEXT,
        review_title TEXT, rating INTEGER, verified INTEGER DEFAULT 0, scraped_at TEXT
    );
    CREATE TABLE IF NOT EXISTS tiktok_videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT UNIQUE, author TEXT, title TEXT,
        views INTEGER, likes INTEGER, comments_count INTEGER,
        create_time TEXT, source TEXT, scraped_at TEXT
    );
    CREATE TABLE IF NOT EXISTS tiktok_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT, comment_id TEXT UNIQUE,
        comment_text TEXT, comment_date TEXT, comment_datetime TEXT,
        likes INTEGER DEFAULT 0, author_name TEXT, scraped_at TEXT
    );
    CREATE TABLE IF NOT EXISTS instagram_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shortcode TEXT UNIQUE, post_url TEXT, account TEXT,
        caption TEXT, post_date TEXT, source TEXT, scraped_at TEXT
    );
    CREATE TABLE IF NOT EXISTS instagram_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shortcode TEXT, comment_id TEXT,
        comment_text TEXT, comment_date TEXT, comment_datetime TEXT,
        likes INTEGER DEFAULT 0, author_name TEXT, scraped_at TEXT
    );
    """)
    conn.commit()

def parse_amz_date(raw):
    m = re.search(r'on\s+(\w+)\s+(\d+),\s+(\d{4})', raw)
    if m:
        mon = MONTH_MAP.get(m.group(1), 0)
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(2)):02d}"
    return None

def scrape_amazon_reviews(page, asin, ip, conn, max_pages=25):
    today = datetime.now().strftime('%Y-%m-%d')
    already = conn.execute("SELECT COUNT(*) FROM amazon_review_dates WHERE asin=? AND scraped_at LIKE ?",
                           (asin, f"{today}%")).fetchone()[0]
    if already > 50:
        print(f"    skip {asin} ({already} rows today)"); return 0
    scraped_at = datetime.now().isoformat(); total = 0
    for pg in range(1, max_pages+1):
        page.goto(f"https://www.amazon.com/product-reviews/{asin}?pageNumber={pg}&sortBy=recent",
                  wait_until="domcontentloaded")
        page.wait_for_timeout(random.randint(2500, 4000))
        if "Sign in" in page.title() or "captcha" in page.url.lower():
            print(f"    blocked ({page.title()})"); break
        reviews = page.query_selector_all("[data-hook='review']")
        if not reviews:
            print(f"    page {pg}: no reviews, stop"); break
        rows = []
        for r in reviews:
            try:
                date_raw = r.query_selector("[data-hook='review-date']").inner_text()
                review_date = parse_amz_date(date_raw)
                try:
                    rating = int(float(r.query_selector("[data-hook='review-star-rating'] .a-icon-alt").inner_text().split()[0]))
                except: rating = None
                try:
                    t = r.query_selector("[data-hook='review-title'] span:last-child").inner_text()[:80]
                except: t = ""
                verified = 1 if r.query_selector("[data-hook='avp-badge']") else 0
                rows.append((asin, ip, review_date, date_raw, t, rating, verified, scraped_at))
            except: pass
        conn.executemany(
            "INSERT OR IGNORE INTO amazon_review_dates (asin,ip,review_date,review_date_raw,review_title,rating,verified,scraped_at) VALUES(?,?,?,?,?,?,?,?)", rows)
        conn.commit(); total += len(rows)
        print(f"    page {pg}: {len(rows)} rows, total {total}")
        if len(reviews) < 8: break
        page.wait_for_timeout(random.randint(1500, 3000))
    return total

def run_amazon(page, conn):
    print("\n=== Amazon Review Timeseries ===")
    page.goto("https://www.amazon.com", wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    for asin, ip in AMAZON_TARGETS:
        print(f"  {ip}: {asin}")
        n = scrape_amazon_reviews(page, asin, ip, conn)
        print(f"  -> {n} rows"); page.wait_for_timeout(random.randint(4000, 8000))

def get_tiktok_videos(page, query, max_results=15):
    page.goto(f"https://www.tiktok.com/search/video?q={query.replace(' ','+')}",
              wait_until="domcontentloaded")
    page.wait_for_timeout(random.randint(4000, 6000))
    for _ in range(3):
        page.evaluate("window.scrollBy(0, 1500)"); page.wait_for_timeout(1200)
    videos = []
    try:
        raw = page.evaluate("""() => {
            const el = document.getElementById('SIGI_STATE') ||
                       document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
            return el ? el.textContent : '';
        }""")
        if raw:
            data = json.loads(raw)
            def walk(obj, d=0):
                if d > 8: return []
                found = []
                if isinstance(obj, dict):
                    if 'stats' in obj and 'desc' in obj and 'id' in obj:
                        s = obj.get('stats', {}); a = obj.get('author', {})
                        found.append({'video_id': str(obj['id']),
                            'author': a.get('nickname','') if isinstance(a,dict) else '',
                            'title': obj.get('desc','')[:100],
                            'views': s.get('playCount',0), 'likes': s.get('diggCount',0),
                            'comments_count': s.get('commentCount',0),
                            'create_time': datetime.fromtimestamp(obj['createTime']).isoformat() if obj.get('createTime') else '',
                            'source': f'search_{query}'})
                    else:
                        for v in obj.values(): found.extend(walk(v, d+1))
                elif isinstance(obj, list):
                    for i in obj: found.extend(walk(i, d+1))
                return found
            vids = walk(data); seen = set(); unique = []
            for v in vids:
                if v['video_id'] not in seen: seen.add(v['video_id']); unique.append(v)
            videos = sorted(unique, key=lambda x: x.get('views',0), reverse=True)[:max_results]
    except Exception as e:
        print(f"    parse error: {e}")
    print(f"  '{query}': {len(videos)} videos"); return videos

def get_tiktok_comments(page, video_id, max_pages=20):
    all_c = []; cursor = 0
    for _ in range(max_pages):
        r = page.evaluate(f"""async () => {{
            try {{
                const resp = await fetch(
                    'https://www.tiktok.com/api/comment/list/?aweme_id={video_id}&count=50&cursor={cursor}',
                    {{credentials:'include', headers:{{'Referer':'https://www.tiktok.com/'}}}}
                );
                return await resp.json();
            }} catch(e) {{ return {{error: e.message}}; }}
        }}""")
        if r.get('error'): print(f"    API error: {r['error']}"); break
        comments = r.get('comments') or []
        has_more = r.get('has_more', False)
        cursor = r.get('cursor', cursor + len(comments))
        if not comments: break
        all_c.extend(comments)
        if not has_more: break
        page.wait_for_timeout(random.randint(600, 1200))
    return all_c

def run_tiktok(page, conn):
    print("\n=== TikTok Comment Timeseries ===")
    page.goto("https://www.tiktok.com", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    scraped_at = datetime.now().isoformat(); all_vids = []
    for q in TIKTOK_QUERIES:
        vids = get_tiktok_videos(page, q)
        for v in vids:
            try:
                conn.execute("INSERT OR IGNORE INTO tiktok_videos (video_id,author,title,views,likes,comments_count,create_time,source,scraped_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (v['video_id'],v['author'],v['title'],v['views'],v['likes'],v['comments_count'],v['create_time'],v['source'],scraped_at))
                conn.commit()
            except: pass
        all_vids.extend(vids); page.wait_for_timeout(random.randint(3000,5000))
    seen=set(); unique=[]
    for v in all_vids:
        if v['video_id'] not in seen: seen.add(v['video_id']); unique.append(v)
    priority = sorted(unique, key=lambda x: x.get('comments_count',0), reverse=True)[:30]
    print(f"\n{len(priority)} videos to scrape...")
    for i, v in enumerate(priority):
        vid = v['video_id']
        already = conn.execute("SELECT COUNT(*) FROM tiktok_comments WHERE video_id=?", (vid,)).fetchone()[0]
        if already > 50: print(f"  [{i+1}] {vid} skip ({already})"); continue
        print(f"  [{i+1}/{len(priority)}] {vid} (~{v.get('comments_count',0)} comments)")
        page.goto(f"https://www.tiktok.com/video/{vid}", wait_until="domcontentloaded")
        page.wait_for_timeout(random.randint(3000,5000))
        raw = get_tiktok_comments(page, vid)
        if not raw: print("    no data, skip"); continue
        rows = []
        for c in raw:
            ts = c.get('create_time',0)
            if ts:
                dt = datetime.fromtimestamp(ts)
                rows.append((vid, str(c.get('cid','')), c.get('text','')[:300],
                    dt.strftime('%Y-%m-%d'), dt.isoformat(),
                    c.get('digg_count',0), (c.get('user',{}) or {}).get('nickname',''), scraped_at))
        conn.executemany("INSERT OR IGNORE INTO tiktok_comments (video_id,comment_id,comment_text,comment_date,comment_datetime,likes,author_name,scraped_at) VALUES(?,?,?,?,?,?,?,?)", rows)
        conn.commit(); print(f"    {len(rows)} rows saved")
        page.wait_for_timeout(random.randint(5000,10000))

def discover_ig_posts(page, username, max_posts=8):
    page.goto(f"https://www.instagram.com/{username}/", wait_until="domcontentloaded")
    page.wait_for_timeout(random.randint(4000,6000))
    if "Page Not Found" in page.title():
        print(f"    @{username} not found"); return []
    posts = []
    try:
        seen = set()
        for lnk in page.query_selector_all("a[href*='/p/']")[:max_posts*2]:
            href = lnk.get_attribute('href') or ''
            m = re.search(r'/p/([A-Za-z0-9_-]+)/', href)
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                posts.append({'shortcode':m.group(1),'post_url':f'https://www.instagram.com/p/{m.group(1)}/','account':username})
    except Exception as e:
        print(f"    discover error: {e}")
    print(f"  @{username}: {len(posts)} posts"); return posts[:max_posts]

def scrape_ig_comments(page, shortcode, conn):
    already = conn.execute("SELECT COUNT(*) FROM instagram_comments WHERE shortcode=?", (shortcode,)).fetchone()[0]
    if already > 10: print(f"    {shortcode} skip ({already})"); return 0
    page.goto(f"https://www.instagram.com/p/{shortcode}/", wait_until="domcontentloaded")
    page.wait_for_timeout(random.randint(4000,6000))
    scraped_at = datetime.now().isoformat(); comments = []
    try:
        for s in page.query_selector_all('script[type="application/json"]'):
            txt = s.inner_text()
            if 'edge_media_to_comment' in txt or 'created_at' in txt:
                data = json.loads(txt)
                def walk(obj, d=0):
                    if d>8: return []
                    found=[]
                    if isinstance(obj,dict):
                        if 'edge_media_to_comment' in obj:
                            for edge in obj['edge_media_to_comment'].get('edges',[]):
                                node=edge.get('node',{}); ts=node.get('created_at',0)
                                if ts:
                                    dt=datetime.fromtimestamp(ts)
                                    found.append({'comment_id':str(node.get('id','')),'comment_text':node.get('text','')[:300],
                                        'comment_date':dt.strftime('%Y-%m-%d'),'comment_datetime':dt.isoformat(),
                                        'likes':node.get('edge_liked_by',{}).get('count',0),
                                        'author_name':(node.get('owner',{}) or {}).get('username','')})
                        for v in obj.values(): found.extend(walk(v,d+1))
                    elif isinstance(obj,list):
                        for i in obj: found.extend(walk(i,d+1))
                    return found
                comments.extend(walk(data))
                if comments: break
    except: pass
    if not comments:
        try:
            for el in page.query_selector_all("time[datetime]"):
                dt_str = el.get_attribute('datetime')
                if not dt_str: continue
                dt = datetime.fromisoformat(dt_str.replace('Z','+00:00'))
                comments.append({'comment_id':'','comment_text':'','comment_date':dt.strftime('%Y-%m-%d'),
                    'comment_datetime':dt.isoformat(),'likes':0,'author_name':''})
        except: pass
    rows=[(shortcode,c['comment_id'],c['comment_text'],c['comment_date'],c['comment_datetime'],c['likes'],c['author_name'],scraped_at) for c in comments]
    if rows:
        conn.executemany("INSERT OR IGNORE INTO instagram_comments (shortcode,comment_id,comment_text,comment_date,comment_datetime,likes,author_name,scraped_at) VALUES(?,?,?,?,?,?,?,?)", rows)
        conn.commit()
    print(f"    {shortcode}: {len(rows)} rows"); return len(rows)

def run_instagram(page, conn):
    print("\n=== Instagram Comment Timeseries ===")
    page.goto("https://www.instagram.com", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    scraped_at = datetime.now().isoformat(); all_posts = []
    for username in INSTAGRAM_ACCOUNTS:
        posts = discover_ig_posts(page, username)
        for p in posts:
            try:
                conn.execute("INSERT OR IGNORE INTO instagram_posts (shortcode,post_url,account,source,scraped_at) VALUES(?,?,?,?,?)",
                    (p['shortcode'],p['post_url'],username,f'account_{username}',scraped_at))
                conn.commit()
            except: pass
        all_posts.extend(posts); page.wait_for_timeout(random.randint(3000,5000))
    print(f"\n{len(all_posts)} posts, scraping comments...")
    for i,post in enumerate(all_posts):
        print(f"  [{i+1}/{len(all_posts)}] @{post.get('account','')} / {post['shortcode']}")
        scrape_ig_comments(page, post['shortcode'], conn)
        page.wait_for_timeout(random.randint(4000,8000))

def print_summary(conn):
    print("\n=== Summary ===")
    for t in ['amazon_review_dates','tiktok_videos','tiktok_comments','instagram_posts','instagram_comments']:
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {n} rows")
    print("\n-- Amazon --")
    for r in conn.execute("SELECT asin,ip,COUNT(*) n,MIN(review_date),MAX(review_date) FROM amazon_review_dates GROUP BY asin ORDER BY n DESC").fetchall():
        print(f"  {r[1]:12} {r[0]}: {r[2]} rows ({r[3]}~{r[4]})")
    print("\n-- TikTok weekly (last 12 weeks) --")
    for r in conn.execute("SELECT strftime('%Y-W%W',comment_date) w,COUNT(*) n FROM tiktok_comments WHERE comment_date IS NOT NULL GROUP BY w ORDER BY w DESC LIMIT 12").fetchall():
        print(f"  {r[0]}: {r[1]:4} {'#'*min(r[1]//20,40)}")

def main():
    modules = sys.argv[1:] if len(sys.argv)>1 else ['amazon','tiktok','instagram']
    print(f"DB: {DB}")
    print(f"Chrome: {CHROME_PROFILE}")
    if not os.path.exists(CHROME_PROFILE):
        print(f"ERROR: Chrome profile not found"); sys.exit(1)
    conn = sqlite3.connect(DB); init_db(conn)
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth
    with Stealth().use_sync(sync_playwright()) as pw:
        print("Launching Chrome with user profile + stealth...")
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=CHROME_PROFILE, channel="chrome", headless=False,
            args=["--no-sandbox","--disable-blink-features=AutomationControlled"],
            viewport={"width":1400,"height":900})
        page = ctx.new_page()
        try:
            if 'amazon'    in modules: run_amazon(page, conn)
            if 'tiktok'    in modules: run_tiktok(page, conn)
            if 'instagram' in modules: run_instagram(page, conn)
            print_summary(conn); print("\nDone.")
        except KeyboardInterrupt:
            print("\nInterrupted, data saved.")
        except Exception as e:
            import traceback; traceback.print_exc()
        finally:
            ctx.close(); conn.close()

if __name__ == "__main__":
    main()
