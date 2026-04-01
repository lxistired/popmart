"""
shared/db.py — 共享数据库连接层
提供: get_conn, init_db, ensure_unique_indexes, get_latest_date, batch_insert
"""

import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, '..', 'overseas_data.db')


def get_conn():
    """Return SQLite connection with WAL mode and NORMAL sync for performance."""
    conn = sqlite3.connect(os.path.abspath(DB_FILE))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def ensure_unique_indexes(conn):
    """Add missing UNIQUE constraints as indexes. Safe to run multiple times (idempotent)."""
    migrations = [
        """CREATE UNIQUE INDEX IF NOT EXISTS uq_amazon_review
           ON amazon_review_dates(asin, review_date_raw, review_title)""",
        """CREATE UNIQUE INDEX IF NOT EXISTS uq_tiktok_comment
           ON tiktok_comments(comment_id)""",
        """CREATE UNIQUE INDEX IF NOT EXISTS uq_ig_comment
           ON instagram_comments(shortcode, comment_id)""",
    ]
    for sql in migrations:
        conn.execute(sql)
    conn.commit()


def _create_timeseries_tables(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS amazon_review_dates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asin TEXT NOT NULL,
        ip TEXT,
        review_date TEXT,
        review_date_raw TEXT,
        review_title TEXT,
        rating REAL,
        verified INTEGER,
        scraped_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS tiktok_videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT UNIQUE,
        author TEXT,
        title TEXT,
        views INTEGER,
        likes INTEGER,
        comments_count INTEGER,
        create_time TEXT,
        source TEXT,
        scraped_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS tiktok_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT,
        comment_id TEXT,
        comment_text TEXT,
        comment_date TEXT,
        comment_datetime TEXT,
        likes INTEGER,
        author_name TEXT,
        scraped_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS instagram_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shortcode TEXT UNIQUE,
        post_url TEXT,
        account TEXT,
        caption TEXT,
        post_date TEXT,
        source TEXT,
        scraped_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS instagram_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shortcode TEXT,
        comment_id TEXT,
        comment_text TEXT,
        comment_date TEXT,
        comment_datetime TEXT,
        likes INTEGER,
        author_name TEXT,
        scraped_at TEXT NOT NULL
    )""")
    conn.commit()


def init_db():
    """Create all time-series tables if they don't exist, add unique indexes, return conn."""
    conn = get_conn()
    _create_timeseries_tables(conn)
    ensure_unique_indexes(conn)
    return conn


def get_latest_date(conn, table: str, date_col: str, key_col: str, key_val: str):
    """Return the most recent date value for a given key, or None if no rows."""
    row = conn.execute(
        f"SELECT MAX({date_col}) FROM {table} WHERE {key_col} = ?", (key_val,)
    ).fetchone()
    return row[0] if row else None


def batch_insert(conn, table: str, rows: list, columns: list):
    """INSERT OR IGNORE rows into table. rows is list of dicts or list of tuples."""
    if not rows:
        return
    cols = ', '.join(columns)
    placeholders = ', '.join(['?'] * len(columns))
    sql = f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({placeholders})"
    if isinstance(rows[0], dict):
        data = [[r[c] for c in columns] for r in rows]
    else:
        data = rows
    conn.executemany(sql, data)
    conn.commit()
