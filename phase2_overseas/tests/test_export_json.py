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
    assert classify_ip('tag/popmart', '星星人 new series') == 'Twinkle'
    assert classify_ip('tag/twinkle twinkle popmart', 'cute star') == 'Twinkle'

def test_classify_ip_crybaby():
    from export_json import classify_ip
    assert classify_ip('tag/crybaby', '') == 'Crybaby'
    assert classify_ip('tag/popmart', 'CryBaby blind box') == 'Crybaby'
    assert classify_ip('tag/popmart', 'cry baby new series') == 'Crybaby'
    assert classify_ip('tag/popmart', '哭娃盲盒') == 'Crybaby'


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
        (4, 'v4', 'popmartglobal', 'Official Labubu launch', 20000, 1000, 100, 20, '1709251200', 'user/popmartglobal', '2026-03-31'),
    ])
    # Insert sample tiktok comments
    conn.executemany("INSERT INTO tiktok_comments VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
        (1, 'v1', 'c1', 'Love it!', '2026-03-01', '2026-03-01T10:00:00', 5, 0, 'fan1', 0, '2026-03-31'),
        (2, 'v1', 'c2', 'Want one!', '2026-03-01', '2026-03-01T11:00:00', 3, 0, 'fan2', 0, '2026-03-31'),
        (3, 'v2', 'c3', 'Cute!', '2026-03-08', '2026-03-08T10:00:00', 2, 0, 'fan3', 0, '2026-03-31'),
        (4, 'v4', 'c4', 'Official reply', '2024-03-02', '2024-03-02T10:00:00', 10, 0, 'fan4', 0, '2026-03-31'),
        (5, 'v4', 'c5', 'Great product!', '2024-03-05', '2024-03-05T10:00:00', 8, 0, 'fan5', 0, '2026-03-31'),
        (6, 'v4', 'c6', 'Late comment', '2024-06-01', '2024-06-01T10:00:00', 1, 0, 'fan6', 0, '2026-03-31'),
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
    assert result['tiktok_videos'] == 4
    assert result['tiktok_comments'] == 6
    assert result['instagram_posts'] == 2
    assert result['instagram_comments'] == 3
    assert 'updated_at' in result


def test_export_ip_share(test_db):
    from export_json import export_ip_share
    result = export_ip_share(test_db)
    # result is a list of {ip, tiktok_videos, tiktok_comments, ...}
    assert isinstance(result, list)
    labubu = next(r for r in result if r['ip'] == 'Labubu')
    assert labubu['tiktok_videos'] == 2  # v1 + v4 (popmartglobal Labubu)


def test_export_tiktok_trend(test_db):
    from export_json import export_tiktok_trend
    result = export_tiktok_trend(test_db)
    # result is list of {week, ip, count}
    assert isinstance(result, list)
    assert all('week' in r and 'ip' in r and 'count' in r for r in result)


def test_export_brand_trend(test_db):
    from export_json import export_brand_trend
    result = export_brand_trend(test_db)
    assert isinstance(result, list)
    assert len(result) > 0
    first = result[0]
    assert 'month' in first and 'comments' in first and 'videos' in first and 'density' in first
    assert first['density'] == first['comments'] / max(first['videos'], 1)

def test_export_ip_share_trend(test_db):
    from export_json import export_ip_share_trend
    result = export_ip_share_trend(test_db)
    assert isinstance(result, list)
    assert len(result) > 0
    first = result[0]
    assert 'month' in first and 'ip' in first and 'share_pct' in first and 'count' in first
    for r in result:
        assert 0 <= r['share_pct'] <= 100

def test_export_cross_platform_index(test_db):
    from export_json import export_cross_platform_index
    result = export_cross_platform_index(test_db)
    assert isinstance(result, list)
    assert len(result) > 0
    first = result[0]
    assert 'month' in first and 'platform' in first and 'index' in first and 'density' in first
    assert first['platform'] in ('TikTok', 'Instagram')

def test_export_brand_vs_ugc(test_db):
    from export_json import export_brand_vs_ugc
    result = export_brand_vs_ugc(test_db)
    assert isinstance(result, dict)
    assert 'brand' in result and 'ugc' in result
    for key in ['avg_views', 'avg_likes', 'avg_er_pct', 'avg_comments']:
        assert key in result['brand'] and key in result['ugc']

def test_export_comment_quality(test_db):
    from export_json import export_comment_quality
    result = export_comment_quality(test_db)
    assert isinstance(result, list)
    assert len(result) == 2
    platforms = {r['platform'] for r in result}
    assert platforms == {'TikTok', 'Instagram'}
    for r in result:
        assert 'high_pct' in r and 'med_pct' in r and 'low_pct' in r and 'total' in r
        assert abs(r['high_pct'] + r['med_pct'] + r['low_pct'] - 100) < 0.5


def test_export_official_engagement(test_db):
    from export_json import export_official_engagement
    result = export_official_engagement(test_db)
    assert 'tiktok' in result and 'instagram' in result

    # TikTok: v4 is popmartglobal, create_time=1709251200 (2024-03-01)
    # Comments c4 (2024-03-02) and c5 (2024-03-05) are within 30 days
    # Comment c6 (2024-06-01) is outside 30 days — should NOT be counted
    tk = result['tiktok']
    assert len(tk) == 1
    assert tk[0]['month'] == '2024-03'
    assert tk[0]['posts'] == 1
    assert tk[0]['total_30d_comments'] == 2  # c4 + c5, not c6
    assert tk[0]['avg_30d_comments'] == 2.0

    # Instagram: popmart account has 2 posts
    ig = result['instagram']
    assert len(ig) >= 1
    # Both posts have comments within 30 days
    total_ig_comments = sum(m['total_30d_comments'] for m in ig)
    assert total_ig_comments == 3  # ic1, ic2, ic3 all within 30d of their posts
