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


def _month_key(date_str):
    """Convert YYYY-MM-DD to YYYY-MM month key."""
    try:
        return date_str[:7]
    except (TypeError, IndexError):
        return None


def export_brand_trend(conn):
    """Monthly TikTok comment volume + video count + density."""
    # Monthly video count from create_time (Unix timestamp)
    video_rows = conn.execute("SELECT create_time FROM tiktok_videos").fetchall()
    monthly_videos = {}
    for (ts,) in video_rows:
        date = _unix_to_date(ts)
        month = _month_key(date)
        if month:
            monthly_videos[month] = monthly_videos.get(month, 0) + 1

    # Monthly comment count from comment_date
    comment_rows = conn.execute("SELECT comment_date FROM tiktok_comments").fetchall()
    monthly_comments = {}
    for (date,) in comment_rows:
        month = _month_key(date)
        if month:
            monthly_comments[month] = monthly_comments.get(month, 0) + 1

    # Combine all months
    all_months = sorted(set(list(monthly_videos.keys()) + list(monthly_comments.keys())))
    result = []
    for month in all_months:
        videos = monthly_videos.get(month, 0)
        comments = monthly_comments.get(month, 0)
        result.append({
            'month': month,
            'comments': comments,
            'videos': videos,
            'density': round(comments / max(videos, 1), 1),
        })
    return result


def export_ip_share_trend(conn):
    """Monthly IP comment share percentages (both platforms combined)."""
    # Build video_id → IP mapping from tiktok_videos
    video_rows = conn.execute("SELECT video_id, source, title FROM tiktok_videos").fetchall()
    video_ip = {vid: classify_ip(src or '', title or '') for vid, src, title in video_rows}

    # Build shortcode → IP mapping from instagram_posts
    post_rows = conn.execute("SELECT shortcode, account, caption FROM instagram_posts").fetchall()
    post_ip = {sc: classify_ip(acc or '', cap or '') for sc, acc, cap in post_rows}

    # Aggregate all comments by month and IP
    monthly_ip_counts = {}

    tiktok_comments = conn.execute("SELECT video_id, comment_date FROM tiktok_comments").fetchall()
    for vid, date in tiktok_comments:
        month = _month_key(date)
        ip = video_ip.get(vid, 'Pop Mart')
        if month:
            key = (month, ip)
            monthly_ip_counts[key] = monthly_ip_counts.get(key, 0) + 1

    ig_comments = conn.execute("SELECT shortcode, comment_date FROM instagram_comments").fetchall()
    for sc, date in ig_comments:
        month = _month_key(date)
        ip = post_ip.get(sc, 'Pop Mart')
        if month:
            key = (month, ip)
            monthly_ip_counts[key] = monthly_ip_counts.get(key, 0) + 1

    # Calculate per-month share_pct
    month_totals = {}
    for (month, ip), count in monthly_ip_counts.items():
        month_totals[month] = month_totals.get(month, 0) + count

    result = []
    for (month, ip), count in sorted(monthly_ip_counts.items()):
        total = month_totals.get(month, 1)
        result.append({
            'month': month,
            'ip': ip,
            'share_pct': round(count / total * 100, 1),
            'count': count,
        })
    return result


def export_cross_platform_index(conn):
    """Monthly density index (mean=100) per platform."""
    # TikTok: monthly video count and comment count
    tiktok_video_rows = conn.execute("SELECT create_time FROM tiktok_videos").fetchall()
    tiktok_monthly_content = {}
    for (ts,) in tiktok_video_rows:
        date = _unix_to_date(ts)
        month = _month_key(date)
        if month:
            tiktok_monthly_content[month] = tiktok_monthly_content.get(month, 0) + 1

    tiktok_comment_rows = conn.execute("SELECT comment_date FROM tiktok_comments").fetchall()
    tiktok_monthly_comments = {}
    for (date,) in tiktok_comment_rows:
        month = _month_key(date)
        if month:
            tiktok_monthly_comments[month] = tiktok_monthly_comments.get(month, 0) + 1

    # Instagram: monthly post count and comment count
    ig_post_rows = conn.execute("SELECT post_date FROM instagram_posts").fetchall()
    ig_monthly_content = {}
    for (date,) in ig_post_rows:
        month = _month_key(date)
        if month:
            ig_monthly_content[month] = ig_monthly_content.get(month, 0) + 1

    ig_comment_rows = conn.execute("SELECT comment_date FROM instagram_comments").fetchall()
    ig_monthly_comments = {}
    for (date,) in ig_comment_rows:
        month = _month_key(date)
        if month:
            ig_monthly_comments[month] = ig_monthly_comments.get(month, 0) + 1

    def _compute_index(monthly_content, monthly_comments):
        all_months = sorted(set(list(monthly_content.keys()) + list(monthly_comments.keys())))
        densities = {}
        for month in all_months:
            content = monthly_content.get(month, 0)
            comments = monthly_comments.get(month, 0)
            densities[month] = comments / content if content else 0.0

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

    tiktok_data = _compute_index(tiktok_monthly_content, tiktok_monthly_comments)
    ig_data = _compute_index(ig_monthly_content, ig_monthly_comments)

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
    """Brand (popmartglobal) vs UGC comparison."""
    rows = conn.execute("""SELECT author, views, likes, comments_count FROM tiktok_videos""").fetchall()

    brand_rows = [r for r in rows if r[0] == 'popmartglobal']
    ugc_rows = [r for r in rows if r[0] != 'popmartglobal']

    def _calc_stats(video_rows):
        if not video_rows:
            return {'avg_views': 0, 'avg_likes': 0, 'avg_er_pct': 0.0, 'avg_comments': 0, 'count': 0}
        total_views = sum(r[1] or 0 for r in video_rows)
        total_likes = sum(r[2] or 0 for r in video_rows)
        total_comments = sum(r[3] or 0 for r in video_rows)
        count = len(video_rows)
        avg_views = total_views / count
        avg_likes = total_likes / count
        avg_comments = total_comments / count
        avg_er_pct = round(
            sum(((r[2] or 0) + (r[3] or 0)) / max(r[1] or 1, 1) * 100 for r in video_rows) / count, 2
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


def export_comment_quality(conn):
    """Comment quality tiers by platform."""
    result = []

    # TikTok comments
    tiktok_likes = conn.execute("SELECT likes FROM tiktok_comments").fetchall()
    tiktok_total = len(tiktok_likes)
    if tiktok_total > 0:
        high = sum(1 for (l,) in tiktok_likes if (l or 0) >= 10)
        med = sum(1 for (l,) in tiktok_likes if 3 <= (l or 0) <= 9)
        low = sum(1 for (l,) in tiktok_likes if (l or 0) < 3)
        result.append({
            'platform': 'TikTok',
            'high_pct': round(high / tiktok_total * 100, 1),
            'med_pct': round(med / tiktok_total * 100, 1),
            'low_pct': round(low / tiktok_total * 100, 1),
            'total': tiktok_total,
        })
    else:
        result.append({'platform': 'TikTok', 'high_pct': 0.0, 'med_pct': 0.0, 'low_pct': 0.0, 'total': 0})

    # Instagram comments
    ig_likes = conn.execute("SELECT likes FROM instagram_comments").fetchall()
    ig_total = len(ig_likes)
    if ig_total > 0:
        high = sum(1 for (l,) in ig_likes if (l or 0) >= 10)
        med = sum(1 for (l,) in ig_likes if 3 <= (l or 0) <= 9)
        low = sum(1 for (l,) in ig_likes if (l or 0) < 3)
        result.append({
            'platform': 'Instagram',
            'high_pct': round(high / ig_total * 100, 1),
            'med_pct': round(med / ig_total * 100, 1),
            'low_pct': round(low / ig_total * 100, 1),
            'total': ig_total,
        })
    else:
        result.append({'platform': 'Instagram', 'high_pct': 0.0, 'med_pct': 0.0, 'low_pct': 0.0, 'total': 0})

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
        'brand-trend.json': export_brand_trend(conn),
        'ip-share-trend.json': export_ip_share_trend(conn),
        'cross-platform-index.json': export_cross_platform_index(conn),
        'brand-vs-ugc.json': export_brand_vs_ugc(conn),
        'comment-quality.json': export_comment_quality(conn),
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
