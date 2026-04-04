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

def test_classify_ip_twinkle():
    from export_json import classify_ip
    assert classify_ip('tag/twinkle', '') == 'Twinkle'
    assert classify_ip('tag/popmart', '\u661f\u661f\u4eba new series') == 'Twinkle'
    assert classify_ip('tag/twinkle twinkle popmart', 'cute star') == 'Twinkle'

def test_classify_ip_crybaby():
    from export_json import classify_ip
    assert classify_ip('tag/crybaby', '') == 'Crybaby'
    assert classify_ip('tag/popmart', 'CryBaby blind box') == 'Crybaby'
    assert classify_ip('tag/popmart', 'cry baby new series') == 'Crybaby'
    assert classify_ip('tag/popmart', '\u54ed\u5a03\u76f2\u76d2') == 'Crybaby'


import sqlite3
import tempfile
import json

@pytest.fixture
def test_db():
    """Create an in-memory DB with sample data using init_db for production schema."""
    conn = sqlite3.connect(':memory:')

    # Use init_db to create tables matching production schema exactly
    from shared.db import init_db
    init_db(conn)

    # Insert sample tiktok videos (create_time is Unix timestamp)
    # v1: Labubu UGC, 2024-04-01, views=10000
    # v2: Dimoo UGC, 2024-04-01, views=5000
    # v3: Pop Mart UGC, 2024-04-08, views=8000
    # v4: Labubu official, 2024-03-01, views=20000
    # v5: Pop Mart official, 2024-05-01, views=15000
    # v6: Labubu UGC in 2024-03, views=5000 (for UGC amplification test)
    conn.executemany("""INSERT INTO tiktok_videos
        (id, video_id, author, title, views, likes, comments_count, shares, create_time, source, scraped_at, last_comment_scraped_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", [
        (1, 'v1', 'user1', 'Labubu unboxing!', 10000, 500, 50, 10, '1711929600', 'tag/labubu', '2026-03-31', '2026-03-31'),
        (2, 'v2', 'user2', 'Dimoo world tour', 5000, 200, 30, 5, '1711929600', 'tag/dimoo', '2026-03-31', '2026-03-31'),
        (3, 'v3', 'user3', 'Pop Mart haul', 8000, 300, 40, 8, '1712534400', 'tag/popmart unboxing', '2026-03-31', None),
        (4, 'v4', 'popmartglobal', 'Official Labubu launch', 20000, 1000, 100, 20, '1709251200', 'user/popmartglobal', '2026-03-31', '2026-03-31'),
        (5, 'v5', 'popmartglobal', 'Pop Mart summer collection', 15000, 800, 80, 15, '1714521600', 'user/popmartglobal', '2026-03-31', '2026-03-31'),
        (6, 'v6', 'user4', 'Labubu fan art', 5000, 250, 25, 3, '1709251200', 'tag/labubu', '2026-03-31', '2026-03-31'),
    ])

    # Insert sample tiktok comments
    conn.executemany("""INSERT INTO tiktok_comments
        (id, video_id, comment_id, comment_text, comment_date, comment_datetime, likes, reply_count, author_name, is_author_reply, scraped_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""", [
        (1, 'v1', 'c1', 'Love it!', '2026-03-01', '2026-03-01T10:00:00', 5, 0, 'fan1', 0, '2026-03-31'),
        (2, 'v1', 'c2', 'Want one!', '2026-03-01', '2026-03-01T11:00:00', 3, 0, 'fan2', 0, '2026-03-31'),
        (3, 'v2', 'c3', 'Cute!', '2026-03-08', '2026-03-08T10:00:00', 2, 0, 'fan3', 0, '2026-03-31'),
        (4, 'v4', 'c4', 'Official reply', '2024-03-02', '2024-03-02T10:00:00', 10, 0, 'fan4', 0, '2026-03-31'),
        (5, 'v4', 'c5', 'Great product!', '2024-03-05', '2024-03-05T10:00:00', 8, 0, 'fan5', 0, '2026-03-31'),
        (6, 'v4', 'c6', 'Late comment', '2024-06-01', '2024-06-01T10:00:00', 1, 0, 'fan6', 0, '2026-03-31'),
    ])

    # Insert sample instagram posts
    conn.executemany("""INSERT INTO instagram_posts
        (id, shortcode, post_url, account, caption, likes, comments_count, post_date, source, scraped_at, last_comment_scraped_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""", [
        (1, 'ABC1', 'https://instagram.com/p/ABC1', 'popmart', 'New Labubu drop!', 1000, 50, '2026-03-01', 'instagrapi', '2026-03-31', '2026-03-31'),
        (2, 'ABC2', 'https://instagram.com/p/ABC2', 'popmart', 'Molly series', 800, 30, '2026-03-08', 'instagrapi', '2026-03-31', '2026-03-31'),
    ])

    # Insert sample instagram comments
    conn.executemany("""INSERT INTO instagram_comments
        (id, shortcode, comment_id, comment_text, comment_date, comment_datetime, likes, author_name, is_author_reply, scraped_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)""", [
        (1, 'ABC1', 'ic1', 'Amazing!', '2026-03-01', '2026-03-01T12:00:00', 5, 'fan1', 0, '2026-03-31'),
        (2, 'ABC1', 'ic2', 'Need this!', '2026-03-02', '2026-03-02T12:00:00', 2, 'fan2', 0, '2026-03-31'),
        (3, 'ABC2', 'ic3', 'So pretty', '2026-03-08', '2026-03-08T12:00:00', 1, 'fan3', 0, '2026-03-31'),
    ])

    conn.commit()
    yield conn
    conn.close()


# ────────────────────────────────────────────────────
# Export function tests — new format with metadata-driven metrics
# ────────────────────────────────────────────────────

def test_export_overview(test_db):
    """ANAL-07 partial: overview has data_freshness, coverage, no comment_quality."""
    from export_json import export_overview
    result = export_overview(test_db)

    # Must have data_freshness with platform keys
    assert 'data_freshness' in result
    assert 'tiktok' in result['data_freshness']
    assert 'instagram' in result['data_freshness']

    # Must have coverage dict with counts
    assert 'coverage' in result
    assert 'tiktok_videos' in result['coverage']
    assert 'instagram_posts' in result['coverage']

    # Must NOT have comment_quality
    assert 'comment_quality' not in result

    # Must have updated_at
    assert 'updated_at' in result


def test_export_ip_share(test_db):
    """ANAL-04, ANAL-08: IP share uses actual comment row counts, excludes Pop Mart."""
    from export_json import export_ip_share
    result = export_ip_share(test_db)

    assert isinstance(result, list)

    # Pop Mart must be excluded entirely
    ips_in_result = [r['ip'] for r in result]
    assert 'Pop Mart' not in ips_in_result

    # Must use new key names (comment-count-based)
    for r in result:
        assert 'tiktok_posts' in r
        assert 'tiktok_comments' in r
        assert 'instagram_posts' in r
        assert 'instagram_comments' in r
        assert 'total_engagement' in r
        assert 'share_pct' in r

    # Old metadata-based key names must NOT exist
    for r in result:
        assert 'tiktok_videos' not in r
        assert 'tiktok_comments_meta' not in r
        assert 'instagram_comments_meta' not in r
        assert 'total_comments' not in r

    # Labubu tiktok: v1(c1+c2=2) + v4(c4+c5+c6=3) + v6(0) = 5 comment rows
    # Labubu instagram: ABC1(ic1+ic2=2) = 2 comment rows
    # Total Labubu engagement = 5 + 2 = 7
    labubu = next(r for r in result if r['ip'] == 'Labubu')
    assert labubu['tiktok_comments'] == 5   # COUNT of comment rows for Labubu TikTok videos
    assert labubu['instagram_comments'] == 2  # COUNT of comment rows for Labubu Instagram posts
    assert labubu['total_engagement'] == 7

    # share_pct should sum to ~100 across all IPs
    total_pct = sum(r['share_pct'] for r in result)
    assert abs(total_pct - 100.0) < 0.5


def test_export_tiktok_trend(test_db):
    """ANAL-02: monthly avg_comments_per_post from actual comment timestamps with n and data_confidence."""
    from export_json import export_tiktok_trend
    result = export_tiktok_trend(test_db)

    assert isinstance(result, list)
    assert len(result) > 0

    # Must have new keys, not old ones
    for r in result:
        assert 'month' in r  # not 'week'
        assert 'ip' in r
        assert 'avg_comments_per_post' in r
        assert 'n' in r
        assert 'data_confidence' in r
        # Old keys must NOT exist
        assert 'week' not in r
        assert 'count' not in r

    # Month format must be YYYY-MM
    for r in result:
        assert len(r['month']) == 7
        assert r['month'][4] == '-'

    # Labubu in 2026-03: v1 has c1+c2 = 2 comments with comment_date in 2026-03
    # avg_comments_per_post = 2 comments / 1 video = 2.0, n = 1 distinct video
    labubu_mar = [r for r in result if r['ip'] == 'Labubu' and r['month'] == '2026-03']
    assert len(labubu_mar) == 1
    assert labubu_mar[0]['avg_comments_per_post'] == 2.0
    assert labubu_mar[0]['n'] == 1
    assert labubu_mar[0]['data_confidence'] == 'low'  # n < 5

    # Labubu in 2024-04 should NOT appear — v1 was published in 2024-04 but comments are in 2026-03
    labubu_apr = [r for r in result if r['ip'] == 'Labubu' and r['month'] == '2024-04']
    assert len(labubu_apr) == 0


def test_export_instagram_trend(test_db):
    """ANAL-03: monthly avg_comments_per_post from actual comment timestamps with n and data_confidence."""
    from export_json import export_instagram_trend
    result = export_instagram_trend(test_db)

    assert isinstance(result, list)
    assert len(result) > 0

    for r in result:
        assert 'month' in r
        assert 'ip' in r
        assert 'avg_comments_per_post' in r
        assert 'n' in r
        assert 'data_confidence' in r
        # Old keys must NOT exist
        assert 'week' not in r
        assert 'count' not in r

    # Month format YYYY-MM
    for r in result:
        assert len(r['month']) == 7

    # Labubu in 2026-03: ABC1 has ic1+ic2 = 2 comments with comment_date in 2026-03
    # avg_comments_per_post = 2 comments / 1 post = 2.0, n = 1 distinct post
    labubu_mar = [r for r in result if r['ip'] == 'Labubu' and r['month'] == '2026-03']
    assert len(labubu_mar) == 1
    assert labubu_mar[0]['avg_comments_per_post'] == 2.0
    assert labubu_mar[0]['n'] == 1


def test_export_brand_trend(test_db):
    """ANAL-01: monthly avg_comments_per_post from comment timestamps, no density/total_comments."""
    from export_json import export_brand_trend
    result = export_brand_trend(test_db)

    assert isinstance(result, list)
    assert len(result) > 0

    first = result[0]
    # Must have new keys
    assert 'month' in first
    assert 'avg_comments_per_post' in first
    assert 'n' in first
    assert 'data_confidence' in first
    assert 'videos' in first

    # Old keys must NOT exist
    assert 'comments' not in first
    assert 'total_comments' not in first
    assert 'density' not in first

    # For 2026-03: c1+c2 (v1) + c3 (v2) = 3 comments on 2 distinct videos (v1, v2)
    # avg = 3 comments / 2 videos = 1.5, n=3 (comment rows), videos=2
    mar_2026 = next(r for r in result if r['month'] == '2026-03')
    assert mar_2026['avg_comments_per_post'] == 1.5
    assert mar_2026['n'] == 3
    assert mar_2026['videos'] == 2
    assert mar_2026['data_confidence'] == 'low'  # n=3 < 5

    # 2024-04 should NOT appear (v1,v2,v3 published but no comments with comment_date in 2024-04)
    apr_2024 = [r for r in result if r['month'] == '2024-04']
    assert len(apr_2024) == 0


def test_export_ip_share_trend(test_db):
    """ANAL-04, ANAL-08: monthly IP share excludes Pop Mart, uses actual comment row counts."""
    from export_json import export_ip_share_trend
    result = export_ip_share_trend(test_db)

    assert isinstance(result, list)
    assert len(result) > 0

    for r in result:
        assert 'month' in r
        assert 'ip' in r
        assert 'share_pct' in r
        assert 'engagement' in r

    # Pop Mart must be excluded
    for r in result:
        assert r['ip'] != 'Pop Mart'

    # Old key 'count' must NOT exist
    for r in result:
        assert 'count' not in r

    # engagement values should come from COUNT of comment rows, not metadata sums
    # In 2024-03: Labubu has c4+c5 (v4, comment_date in 2024-03) = 2 comment rows
    labubu_mar = [r for r in result if r['ip'] == 'Labubu' and r['month'] == '2024-03']
    assert len(labubu_mar) == 1
    assert labubu_mar[0]['engagement'] == 2

    # In 2026-03: Labubu TikTok c1+c2(v1)=2, Instagram ABC1 ic1+ic2=2 => total=4
    labubu_mar26 = [r for r in result if r['ip'] == 'Labubu' and r['month'] == '2026-03']
    assert len(labubu_mar26) == 1
    assert labubu_mar26[0]['engagement'] == 4

    # Check share_pct sums to ~100 per month
    months = set(r['month'] for r in result)
    for month in months:
        month_rows = [r for r in result if r['month'] == month]
        total_pct = sum(r['share_pct'] for r in month_rows)
        assert abs(total_pct - 100.0) < 0.5


def test_export_cross_platform_index(test_db):
    """ANAL-05: density uses COUNT(comment rows) / COUNT(distinct posts with comments), not metadata."""
    from export_json import export_cross_platform_index
    result = export_cross_platform_index(test_db)

    assert isinstance(result, list)
    assert len(result) > 0

    for r in result:
        assert 'month' in r
        assert 'platform' in r
        assert 'density' in r
        assert 'index' in r

    # TikTok density for 2026-03: comments in that month c1+c2(v1) + c3(v2) = 3 comment rows
    # distinct posts with comments = v1, v2 = 2 posts
    # density = 3 / 2 = 1.5
    tiktok_mar = [r for r in result if r['platform'] == 'TikTok' and r['month'] == '2026-03']
    assert len(tiktok_mar) == 1
    assert tiktok_mar[0]['density'] == 1.5

    # Instagram density for 2026-03: ic1+ic2(ABC1) + ic3(ABC2) = 3 comment rows
    # distinct posts with comments = ABC1, ABC2 = 2 posts
    # density = 3 / 2 = 1.5
    ig_mar = [r for r in result if r['platform'] == 'Instagram' and r['month'] == '2026-03']
    assert len(ig_mar) == 1
    assert ig_mar[0]['density'] == 1.5


def test_export_official_engagement(test_db):
    """ANAL-06: official avg_comments uses comment rows by month; avg_views/avg_likes from metadata."""
    from export_json import export_official_engagement
    result = export_official_engagement(test_db)

    assert 'tiktok' in result
    assert 'instagram' in result

    tk = result['tiktok']
    assert isinstance(tk, list)
    assert len(tk) > 0

    # Check each monthly entry has required keys
    for entry in tk:
        assert 'month' in entry
        assert 'posts' in entry
        assert 'avg_comments' in entry
        assert 'avg_views' in entry
        assert 'avg_likes' in entry

    # Old keys must NOT exist
    for entry in tk:
        assert 'total_comments' not in entry

    # TikTok 2024-03: v4 (popmartglobal) published 2024-03, avg_views/avg_likes from metadata
    tk_mar = next(e for e in tk if e['month'] == '2024-03')
    assert tk_mar['avg_views'] == 20000.0   # from metadata — no change
    assert tk_mar['avg_likes'] == 1000.0    # from metadata — no change
    # avg_comments from comment rows: c4+c5 have comment_date in 2024-03 for v4 = 2 comment rows
    # posts_in_month with comments = 1 (v4), avg_comments = 2/1 = 2.0
    assert tk_mar['avg_comments'] == 2.0

    # TikTok 2024-05: v5 (popmartglobal) published 2024-05 with 0 comments in tiktok_comments
    # avg_views/avg_likes unchanged but avg_comments = 0
    tk_may = next((e for e in tk if e['month'] == '2024-05'), None)
    if tk_may:
        assert tk_may['avg_views'] == 15000.0
        assert tk_may['avg_comments'] == 0.0

    # Instagram official (popmart account) — both ABC1 and ABC2 are popmart
    ig = result['instagram']
    assert isinstance(ig, list)
    assert len(ig) > 0
    # 2026-03: ABC1 (ic1+ic2=2) + ABC2 (ic3=1) = 3 comment rows on 2 posts
    # avg_comments = 3/2 = 1.5
    ig_mar = next(e for e in ig if e['month'] == '2026-03')
    assert ig_mar['avg_comments'] == 1.5
    for entry in ig:
        assert 'avg_comments' in entry
        assert 'avg_likes' in entry


def test_export_brand_vs_ugc(test_db):
    """avg_comments uses COUNT of tiktok_comment rows per video; avg_views/avg_likes from metadata."""
    from export_json import export_brand_vs_ugc
    result = export_brand_vs_ugc(test_db)
    assert isinstance(result, dict)
    assert 'brand' in result and 'ugc' in result
    for key in ['avg_views', 'avg_likes', 'avg_er_pct', 'avg_comments']:
        assert key in result['brand'] and key in result['ugc']

    # Brand: v4 (popmartglobal) has 3 comment rows (c4,c5,c6), v5 has 0 comment rows
    # avg_comments = (3 + 0) / 2 = 1.5
    assert result['brand']['avg_comments'] == 1.5
    # avg_views from metadata: (20000 + 15000) / 2 = 17500.0
    assert result['brand']['avg_views'] == 17500.0

    # UGC: v1(2 comments), v2(1 comment), v3(0 comments), v6(0 comments) = 3/4 = 0.75
    # round(0.75, 1) = 0.8 due to Python banker's rounding (round half to even)
    assert result['ugc']['avg_comments'] == pytest.approx(0.75, abs=0.1)


def test_export_data_coverage(test_db):
    """ANAL-07: data coverage replaces comment_quality."""
    from export_json import export_data_coverage
    result = export_data_coverage(test_db)

    assert isinstance(result, dict)
    assert 'tiktok' in result
    assert 'instagram' in result

    # Each platform has required fields
    for platform in ['tiktok', 'instagram']:
        p = result[platform]
        assert 'total_posts' in p
        assert 'date_range' in p
        assert 'min' in p['date_range']
        assert 'max' in p['date_range']
        assert 'monthly_counts' in p
        assert isinstance(p['monthly_counts'], list)
        assert 'coverage_pct' in p

    # TikTok: 6 videos, 5 with last_comment_scraped_at, 1 without (v3)
    tk = result['tiktok']
    assert tk['total_posts'] == 6
    # coverage_pct = 5/6 * 100 = 83.3
    assert tk['coverage_pct'] == pytest.approx(83.3, abs=0.1)

    # Instagram: 2 posts, both have last_comment_scraped_at
    ig = result['instagram']
    assert ig['total_posts'] == 2
    assert ig['coverage_pct'] == 100.0


def test_export_ugc_amplification(test_db):
    """ANAL-09: monthly UGC/official avg_views ratio trend."""
    from export_json import export_ugc_amplification
    result = export_ugc_amplification(test_db)

    assert isinstance(result, list)

    for r in result:
        assert 'month' in r
        assert 'ugc_avg_views' in r
        assert 'official_avg_views' in r
        assert 'amplification_ratio' in r
        assert 'ugc_n' in r
        assert 'official_n' in r

    # 2024-03: official v4 views=20000, UGC v6 views=5000
    # amplification_ratio = 5000 / 20000 = 0.25
    mar_2024 = [r for r in result if r['month'] == '2024-03']
    assert len(mar_2024) == 1
    assert mar_2024[0]['official_avg_views'] == 20000.0
    assert mar_2024[0]['ugc_avg_views'] == 5000.0
    assert mar_2024[0]['amplification_ratio'] == 0.25
    assert mar_2024[0]['official_n'] == 1
    assert mar_2024[0]['ugc_n'] == 1

    # 2024-04: UGC only (v1, v2, v3) — should NOT appear in result (no official)
    apr_2024 = [r for r in result if r['month'] == '2024-04']
    assert len(apr_2024) == 0

    # 2024-05: official only (v5) — should NOT appear in result (no UGC)
    may_2024 = [r for r in result if r['month'] == '2024-05']
    assert len(may_2024) == 0


def test_no_export_comment_quality():
    """Verify export_comment_quality function has been removed."""
    with pytest.raises(ImportError):
        from export_json import export_comment_quality
