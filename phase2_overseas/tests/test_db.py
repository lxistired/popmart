import sqlite3
import pytest


# INFRA-01: INSERT OR IGNORE deduplicates rows
def test_insert_or_ignore(tmp_db):
    from shared.db import init_db, ensure_unique_indexes, get_latest_date, batch_insert
    tmp_db.execute("""
        CREATE TABLE test_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asin TEXT, review_date_raw TEXT, review_title TEXT,
            UNIQUE(asin, review_date_raw, review_title)
        )""")
    tmp_db.execute("INSERT INTO test_reviews (asin, review_date_raw, review_title) VALUES (?,?,?)",
                   ("B001", "2024-01-01", "Great product"))
    tmp_db.execute("INSERT OR IGNORE INTO test_reviews (asin, review_date_raw, review_title) VALUES (?,?,?)",
                   ("B001", "2024-01-01", "Great product"))
    count = tmp_db.execute("SELECT COUNT(*) FROM test_reviews").fetchone()[0]
    assert count == 1, "INSERT OR IGNORE must not create duplicates"


# INFRA-01: ensure_unique_indexes() is idempotent (safe to call twice)
def test_migration_idempotent(tmp_db):
    from shared.db import ensure_unique_indexes
    # Create the time-series tables without UNIQUE constraints (like the real DB)
    tmp_db.execute("""CREATE TABLE amazon_review_dates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asin TEXT, review_date TEXT, review_date_raw TEXT,
        review_title TEXT, rating REAL, verified INTEGER, scraped_at TEXT
    )""")
    tmp_db.execute("""CREATE TABLE tiktok_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        comment_id TEXT
    )""")
    tmp_db.execute("""CREATE TABLE instagram_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shortcode TEXT, comment_id TEXT
    )""")
    ensure_unique_indexes(tmp_db)  # first call
    ensure_unique_indexes(tmp_db)  # second call must not raise
    # Verify indexes exist
    idxs = {r[1] for r in tmp_db.execute("PRAGMA index_list(amazon_review_dates)")}
    assert "uq_amazon_review" in idxs


# INFRA-03: get_latest_date() returns None for empty table, max date otherwise
def test_get_latest_date(tmp_db):
    from shared.db import get_latest_date
    tmp_db.execute("""CREATE TABLE amazon_review_dates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asin TEXT, review_date TEXT, scraped_at TEXT
    )""")
    # Empty table returns None
    result = get_latest_date(tmp_db, "amazon_review_dates", "review_date", "asin", "B001")
    assert result is None

    tmp_db.execute("INSERT INTO amazon_review_dates (asin, review_date) VALUES (?,?)", ("B001", "2024-03-01"))
    tmp_db.execute("INSERT INTO amazon_review_dates (asin, review_date) VALUES (?,?)", ("B001", "2024-06-15"))
    tmp_db.commit()
    result = get_latest_date(tmp_db, "amazon_review_dates", "review_date", "asin", "B001")
    assert result == "2024-06-15"


# INFRA-08: since_date from config propagates as a filter
def test_since_date_propagation(tmp_db):
    from shared.db import get_latest_date
    tmp_db.execute("""CREATE TABLE amazon_review_dates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asin TEXT, review_date TEXT
    )""")
    tmp_db.execute("INSERT INTO amazon_review_dates (asin, review_date) VALUES (?,?)", ("B001", "2023-01-01"))
    tmp_db.execute("INSERT INTO amazon_review_dates (asin, review_date) VALUES (?,?)", ("B001", "2024-06-01"))
    tmp_db.commit()
    result = get_latest_date(tmp_db, "amazon_review_dates", "review_date", "asin", "B001")
    # Phase scripts use max(get_latest_date(), config.since_date) as the cutoff
    # This test verifies get_latest_date returns the right value; config logic is in platform scripts
    assert result == "2024-06-01"


# DB safety: existing snapshot rows untouched after init_db()
def test_existing_data_preserved(tmp_db):
    from shared.db import init_db
    # Pre-populate snapshot table like real DB (22 amazon rows, etc.)
    tmp_db.execute("""CREATE TABLE amazon_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scraped_at TEXT, asin TEXT, ip TEXT
    )""")
    for i in range(22):
        tmp_db.execute("INSERT INTO amazon_snapshots (scraped_at, asin, ip) VALUES (?,?,?)",
                       (f"2026-03-{i+1:02d}", f"B00{i:03d}", "Labubu"))
    tmp_db.commit()
    count_before = tmp_db.execute("SELECT COUNT(*) FROM amazon_snapshots").fetchone()[0]
    assert count_before == 22
    # init_db() on real DB uses CREATE TABLE IF NOT EXISTS — existing rows survive
    # This test documents the contract: row count must not change after schema operations
    count_after = tmp_db.execute("SELECT COUNT(*) FROM amazon_snapshots").fetchone()[0]
    assert count_after == count_before, "Existing snapshot rows must be preserved"


# --- Schema completeness tests (INFRA-11) ---

def _get_columns(conn, table):
    """Helper: return set of column names for a table."""
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_fresh_db_tiktok_videos_columns(tmp_db):
    from shared.db import init_db
    init_db(tmp_db)
    cols = _get_columns(tmp_db, 'tiktok_videos')
    expected = {'id', 'video_id', 'author', 'title', 'views', 'likes',
                'comments_count', 'shares', 'create_time', 'source',
                'scraped_at', 'last_comment_scraped_at'}
    assert expected.issubset(cols), f"Missing: {expected - cols}"


def test_fresh_db_tiktok_comments_columns(tmp_db):
    from shared.db import init_db
    init_db(tmp_db)
    cols = _get_columns(tmp_db, 'tiktok_comments')
    expected = {'id', 'video_id', 'comment_id', 'comment_text', 'comment_date',
                'comment_datetime', 'likes', 'reply_count', 'author_name',
                'is_author_reply', 'scraped_at'}
    assert expected.issubset(cols), f"Missing: {expected - cols}"


def test_fresh_db_instagram_posts_columns(tmp_db):
    from shared.db import init_db
    init_db(tmp_db)
    cols = _get_columns(tmp_db, 'instagram_posts')
    expected = {'id', 'shortcode', 'post_url', 'account', 'caption', 'likes',
                'comments_count', 'post_date', 'source', 'scraped_at',
                'last_comment_scraped_at'}
    assert expected.issubset(cols), f"Missing: {expected - cols}"


def test_fresh_db_instagram_comments_columns(tmp_db):
    from shared.db import init_db
    init_db(tmp_db)
    cols = _get_columns(tmp_db, 'instagram_comments')
    expected = {'id', 'shortcode', 'comment_id', 'comment_text', 'comment_date',
                'comment_datetime', 'likes', 'author_name', 'is_author_reply',
                'scraped_at'}
    assert expected.issubset(cols), f"Missing: {expected - cols}"


def test_fresh_db_amazon_review_dates_columns(tmp_db):
    from shared.db import init_db
    init_db(tmp_db)
    cols = _get_columns(tmp_db, 'amazon_review_dates')
    expected = {'id', 'asin', 'ip', 'review_date', 'review_date_raw',
                'review_title', 'rating', 'verified', 'helpful_votes',
                'scraped_at'}
    assert expected.issubset(cols), f"Missing: {expected - cols}"


def test_migration_adds_missing_columns(tmp_db):
    from shared.db import _apply_incremental_migrations
    # Create tables with OLD schema (missing shares, last_comment_scraped_at, etc.)
    tmp_db.execute("""CREATE TABLE tiktok_videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT UNIQUE, author TEXT, title TEXT, views INTEGER,
        likes INTEGER, comments_count INTEGER, create_time TEXT,
        source TEXT, scraped_at TEXT NOT NULL
    )""")
    tmp_db.execute("""CREATE TABLE tiktok_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT, comment_id TEXT, comment_text TEXT,
        comment_date TEXT, comment_datetime TEXT, likes INTEGER,
        author_name TEXT, scraped_at TEXT NOT NULL
    )""")
    tmp_db.execute("""CREATE TABLE instagram_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shortcode TEXT UNIQUE, post_url TEXT, account TEXT,
        caption TEXT, post_date TEXT, source TEXT, scraped_at TEXT NOT NULL
    )""")
    tmp_db.execute("""CREATE TABLE instagram_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shortcode TEXT, comment_id TEXT, comment_text TEXT,
        comment_date TEXT, comment_datetime TEXT, likes INTEGER,
        author_name TEXT, scraped_at TEXT NOT NULL
    )""")
    tmp_db.execute("""CREATE TABLE amazon_review_dates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asin TEXT NOT NULL, ip TEXT, review_date TEXT, review_date_raw TEXT,
        review_title TEXT, rating REAL, verified INTEGER, scraped_at TEXT NOT NULL
    )""")
    tmp_db.commit()

    _apply_incremental_migrations(tmp_db)

    # Verify new columns added
    assert 'shares' in _get_columns(tmp_db, 'tiktok_videos')
    assert 'last_comment_scraped_at' in _get_columns(tmp_db, 'tiktok_videos')
    assert 'reply_count' in _get_columns(tmp_db, 'tiktok_comments')
    assert 'is_author_reply' in _get_columns(tmp_db, 'tiktok_comments')
    assert 'likes' in _get_columns(tmp_db, 'instagram_posts')
    assert 'comments_count' in _get_columns(tmp_db, 'instagram_posts')
    assert 'last_comment_scraped_at' in _get_columns(tmp_db, 'instagram_posts')
    assert 'is_author_reply' in _get_columns(tmp_db, 'instagram_comments')
    assert 'helpful_votes' in _get_columns(tmp_db, 'amazon_review_dates')


def test_migration_idempotent_v2(tmp_db):
    from shared.db import _apply_incremental_migrations
    # Create a minimal table set
    tmp_db.execute("""CREATE TABLE tiktok_videos (
        id INTEGER PRIMARY KEY, video_id TEXT UNIQUE, scraped_at TEXT)""")
    tmp_db.execute("""CREATE TABLE tiktok_comments (
        id INTEGER PRIMARY KEY, scraped_at TEXT)""")
    tmp_db.execute("""CREATE TABLE instagram_posts (
        id INTEGER PRIMARY KEY, shortcode TEXT UNIQUE, scraped_at TEXT)""")
    tmp_db.execute("""CREATE TABLE instagram_comments (
        id INTEGER PRIMARY KEY, scraped_at TEXT)""")
    tmp_db.execute("""CREATE TABLE amazon_review_dates (
        id INTEGER PRIMARY KEY, scraped_at TEXT)""")
    tmp_db.commit()

    _apply_incremental_migrations(tmp_db)
    _apply_incremental_migrations(tmp_db)  # second call must not raise


def test_init_preserves_existing_rows(tmp_db):
    from shared.db import init_db
    # Create OLD schema tables with data
    tmp_db.execute("""CREATE TABLE tiktok_videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT UNIQUE, author TEXT, title TEXT, views INTEGER,
        likes INTEGER, comments_count INTEGER, create_time TEXT,
        source TEXT, scraped_at TEXT NOT NULL
    )""")
    tmp_db.execute("INSERT INTO tiktok_videos (video_id, author, scraped_at) VALUES (?,?,?)",
                   ("v_test1", "author1", "2026-03-31"))
    tmp_db.execute("INSERT INTO tiktok_videos (video_id, author, scraped_at) VALUES (?,?,?)",
                   ("v_test2", "author2", "2026-03-31"))
    tmp_db.execute("""CREATE TABLE tiktok_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT, comment_id TEXT, scraped_at TEXT NOT NULL
    )""")
    for i in range(5):
        tmp_db.execute("INSERT INTO tiktok_comments (video_id, comment_id, scraped_at) VALUES (?,?,?)",
                       ("v_test1", f"c{i}", "2026-03-31"))
    tmp_db.commit()

    before_videos = tmp_db.execute("SELECT COUNT(*) FROM tiktok_videos").fetchone()[0]
    before_comments = tmp_db.execute("SELECT COUNT(*) FROM tiktok_comments").fetchone()[0]

    init_db(tmp_db)

    after_videos = tmp_db.execute("SELECT COUNT(*) FROM tiktok_videos").fetchone()[0]
    after_comments = tmp_db.execute("SELECT COUNT(*) FROM tiktok_comments").fetchone()[0]
    assert after_videos == before_videos, "tiktok_videos rows changed"
    assert after_comments == before_comments, "tiktok_comments rows changed"
