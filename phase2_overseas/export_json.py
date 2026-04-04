"""
export_json.py — Export overseas_data.db to JSON files for the Astro website.

Comment-based engagement metrics use actual comment timestamps from
tiktok_comments.comment_date and instagram_comments.comment_date, giving accurate
monthly engagement signals (a comment in 2024-06 counts in 2024-06 regardless of when
the video was published). Views/likes metrics remain from metadata since those have
no per-comment timestamps.

Functions that use comment timestamps:
  export_tiktok_trend, export_instagram_trend, export_brand_trend,
  export_ip_share_trend, export_cross_platform_index, export_official_engagement,
  export_ip_share, export_brand_vs_ugc

Functions unchanged (no comment aggregation):
  export_ugc_amplification, export_data_coverage, export_overview,
  export_tiktok_videos, export_instagram_posts

Usage: python export_json.py [--output-dir website/src/data]
"""

import sqlite3
import json
import os
import re
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'overseas_data.db')

IP_PATTERNS = [
    ('Labubu', re.compile(r'labubu|拉布布', re.IGNORECASE)),
    ('Molly', re.compile(r'molly', re.IGNORECASE)),
    ('Dimoo', re.compile(r'dimoo', re.IGNORECASE)),
    ('Skullpanda', re.compile(r'skullpanda|skull\s*panda', re.IGNORECASE)),
    ('Zsiga', re.compile(r'zsiga|嘎子', re.IGNORECASE)),
    ('Twinkle', re.compile(r'twinkle|星星人', re.IGNORECASE)),
    ('Crybaby', re.compile(r'crybaby|cry\s*baby|哭娃', re.IGNORECASE)),
]


def classify_ip(source, text):
    """Classify content to an IP based on source tag and text content."""
    combined = f'{source} {text}'.lower()
    for ip_name, pattern in IP_PATTERNS:
        if pattern.search(combined):
            return ip_name
    return 'Pop Mart'


def _unix_to_date(ts):
    """Convert Unix timestamp string to YYYY-MM-DD."""
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime('%Y-%m-%d')
    except (ValueError, TypeError, OSError):
        return None


def _week_key(date_str):
    """Convert YYYY-MM-DD to ISO week key like '2026-W09'."""
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        return f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"
    except (ValueError, TypeError):
        return None


def _month_key(date_str):
    """Convert YYYY-MM-DD to YYYY-MM month key."""
    try:
        return date_str[:7]
    except (TypeError, IndexError):
        return None


def _data_confidence(n):
    """Return confidence level based on sample count n."""
    if n >= 10:
        return "high"
    if n >= 5:
        return "medium"
    return "low"


def export_overview(conn):
    """Export summary statistics with data freshness and coverage."""
    counts = {}
    for table in ['tiktok_videos', 'tiktok_comments', 'instagram_posts', 'instagram_comments']:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        counts[table] = row[0]

    # Data freshness: MAX(scraped_at) per platform
    tk_fresh = conn.execute("SELECT MAX(scraped_at) FROM tiktok_videos").fetchone()[0]
    ig_fresh = conn.execute("SELECT MAX(scraped_at) FROM instagram_posts").fetchone()[0]
    counts['data_freshness'] = {
        'tiktok': tk_fresh,
        'instagram': ig_fresh,
    }

    # Coverage summary
    counts['coverage'] = {
        'tiktok_videos': counts['tiktok_videos'],
        'tiktok_comments': counts['tiktok_comments'],
        'instagram_posts': counts['instagram_posts'],
        'instagram_comments': counts['instagram_comments'],
    }

    counts['updated_at'] = datetime.now(tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    return counts


def export_ip_share(conn):
    """Export IP share of voice using actual comment row counts, excluding Pop Mart."""
    # Build IP classification for each tiktok video
    tk_videos = conn.execute("SELECT video_id, source, title FROM tiktok_videos").fetchall()
    tk_ip_map = {}  # video_id -> ip
    for video_id, source, title in tk_videos:
        tk_ip_map[video_id] = classify_ip(source or '', title or '')

    # Count tiktok_comments rows per video_id
    tk_comment_rows = conn.execute("SELECT video_id FROM tiktok_comments").fetchall()
    tk_comment_count = {}
    for (video_id,) in tk_comment_rows:
        tk_comment_count[video_id] = tk_comment_count.get(video_id, 0) + 1

    # Accumulate by IP
    ip_stats = {}
    for video_id, source, title in tk_videos:
        ip = tk_ip_map[video_id]
        if ip not in ip_stats:
            ip_stats[ip] = {'ip': ip, 'tiktok_posts': 0, 'tiktok_comments': 0,
                            'instagram_posts': 0, 'instagram_comments': 0}
        ip_stats[ip]['tiktok_posts'] += 1
        ip_stats[ip]['tiktok_comments'] += tk_comment_count.get(video_id, 0)

    # Build IP classification for each instagram post
    ig_posts = conn.execute("SELECT shortcode, account, caption FROM instagram_posts").fetchall()
    ig_ip_map = {}
    for shortcode, account, caption in ig_posts:
        ig_ip_map[shortcode] = classify_ip(account or '', caption or '')

    # Count instagram_comments rows per shortcode
    ig_comment_rows = conn.execute("SELECT shortcode FROM instagram_comments").fetchall()
    ig_comment_count = {}
    for (shortcode,) in ig_comment_rows:
        ig_comment_count[shortcode] = ig_comment_count.get(shortcode, 0) + 1

    for shortcode, account, caption in ig_posts:
        ip = ig_ip_map[shortcode]
        if ip not in ip_stats:
            ip_stats[ip] = {'ip': ip, 'tiktok_posts': 0, 'tiktok_comments': 0,
                            'instagram_posts': 0, 'instagram_comments': 0}
        ip_stats[ip]['instagram_posts'] += 1
        ip_stats[ip]['instagram_comments'] += ig_comment_count.get(shortcode, 0)

    # Exclude Pop Mart brand
    ip_stats.pop('Pop Mart', None)

    # Calculate total engagement (comment rows) and share percentages
    for r in ip_stats.values():
        r['total_engagement'] = r['tiktok_comments'] + r['instagram_comments']

    result = sorted(ip_stats.values(), key=lambda x: x['total_engagement'], reverse=True)
    total = sum(r['total_engagement'] for r in result)
    for r in result:
        r['share_pct'] = round(r['total_engagement'] / total * 100, 1) if total else 0
    return result


def export_tiktok_trend(conn):
    """Export monthly avg_comments_per_post by IP from actual comment timestamps.

    Groups by comment_date month (not video publish month). A comment on a Labubu
    video in 2024-06 counts in 2024-06 even if the video was published in 2024-03.
    avg_comments_per_post = comment_count / distinct_video_count for that (month, IP).
    n = distinct video count receiving comments in that month for that IP.
    """
    rows = conn.execute("""
        SELECT tc.comment_date, tv.source, tv.title, tc.video_id
        FROM tiktok_comments tc
        JOIN tiktok_videos tv ON tc.video_id = tv.video_id
        WHERE tc.comment_date IS NOT NULL
    """).fetchall()

    # Group by (month, IP) -> count comments and distinct videos
    groups = {}  # (month, ip) -> {'comments': int, 'videos': set}
    for comment_date, source, title, video_id in rows:
        month = _month_key(comment_date)
        if not month:
            continue
        ip = classify_ip(source or '', title or '')
        key = (month, ip)
        if key not in groups:
            groups[key] = {'comments': 0, 'videos': set()}
        groups[key]['comments'] += 1
        groups[key]['videos'].add(video_id)

    result = []
    for (month, ip), g in sorted(groups.items()):
        n = len(g['videos'])
        avg = round(g['comments'] / n, 1) if n else 0.0
        result.append({
            'month': month,
            'ip': ip,
            'avg_comments_per_post': avg,
            'n': n,
            'data_confidence': _data_confidence(n),
        })
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
    """Export monthly avg_comments_per_post by IP from actual comment timestamps.

    Groups by comment_date month (not post publish month). avg_comments_per_post =
    comment_count / distinct_post_count for that (month, IP).
    n = distinct post count receiving comments in that month for that IP.
    """
    rows = conn.execute("""
        SELECT ic.comment_date, ip.account, ip.caption, ic.shortcode
        FROM instagram_comments ic
        JOIN instagram_posts ip ON ic.shortcode = ip.shortcode
        WHERE ic.comment_date IS NOT NULL
    """).fetchall()

    groups = {}  # (month, ip) -> {'comments': int, 'posts': set}
    for comment_date, account, caption, shortcode in rows:
        month = _month_key(comment_date)
        if not month:
            continue
        ip = classify_ip(account or '', caption or '')
        key = (month, ip)
        if key not in groups:
            groups[key] = {'comments': 0, 'posts': set()}
        groups[key]['comments'] += 1
        groups[key]['posts'].add(shortcode)

    result = []
    for (month, ip), g in sorted(groups.items()):
        n = len(g['posts'])
        avg = round(g['comments'] / n, 1) if n else 0.0
        result.append({
            'month': month,
            'ip': ip,
            'avg_comments_per_post': avg,
            'n': n,
            'data_confidence': _data_confidence(n),
        })
    return result


def export_brand_trend(conn):
    """Monthly TikTok avg_comments_per_post from actual comment timestamps.

    Groups by comment_date month. avg_comments_per_post = total_comments / distinct_videos.
    n = total comment row count. videos = distinct video count.
    """
    rows = conn.execute("""
        SELECT tc.comment_date, tc.video_id
        FROM tiktok_comments tc
        JOIN tiktok_videos tv ON tc.video_id = tv.video_id
        WHERE tc.comment_date IS NOT NULL
    """).fetchall()

    monthly = {}  # month -> {'comments': int, 'videos': set}
    for comment_date, video_id in rows:
        month = _month_key(comment_date)
        if not month:
            continue
        if month not in monthly:
            monthly[month] = {'comments': 0, 'videos': set()}
        monthly[month]['comments'] += 1
        monthly[month]['videos'].add(video_id)

    result = []
    for month in sorted(monthly.keys()):
        g = monthly[month]
        n = g['comments']
        vids = len(g['videos'])
        avg = round(n / vids, 1) if vids else 0.0
        result.append({
            'month': month,
            'avg_comments_per_post': avg,
            'n': n,
            'data_confidence': _data_confidence(n),
            'videos': vids,
        })
    return result


def export_ip_share_trend(conn):
    """Monthly IP share from actual comment row counts (both platforms), excluding Pop Mart.

    engagement = COUNT of comment rows in that month for that IP (across both platforms).
    """
    monthly_ip_engagement = {}

    # TikTok: count comment rows by (comment_date month, IP)
    tk_rows = conn.execute("""
        SELECT tc.comment_date, tv.source, tv.title
        FROM tiktok_comments tc
        JOIN tiktok_videos tv ON tc.video_id = tv.video_id
        WHERE tc.comment_date IS NOT NULL
    """).fetchall()
    for comment_date, source, title in tk_rows:
        month = _month_key(comment_date)
        ip = classify_ip(source or '', title or '')
        if month:
            key = (month, ip)
            monthly_ip_engagement[key] = monthly_ip_engagement.get(key, 0) + 1

    # Instagram: count comment rows by (comment_date month, IP)
    ig_rows = conn.execute("""
        SELECT ic.comment_date, ip.account, ip.caption
        FROM instagram_comments ic
        JOIN instagram_posts ip ON ic.shortcode = ip.shortcode
        WHERE ic.comment_date IS NOT NULL
    """).fetchall()
    for comment_date, account, caption in ig_rows:
        month = _month_key(comment_date)
        ip = classify_ip(account or '', caption or '')
        if month:
            key = (month, ip)
            monthly_ip_engagement[key] = monthly_ip_engagement.get(key, 0) + 1

    # Exclude Pop Mart
    ip_engagement_no_brand = {k: v for k, v in monthly_ip_engagement.items() if k[1] != 'Pop Mart'}

    # Calculate per-month totals for share_pct
    month_totals = {}
    for (month, ip), engagement in ip_engagement_no_brand.items():
        month_totals[month] = month_totals.get(month, 0) + engagement

    result = []
    for (month, ip), engagement in sorted(ip_engagement_no_brand.items()):
        total = month_totals.get(month, 1)
        result.append({
            'month': month,
            'ip': ip,
            'share_pct': round(engagement / total * 100, 1),
            'engagement': engagement,
        })
    return result


def export_cross_platform_index(conn):
    """Monthly density index (mean=100) per platform using actual comment row counts.

    density = COUNT(comment rows in month) / COUNT(distinct posts with comments in month).
    """
    # TikTok: count comment rows and distinct posts per comment_date month
    tiktok_rows = conn.execute("""
        SELECT tc.comment_date, tc.video_id
        FROM tiktok_comments tc
        WHERE tc.comment_date IS NOT NULL
    """).fetchall()
    tiktok_monthly_comments = {}   # month -> total comment rows
    tiktok_monthly_posts = {}      # month -> set of post ids with comments
    for comment_date, video_id in tiktok_rows:
        month = _month_key(comment_date)
        if not month:
            continue
        tiktok_monthly_comments[month] = tiktok_monthly_comments.get(month, 0) + 1
        if month not in tiktok_monthly_posts:
            tiktok_monthly_posts[month] = set()
        tiktok_monthly_posts[month].add(video_id)

    # Instagram: count comment rows and distinct posts per comment_date month
    ig_rows = conn.execute("""
        SELECT ic.comment_date, ic.shortcode
        FROM instagram_comments ic
        WHERE ic.comment_date IS NOT NULL
    """).fetchall()
    ig_monthly_comments = {}
    ig_monthly_posts = {}
    for comment_date, shortcode in ig_rows:
        month = _month_key(comment_date)
        if not month:
            continue
        ig_monthly_comments[month] = ig_monthly_comments.get(month, 0) + 1
        if month not in ig_monthly_posts:
            ig_monthly_posts[month] = set()
        ig_monthly_posts[month].add(shortcode)

    def _compute_index(monthly_comments, monthly_posts):
        all_months = sorted(set(list(monthly_comments.keys()) + list(monthly_posts.keys())))
        densities = {}
        for month in all_months:
            comment_count = monthly_comments.get(month, 0)
            post_count = len(monthly_posts.get(month, set()))
            densities[month] = comment_count / post_count if post_count else 0.0

        # 3-month rolling average
        ma3 = {}
        for i, month in enumerate(all_months):
            window = [densities[all_months[j]] for j in range(max(0, i - 2), i + 1)]
            ma3[month] = sum(window) / len(window)

        # Normalize: index = ma3 / mean(density) * 100
        avg_density = sum(densities.values()) / len(densities) if densities else 1.0
        result = []
        for month in all_months:
            result.append({
                'month': month,
                'density': round(densities[month], 2),
                'index': round(ma3[month] / avg_density * 100, 1) if avg_density else 0.0,
            })
        return result

    tiktok_data = _compute_index(tiktok_monthly_comments, tiktok_monthly_posts)
    ig_data = _compute_index(ig_monthly_comments, ig_monthly_posts)

    result = []
    for row in tiktok_data:
        result.append({'month': row['month'], 'platform': 'TikTok',
                       'index': row['index'], 'density': row['density']})
    for row in ig_data:
        result.append({'month': row['month'], 'platform': 'Instagram',
                       'index': row['index'], 'density': row['density']})
    result.sort(key=lambda x: (x['month'], x['platform']))
    return result


def export_brand_vs_ugc(conn):
    """Brand (popmartglobal) vs UGC comparison.

    avg_comments per video uses COUNT of tiktok_comments rows for that video_id.
    avg_views/avg_likes/avg_er_pct remain from metadata.
    """
    rows = conn.execute("""SELECT video_id, author, views, likes, comments_count FROM tiktok_videos""").fetchall()

    # Count actual comment rows per video_id
    comment_rows = conn.execute("SELECT video_id FROM tiktok_comments").fetchall()
    comment_count_map = {}
    for (vid_id,) in comment_rows:
        comment_count_map[vid_id] = comment_count_map.get(vid_id, 0) + 1

    brand_rows = [r for r in rows if r[1] == 'popmartglobal']
    ugc_rows = [r for r in rows if r[1] != 'popmartglobal']

    def _calc_stats(video_rows):
        if not video_rows:
            return {'avg_views': 0, 'avg_likes': 0, 'avg_er_pct': 0.0, 'avg_comments': 0, 'count': 0}
        total_views = sum(r[2] or 0 for r in video_rows)
        total_likes = sum(r[3] or 0 for r in video_rows)
        # avg_comments from actual comment rows, not metadata
        total_comments = sum(comment_count_map.get(r[0], 0) for r in video_rows)
        count = len(video_rows)
        avg_views = total_views / count
        avg_likes = total_likes / count
        avg_comments = total_comments / count
        avg_er_pct = round(
            sum(((r[3] or 0) + (r[4] or 0)) / max(r[2] or 1, 1) * 100 for r in video_rows) / count, 2
        )
        return {
            'avg_views': round(avg_views, 1),
            'avg_likes': round(avg_likes, 1),
            'avg_er_pct': avg_er_pct,
            'avg_comments': round(avg_comments, 1),
            'count': count,
        }

    return {
        'brand': _calc_stats(brand_rows),
        'ugc': _calc_stats(ugc_rows),
    }


def export_official_engagement(conn):
    """Official account engagement.

    TikTok: author='popmartglobal', Instagram: account='popmart'.
    avg_comments: COUNT of comment rows grouped by comment_date month, divided by
      number of posts that received comments in that month.
    avg_views / avg_likes: from metadata grouped by video publish month (no change).
    posts: number of official videos published in that month (metadata-based).
    """
    result = {}

    # TikTok metadata: views/likes grouped by video publish month
    tk_meta = conn.execute("""
        SELECT create_time, views, likes, video_id
        FROM tiktok_videos
        WHERE author = 'popmartglobal'
    """).fetchall()

    tk_meta_monthly = {}  # month -> {'views': [], 'likes': [], 'video_ids': set}
    for ts, views, likes, video_id in tk_meta:
        date = _unix_to_date(ts)
        month = _month_key(date)
        if month:
            if month not in tk_meta_monthly:
                tk_meta_monthly[month] = {'views': [], 'likes': [], 'video_ids': set()}
            tk_meta_monthly[month]['views'].append(views or 0)
            tk_meta_monthly[month]['likes'].append(likes or 0)
            tk_meta_monthly[month]['video_ids'].add(video_id)

    # TikTok comment rows: count by comment_date month for popmartglobal videos
    official_video_ids = set(r[3] for r in tk_meta)
    tk_comment_rows = conn.execute("""
        SELECT tc.comment_date, tc.video_id
        FROM tiktok_comments tc
        WHERE tc.comment_date IS NOT NULL
    """).fetchall()
    tk_comment_monthly = {}  # month -> {'comments': int, 'posts': set}
    for comment_date, video_id in tk_comment_rows:
        if video_id not in official_video_ids:
            continue
        month = _month_key(comment_date)
        if not month:
            continue
        if month not in tk_comment_monthly:
            tk_comment_monthly[month] = {'comments': 0, 'posts': set()}
        tk_comment_monthly[month]['comments'] += 1
        tk_comment_monthly[month]['posts'].add(video_id)

    result['tiktok'] = []
    all_tk_months = sorted(set(list(tk_meta_monthly.keys()) + list(tk_comment_monthly.keys())))
    for m in all_tk_months:
        meta = tk_meta_monthly.get(m, {'views': [], 'likes': [], 'video_ids': set()})
        comment_data = tk_comment_monthly.get(m, {'comments': 0, 'posts': set()})
        n_posts = len(meta['video_ids']) if meta['video_ids'] else len(comment_data['posts'])
        n_comment_posts = len(comment_data['posts'])
        avg_comments = round(comment_data['comments'] / n_comment_posts, 1) if n_comment_posts else 0.0
        avg_views = round(sum(meta['views']) / len(meta['views']), 1) if meta['views'] else 0.0
        avg_likes = round(sum(meta['likes']) / len(meta['likes']), 1) if meta['likes'] else 0.0
        result['tiktok'].append({
            'month': m,
            'posts': n_posts,
            'avg_comments': avg_comments,
            'avg_views': avg_views,
            'avg_likes': avg_likes,
        })

    # Instagram metadata: likes grouped by post publish month
    ig_meta = conn.execute("""
        SELECT post_date, likes, shortcode
        FROM instagram_posts
        WHERE account = 'popmart'
    """).fetchall()

    ig_meta_monthly = {}  # month -> {'likes': [], 'shortcodes': set}
    for post_date, likes, shortcode in ig_meta:
        month = _month_key(post_date)
        if month:
            if month not in ig_meta_monthly:
                ig_meta_monthly[month] = {'likes': [], 'shortcodes': set()}
            ig_meta_monthly[month]['likes'].append(likes or 0)
            ig_meta_monthly[month]['shortcodes'].add(shortcode)

    # Instagram comment rows: count by comment_date month for popmart posts
    official_ig_codes = set(r[2] for r in ig_meta)
    ig_comment_rows = conn.execute("""
        SELECT ic.comment_date, ic.shortcode
        FROM instagram_comments ic
        WHERE ic.comment_date IS NOT NULL
    """).fetchall()
    ig_comment_monthly = {}  # month -> {'comments': int, 'posts': set}
    for comment_date, shortcode in ig_comment_rows:
        if shortcode not in official_ig_codes:
            continue
        month = _month_key(comment_date)
        if not month:
            continue
        if month not in ig_comment_monthly:
            ig_comment_monthly[month] = {'comments': 0, 'posts': set()}
        ig_comment_monthly[month]['comments'] += 1
        ig_comment_monthly[month]['posts'].add(shortcode)

    result['instagram'] = []
    all_ig_months = sorted(set(list(ig_meta_monthly.keys()) + list(ig_comment_monthly.keys())))
    for m in all_ig_months:
        meta = ig_meta_monthly.get(m, {'likes': [], 'shortcodes': set()})
        comment_data = ig_comment_monthly.get(m, {'comments': 0, 'posts': set()})
        n_posts = len(meta['shortcodes']) if meta['shortcodes'] else len(comment_data['posts'])
        n_comment_posts = len(comment_data['posts'])
        avg_comments = round(comment_data['comments'] / n_comment_posts, 1) if n_comment_posts else 0.0
        avg_likes = round(sum(meta['likes']) / len(meta['likes']), 1) if meta['likes'] else 0.0
        result['instagram'].append({
            'month': m,
            'posts': n_posts,
            'avg_comments': avg_comments,
            'avg_likes': avg_likes,
        })

    return result


def export_data_coverage(conn):
    """Platform data coverage stats."""
    result = {}

    # TikTok coverage
    tk_total = conn.execute("SELECT COUNT(*) FROM tiktok_videos").fetchone()[0]
    tk_scraped = conn.execute(
        "SELECT COUNT(*) FROM tiktok_videos WHERE last_comment_scraped_at IS NOT NULL"
    ).fetchone()[0]

    tk_rows = conn.execute("SELECT create_time FROM tiktok_videos").fetchall()
    tk_dates = [_unix_to_date(ts) for (ts,) in tk_rows]
    tk_dates = [d for d in tk_dates if d]

    tk_months = {}
    for d in tk_dates:
        m = _month_key(d)
        if m:
            tk_months[m] = tk_months.get(m, 0) + 1

    result['tiktok'] = {
        'total_posts': tk_total,
        'date_range': {
            'min': min(tk_dates) if tk_dates else None,
            'max': max(tk_dates) if tk_dates else None,
        },
        'monthly_counts': [{'month': m, 'n': n} for m, n in sorted(tk_months.items())],
        'coverage_pct': round(tk_scraped / tk_total * 100, 1) if tk_total else 0.0,
    }

    # Instagram coverage
    ig_total = conn.execute("SELECT COUNT(*) FROM instagram_posts").fetchone()[0]
    ig_scraped = conn.execute(
        "SELECT COUNT(*) FROM instagram_posts WHERE last_comment_scraped_at IS NOT NULL"
    ).fetchone()[0]

    ig_rows = conn.execute("SELECT post_date FROM instagram_posts").fetchall()
    ig_dates = [d for (d,) in ig_rows if d]

    ig_months = {}
    for d in ig_dates:
        m = _month_key(d)
        if m:
            ig_months[m] = ig_months.get(m, 0) + 1

    result['instagram'] = {
        'total_posts': ig_total,
        'date_range': {
            'min': min(ig_dates) if ig_dates else None,
            'max': max(ig_dates) if ig_dates else None,
        },
        'monthly_counts': [{'month': m, 'n': n} for m, n in sorted(ig_months.items())],
        'coverage_pct': round(ig_scraped / ig_total * 100, 1) if ig_total else 0.0,
    }

    return result


def export_ugc_amplification(conn):
    """Monthly UGC/official avg_views ratio trend from TikTok."""
    rows = conn.execute(
        "SELECT create_time, author, views FROM tiktok_videos"
    ).fetchall()

    official_monthly = {}
    ugc_monthly = {}
    for ts, author, views in rows:
        date = _unix_to_date(ts)
        month = _month_key(date)
        if not month:
            continue
        if author == 'popmartglobal':
            if month not in official_monthly:
                official_monthly[month] = []
            official_monthly[month].append(views or 0)
        else:
            if month not in ugc_monthly:
                ugc_monthly[month] = []
            ugc_monthly[month].append(views or 0)

    # Only months with BOTH official and UGC data
    common_months = sorted(set(official_monthly.keys()) & set(ugc_monthly.keys()))

    result = []
    for month in common_months:
        off_views = official_monthly[month]
        ugc_views = ugc_monthly[month]
        off_avg = sum(off_views) / len(off_views)
        ugc_avg = sum(ugc_views) / len(ugc_views)
        ratio = round(ugc_avg / off_avg, 2) if off_avg else None
        result.append({
            'month': month,
            'ugc_avg_views': round(ugc_avg, 1),
            'official_avg_views': round(off_avg, 1),
            'amplification_ratio': ratio,
            'ugc_n': len(ugc_views),
            'official_n': len(off_views),
        })
    return result


def write_all(output_dir):
    """Export all JSON files to output_dir."""
    conn = sqlite3.connect(DB_PATH)
    os.makedirs(output_dir, exist_ok=True)

    exports = {
        'brand-trend.json': export_brand_trend(conn),
        'brand-vs-ugc.json': export_brand_vs_ugc(conn),
        'cross-platform-index.json': export_cross_platform_index(conn),
        'data-coverage.json': export_data_coverage(conn),
        'instagram-posts.json': export_instagram_posts(conn),
        'instagram-trend.json': export_instagram_trend(conn),
        'ip-share-trend.json': export_ip_share_trend(conn),
        'ip-share.json': export_ip_share(conn),
        'official-engagement.json': export_official_engagement(conn),
        'overview.json': export_overview(conn),
        'tiktok-trend.json': export_tiktok_trend(conn),
        'tiktok-videos.json': export_tiktok_videos(conn),
        'ugc-amplification.json': export_ugc_amplification(conn),
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
    src_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE_DIR, '..', 'website', 'src', 'data')
    pub_dir = os.path.join(os.path.dirname(src_dir), '..', 'public', 'data')
    write_all(src_dir)
    write_all(pub_dir)
    print("✅ Exported to both src/data and public/data")
