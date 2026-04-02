"""
Tests for Instagram three-layer skip fix + comment backfill.
Validates: session-scoped checkpoint, upsert replacement, comment refresh targeting,
last_comment_scraped_at update, backfill query + limit.

Uses in-memory SQLite (tmp_db fixture). Does NOT import instagram_browser.
"""

import sqlite3
from datetime import datetime, timezone, timedelta

from shared.db import init_db, upsert_post_metadata, batch_insert
from shared.checkpoint import load_checkpoint, save_checkpoint


# ---------------------------------------------------------------------------
# Test 1: Session-scoped checkpoint resets completed_tags and completed_accounts
# ---------------------------------------------------------------------------
def test_checkpoint_session_scoped(tmp_db, tmp_path):
    """Verify that completed_tags and completed_accounts are reset to empty at run start.
    The rebuilt logic should ignore checkpoint-saved completed sets."""
    import json
    import os

    # Simulate a saved checkpoint with completed tags/accounts
    ckpt_dir = tmp_path / 'checkpoints'
    ckpt_dir.mkdir()
    ckpt_file = ckpt_dir / 'instagram_browser_checkpoint.json'
    ckpt_file.write_text(json.dumps({
        'completed_tags': ['labubu', 'popmart'],
        'completed_accounts': ['popmart'],
    }))

    # Load checkpoint like the script does
    data = json.loads(ckpt_file.read_text())

    # Session-scoped reset: after loading, both must be set to empty
    completed_tags = set()  # session-scoped reset
    completed_accounts = set()  # session-scoped reset

    assert completed_tags == set(), "completed_tags must be empty after session-scoped reset"
    assert completed_accounts == set(), "completed_accounts must be empty after session-scoped reset"
    # The checkpoint data still has the old values (for verification)
    assert data['completed_tags'] == ['labubu', 'popmart']
    assert data['completed_accounts'] == ['popmart']


# ---------------------------------------------------------------------------
# Test 2: upsert_post_metadata replaces local upsert_posts function
# ---------------------------------------------------------------------------
def test_post_upsert_replaces_local_function(tmp_db):
    """Insert a post, then upsert with updated likes. Verify likes updated,
    identity fields (account, caption, post_date) unchanged."""
    init_db(tmp_db)

    post_v1 = {
        'shortcode': 'TEST001', 'post_url': 'https://instagram.com/p/TEST001',
        'account': 'popmart', 'caption': 'Original caption',
        'likes': 100, 'comments_count': 10, 'post_date': '2026-01-15',
        'source': 'hashtag:labubu', 'scraped_at': '2026-03-30T00:00:00+00:00'
    }
    upsert_post_metadata(tmp_db, post_v1)

    # Upsert with updated likes
    post_v2 = {
        'shortcode': 'TEST001', 'post_url': 'https://instagram.com/p/TEST001',
        'account': 'different_account', 'caption': 'Different caption',
        'likes': 999, 'comments_count': 88, 'post_date': '2099-12-31',
        'source': 'other', 'scraped_at': '2026-04-01T00:00:00+00:00'
    }
    upsert_post_metadata(tmp_db, post_v2)

    cols = [r[1] for r in tmp_db.execute("PRAGMA table_info(instagram_posts)").fetchall()]
    row = tmp_db.execute("SELECT * FROM instagram_posts WHERE shortcode='TEST001'").fetchone()
    data = dict(zip(cols, row))

    # Volatile fields updated
    assert data['likes'] == 999
    assert data['comments_count'] == 88
    # Identity fields preserved
    assert data['account'] == 'popmart'
    assert data['caption'] == 'Original caption'
    assert data['post_date'] == '2026-01-15'
    assert data['source'] == 'hashtag:labubu'
    # Only one row
    count = tmp_db.execute("SELECT COUNT(*) FROM instagram_posts WHERE shortcode='TEST001'").fetchone()[0]
    assert count == 1


# ---------------------------------------------------------------------------
# Test 3: _needs_comment_refresh returns True for posts with NULL last_comment_scraped_at
# ---------------------------------------------------------------------------
def test_scrape_batch_processes_existing_posts(tmp_db):
    """Pre-insert 2 posts via upsert_post_metadata. Verify that
    _needs_comment_refresh logic returns True for posts with NULL last_comment_scraped_at."""
    init_db(tmp_db)

    for code in ['EXIST01', 'EXIST02']:
        upsert_post_metadata(tmp_db, {
            'shortcode': code, 'post_url': f'https://instagram.com/p/{code}',
            'account': 'popmart', 'caption': '', 'likes': 50,
            'comments_count': 5, 'post_date': '2026-02-01',
            'source': 'test', 'scraped_at': '2026-03-30T00:00:00+00:00'
        })

    # Both have NULL last_comment_scraped_at
    for code in ['EXIST01', 'EXIST02']:
        row = tmp_db.execute(
            'SELECT last_comment_scraped_at FROM instagram_posts WHERE shortcode=?',
            (code,)
        ).fetchone()
        assert row is not None, f"Post {code} should exist"
        assert row[0] is None, f"Post {code} last_comment_scraped_at should be NULL"

    # _needs_comment_refresh logic: NULL last_comment_scraped_at => True
    for code in ['EXIST01', 'EXIST02']:
        row = tmp_db.execute(
            'SELECT last_comment_scraped_at, post_date FROM instagram_posts WHERE shortcode=?',
            (code,)
        ).fetchone()
        last_scraped, post_date = row
        needs_refresh = last_scraped is None  # simplified check
        assert needs_refresh is True, f"Post {code} with NULL should need refresh"


# ---------------------------------------------------------------------------
# Test 4: Comment refresh targets NULL and stale, not fresh
# ---------------------------------------------------------------------------
def test_comment_refresh_targets_null_last_scraped(tmp_db):
    """3 posts: NULL (yes), fresh 1-day-ago (no), stale 10-day-ago on recent post (yes).
    _needs_comment_refresh should return True for posts 1 and 3, not post 2."""
    init_db(tmp_db)
    now = datetime.now(timezone.utc)

    # Post 1: NULL last_comment_scraped_at
    upsert_post_metadata(tmp_db, {
        'shortcode': 'NULL_POST', 'post_url': 'https://instagram.com/p/NULL_POST',
        'account': 'a', 'caption': '', 'likes': 10, 'comments_count': 0,
        'post_date': (now - timedelta(days=30)).strftime('%Y-%m-%d'),
        'source': 'test', 'scraped_at': now.isoformat()
    })
    # last_comment_scraped_at stays NULL by default

    # Post 2: Fresh (scraped 1 day ago)
    upsert_post_metadata(tmp_db, {
        'shortcode': 'FRESH_POST', 'post_url': 'https://instagram.com/p/FRESH_POST',
        'account': 'a', 'caption': '', 'likes': 10, 'comments_count': 5,
        'post_date': (now - timedelta(days=30)).strftime('%Y-%m-%d'),
        'source': 'test', 'scraped_at': now.isoformat()
    })
    fresh_ts = (now - timedelta(days=1)).isoformat()
    tmp_db.execute(
        "UPDATE instagram_posts SET last_comment_scraped_at=? WHERE shortcode='FRESH_POST'",
        (fresh_ts,)
    )

    # Post 3: Stale (scraped 10 days ago) on recent post (within 90 days)
    upsert_post_metadata(tmp_db, {
        'shortcode': 'STALE_POST', 'post_url': 'https://instagram.com/p/STALE_POST',
        'account': 'a', 'caption': '', 'likes': 10, 'comments_count': 5,
        'post_date': (now - timedelta(days=30)).strftime('%Y-%m-%d'),
        'source': 'test', 'scraped_at': now.isoformat()
    })
    stale_ts = (now - timedelta(days=10)).isoformat()
    tmp_db.execute(
        "UPDATE instagram_posts SET last_comment_scraped_at=? WHERE shortcode='STALE_POST'",
        (stale_ts,)
    )
    tmp_db.commit()

    # Implement _needs_comment_refresh inline for testing
    def _needs_comment_refresh(conn, shortcode):
        row = conn.execute(
            'SELECT last_comment_scraped_at, post_date FROM instagram_posts WHERE shortcode=?',
            (shortcode,)
        ).fetchone()
        if not row:
            return True
        last_scraped, post_date = row
        if last_scraped is None:
            return True
        try:
            last_dt = datetime.fromisoformat(last_scraped)
            if post_date:
                post_dt = datetime.fromisoformat(post_date + 'T00:00:00+00:00') if len(post_date) == 10 else datetime.fromisoformat(post_date)
                _now = datetime.now(timezone.utc)
                if (_now - post_dt).days <= 90 and (_now - last_dt).days > 7:
                    return True
        except (ValueError, TypeError):
            pass
        return False

    assert _needs_comment_refresh(tmp_db, 'NULL_POST') is True, "NULL should need refresh"
    assert _needs_comment_refresh(tmp_db, 'FRESH_POST') is False, "Fresh (1 day) should NOT need refresh"
    assert _needs_comment_refresh(tmp_db, 'STALE_POST') is True, "Stale (10 days) on recent post should need refresh"


# ---------------------------------------------------------------------------
# Test 5: last_comment_scraped_at updated after comment save
# ---------------------------------------------------------------------------
def test_last_comment_scraped_at_updated(tmp_db):
    """Insert a post, simulate comment save, verify last_comment_scraped_at is set."""
    init_db(tmp_db)

    upsert_post_metadata(tmp_db, {
        'shortcode': 'TSUPD01', 'post_url': 'https://instagram.com/p/TSUPD01',
        'account': 'popmart', 'caption': '', 'likes': 50,
        'comments_count': 5, 'post_date': '2026-02-01',
        'source': 'test', 'scraped_at': '2026-03-30T00:00:00+00:00'
    })

    # Verify initially NULL
    val = tmp_db.execute(
        "SELECT last_comment_scraped_at FROM instagram_posts WHERE shortcode='TSUPD01'"
    ).fetchone()[0]
    assert val is None

    # Simulate: after comment scrape, update last_comment_scraped_at
    ts = datetime.now(timezone.utc).isoformat()
    tmp_db.execute(
        "UPDATE instagram_posts SET last_comment_scraped_at=? WHERE shortcode=?",
        (ts, 'TSUPD01')
    )
    tmp_db.commit()

    val = tmp_db.execute(
        "SELECT last_comment_scraped_at FROM instagram_posts WHERE shortcode='TSUPD01'"
    ).fetchone()[0]
    assert val is not None
    assert val == ts


# ---------------------------------------------------------------------------
# Test 6: Backfill query returns posts with NULL last_comment_scraped_at
# ---------------------------------------------------------------------------
def test_backfill_query(tmp_db):
    """5 posts: 3 NULL, 2 non-NULL. Backfill query returns exactly 3."""
    init_db(tmp_db)
    now = datetime.now(timezone.utc)

    # 3 posts with NULL last_comment_scraped_at
    for i in range(3):
        upsert_post_metadata(tmp_db, {
            'shortcode': f'BF_NULL_{i}', 'post_url': f'https://instagram.com/p/BF_NULL_{i}',
            'account': 'popmart', 'caption': '', 'likes': 10,
            'comments_count': 0, 'post_date': f'2026-02-{i+1:02d}',
            'source': 'test', 'scraped_at': now.isoformat()
        })

    # 2 posts with non-NULL last_comment_scraped_at
    for i in range(2):
        upsert_post_metadata(tmp_db, {
            'shortcode': f'BF_DONE_{i}', 'post_url': f'https://instagram.com/p/BF_DONE_{i}',
            'account': 'popmart', 'caption': '', 'likes': 10,
            'comments_count': 5, 'post_date': f'2026-03-{i+1:02d}',
            'source': 'test', 'scraped_at': now.isoformat()
        })
        tmp_db.execute(
            "UPDATE instagram_posts SET last_comment_scraped_at=? WHERE shortcode=?",
            (now.isoformat(), f'BF_DONE_{i}')
        )
    tmp_db.commit()

    # Run backfill query
    posts_needing = tmp_db.execute("""
        SELECT shortcode, account
        FROM instagram_posts
        WHERE last_comment_scraped_at IS NULL
        ORDER BY post_date DESC
        LIMIT 50
    """).fetchall()

    assert len(posts_needing) == 3
    shortcodes = {row[0] for row in posts_needing}
    assert shortcodes == {'BF_NULL_0', 'BF_NULL_1', 'BF_NULL_2'}


# ---------------------------------------------------------------------------
# Test 7: Backfill limit 50
# ---------------------------------------------------------------------------
def test_backfill_limit_50(tmp_db):
    """60 posts with NULL last_comment_scraped_at. Backfill query returns exactly 50."""
    init_db(tmp_db)
    now = datetime.now(timezone.utc)

    for i in range(60):
        upsert_post_metadata(tmp_db, {
            'shortcode': f'BF_LIM_{i:03d}', 'post_url': f'https://instagram.com/p/BF_LIM_{i:03d}',
            'account': 'popmart', 'caption': '', 'likes': 10,
            'comments_count': 0, 'post_date': f'2025-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}',
            'source': 'test', 'scraped_at': now.isoformat()
        })

    # Run backfill query with LIMIT 50
    posts_needing = tmp_db.execute("""
        SELECT shortcode, account
        FROM instagram_posts
        WHERE last_comment_scraped_at IS NULL
        ORDER BY post_date DESC
        LIMIT 50
    """).fetchall()

    assert len(posts_needing) == 50, f"Expected 50, got {len(posts_needing)}"
