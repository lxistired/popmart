"""
export_json.py — Export overseas_data.db to JSON files for the Astro website.

All volume metrics use tiktok_videos.comments_count or instagram_posts.comments_count
(metadata), NOT COUNT of tiktok_comments/instagram_comments rows. This decouples
analysis metrics from actual comment scraping coverage.

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
    """Export IP share of voice using metadata comments_count, excluding Pop Mart."""
    # Classify tiktok videos and accumulate metadata comments_count
    rows = conn.execute("SELECT video_id, source, title, comments_count FROM tiktok_videos").fetchall()
    ip_stats = {}
    for video_id, source, title, comments_count in rows:
        ip = classify_ip(source or '', title or '')
        if ip not in ip_stats:
            ip_stats[ip] = {'ip': ip, 'tiktok_posts': 0, 'tiktok_comments_meta': 0,
                            'instagram_posts': 0, 'instagram_comments_meta': 0}
        ip_stats[ip]['tiktok_posts'] += 1
        ip_stats[ip]['tiktok_comments_meta'] += (comments_count or 0)

    # Classify instagram posts and accumulate metadata comments_count
    ig_rows = conn.execute("SELECT shortcode, account, caption, comments_count FROM instagram_posts").fetchall()
    for shortcode, account, caption, comments_count in ig_rows:
        ip = classify_ip(account or '', caption or '')
        if ip not in ip_stats:
            ip_stats[ip] = {'ip': ip, 'tiktok_posts': 0, 'tiktok_comments_meta': 0,
                            'instagram_posts': 0, 'instagram_comments_meta': 0}
        ip_stats[ip]['instagram_posts'] += 1
        ip_stats[ip]['instagram_comments_meta'] += (comments_count or 0)

    # Exclude Pop Mart brand
    ip_stats.pop('Pop Mart', None)

    # Calculate total engagement and share percentages
    for r in ip_stats.values():
        r['total_engagement'] = r['tiktok_comments_meta'] + r['instagram_comments_meta']

    result = sorted(ip_stats.values(), key=lambda x: x['total_engagement'], reverse=True)
    total = sum(r['total_engagement'] for r in result)
    for r in result:
        r['share_pct'] = round(r['total_engagement'] / total * 100, 1) if total else 0
    return result


def export_tiktok_trend(conn):
    """Export monthly avg_comments_per_post by IP from TikTok metadata."""
    rows = conn.execute(
        "SELECT create_time, source, title, comments_count FROM tiktok_videos"
    ).fetchall()

    # Group by (month, IP)
    groups = {}
    for ts, source, title, comments_count in rows:
        date = _unix_to_date(ts)
        month = _month_key(date)
        ip = classify_ip(source or '', title or '')
        if month:
            key = (month, ip)
            if key not in groups:
                groups[key] = []
            groups[key].append(comments_count or 0)

    result = []
    for (month, ip), values in sorted(groups.items()):
        n = len(values)
        avg = round(sum(values) / n, 1)
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
    """Export monthly avg_comments_per_post by IP from Instagram metadata."""
    rows = conn.execute(
        "SELECT post_date, account, caption, comments_count FROM instagram_posts"
    ).fetchall()

    groups = {}
    for post_date, account, caption, comments_count in rows:
        month = _month_key(post_date)
        ip = classify_ip(account or '', caption or '')
        if month:
            key = (month, ip)
            if key not in groups:
                groups[key] = []
            groups[key].append(comments_count or 0)

    result = []
    for (month, ip), values in sorted(groups.items()):
        n = len(values)
        avg = round(sum(values) / n, 1)
        result.append({
            'month': month,
            'ip': ip,
            'avg_comments_per_post': avg,
            'n': n,
            'data_confidence': _data_confidence(n),
        })
    return result


def export_brand_trend(conn):
    """Monthly TikTok avg_comments_per_post from metadata with n and data_confidence."""
    rows = conn.execute("SELECT create_time, comments_count FROM tiktok_videos").fetchall()

    monthly = {}
    for ts, comments_count in rows:
        date = _unix_to_date(ts)
        month = _month_key(date)
        if month:
            if month not in monthly:
                monthly[month] = []
            monthly[month].append(comments_count or 0)

    result = []
    for month in sorted(monthly.keys()):
        values = monthly[month]
        n = len(values)
        avg = round(sum(values) / n, 1)
        result.append({
            'month': month,
            'avg_comments_per_post': avg,
            'n': n,
            'data_confidence': _data_confidence(n),
            'videos': n,
        })
    return result


def export_ip_share_trend(conn):
    """Monthly IP share from metadata comments_count (both platforms), excluding Pop Mart."""
    # TikTok videos: classify and accumulate metadata comments_count by (month, IP)
    tk_rows = conn.execute(
        "SELECT create_time, source, title, comments_count FROM tiktok_videos"
    ).fetchall()
    monthly_ip_engagement = {}
    for ts, source, title, comments_count in tk_rows:
        date = _unix_to_date(ts)
        month = _month_key(date)
        ip = classify_ip(source or '', title or '')
        if month:
            key = (month, ip)
            monthly_ip_engagement[key] = monthly_ip_engagement.get(key, 0) + (comments_count or 0)

    # Instagram posts: classify and accumulate metadata comments_count by (month, IP)
    ig_rows = conn.execute(
        "SELECT post_date, account, caption, comments_count FROM instagram_posts"
    ).fetchall()
    for post_date, account, caption, comments_count in ig_rows:
        month = _month_key(post_date)
        ip = classify_ip(account or '', caption or '')
        if month:
            key = (month, ip)
            monthly_ip_engagement[key] = monthly_ip_engagement.get(key, 0) + (comments_count or 0)

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
    """Monthly density index (mean=100) per platform using metadata comments_count."""
    # TikTok: monthly SUM(comments_count) / COUNT(*) from tiktok_videos
    tiktok_rows = conn.execute(
        "SELECT create_time, comments_count FROM tiktok_videos"
    ).fetchall()
    tiktok_monthly_content = {}
    tiktok_monthly_meta_comments = {}
    for ts, comments_count in tiktok_rows:
        date = _unix_to_date(ts)
        month = _month_key(date)
        if month:
            tiktok_monthly_content[month] = tiktok_monthly_content.get(month, 0) + 1
            tiktok_monthly_meta_comments[month] = tiktok_monthly_meta_comments.get(month, 0) + (comments_count or 0)

    # Instagram: monthly SUM(comments_count) / COUNT(*) from instagram_posts
    ig_rows = conn.execute(
        "SELECT post_date, comments_count FROM instagram_posts"
    ).fetchall()
    ig_monthly_content = {}
    ig_monthly_meta_comments = {}
    for post_date, comments_count in ig_rows:
        month = _month_key(post_date)
        if month:
            ig_monthly_content[month] = ig_monthly_content.get(month, 0) + 1
            ig_monthly_meta_comments[month] = ig_monthly_meta_comments.get(month, 0) + (comments_count or 0)

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

    tiktok_data = _compute_index(tiktok_monthly_content, tiktok_monthly_meta_comments)
    ig_data = _compute_index(ig_monthly_content, ig_monthly_meta_comments)

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


def export_official_engagement(conn):
    """Official account engagement from metadata (no comment JOIN).

    TikTok: author='popmartglobal', grouped by month.
    Instagram: account='popmart', grouped by month.
    Uses metadata comments_count, views, likes directly.
    """
    result = {}

    # TikTok: popmartglobal — metadata only
    tk_rows = conn.execute("""
        SELECT create_time, comments_count, views, likes
        FROM tiktok_videos
        WHERE author = 'popmartglobal'
    """).fetchall()

    tk_monthly = {}
    for ts, comments_count, views, likes in tk_rows:
        date = _unix_to_date(ts)
        month = _month_key(date)
        if month:
            if month not in tk_monthly:
                tk_monthly[month] = {'comments': [], 'views': [], 'likes': []}
            tk_monthly[month]['comments'].append(comments_count or 0)
            tk_monthly[month]['views'].append(views or 0)
            tk_monthly[month]['likes'].append(likes or 0)

    result['tiktok'] = []
    for m in sorted(tk_monthly.keys()):
        v = tk_monthly[m]
        n = len(v['comments'])
        result['tiktok'].append({
            'month': m,
            'posts': n,
            'avg_comments': round(sum(v['comments']) / n, 1),
            'avg_views': round(sum(v['views']) / n, 1),
            'avg_likes': round(sum(v['likes']) / n, 1),
        })

    # Instagram: popmart — metadata only
    ig_rows = conn.execute("""
        SELECT post_date, comments_count, likes
        FROM instagram_posts
        WHERE account = 'popmart'
    """).fetchall()

    ig_monthly = {}
    for post_date, comments_count, likes in ig_rows:
        month = _month_key(post_date)
        if month:
            if month not in ig_monthly:
                ig_monthly[month] = {'comments': [], 'likes': []}
            ig_monthly[month]['comments'].append(comments_count or 0)
            ig_monthly[month]['likes'].append(likes or 0)

    result['instagram'] = []
    for m in sorted(ig_monthly.keys()):
        v = ig_monthly[m]
        n = len(v['comments'])
        result['instagram'].append({
            'month': m,
            'posts': n,
            'avg_comments': round(sum(v['comments']) / n, 1),
            'avg_likes': round(sum(v['likes']) / n, 1),
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
