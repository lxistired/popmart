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
    src_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE_DIR, '..', 'website', 'src', 'data')
    pub_dir = os.path.join(os.path.dirname(src_dir), '..', 'public', 'data')
    write_all(src_dir)
    write_all(pub_dir)
    print("✅ Exported to both src/data and public/data")
