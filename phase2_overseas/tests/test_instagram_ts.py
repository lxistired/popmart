"""
tests/test_instagram_ts.py — TDD tests for instagram_ts.py (Phase 2)
Tests use mocked instagrapi.Client — NO real API calls.
API_LIMIT = 1900 (user approved 2000/day with 100 buffer)
"""

import sqlite3
import sys
import os
from datetime import datetime
from unittest.mock import MagicMock, patch, call


def _setup_ig_tables(conn):
    """Create instagram_posts + instagram_comments tables with full schema (including UNIQUE indexes)."""
    conn.execute("""CREATE TABLE IF NOT EXISTS instagram_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shortcode TEXT UNIQUE,
        post_url TEXT,
        account TEXT,
        caption TEXT,
        likes INTEGER,
        comments_count INTEGER,
        post_date TEXT,
        source TEXT,
        scraped_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS instagram_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shortcode TEXT NOT NULL,
        comment_id TEXT,
        comment_text TEXT,
        comment_date TEXT,
        comment_datetime TEXT,
        likes INTEGER DEFAULT 0,
        author_name TEXT,
        is_author_reply INTEGER DEFAULT 0,
        scraped_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_ig_comment
                    ON instagram_comments(shortcode, comment_id)""")
    conn.commit()


def _make_media(code='ABC123', pk=111111, caption='test post', like_count=100,
                comment_count=5, taken_at=None):
    """Build a mock instagrapi Media object."""
    m = MagicMock()
    m.code = code
    m.pk = pk
    m.caption_text = caption
    m.like_count = like_count
    m.comment_count = comment_count
    m.taken_at = taken_at or datetime(2025, 6, 15, 0, 0, 0)
    return m


def _make_comment(pk='18192358901234567', text='nice!', created_at_utc=None,
                  like_count=0, username='testuser'):
    """Build a mock instagrapi Comment object."""
    c = MagicMock()
    c.pk = pk
    c.text = text
    c.created_at_utc = created_at_utc or datetime(2025, 6, 15, 10, 30, 0)
    c.like_count = like_count
    c.user = MagicMock()
    c.user.username = username
    return c


# ---------------------------------------------------------------------------
# Test 1: Session load does NOT call login(), sets user_id from load_settings
# ---------------------------------------------------------------------------
def test_session_load_no_network():
    """After load_settings(), cl.user_id is set; login() is NOT called."""
    from instagram_ts import init_client

    mock_client_instance = MagicMock()
    mock_client_instance.user_id = None

    def set_user_id_side_effect(path):
        mock_client_instance.user_id = '67890'

    mock_client_instance.load_settings.side_effect = set_user_id_side_effect

    with patch('instagram_ts.Client', return_value=mock_client_instance) as MockClient:
        with patch('instagram_ts.SESSION_FILE', '/fake/session.json'):
            result = init_client('/fake/session.json')

    mock_client_instance.load_settings.assert_called_once()
    mock_client_instance.login.assert_not_called()
    assert mock_client_instance.user_id == '67890'


# ---------------------------------------------------------------------------
# Test 2: Comment date mapping — created_at_utc -> comment_date + comment_datetime
# ---------------------------------------------------------------------------
def test_comment_date_mapping():
    """Given a Comment with created_at_utc=datetime(2025,6,15,10,30,0),
    map_comment_row() produces comment_date='2025-06-15' and comment_datetime containing that date."""
    from instagram_ts import map_comment_row

    comment = _make_comment(
        pk='18192358901234567',
        text='great!',
        created_at_utc=datetime(2025, 6, 15, 10, 30, 0),
        like_count=3,
        username='testuser'
    )
    row = map_comment_row(comment, shortcode='ABC123', username='popmart')

    assert row['comment_date'] == '2025-06-15', f"Expected '2025-06-15', got {row['comment_date']!r}"
    assert '2025-06-15T10:30:00' in row['comment_datetime'], (
        f"Expected ISO datetime containing '2025-06-15T10:30:00', got {row['comment_datetime']!r}"
    )
    assert row['comment_id'] == '18192358901234567'
    assert row['shortcode'] == 'ABC123'
    assert row['author_name'] == 'testuser'


# ---------------------------------------------------------------------------
# Test 3: API counter stops at 1900
# ---------------------------------------------------------------------------
def test_api_counter_stops_at_1900(tmp_db):
    """Mock client returning 12 medias per page; after counter reaches 1900,
    scrape_account() stops without fetching more pages."""
    _setup_ig_tables(tmp_db)

    from instagram_ts import scrape_account
    import instagram_ts

    mock_cl = MagicMock()
    mock_cl.user_id_from_username.return_value = 12345

    # Each paginated call returns 12 medias with a non-empty end_cursor (endless pages)
    media_batch = [_make_media(code=f'POST{i}', pk=i) for i in range(12)]
    mock_cl.user_medias_paginated.return_value = (media_batch, 'next_cursor')
    mock_cl.media_comments.return_value = []

    logger = MagicMock()
    api_counter = {'count': 1895}  # Already near limit

    cfg_account = {'username': 'popmart', 'label': 'official'}
    cfg = {
        'since_date': '2024-01-01',
        'max_posts_per_account': 50,
        'max_comments_per_post': 500,
    }
    checkpoint_state = {
        'completed_accounts': [],
        'in_progress': None,
        'api_calls_today': 1895,
        'last_run_date': '2026-03-28',
    }

    with patch.object(instagram_ts, 'API_LIMIT', 1900):
        with patch('instagram_ts.save_checkpoint') as mock_save:
            scrape_account(mock_cl, tmp_db, logger, api_counter, cfg_account, cfg, checkpoint_state)

    # With counter starting at 1895, at most a few calls before hitting 1900
    # The key assertion: paginated calls stop well before 50 posts (max_posts_per_account)
    total_paginated_calls = mock_cl.user_medias_paginated.call_count
    # 1 user_id_from_username call + limited paginated calls; should not fetch many pages
    assert api_counter['count'] >= 1900 or total_paginated_calls <= 3, (
        f"Expected scraping to stop near 1900 limit, got {api_counter['count']} calls, "
        f"{total_paginated_calls} paginated calls"
    )


# ---------------------------------------------------------------------------
# Test 4: delay_range is set to [1, 3]
# ---------------------------------------------------------------------------
def test_delay_range_set():
    """After init_client(), cl.delay_range == [1, 3] (IG-04 rate limit)."""
    from instagram_ts import init_client

    mock_client_instance = MagicMock()
    mock_client_instance.user_id = None

    def set_user_id_side_effect(path):
        mock_client_instance.user_id = '67890'

    mock_client_instance.load_settings.side_effect = set_user_id_side_effect

    with patch('instagram_ts.Client', return_value=mock_client_instance):
        with patch('instagram_ts.SESSION_FILE', '/fake/session.json'):
            init_client('/fake/session.json')

    # Verify delay_range was set to [1, 3]
    assert mock_client_instance.delay_range == [1, 3], (
        f"Expected delay_range [1, 3], got {mock_client_instance.delay_range!r}"
    )


# ---------------------------------------------------------------------------
# Test 5: scrape_comments_writes_rows — 2 posts × 3 comments = 6 rows in DB
# ---------------------------------------------------------------------------
def test_scrape_comments_writes_rows(tmp_db):
    """Mock client returning 2 posts with 3 comments each; after scrape_account(),
    instagram_comments table has 6 rows with non-null comment_date."""
    _setup_ig_tables(tmp_db)

    from instagram_ts import scrape_account
    import instagram_ts

    mock_cl = MagicMock()
    mock_cl.user_id_from_username.return_value = 12345

    posts = [
        _make_media(code='POST_A', pk=1001),
        _make_media(code='POST_B', pk=1002),
    ]
    # Empty end_cursor means no more pages
    mock_cl.user_medias_paginated.return_value = (posts, '')

    comments_a = [
        _make_comment(pk=f'1000{i}', text=f'comment {i}', username='user1')
        for i in range(3)
    ]
    comments_b = [
        _make_comment(pk=f'2000{i}', text=f'comment {i}', username='user2')
        for i in range(3)
    ]
    mock_cl.media_comments.side_effect = [comments_a, comments_b]

    logger = MagicMock()
    api_counter = {'count': 0}
    cfg_account = {'username': 'popmart', 'label': 'official'}
    cfg = {
        'since_date': '2024-01-01',
        'max_posts_per_account': 50,
        'max_comments_per_post': 500,
    }
    checkpoint_state = {
        'completed_accounts': [],
        'in_progress': None,
        'api_calls_today': 0,
        'last_run_date': '2026-03-28',
    }

    with patch.object(instagram_ts, 'API_LIMIT', 1900):
        scrape_account(mock_cl, tmp_db, logger, api_counter, cfg_account, cfg, checkpoint_state)

    rows = tmp_db.execute(
        "SELECT comment_date FROM instagram_comments"
    ).fetchall()
    assert len(rows) == 6, f"Expected 6 rows, got {len(rows)}"
    for (comment_date,) in rows:
        assert comment_date is not None, "comment_date should not be NULL"
        assert len(comment_date) == 10, f"comment_date should be YYYY-MM-DD, got {comment_date!r}"


# ---------------------------------------------------------------------------
# Test 6: No duplicates on rerun — INSERT OR IGNORE works
# ---------------------------------------------------------------------------
def test_no_duplicates_on_rerun(tmp_db):
    """Run scrape_account() twice with same mock data; instagram_comments table
    still has same row count (INSERT OR IGNORE with UNIQUE constraint)."""
    _setup_ig_tables(tmp_db)

    from instagram_ts import scrape_account
    import instagram_ts

    mock_cl = MagicMock()
    mock_cl.user_id_from_username.return_value = 12345

    post = _make_media(code='POST_X', pk=9001)
    mock_cl.user_medias_paginated.return_value = ([post], '')

    comments = [_make_comment(pk='777001', username='alice')]
    mock_cl.media_comments.return_value = comments

    logger = MagicMock()
    cfg_account = {'username': 'popmart', 'label': 'official'}
    cfg = {
        'since_date': '2024-01-01',
        'max_posts_per_account': 50,
        'max_comments_per_post': 500,
    }
    checkpoint_state = {
        'completed_accounts': [],
        'in_progress': None,
        'api_calls_today': 0,
        'last_run_date': '2026-03-28',
    }

    with patch.object(instagram_ts, 'API_LIMIT', 1900):
        api_counter = {'count': 0}
        scrape_account(mock_cl, tmp_db, logger, api_counter, cfg_account, cfg, checkpoint_state)

        count_after_first = tmp_db.execute(
            "SELECT COUNT(*) FROM instagram_comments"
        ).fetchone()[0]

        api_counter = {'count': 0}
        scrape_account(mock_cl, tmp_db, logger, api_counter, cfg_account, cfg, checkpoint_state)

        count_after_second = tmp_db.execute(
            "SELECT COUNT(*) FROM instagram_comments"
        ).fetchone()[0]

    assert count_after_first == count_after_second, (
        f"Expected same count after rerun, got {count_after_first} then {count_after_second}"
    )
    assert count_after_first == 1, f"Expected 1 comment row, got {count_after_first}"


# ---------------------------------------------------------------------------
# Test 7: Incremental skip — comments older than cutoff date are not inserted
# ---------------------------------------------------------------------------
def test_incremental_skip(tmp_db):
    """Insert a comment with comment_date='2025-06-01' for shortcode X;
    on next scrape, comments before 2025-06-01 for shortcode X are filtered out."""
    _setup_ig_tables(tmp_db)

    # Pre-insert a comment at 2025-06-01
    tmp_db.execute("""
        INSERT INTO instagram_comments
        (shortcode, comment_id, comment_text, comment_date, comment_datetime, likes, author_name, scraped_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, ('POST_INCR', 'old_comment_001', 'old comment', '2025-06-01',
          '2025-06-01T00:00:00', 0, 'olduser', '2026-01-01T00:00:00'))
    tmp_db.commit()

    from instagram_ts import scrape_account
    import instagram_ts

    mock_cl = MagicMock()
    mock_cl.user_id_from_username.return_value = 12345

    post = _make_media(code='POST_INCR', pk=8888)
    mock_cl.user_medias_paginated.return_value = ([post], '')

    # Two comments: one old (before cutoff), one new (after cutoff)
    old_comment = _make_comment(
        pk='OLD001',
        text='old comment',
        created_at_utc=datetime(2025, 5, 1, 0, 0, 0)  # Before cutoff 2025-06-01
    )
    new_comment = _make_comment(
        pk='NEW001',
        text='new comment',
        created_at_utc=datetime(2025, 7, 1, 0, 0, 0)  # After cutoff
    )
    mock_cl.media_comments.return_value = [old_comment, new_comment]

    logger = MagicMock()
    api_counter = {'count': 0}
    cfg_account = {'username': 'popmart', 'label': 'official'}
    cfg = {
        'since_date': '2024-01-01',
        'max_posts_per_account': 50,
        'max_comments_per_post': 500,
    }
    checkpoint_state = {
        'completed_accounts': [],
        'in_progress': None,
        'api_calls_today': 0,
        'last_run_date': '2026-03-28',
    }

    with patch.object(instagram_ts, 'API_LIMIT', 1900):
        scrape_account(mock_cl, tmp_db, logger, api_counter, cfg_account, cfg, checkpoint_state)

    rows = tmp_db.execute(
        "SELECT comment_id, comment_date FROM instagram_comments WHERE shortcode='POST_INCR'"
    ).fetchall()
    comment_ids = {r[0] for r in rows}

    # NEW001 (2025-07-01) should be inserted; OLD001 (2025-05-01) should be filtered out
    assert 'NEW001' in comment_ids, f"Expected NEW001 to be inserted, got {comment_ids}"
    assert 'OLD001' not in comment_ids, f"Expected OLD001 to be filtered (before cutoff), got {comment_ids}"


# ---------------------------------------------------------------------------
# Test 8: Checkpoint saved when API limit hit mid-account
# ---------------------------------------------------------------------------
def test_checkpoint_saves_on_api_limit(tmp_db):
    """When api_counter hits 1900 mid-account, checkpoint is saved with in_progress state."""
    _setup_ig_tables(tmp_db)

    from instagram_ts import scrape_account
    import instagram_ts

    mock_cl = MagicMock()
    mock_cl.user_id_from_username.return_value = 12345

    media_batch = [_make_media(code=f'POST{i}', pk=i) for i in range(12)]
    mock_cl.user_medias_paginated.return_value = (media_batch, 'next_cursor')
    mock_cl.media_comments.return_value = []

    logger = MagicMock()
    # Start right at limit so first paginated call triggers stop
    api_counter = {'count': 1899}

    cfg_account = {'username': 'popmart', 'label': 'official'}
    cfg = {
        'since_date': '2024-01-01',
        'max_posts_per_account': 50,
        'max_comments_per_post': 500,
    }
    checkpoint_state = {
        'completed_accounts': [],
        'in_progress': None,
        'api_calls_today': 1899,
        'last_run_date': '2026-03-28',
    }

    with patch.object(instagram_ts, 'API_LIMIT', 1900):
        with patch('instagram_ts.save_checkpoint') as mock_save:
            scrape_account(mock_cl, tmp_db, logger, api_counter, cfg_account, cfg, checkpoint_state)

    # save_checkpoint should have been called
    assert mock_save.called, "Expected save_checkpoint to be called when API limit hit"
    # The saved state should have in_progress with 'account' == 'popmart'
    saved_state = mock_save.call_args[0][1]
    assert saved_state.get('in_progress') is not None or saved_state.get('api_calls_today', 0) >= 1900, (
        f"Expected checkpoint to record API limit state, got: {saved_state}"
    )


# ---------------------------------------------------------------------------
# Test 9: Post upsert fills NULL metadata (INSERT OR REPLACE)
# ---------------------------------------------------------------------------
def test_posts_upsert_fills_null_metadata(tmp_db):
    """Insert a post with shortcode='ABC' and NULL post_date;
    after scrape with mock media having taken_at, the row has non-NULL post_date."""
    _setup_ig_tables(tmp_db)

    # Pre-insert a post with NULL metadata (simulating old Playwright scrape)
    tmp_db.execute("""
        INSERT INTO instagram_posts
        (shortcode, post_url, account, caption, likes, comments_count, post_date, source, scraped_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ('UPSERT_TEST', 'https://www.instagram.com/p/UPSERT_TEST/', 'popmart',
          '', None, None, None, 'playwright', '2025-01-01T00:00:00'))
    tmp_db.commit()

    from instagram_ts import scrape_account, upsert_posts
    import instagram_ts

    mock_cl = MagicMock()
    mock_cl.user_id_from_username.return_value = 12345

    post = _make_media(
        code='UPSERT_TEST',
        pk=5555,
        caption='Pop Mart post',
        like_count=200,
        comment_count=10,
        taken_at=datetime(2025, 8, 20, 12, 0, 0)
    )
    mock_cl.user_medias_paginated.return_value = ([post], '')
    mock_cl.media_comments.return_value = []

    logger = MagicMock()
    api_counter = {'count': 0}
    cfg_account = {'username': 'popmart', 'label': 'official'}
    cfg = {
        'since_date': '2024-01-01',
        'max_posts_per_account': 50,
        'max_comments_per_post': 500,
    }
    checkpoint_state = {
        'completed_accounts': [],
        'in_progress': None,
        'api_calls_today': 0,
        'last_run_date': '2026-03-28',
    }

    with patch.object(instagram_ts, 'API_LIMIT', 1900):
        scrape_account(mock_cl, tmp_db, logger, api_counter, cfg_account, cfg, checkpoint_state)

    row = tmp_db.execute(
        "SELECT post_date, likes, comments_count FROM instagram_posts WHERE shortcode='UPSERT_TEST'"
    ).fetchone()
    assert row is not None, "Expected row to exist after upsert"
    post_date, likes, comments_count = row
    assert post_date == '2025-08-20', f"Expected post_date='2025-08-20', got {post_date!r}"
    assert likes == 200, f"Expected likes=200, got {likes!r}"
    assert comments_count == 10, f"Expected comments_count=10, got {comments_count!r}"
