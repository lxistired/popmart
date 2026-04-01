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
