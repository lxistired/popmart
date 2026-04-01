# 泡泡玛特.md Website Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a daily-updating static website at 泡泡玛特.md displaying Pop Mart overseas social media data (TikTok + Instagram) with character-avatar chart legends, optimized for both human readers and LLM consumption.

**Architecture:** Python exports SQLite → JSON, Astro SSG reads JSON at build time and generates pure HTML pages with ECharts islands for interactive charts. GitHub Actions builds on push, deploys to Cloudflare Pages.

**Tech Stack:** Astro 5, ECharts 5, Python 3.13, SQLite, GitHub Actions, Cloudflare Pages

**Design spec:** `docs/superpowers/specs/2026-03-31-popmart-website-design.md`
**Visual mockup:** `.superpowers/brainstorm/29166-1775008544/content/homepage-v3.html`

---

## File Structure

```
website/                          # New Astro project root
├── astro.config.mjs              # Astro config: output static, no integrations
├── package.json                  # Astro + echarts deps
├── tsconfig.json                 # Astro default
├── src/
│   ├── layouts/
│   │   └── Base.astro            # Shared layout: nav + footer + global CSS
│   ├── pages/
│   │   ├── index.astro           # Homepage: compose all section components
│   │   ├── tiktok.astro          # TikTok detail: timeline + top videos + data table
│   │   ├── instagram.astro       # Instagram detail: timeline + account comparison + data table
│   │   ├── methodology.astro     # Methodology: transparent data collection docs
│   │   └── llms.txt.ts           # Astro endpoint: generates /llms.txt
│   ├── components/
│   │   ├── Hero.astro            # Hero section with floating character avatars
│   │   ├── StatCards.astro       # 4 summary stat cards
│   │   ├── TrendChart.astro      # ECharts stacked bar (client:load island)
│   │   ├── IpShareCards.astro    # 5 IP share cards with avatars
│   │   ├── LatestPosts.astro     # Recent trending posts grid
│   │   └── DataTable.astro       # Semantic <table> for LLM-readable data
│   ├── data/                     # JSON from export_json.py (git-tracked)
│   │   ├── overview.json
│   │   ├── tiktok-videos.json
│   │   ├── tiktok-trend.json
│   │   ├── instagram-posts.json
│   │   ├── instagram-trend.json
│   │   └── ip-share.json
│   └── styles/
│       └── global.css            # Shared styles (fonts, variables, reset)
├── public/
│   ├── characters/               # IP character PNGs (downloaded from Pop Mart CDN)
│   │   ├── labubu.png
│   │   ├── molly.png
│   │   ├── dimoo.png
│   │   └── skullpanda.png
│   └── favicon.svg
└── dist/                         # Build output (gitignored)

phase2_overseas/
├── export_json.py                # New: DB → JSON export script
└── tests/
    └── test_export_json.py       # New: tests for export logic

.github/workflows/
└── deploy-website.yml            # New: build + deploy workflow
```

---

## Task 1: export_json.py — IP Classification + Data Export (TDD)

**Files:**
- Create: `phase2_overseas/export_json.py`
- Create: `phase2_overseas/tests/test_export_json.py`

This is the data pipeline core. Reads overseas_data.db, classifies content by IP, aggregates weekly trends, and writes JSON files consumed by Astro.

- [ ] **Step 1: Write failing tests for IP classification**

```python
# phase2_overseas/tests/test_export_json.py
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_classify_ip_from_source_labubu():
    from export_json import classify_ip
    assert classify_ip('tag/labubu', '') == 'Labubu'

def test_classify_ip_from_source_dimoo():
    from export_json import classify_ip
    assert classify_ip('tag/dimoo', '') == 'Dimoo'

def test_classify_ip_from_source_molly():
    from export_json import classify_ip
    assert classify_ip('tag/molly popmart', '') == 'Molly'

def test_classify_ip_from_source_skullpanda():
    from export_json import classify_ip
    assert classify_ip('tag/skullpanda', '') == 'Skullpanda'

def test_classify_ip_from_title_fallback():
    from export_json import classify_ip
    assert classify_ip('tag/popmart unboxing', 'New Labubu collection!') == 'Labubu'
    assert classify_ip('user/popmartglobal', 'Check out dimoo world') == 'Dimoo'

def test_classify_ip_default():
    from export_json import classify_ip
    assert classify_ip('user/popmartglobal', 'Pop Mart new store opening') == 'Pop Mart'

def test_classify_ip_case_insensitive():
    from export_json import classify_ip
    assert classify_ip('tag/LABUBU', '') == 'Labubu'
    assert classify_ip('tag/popmart', 'SKULLPANDA new series') == 'Skullpanda'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd phase2_overseas && python -m pytest tests/test_export_json.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'export_json'`

- [ ] **Step 3: Implement classify_ip**

```python
# phase2_overseas/export_json.py
"""
export_json.py — Export overseas_data.db to JSON files for the Astro website.

Usage: python export_json.py [--output-dir website/src/data]
"""

import sqlite3
import json
import os
import re
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'overseas_data.db')

IP_PATTERNS = [
    ('Labubu', re.compile(r'labubu|拉布布', re.IGNORECASE)),
    ('Molly', re.compile(r'molly', re.IGNORECASE)),
    ('Dimoo', re.compile(r'dimoo', re.IGNORECASE)),
    ('Skullpanda', re.compile(r'skullpanda|skull\s*panda', re.IGNORECASE)),
    ('Zsiga', re.compile(r'zsiga|嘎子', re.IGNORECASE)),
]


def classify_ip(source, text):
    """Classify content to an IP based on source tag and text content."""
    combined = f'{source} {text}'.lower()
    for ip_name, pattern in IP_PATTERNS:
        if pattern.search(combined):
            return ip_name
    return 'Pop Mart'
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd phase2_overseas && python -m pytest tests/test_export_json.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Write failing tests for data export functions**

```python
# Append to phase2_overseas/tests/test_export_json.py

import sqlite3
import tempfile
import json

@pytest.fixture
def test_db():
    """Create an in-memory DB with sample data."""
    conn = sqlite3.connect(':memory:')
    conn.execute("""CREATE TABLE tiktok_videos (
        id INTEGER PRIMARY KEY, video_id TEXT UNIQUE, author TEXT,
        title TEXT, views INTEGER, likes INTEGER, comments_count INTEGER,
        shares INTEGER, create_time TEXT, source TEXT, scraped_at TEXT)""")
    conn.execute("""CREATE TABLE tiktok_comments (
        id INTEGER PRIMARY KEY, video_id TEXT, comment_id TEXT UNIQUE,
        comment_text TEXT, comment_date TEXT, comment_datetime TEXT,
        likes INTEGER, reply_count INTEGER, author_name TEXT,
        is_author_reply INTEGER, scraped_at TEXT)""")
    conn.execute("""CREATE TABLE instagram_posts (
        id INTEGER PRIMARY KEY, shortcode TEXT UNIQUE, post_url TEXT,
        account TEXT, caption TEXT, likes INTEGER, comments_count INTEGER,
        post_date TEXT, source TEXT, scraped_at TEXT)""")
    conn.execute("""CREATE TABLE instagram_comments (
        id INTEGER PRIMARY KEY, shortcode TEXT, comment_id TEXT,
        comment_text TEXT, comment_date TEXT, comment_datetime TEXT,
        likes INTEGER, author_name TEXT, is_author_reply INTEGER,
        scraped_at TEXT)""")

    # Insert sample tiktok videos (create_time is Unix timestamp)
    conn.executemany("INSERT INTO tiktok_videos VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
        (1, 'v1', 'user1', 'Labubu unboxing!', 10000, 500, 50, 10, '1711929600', 'tag/labubu', '2026-03-31'),
        (2, 'v2', 'user2', 'Dimoo world tour', 5000, 200, 30, 5, '1711929600', 'tag/dimoo', '2026-03-31'),
        (3, 'v3', 'user3', 'Pop Mart haul', 8000, 300, 40, 8, '1712534400', 'tag/popmart unboxing', '2026-03-31'),
    ])
    # Insert sample tiktok comments
    conn.executemany("INSERT INTO tiktok_comments VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
        (1, 'v1', 'c1', 'Love it!', '2026-03-01', '2026-03-01T10:00:00', 5, 0, 'fan1', 0, '2026-03-31'),
        (2, 'v1', 'c2', 'Want one!', '2026-03-01', '2026-03-01T11:00:00', 3, 0, 'fan2', 0, '2026-03-31'),
        (3, 'v2', 'c3', 'Cute!', '2026-03-08', '2026-03-08T10:00:00', 2, 0, 'fan3', 0, '2026-03-31'),
    ])
    # Insert sample instagram posts
    conn.executemany("INSERT INTO instagram_posts VALUES (?,?,?,?,?,?,?,?,?,?)", [
        (1, 'ABC1', 'https://instagram.com/p/ABC1', 'popmart', 'New Labubu drop!', 1000, 50, '2026-03-01', 'instagrapi', '2026-03-31'),
        (2, 'ABC2', 'https://instagram.com/p/ABC2', 'popmart', 'Molly series', 800, 30, '2026-03-08', 'instagrapi', '2026-03-31'),
    ])
    # Insert sample instagram comments
    conn.executemany("INSERT INTO instagram_comments VALUES (?,?,?,?,?,?,?,?,?,?)", [
        (1, 'ABC1', 'ic1', 'Amazing!', '2026-03-01', '2026-03-01T12:00:00', 5, 'fan1', 0, '2026-03-31'),
        (2, 'ABC1', 'ic2', 'Need this!', '2026-03-02', '2026-03-02T12:00:00', 2, 'fan2', 0, '2026-03-31'),
        (3, 'ABC2', 'ic3', 'So pretty', '2026-03-08', '2026-03-08T12:00:00', 1, 'fan3', 0, '2026-03-31'),
    ])
    conn.commit()
    yield conn
    conn.close()


def test_export_overview(test_db):
    from export_json import export_overview
    result = export_overview(test_db)
    assert result['tiktok_videos'] == 3
    assert result['tiktok_comments'] == 3
    assert result['instagram_posts'] == 2
    assert result['instagram_comments'] == 3
    assert 'updated_at' in result


def test_export_ip_share(test_db):
    from export_json import export_ip_share
    result = export_ip_share(test_db)
    # result is a list of {ip, tiktok_videos, tiktok_comments, ...}
    assert isinstance(result, list)
    labubu = next(r for r in result if r['ip'] == 'Labubu')
    assert labubu['tiktok_videos'] == 1


def test_export_tiktok_trend(test_db):
    from export_json import export_tiktok_trend
    result = export_tiktok_trend(test_db)
    # result is list of {week, ip, count}
    assert isinstance(result, list)
    assert all('week' in r and 'ip' in r and 'count' in r for r in result)
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd phase2_overseas && python -m pytest tests/test_export_json.py -v`
Expected: FAIL — `ImportError: cannot import name 'export_overview'`

- [ ] **Step 7: Implement export functions**

Append to `phase2_overseas/export_json.py`:

```python
def _unix_to_date(ts):
    """Convert Unix timestamp string to YYYY-MM-DD."""
    try:
        return datetime.utcfromtimestamp(int(ts)).strftime('%Y-%m-%d')
    except (ValueError, TypeError, OSError):
        return None


def _week_key(date_str):
    """Convert YYYY-MM-DD to ISO week key like '2026-W09'."""
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        return f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"
    except (ValueError, TypeError):
        return None


def export_overview(conn):
    """Export summary statistics."""
    counts = {}
    for table in ['tiktok_videos', 'tiktok_comments', 'instagram_posts', 'instagram_comments']:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        counts[table] = row[0]
    counts['updated_at'] = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    return counts


def export_ip_share(conn):
    """Export IP share of voice across platforms."""
    # Classify tiktok videos
    rows = conn.execute("SELECT video_id, source, title FROM tiktok_videos").fetchall()
    video_ip = {}
    ip_stats = {}
    for video_id, source, title in rows:
        ip = classify_ip(source or '', title or '')
        video_ip[video_id] = ip
        if ip not in ip_stats:
            ip_stats[ip] = {'ip': ip, 'tiktok_videos': 0, 'tiktok_comments': 0,
                            'instagram_posts': 0, 'instagram_comments': 0}
        ip_stats[ip]['tiktok_videos'] += 1

    # Count tiktok comments by IP (via video)
    comment_rows = conn.execute("SELECT video_id FROM tiktok_comments").fetchall()
    for (vid,) in comment_rows:
        ip = video_ip.get(vid, 'Pop Mart')
        if ip not in ip_stats:
            ip_stats[ip] = {'ip': ip, 'tiktok_videos': 0, 'tiktok_comments': 0,
                            'instagram_posts': 0, 'instagram_comments': 0}
        ip_stats[ip]['tiktok_comments'] += 1

    # Classify instagram posts
    post_ip = {}
    ig_rows = conn.execute("SELECT shortcode, account, caption FROM instagram_posts").fetchall()
    for shortcode, account, caption in ig_rows:
        ip = classify_ip(account or '', caption or '')
        post_ip[shortcode] = ip
        if ip not in ip_stats:
            ip_stats[ip] = {'ip': ip, 'tiktok_videos': 0, 'tiktok_comments': 0,
                            'instagram_posts': 0, 'instagram_comments': 0}
        ip_stats[ip]['instagram_posts'] += 1

    # Count instagram comments by IP (via post)
    ig_comment_rows = conn.execute("SELECT shortcode FROM instagram_comments").fetchall()
    for (sc,) in ig_comment_rows:
        ip = post_ip.get(sc, 'Pop Mart')
        if ip not in ip_stats:
            ip_stats[ip] = {'ip': ip, 'tiktok_videos': 0, 'tiktok_comments': 0,
                            'instagram_posts': 0, 'instagram_comments': 0}
        ip_stats[ip]['instagram_comments'] += 1

    # Calculate total share
    result = sorted(ip_stats.values(), key=lambda x: x['tiktok_comments'] + x['instagram_comments'], reverse=True)
    total = sum(r['tiktok_comments'] + r['instagram_comments'] for r in result)
    for r in result:
        r['total_comments'] = r['tiktok_comments'] + r['instagram_comments']
        r['share_pct'] = round(r['total_comments'] / total * 100, 1) if total else 0
    return result


def export_tiktok_trend(conn):
    """Export weekly comment counts by IP for TikTok."""
    # Build video_id → IP mapping
    rows = conn.execute("SELECT video_id, source, title FROM tiktok_videos").fetchall()
    video_ip = {vid: classify_ip(src or '', title or '') for vid, src, title in rows}

    # Aggregate comments by week and IP
    comments = conn.execute("SELECT video_id, comment_date FROM tiktok_comments").fetchall()
    weekly = {}
    for vid, date in comments:
        week = _week_key(date)
        ip = video_ip.get(vid, 'Pop Mart')
        if week:
            key = (week, ip)
            weekly[key] = weekly.get(key, 0) + 1

    result = [{'week': w, 'ip': ip, 'count': c} for (w, ip), c in sorted(weekly.items())]
    return result


def export_tiktok_videos(conn):
    """Export top TikTok videos with IP classification."""
    rows = conn.execute("""SELECT video_id, author, title, views, likes,
        comments_count, shares, create_time, source FROM tiktok_videos
        ORDER BY views DESC""").fetchall()
    result = []
    for vid, author, title, views, likes, comments, shares, ts, source in rows:
        result.append({
            'video_id': vid, 'author': author, 'title': title,
            'views': views, 'likes': likes, 'comments': comments,
            'shares': shares, 'date': _unix_to_date(ts),
            'ip': classify_ip(source or '', title or ''),
        })
    return result


def export_instagram_posts(conn):
    """Export Instagram posts with IP classification."""
    rows = conn.execute("""SELECT shortcode, post_url, account, caption,
        likes, comments_count, post_date FROM instagram_posts
        ORDER BY post_date DESC""").fetchall()
    result = []
    for sc, url, account, caption, likes, comments, date in rows:
        result.append({
            'shortcode': sc, 'url': url, 'account': account,
            'caption': (caption or '')[:200], 'likes': likes,
            'comments': comments, 'date': date,
            'ip': classify_ip(account or '', caption or ''),
        })
    return result


def export_instagram_trend(conn):
    """Export weekly comment counts by IP for Instagram."""
    # Build shortcode → IP mapping
    rows = conn.execute("SELECT shortcode, account, caption FROM instagram_posts").fetchall()
    post_ip = {sc: classify_ip(acc or '', cap or '') for sc, acc, cap in rows}

    comments = conn.execute("SELECT shortcode, comment_date FROM instagram_comments").fetchall()
    weekly = {}
    for sc, date in comments:
        week = _week_key(date)
        ip = post_ip.get(sc, 'Pop Mart')
        if week:
            key = (week, ip)
            weekly[key] = weekly.get(key, 0) + 1

    result = [{'week': w, 'ip': ip, 'count': c} for (w, ip), c in sorted(weekly.items())]
    return result


def write_all(output_dir):
    """Export all JSON files to output_dir."""
    conn = sqlite3.connect(DB_PATH)
    os.makedirs(output_dir, exist_ok=True)

    exports = {
        'overview.json': export_overview(conn),
        'tiktok-videos.json': export_tiktok_videos(conn),
        'tiktok-trend.json': export_tiktok_trend(conn),
        'instagram-posts.json': export_instagram_posts(conn),
        'instagram-trend.json': export_instagram_trend(conn),
        'ip-share.json': export_ip_share(conn),
    }

    for filename, data in exports.items():
        path = os.path.join(output_dir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ {filename} ({len(json.dumps(data))} bytes)")

    conn.close()
    print(f"\n✅ All JSON exported to {output_dir}")


if __name__ == '__main__':
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE_DIR, '..', 'website', 'src', 'data')
    write_all(out)
```

- [ ] **Step 8: Run all tests**

Run: `cd phase2_overseas && python -m pytest tests/test_export_json.py -v`
Expected: All 10 tests PASS

- [ ] **Step 9: Run export against real DB and verify output**

Run: `cd phase2_overseas && python -u export_json.py ../website/src/data`
Expected: 6 JSON files written with real data counts

- [ ] **Step 10: Commit**

```bash
cd phase2_overseas
git add export_json.py tests/test_export_json.py
git commit -m "feat: add export_json.py for website data pipeline (TDD)"
```

---

## Task 2: Scaffold Astro Project

**Files:**
- Create: `website/package.json`
- Create: `website/astro.config.mjs`
- Create: `website/tsconfig.json`
- Create: `website/public/favicon.svg`
- Create: `website/.gitignore`

- [ ] **Step 1: Initialize Astro project**

```bash
cd "C:/Users/lxxxxxx/Desktop/个人项目/popmart"
npm create astro@latest website -- --template minimal --no-install --no-git --typescript strict
```

- [ ] **Step 2: Install dependencies**

```bash
cd website
npm install
npm install echarts
```

- [ ] **Step 3: Configure Astro for static output**

Replace `website/astro.config.mjs`:

```javascript
// @ts-check
import { defineConfig } from 'astro/config';

export default defineConfig({
  output: 'static',
  build: { format: 'directory' },
  vite: {
    build: { rollupOptions: { external: [] } }
  }
});
```

- [ ] **Step 4: Create favicon**

```svg
<!-- website/public/favicon.svg -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="6" fill="#DC143C"/>
  <text x="16" y="23" text-anchor="middle" font-family="sans-serif" font-weight="900" font-size="16" fill="white">PM</text>
</svg>
```

- [ ] **Step 5: Verify build works**

Run: `cd website && npm run build`
Expected: Build succeeds, `dist/` directory created

- [ ] **Step 6: Commit**

```bash
git add website/
git commit -m "feat: scaffold Astro project with ECharts"
```

---

## Task 3: Download Character Images + Global CSS

**Files:**
- Create: `website/public/characters/labubu.png`
- Create: `website/public/characters/molly.png`
- Create: `website/public/characters/dimoo.png`
- Create: `website/public/characters/skullpanda.png`
- Create: `website/src/styles/global.css`

- [ ] **Step 1: Download character images from Pop Mart CDN**

```bash
cd website/public
mkdir -p characters
curl -o characters/labubu.png "https://prod-america-res.popmart.com/default/20260326_145609_754974____local-warehouse-labubu-time-to-chill_____1200x1200.jpg?x-oss-process=image/format,webp"
curl -o characters/molly.png "https://prod-america-res.popmart.com/default/20260220_170237_780323____1_angry-molly-original-fire-xl-designer-toy_figurine_details_pop-mart-us_____1200x1200.jpg?x-oss-process=image/format,webp"
curl -o characters/dimoo.png "https://prod-america-res.popmart.com/default/20260226_143552_928377____1_-dimoo-world-cinnamoroll-figurine_figurine_details_pop-mart-us_____1200x1200.jpg?x-oss-process=image/format,webp"
curl -o characters/skullpanda.png "https://prod-america-res.popmart.com/default/20260205_150600_742869____skullpanda_____1200x1200.jpg?x-oss-process=image/format,webp"
```

- [ ] **Step 2: Write global CSS**

```css
/* website/src/styles/global.css */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&family=Noto+Sans+SC:wght@400;500;700;900&display=swap');

:root {
  --color-brand: #DC143C;
  --color-bg: #fafafa;
  --color-card: #ffffff;
  --color-text: #1a1a1a;
  --color-muted: #999;
  --color-labubu: #FF6F00;
  --color-dimoo: #1976D2;
  --color-molly: #E91E63;
  --color-skullpanda: #7B1FA2;
  --color-popmart: #D32F2F;
  --radius: 16px;
  --shadow: 0 2px 12px rgba(0,0,0,0.04);
  --shadow-hover: 0 12px 32px rgba(0,0,0,0.1);
  --max-width: 1100px;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: 'Inter', 'Noto Sans SC', sans-serif;
  background: var(--color-bg);
  color: var(--color-text);
  overflow-x: hidden;
}

a { text-decoration: none; color: inherit; }

.section {
  max-width: var(--max-width);
  margin: 48px auto;
  padding: 0 24px;
}

.section-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 24px;
}

.section-header h2 { font-size: 24px; font-weight: 800; }

.section-header .en {
  font-size: 13px; color: #bbb; font-weight: 600;
  letter-spacing: 1px; text-transform: uppercase;
}
```

- [ ] **Step 3: Commit**

```bash
git add website/public/characters/ website/src/styles/
git commit -m "feat: add character images and global CSS"
```

---

## Task 4: Base Layout (Nav + Footer)

**Files:**
- Create: `website/src/layouts/Base.astro`

- [ ] **Step 1: Write Base layout**

```astro
---
// website/src/layouts/Base.astro
interface Props { title: string; description?: string; }
const { title, description = '海外社媒另类数据追踪 · 日更 · LLM 友好' } = Astro.props;
import '../styles/global.css';
---
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <meta name="description" content={description}>
  <meta property="og:title" content={title}>
  <meta property="og:description" content={description}>
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
</head>
<body>
  <nav>
    <div class="nav-logo">
      <a href="/">POP MART<span>.md</span></a>
    </div>
    <div class="nav-links">
      <a href="/">首页</a>
      <a href="/tiktok">TikTok</a>
      <a href="/instagram">Instagram</a>
      <a href="/methodology">方法论</a>
      <a href="/llms.txt" class="llms-link">llms.txt</a>
    </div>
  </nav>

  <main>
    <slot />
  </main>

  <footer>
    <div>
      <span class="footer-brand">泡泡玛特.md</span>
      <span class="footer-desc">海外社媒另类数据追踪 · 数据每日更新</span>
    </div>
    <div class="footer-links">
      <span class="llms-badge">🤖 LLM-friendly · /llms.txt</span>
      <a href="https://github.com/lxistired/popmart" target="_blank">GitHub</a>
      <a href="/methodology">方法论</a>
    </div>
  </footer>
</body>
</html>

<style>
  nav {
    position: fixed; top: 0; left: 0; right: 0; z-index: 100;
    background: rgba(255,255,255,0.92);
    backdrop-filter: blur(20px);
    border-bottom: 1px solid rgba(0,0,0,0.06);
    padding: 0 48px; height: 64px;
    display: flex; align-items: center; justify-content: space-between;
  }
  .nav-logo a {
    font-weight: 900; font-size: 20px;
    letter-spacing: 2px; color: var(--color-brand);
  }
  .nav-logo span { color: #1a1a1a; font-weight: 600; font-size: 14px; margin-left: 8px; letter-spacing: 0; }
  .nav-links { display: flex; gap: 32px; align-items: center; }
  .nav-links a { color: #666; font-size: 14px; font-weight: 500; transition: color 0.2s; }
  .nav-links a:hover { color: var(--color-brand); }
  .llms-link {
    font-family: 'SF Mono', 'Fira Code', monospace !important;
    font-size: 12px !important;
    background: #f5f5f5; padding: 4px 10px;
    border-radius: 6px; color: #888 !important;
  }
  main { margin-top: 64px; }
  footer {
    margin-top: 64px; padding: 32px 48px;
    background: #1a1a1a; color: rgba(255,255,255,0.5);
    font-size: 13px; display: flex;
    justify-content: space-between; align-items: center;
  }
  .footer-brand { font-weight: 700; color: rgba(255,255,255,0.8); }
  .footer-desc { margin-left: 16px; }
  .footer-links { display: flex; align-items: center; gap: 16px; }
  .footer-links a { color: rgba(255,255,255,0.7); }
  .llms-badge {
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 8px; padding: 6px 12px;
    font-size: 12px; font-family: 'SF Mono', monospace;
    color: rgba(255,255,255,0.6);
  }
</style>
```

- [ ] **Step 2: Create minimal index page to test layout**

```astro
---
// website/src/pages/index.astro
import Base from '../layouts/Base.astro';
---
<Base title="泡泡玛特.md — 海外另类数据追踪">
  <div style="padding: 100px 48px; text-align: center;">
    <h1>Layout works!</h1>
  </div>
</Base>
```

- [ ] **Step 3: Test build and dev server**

Run: `cd website && npm run build`
Expected: Build succeeds, `dist/index.html` contains nav and footer HTML

- [ ] **Step 4: Commit**

```bash
git add website/src/layouts/ website/src/pages/index.astro
git commit -m "feat: add Base layout with nav and footer"
```

---

## Task 5: Homepage Components (Hero + StatCards + IpShareCards + LatestPosts)

**Files:**
- Create: `website/src/components/Hero.astro`
- Create: `website/src/components/StatCards.astro`
- Create: `website/src/components/IpShareCards.astro`
- Create: `website/src/components/LatestPosts.astro`

These are all pure Astro components (no client JS). They read JSON data at build time and output semantic HTML.

- [ ] **Step 1: Ensure JSON data files exist**

Run: `cd phase2_overseas && python -u export_json.py ../website/src/data`
Expected: 6 JSON files in `website/src/data/`

- [ ] **Step 2: Write Hero.astro**

```astro
---
// website/src/components/Hero.astro
import overview from '../data/overview.json';
const characters = [
  { name: 'Labubu', img: '/characters/labubu.png', size: 110, pos: 'left:6%;top:16%', delay: '0s' },
  { name: 'Molly', img: '/characters/molly.png', size: 85, pos: 'right:7%;top:10%', delay: '1.5s' },
  { name: 'Dimoo', img: '/characters/dimoo.png', size: 75, pos: 'left:11%;bottom:14%', delay: '3s' },
  { name: 'Skullpanda', img: '/characters/skullpanda.png', size: 95, pos: 'right:10%;bottom:16%', delay: '0.8s' },
];
---
<section class="hero">
  <div class="hero-chars">
    {characters.map(c => (
      <div class="char-float" style={`width:${c.size}px;height:${c.size}px;${c.pos};animation-delay:${c.delay}`}>
        <img src={c.img} alt={c.name} width={c.size} height={c.size} loading="eager">
      </div>
    ))}
  </div>
  <div class="hero-content">
    <div class="hero-badge">ALTERNATIVE DATA TRACKER</div>
    <h1>泡泡玛特<span class="dot-md">.md</span></h1>
    <p class="hero-sub">海外社媒另类数据 · 日更追踪 · LLM 友好</p>
    <p class="hero-update">数据更新于 <strong>{overview.updated_at?.slice(0,16).replace('T',' ')} UTC</strong> · 覆盖 TikTok & Instagram</p>
  </div>
</section>

<style>
  .hero {
    height: 480px;
    background: linear-gradient(135deg, #1a0a2e 0%, #16213e 40%, #0f3460 100%);
    position: relative; overflow: hidden;
    display: flex; align-items: center; justify-content: center;
  }
  .hero::before {
    content: ''; position: absolute; inset: 0;
    background:
      radial-gradient(circle at 20% 50%, rgba(220,20,60,0.15) 0%, transparent 50%),
      radial-gradient(circle at 80% 30%, rgba(255,176,0,0.1) 0%, transparent 40%),
      radial-gradient(circle at 60% 80%, rgba(138,43,226,0.1) 0%, transparent 40%);
  }
  .hero-chars { position: absolute; inset: 0; pointer-events: none; }
  .char-float {
    position: absolute; border-radius: 50%; overflow: hidden;
    box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    animation: float 6s ease-in-out infinite;
    border: 3px solid rgba(255,255,255,0.2); background: #fff;
  }
  .char-float img { width: 100%; height: 100%; object-fit: cover; transform: scale(1.3); }
  @keyframes float {
    0%, 100% { transform: translateY(0) rotate(0deg); }
    33% { transform: translateY(-15px) rotate(3deg); }
    66% { transform: translateY(8px) rotate(-2deg); }
  }
  .hero-content { position: relative; z-index: 2; text-align: center; color: white; }
  .hero-badge {
    display: inline-block; background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.2); border-radius: 20px;
    padding: 6px 16px; font-size: 12px; font-weight: 600;
    letter-spacing: 1px; margin-bottom: 24px; color: rgba(255,255,255,0.8);
  }
  .hero h1 {
    font-size: 56px; font-weight: 900; letter-spacing: -1px; margin-bottom: 8px;
    background: linear-gradient(135deg, #fff 0%, #FFB74D 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }
  .dot-md {
    font-weight: 400;
    background: linear-gradient(135deg, #FFB74D 0%, #FF7043 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }
  .hero-sub { font-size: 18px; color: rgba(255,255,255,0.6); margin-bottom: 32px; }
  .hero-update { font-size: 13px; color: rgba(255,255,255,0.4); }
  .hero-update strong { color: rgba(255,255,255,0.7); }
</style>
```

- [ ] **Step 3: Write StatCards.astro**

```astro
---
// website/src/components/StatCards.astro
import overview from '../data/overview.json';
const stats = [
  { icon: '📹', value: overview.tiktok_videos.toLocaleString(), label: 'TikTok 视频', bg: '#fff3e0' },
  { icon: '💬', value: (overview.tiktok_comments + overview.instagram_comments).toLocaleString(), label: '总评论数', bg: '#e8f5e9' },
  { icon: '📸', value: overview.instagram_posts.toLocaleString(), label: 'Instagram 帖子', bg: '#fce4ec' },
  { icon: '📊', value: `${((overview.tiktok_comments + overview.instagram_comments) / (overview.tiktok_videos + overview.instagram_posts)).toFixed(1)}`, label: '平均评论/帖', bg: '#e3f2fd' },
];
---
<div class="stats-row">
  {stats.map(s => (
    <article class="stat-card">
      <div class="stat-icon" style={`background:${s.bg}`}>{s.icon}</div>
      <div class="stat-value">{s.value}</div>
      <div class="stat-label">{s.label}</div>
    </article>
  ))}
</div>

<style>
  .stats-row {
    max-width: var(--max-width); margin: -50px auto 0;
    padding: 0 24px; position: relative; z-index: 10;
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;
  }
  .stat-card {
    background: var(--color-card); border-radius: var(--radius);
    padding: 24px; box-shadow: var(--shadow);
    transition: transform 0.2s, box-shadow 0.2s;
  }
  .stat-card:hover { transform: translateY(-4px); box-shadow: var(--shadow-hover); }
  .stat-icon {
    width: 40px; height: 40px; border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 20px; margin-bottom: 16px;
  }
  .stat-value { font-size: 32px; font-weight: 900; letter-spacing: -1px; }
  .stat-label { font-size: 13px; color: var(--color-muted); margin-top: 4px; font-weight: 500; }
</style>
```

- [ ] **Step 4: Write IpShareCards.astro**

```astro
---
// website/src/components/IpShareCards.astro
import ipShare from '../data/ip-share.json';
const IP_COLORS: Record<string, string> = {
  Labubu: '#FF6F00', Dimoo: '#1976D2', Molly: '#E91E63',
  Skullpanda: '#7B1FA2', 'Pop Mart': '#D32F2F', Zsiga: '#00897B',
};
const IP_IMAGES: Record<string, string> = {
  Labubu: '/characters/labubu.png', Dimoo: '/characters/dimoo.png',
  Molly: '/characters/molly.png', Skullpanda: '/characters/skullpanda.png',
};
const top5 = ipShare.slice(0, 5);
---
<section class="section">
  <div class="section-header">
    <h2>IP 声量份额</h2>
    <span class="en">IP Share of Voice</span>
  </div>
  <div class="ip-grid">
    {top5.map((ip: any) => (
      <article class="ip-card" style={`--accent: ${IP_COLORS[ip.ip] || '#999'}`}>
        <div class="ip-avatar">
          {IP_IMAGES[ip.ip]
            ? <img src={IP_IMAGES[ip.ip]} alt={ip.ip} width="72" height="72" loading="lazy">
            : <span class="ip-initial">{ip.ip.slice(0,2)}</span>
          }
        </div>
        <h4>{ip.ip}</h4>
        <div class="ip-share">{ip.share_pct}%</div>
        <div class="ip-label">评论占比</div>
      </article>
    ))}
  </div>
</section>

<style>
  .ip-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; }
  .ip-card {
    background: var(--color-card); border-radius: var(--radius);
    padding: 24px 16px; text-align: center;
    box-shadow: var(--shadow); transition: transform 0.2s;
    position: relative; overflow: hidden; cursor: default;
  }
  .ip-card::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0;
    height: 4px; background: var(--accent);
  }
  .ip-card:hover { transform: translateY(-6px); box-shadow: var(--shadow-hover); }
  .ip-avatar {
    width: 72px; height: 72px; border-radius: 50%;
    margin: 0 auto 14px; overflow: hidden;
    box-shadow: 0 4px 16px rgba(0,0,0,0.1);
    border: 3px solid white; background: #fff;
  }
  .ip-avatar img { width: 100%; height: 100%; object-fit: cover; transform: scale(1.3); }
  .ip-initial {
    display: flex; width: 100%; height: 100%;
    align-items: center; justify-content: center;
    font-size: 24px; font-weight: 900; color: white;
    background: var(--accent);
  }
  .ip-card h4 { font-size: 15px; font-weight: 700; margin-bottom: 6px; }
  .ip-share { font-size: 28px; font-weight: 900; }
  .ip-label { font-size: 11px; color: var(--color-muted); margin-top: 2px; }
</style>
```

- [ ] **Step 5: Write LatestPosts.astro**

```astro
---
// website/src/components/LatestPosts.astro
import tiktokVideos from '../data/tiktok-videos.json';
import instagramPosts from '../data/instagram-posts.json';

// Mix latest from both platforms, sort by date desc, take 4
const tiktok = tiktokVideos.slice(0, 20).map((v: any) => ({ ...v, platform: 'tiktok' }));
const instagram = instagramPosts.slice(0, 20).map((p: any) => ({ ...p, platform: 'instagram' }));
const all = [...tiktok, ...instagram]
  .sort((a: any, b: any) => (b.date || '').localeCompare(a.date || ''))
  .slice(0, 4);
---
<section class="section">
  <div class="section-header">
    <h2>最新热门</h2>
    <span class="en">Trending Now</span>
  </div>
  <div class="posts-grid">
    {all.map((post: any) => (
      <article class="post-card">
        <div class={`post-platform ${post.platform}`}>
          {post.platform === 'tiktok' ? 'T' : 'I'}
        </div>
        <div class="post-meta">
          <h4>{(post.title || post.caption || '').slice(0, 60)}</h4>
          <div class="post-stats">
            {post.views != null && <span>👁 {(post.views/1000).toFixed(0)}K</span>}
            {post.likes != null && <span>❤️ {post.likes > 1000 ? `${(post.likes/1000).toFixed(1)}K` : post.likes}</span>}
            {(post.comments ?? post.comments_count) != null && <span>💬 {(post.comments ?? post.comments_count).toLocaleString()}</span>}
          </div>
          <div class="post-date">{post.date} · @{post.author || post.account}</div>
        </div>
      </article>
    ))}
  </div>
</section>

<style>
  .posts-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
  .post-card {
    background: var(--color-card); border-radius: var(--radius);
    padding: 20px 24px; box-shadow: var(--shadow);
    display: flex; gap: 16px; align-items: flex-start;
    transition: transform 0.2s;
  }
  .post-card:hover { transform: translateY(-2px); }
  .post-platform {
    width: 44px; height: 44px; border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0; color: white; font-weight: 900; font-size: 18px;
  }
  .post-platform.tiktok { background: #1a1a1a; }
  .post-platform.instagram { background: linear-gradient(135deg, #833ab4, #fd1d1d, #fcb045); }
  .post-meta { flex: 1; }
  .post-meta h4 {
    font-size: 14px; font-weight: 600;
    display: -webkit-box; -webkit-line-clamp: 1;
    -webkit-box-orient: vertical; overflow: hidden;
    margin-bottom: 6px;
  }
  .post-stats { font-size: 12px; color: #888; margin-top: 4px; display: flex; gap: 14px; }
  .post-date { font-size: 11px; color: #ccc; margin-top: 6px; }
</style>
```

- [ ] **Step 6: Build to verify all components compile**

Run: `cd website && npm run build`
Expected: Build succeeds without errors

- [ ] **Step 7: Commit**

```bash
git add website/src/components/Hero.astro website/src/components/StatCards.astro \
       website/src/components/IpShareCards.astro website/src/components/LatestPosts.astro
git commit -m "feat: add homepage components (Hero, Stats, IpShare, Posts)"
```

---

## Task 6: TrendChart ECharts Island + DataTable

**Files:**
- Create: `website/src/components/TrendChart.astro`
- Create: `website/src/components/DataTable.astro`

TrendChart is the only component that uses client-side JS (ECharts). It loads as an Astro island with `client:load`.

- [ ] **Step 1: Write TrendChart.astro**

```astro
---
// website/src/components/TrendChart.astro
// This component renders the ECharts container and injects data as a script
import tiktokTrend from '../data/tiktok-trend.json';
import instagramTrend from '../data/instagram-trend.json';

// Merge both platform trends
const allTrend = [...tiktokTrend, ...instagramTrend];

// Get unique weeks and IPs
const weeks = [...new Set(allTrend.map((r: any) => r.week))].sort();
const ips = ['Labubu', 'Dimoo', 'Molly', 'Skullpanda', 'Pop Mart'];
const IP_COLORS: Record<string, string> = {
  Labubu: '#FF6F00', Dimoo: '#1976D2', Molly: '#E91E63',
  Skullpanda: '#7B1FA2', 'Pop Mart': '#D32F2F',
};

// Build series data
const series = ips.map(ip => ({
  name: ip,
  type: 'bar',
  stack: 'total',
  data: weeks.map(w => {
    const matches = allTrend.filter((r: any) => r.week === w && r.ip === ip);
    return matches.reduce((sum: number, r: any) => sum + r.count, 0);
  }),
  itemStyle: { color: IP_COLORS[ip] || '#999' },
}));

const chartData = JSON.stringify({ weeks, series });
---
<section class="section">
  <div class="section-header">
    <h2>评论趋势</h2>
    <span class="en">Weekly Comment Trend</span>
  </div>
  <div class="chart-container">
    <div id="trend-chart" style="width:100%;height:400px;"></div>
    <div class="chart-legend">
      {ips.map(ip => (
        <div class="legend-item">
          {['/characters/labubu.png','/characters/dimoo.png','/characters/molly.png','/characters/skullpanda.png',''][ips.indexOf(ip)] && (
            <div class="legend-avatar">
              <img src={['/characters/labubu.png','/characters/dimoo.png','/characters/molly.png','/characters/skullpanda.png',''][ips.indexOf(ip)]} alt={ip} width="36" height="36" loading="lazy">
            </div>
          )}
          <div class="legend-color" style={`background:${IP_COLORS[ip]}`}></div>
          {ip}
        </div>
      ))}
    </div>
  </div>
</section>

<script define:vars={{ chartData }}>
  import('https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.esm.min.js').then(echarts => {
    const data = JSON.parse(chartData);
    const chart = echarts.init(document.getElementById('trend-chart'));
    chart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 40, right: 20, top: 20, bottom: 40 },
      xAxis: { type: 'category', data: data.weeks, axisLabel: { rotate: 45, fontSize: 10 } },
      yAxis: { type: 'value' },
      series: data.series,
    });
    window.addEventListener('resize', () => chart.resize());
  });
</script>

<style>
  .chart-container {
    background: var(--color-card); border-radius: 20px;
    padding: 32px; box-shadow: var(--shadow);
  }
  .chart-legend {
    display: flex; justify-content: center; gap: 28px;
    margin-top: 20px; flex-wrap: wrap;
  }
  .legend-item {
    display: flex; align-items: center; gap: 10px;
    font-size: 14px; font-weight: 600; color: #444;
  }
  .legend-avatar {
    width: 36px; height: 36px; border-radius: 50%;
    overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.12);
    border: 2px solid white; flex-shrink: 0; background: #fff;
  }
  .legend-avatar img { width: 100%; height: 100%; object-fit: cover; transform: scale(1.3); }
  .legend-color { width: 12px; height: 12px; border-radius: 3px; flex-shrink: 0; }
</style>
```

- [ ] **Step 2: Write DataTable.astro**

```astro
---
// website/src/components/DataTable.astro
// Generic semantic table for LLM-readable data
interface Props {
  title: string;
  columns: { key: string; label: string }[];
  rows: Record<string, any>[];
  maxRows?: number;
}
const { title, columns, rows, maxRows = 50 } = Astro.props;
const displayRows = rows.slice(0, maxRows);
---
<section class="section" aria-label={title}>
  <div class="section-header">
    <h2>{title}</h2>
    <span class="en">{displayRows.length} of {rows.length} rows</span>
  </div>
  <div class="table-wrapper">
    <table>
      <thead>
        <tr>
          {columns.map(col => <th>{col.label}</th>)}
        </tr>
      </thead>
      <tbody>
        {displayRows.map(row => (
          <tr>
            {columns.map(col => <td>{row[col.key] ?? ''}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
</section>

<style>
  .table-wrapper { overflow-x: auto; }
  table {
    width: 100%; border-collapse: collapse;
    background: var(--color-card); border-radius: var(--radius);
    box-shadow: var(--shadow); overflow: hidden;
  }
  th {
    text-align: left; padding: 12px 16px;
    font-size: 12px; font-weight: 600;
    color: var(--color-muted); text-transform: uppercase;
    letter-spacing: 0.5px; border-bottom: 2px solid #f0f0f0;
  }
  td {
    padding: 10px 16px; font-size: 13px;
    border-bottom: 1px solid #f5f5f5;
    max-width: 300px; overflow: hidden;
    text-overflow: ellipsis; white-space: nowrap;
  }
  tr:hover td { background: #fafafa; }
</style>
```

- [ ] **Step 3: Build to verify**

Run: `cd website && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add website/src/components/TrendChart.astro website/src/components/DataTable.astro
git commit -m "feat: add TrendChart (ECharts island) and DataTable components"
```

---

## Task 7: Assemble Homepage

**Files:**
- Modify: `website/src/pages/index.astro`

- [ ] **Step 1: Write full homepage**

```astro
---
// website/src/pages/index.astro
import Base from '../layouts/Base.astro';
import Hero from '../components/Hero.astro';
import StatCards from '../components/StatCards.astro';
import TrendChart from '../components/TrendChart.astro';
import IpShareCards from '../components/IpShareCards.astro';
import LatestPosts from '../components/LatestPosts.astro';
---
<Base title="泡泡玛特.md — 海外另类数据追踪">
  <Hero />
  <StatCards />
  <TrendChart />
  <IpShareCards />
  <LatestPosts />
</Base>
```

- [ ] **Step 2: Build and verify HTML output**

Run: `cd website && npm run build && head -100 dist/index.html`
Expected: Semantic HTML with `<section>`, `<article>`, `<table>` tags. No JS hydration framework code.

- [ ] **Step 3: Commit**

```bash
git add website/src/pages/index.astro
git commit -m "feat: assemble homepage with all components"
```

---

## Task 8: TikTok + Instagram Detail Pages

**Files:**
- Create: `website/src/pages/tiktok.astro`
- Create: `website/src/pages/instagram.astro`

- [ ] **Step 1: Write TikTok detail page**

```astro
---
// website/src/pages/tiktok.astro
import Base from '../layouts/Base.astro';
import DataTable from '../components/DataTable.astro';
import tiktokVideos from '../data/tiktok-videos.json';
import tiktokTrend from '../data/tiktok-trend.json';

const columns = [
  { key: 'date', label: '日期' },
  { key: 'author', label: '作者' },
  { key: 'title', label: '标题' },
  { key: 'views', label: '播放' },
  { key: 'likes', label: '点赞' },
  { key: 'comments', label: '评论' },
  { key: 'ip', label: 'IP' },
];
---
<Base title="TikTok 数据 — 泡泡玛特.md" description="Pop Mart TikTok 视频和评论时序数据">
  <div class="page-header">
    <h1>TikTok 视频数据</h1>
    <p>{tiktokVideos.length} 个视频 · 按播放量排序</p>
  </div>
  <DataTable title="热门视频" columns={columns} rows={tiktokVideos} maxRows={100} />
</Base>

<style>
  .page-header {
    max-width: var(--max-width); margin: 32px auto;
    padding: 0 24px;
  }
  .page-header h1 { font-size: 32px; font-weight: 900; margin-bottom: 8px; }
  .page-header p { color: var(--color-muted); font-size: 14px; }
</style>
```

- [ ] **Step 2: Write Instagram detail page**

```astro
---
// website/src/pages/instagram.astro
import Base from '../layouts/Base.astro';
import DataTable from '../components/DataTable.astro';
import instagramPosts from '../data/instagram-posts.json';

const columns = [
  { key: 'date', label: '日期' },
  { key: 'account', label: '账号' },
  { key: 'caption', label: '内容' },
  { key: 'likes', label: '点赞' },
  { key: 'comments', label: '评论' },
  { key: 'ip', label: 'IP' },
];
---
<Base title="Instagram 数据 — 泡泡玛特.md" description="Pop Mart Instagram 帖子和评论时序数据">
  <div class="page-header">
    <h1>Instagram 帖子数据</h1>
    <p>{instagramPosts.length} 个帖子 · 按日期排序</p>
  </div>
  <DataTable title="帖子列表" columns={columns} rows={instagramPosts} maxRows={100} />
</Base>

<style>
  .page-header {
    max-width: var(--max-width); margin: 32px auto; padding: 0 24px;
  }
  .page-header h1 { font-size: 32px; font-weight: 900; margin-bottom: 8px; }
  .page-header p { color: var(--color-muted); font-size: 14px; }
</style>
```

- [ ] **Step 3: Build and verify**

Run: `cd website && npm run build`
Expected: `dist/tiktok/index.html` and `dist/instagram/index.html` exist with `<table>` data

- [ ] **Step 4: Commit**

```bash
git add website/src/pages/tiktok.astro website/src/pages/instagram.astro
git commit -m "feat: add TikTok and Instagram detail pages"
```

---

## Task 9: Methodology Page + llms.txt Endpoint

**Files:**
- Create: `website/src/pages/methodology.astro`
- Create: `website/src/pages/llms.txt.ts`

- [ ] **Step 1: Write methodology page**

```astro
---
// website/src/pages/methodology.astro
import Base from '../layouts/Base.astro';
import overview from '../data/overview.json';
---
<Base title="方法论 — 泡泡玛特.md" description="数据采集方法论和计算公式的完整说明">
  <div class="page-header">
    <h1>方法论</h1>
    <p>数据采集方法 · IP 分类规则 · 数据局限性</p>
  </div>
  <article class="content section">
    <h2>数据采集</h2>
    <dl>
      <dt>TikTok</dt>
      <dd>通过 7 个话题标签（#labubu, #popmart, #dimoo, #skullpanda 等）和 @popmartglobal 官方账号采集视频元数据和评论。采集频率：每日增量。</dd>
      <dt>Instagram</dt>
      <dd>通过 @popmart 官方账号、@lalalalisa_m、@davidbeckham 等关联账号采集帖子和评论。采集频率：每日增量。</dd>
    </dl>

    <h2>IP 分类规则</h2>
    <p>内容通过来源标签和文本关键词匹配分类到 IP：</p>
    <ul>
      <li><strong>Labubu</strong> — 关键词: labubu, 拉布布</li>
      <li><strong>Molly</strong> — 关键词: molly</li>
      <li><strong>Dimoo</strong> — 关键词: dimoo</li>
      <li><strong>Skullpanda</strong> — 关键词: skullpanda, skull panda</li>
      <li><strong>Zsiga</strong> — 关键词: zsiga, 嘎子</li>
      <li><strong>Pop Mart</strong> — 未匹配到特定 IP 的内容</li>
    </ul>

    <h2>数据局限性</h2>
    <ul>
      <li>TikTok 数据受平台 API 限制，可能遗漏部分视频</li>
      <li>Instagram 评论采集依赖页面加载，深层评论可能不完整</li>
      <li>IP 分类基于关键词匹配，跨 IP 内容可能分类不准确</li>
      <li>数据每日更新一次，不反映实时变化</li>
    </ul>

    <h2>开源</h2>
    <p>本站代码和采集脚本完全开源，欢迎复现和改进。</p>
  </article>
</Base>

<style>
  .page-header {
    max-width: var(--max-width); margin: 32px auto; padding: 0 24px;
  }
  .page-header h1 { font-size: 32px; font-weight: 900; margin-bottom: 8px; }
  .page-header p { color: var(--color-muted); font-size: 14px; }
  .content { line-height: 1.8; font-size: 15px; }
  .content h2 { font-size: 20px; margin: 32px 0 12px; }
  .content dt { font-weight: 700; margin-top: 12px; }
  .content dd { margin-left: 0; margin-bottom: 8px; color: #555; }
  .content ul { padding-left: 20px; }
  .content li { margin-bottom: 6px; }
</style>
```

- [ ] **Step 2: Write llms.txt endpoint**

```typescript
// website/src/pages/llms.txt.ts
import type { APIRoute } from 'astro';
import overview from '../data/overview.json';

export const GET: APIRoute = () => {
  const body = `# 泡泡玛特.md

> Pop Mart 海外社媒另类数据追踪，日更静态网站

## 数据范围
- TikTok: ${overview.tiktok_videos}+ 视频, ${overview.tiktok_comments}+ 评论
- Instagram: ${overview.instagram_posts} 帖子, ${overview.instagram_comments} 评论

## 数据接口 (JSON)
- /data/overview.json — 汇总统计
- /data/tiktok-videos.json — 视频元数据（含 IP 分类）
- /data/tiktok-trend.json — 每周评论趋势（按 IP 分组）
- /data/instagram-posts.json — 帖子列表（含 IP 分类）
- /data/instagram-trend.json — 每周评论趋势
- /data/ip-share.json — IP 声量占比

## 页面
- / — 首页概览
- /tiktok — TikTok 详细数据表格
- /instagram — Instagram 详细数据表格
- /methodology — 采集方法论和 IP 分类规则

## 更新频率
每日 UTC 08:00 自动更新
`;

  return new Response(body, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
```

- [ ] **Step 3: Copy JSON data files to public for direct download**

Add a post-build step or create a redirect. The simplest approach: also output JSON to `public/data/`.

Add to `export_json.py` CLI: export to both `website/src/data/` (for Astro build-time) and `website/public/data/` (for direct download).

```python
# Update the __main__ block in export_json.py:
if __name__ == '__main__':
    import sys
    src_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE_DIR, '..', 'website', 'src', 'data')
    pub_dir = os.path.join(os.path.dirname(src_dir), '..', 'public', 'data')
    write_all(src_dir)
    write_all(pub_dir)
    print("✅ Exported to both src/data and public/data")
```

- [ ] **Step 4: Build and verify**

Run: `cd website && npm run build`
Expected: `dist/llms.txt` exists as plain text, `dist/methodology/index.html` has semantic HTML

- [ ] **Step 5: Commit**

```bash
git add website/src/pages/methodology.astro website/src/pages/llms.txt.ts
git commit -m "feat: add methodology page and llms.txt endpoint"
```

---

## Task 10: GitHub Actions Deploy Workflow

**Files:**
- Create: `.github/workflows/deploy-website.yml`

- [ ] **Step 1: Write workflow file**

```yaml
# .github/workflows/deploy-website.yml
name: Deploy Website

on:
  push:
    branches: [main]
    paths: ['website/**']
  workflow_dispatch:

jobs:
  build-deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      deployments: write
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: website/package-lock.json

      - name: Install and build
        run: cd website && npm ci && npm run build

      - name: Deploy to Cloudflare Pages
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          command: pages deploy website/dist --project-name=popmart-md
```

- [ ] **Step 2: Commit**

```bash
mkdir -p .github/workflows
git add .github/workflows/deploy-website.yml
git commit -m "ci: add GitHub Actions workflow for Cloudflare Pages deploy"
```

---

## Task 11: Daily Update Batch Script

**Files:**
- Create: `scripts/daily_update.bat`

- [ ] **Step 1: Write batch script for Windows Task Scheduler**

```batch
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
```

- [ ] **Step 2: Commit**

```bash
mkdir -p scripts
git add scripts/daily_update.bat
git commit -m "feat: add daily update batch script for Task Scheduler"
```

---

## Task 12: Final Integration Test

- [ ] **Step 1: Run full pipeline end-to-end**

```bash
cd phase2_overseas && python -u export_json.py ../website/src/data
cd ../website && npm run build
```

Expected: Build succeeds, `dist/` contains:
- `index.html` — homepage with all sections
- `tiktok/index.html` — TikTok data table
- `instagram/index.html` — Instagram data table
- `methodology/index.html` — methodology page
- `llms.txt` — LLM discovery file
- `data/*.json` — raw JSON data files
- `characters/*.png` — character images

- [ ] **Step 2: Verify LLM-friendliness**

Run: `grep -c '<table>' website/dist/tiktok/index.html`
Expected: 1 (semantic table present)

Run: `grep -c '<script' website/dist/index.html`
Expected: 1 (only the ECharts loader, no framework hydration)

- [ ] **Step 3: Preview locally**

Run: `cd website && npm run preview`
Open: http://localhost:4321 — verify all pages render correctly

- [ ] **Step 4: Run Python tests**

Run: `cd phase2_overseas && python -m pytest tests/test_export_json.py -v`
Expected: All tests PASS

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: complete 泡泡玛特.md website (Astro + ECharts)"
```
