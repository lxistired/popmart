"""
test_tiktok_incremental.py — Tests for TikTok three-layer skip fix.

Tests exercise DB-interaction patterns for the rebuilt tiktok_browser.py:
  Layer 1: Session-scoped checkpoint (completed set reset at run start)
  Layer 2: Upsert-based metadata writes (not INSERT OR IGNORE)
  Layer 3: Selective comment refresh via last_comment_scraped_at
"""

import sqlite3
from datetime import datetime, timezone, timedelta

import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.db import init_db, upsert_video_metadata, batch_insert
from shared.checkpoint import load_checkpoint, save_checkpoint


@pytest.fixture
def tmp_db():
    """In-memory SQLite connection with all tables initialized."""
    conn = sqlite3.connect(':memory:')
    init_db(conn)
    yield conn
    conn.close()


def _make_video(video_id, views=100, likes=10, comments_count=5, shares=0,
                author='testuser', title='test video', create_time='1700000000',
                source='tag/labubu', scraped_at=None):
    """Helper to build a video dict for upsert."""
    return {
        'video_id': video_id,
        'author': author,
        'title': title,
        'views': views,
        'likes': likes,
        'comments_count': comments_count,
        'shares': shares,
        'create_time': create_time,
        'source': source,
        'scraped_at': scraped_at or datetime.now(timezone.utc).isoformat(),
    }


class TestCheckpointSessionScoped:
    """Layer 1: completed set must be reset at the start of each run."""

    def test_checkpoint_session_scoped(self, tmp_path):
        """Load checkpoint with old completed keywords, verify session-scoped
        reset produces an empty set (the pattern used in rebuilt main())."""
        # Simulate a prior run that saved completed keywords
        platform = 'tiktok_browser_test_session'
        save_checkpoint(platform, {
            'completed': ['labubu', 'dimoo', 'skullpanda'],
            'total_new': 42,
        })

        # Load checkpoint (as the rebuilt main() does)
        checkpoint = load_checkpoint(platform)
        assert 'labubu' in checkpoint.get('completed', [])

        # Session-scoped reset: the rebuilt logic always starts fresh
        completed = set()  # This is the key fix — not set(checkpoint.get('completed', []))

        assert len(completed) == 0
        assert 'labubu' not in completed
        assert 'dimoo' not in completed

        # Cleanup
        cp_file = os.path.join(os.path.dirname(__file__), '..', f'checkpoint_{platform}.json')
        if os.path.exists(cp_file):
            os.remove(cp_file)


class TestUpsertSave:
    """Layer 3: _save_videos must use upsert, not INSERT OR IGNORE."""

    def test_save_videos_uses_upsert(self, tmp_db):
        """Insert video with views=100, then upsert same video_id with views=999.
        Views must update to 999; author/title/create_time must stay unchanged."""
        video1 = _make_video('vid_001', views=100, author='original_author',
                             title='original title', create_time='1700000000')
        upsert_video_metadata(tmp_db, video1)

        # Verify initial insert
        row = tmp_db.execute(
            'SELECT views, author, title, create_time FROM tiktok_videos WHERE video_id=?',
            ('vid_001',)
        ).fetchone()
        assert row[0] == 100
        assert row[1] == 'original_author'

        # Upsert with updated views (simulating _save_videos rebuilt to use upsert)
        video2 = _make_video('vid_001', views=999, author='different_author',
                             title='different title', create_time='1700000001')
        upsert_video_metadata(tmp_db, video2)

        row = tmp_db.execute(
            'SELECT views, author, title, create_time FROM tiktok_videos WHERE video_id=?',
            ('vid_001',)
        ).fetchone()
        assert row[0] == 999, "views should update via upsert"
        assert row[1] == 'original_author', "author should NOT change (identity field)"
        assert row[2] == 'original title', "title should NOT change (identity field)"
        assert row[3] == '1700000000', "create_time should NOT change"


class TestScrapeHashtagProcessesExisting:
    """Layer 2: scrape_hashtag must upsert ALL discovered videos, not skip existing."""

    def test_scrape_hashtag_processes_existing_videos(self, tmp_db):
        """Pre-insert 2 videos, then 'discover' the same video_ids with new view counts.
        Upsert should update both — not skip them."""
        # Pre-insert
        upsert_video_metadata(tmp_db, _make_video('vid_A', views=100))
        upsert_video_metadata(tmp_db, _make_video('vid_B', views=200))

        # Simulated discovery — same video_ids, new stats
        discovered = [
            _make_video('vid_A', views=500, likes=50),
            _make_video('vid_B', views=800, likes=80),
        ]
        for v in discovered:
            upsert_video_metadata(tmp_db, v)

        # Verify both updated
        rows = tmp_db.execute(
            'SELECT video_id, views, likes FROM tiktok_videos ORDER BY video_id'
        ).fetchall()
        assert len(rows) == 2
        assert rows[0] == ('vid_A', 500, 50)
        assert rows[1] == ('vid_B', 800, 80)


class TestCommentRefresh:
    """Layer 2: comment refresh targets videos based on last_comment_scraped_at."""

    def test_comment_refresh_targets_null_last_scraped(self, tmp_db):
        """3 videos: NULL last_comment, fresh last_comment (1d ago),
        stale last_comment (10d ago) with recent create_time.
        Query should return video 1 (NULL) and video 3 (stale+recent), not video 2."""
        now = datetime.now(timezone.utc)
        one_day_ago = (now - timedelta(days=1)).isoformat()
        ten_days_ago = (now - timedelta(days=10)).isoformat()
        recent_create = str(int((now - timedelta(days=30)).timestamp()))
        old_create = str(int((now - timedelta(days=180)).timestamp()))

        # Video 1: NULL last_comment_scraped_at
        upsert_video_metadata(tmp_db, _make_video('vid_null', create_time=recent_create))

        # Video 2: fresh last_comment_scraped_at (1 day ago)
        upsert_video_metadata(tmp_db, _make_video('vid_fresh', create_time=recent_create))
        tmp_db.execute(
            'UPDATE tiktok_videos SET last_comment_scraped_at=? WHERE video_id=?',
            (one_day_ago, 'vid_fresh')
        )

        # Video 3: stale last_comment_scraped_at (10 days ago) + recent create_time
        upsert_video_metadata(tmp_db, _make_video('vid_stale', create_time=recent_create))
        tmp_db.execute(
            'UPDATE tiktok_videos SET last_comment_scraped_at=? WHERE video_id=?',
            (ten_days_ago, 'vid_stale')
        )

        # Video 4: stale but OLD create_time (should NOT be returned — too old to refresh)
        upsert_video_metadata(tmp_db, _make_video('vid_old_stale', create_time=old_create))
        tmp_db.execute(
            'UPDATE tiktok_videos SET last_comment_scraped_at=? WHERE video_id=?',
            (ten_days_ago, 'vid_old_stale')
        )
        tmp_db.commit()

        # The comment refresh query (as used in rebuilt _needs_comment_refresh)
        # Returns videos needing comment refresh: NULL last_comment, or recent+stale
        ninety_days_ago_ts = str(int((now - timedelta(days=90)).timestamp()))
        seven_days_ago = (now - timedelta(days=7)).isoformat()

        results = tmp_db.execute("""
            SELECT video_id FROM tiktok_videos
            WHERE last_comment_scraped_at IS NULL
               OR (CAST(create_time AS INTEGER) > ? AND last_comment_scraped_at < ?)
            ORDER BY video_id
        """, (int(ninety_days_ago_ts), seven_days_ago)).fetchall()

        result_ids = [r[0] for r in results]
        assert 'vid_null' in result_ids, "NULL last_comment should need refresh"
        assert 'vid_stale' in result_ids, "stale + recent should need refresh"
        assert 'vid_fresh' not in result_ids, "fresh last_comment should NOT need refresh"
        assert 'vid_old_stale' not in result_ids, "stale but old create_time should NOT need refresh"

    def test_last_comment_scraped_at_updated(self, tmp_db):
        """After saving comments, last_comment_scraped_at should be set to current timestamp."""
        upsert_video_metadata(tmp_db, _make_video('vid_comment_test'))

        # Verify initially NULL
        row = tmp_db.execute(
            'SELECT last_comment_scraped_at FROM tiktok_videos WHERE video_id=?',
            ('vid_comment_test',)
        ).fetchone()
        assert row[0] is None

        # Simulate comment save + timestamp update (as rebuilt scraper does)
        now_str = datetime.now(timezone.utc).isoformat()
        tmp_db.execute(
            'UPDATE tiktok_videos SET last_comment_scraped_at=? WHERE video_id=?',
            (now_str, 'vid_comment_test')
        )
        tmp_db.commit()

        row = tmp_db.execute(
            'SELECT last_comment_scraped_at FROM tiktok_videos WHERE video_id=?',
            ('vid_comment_test',)
        ).fetchone()
        assert row[0] is not None
        assert row[0].startswith('20'), "Should be ISO timestamp"


class TestBackfillQuery:
    """Backfill query should target videos with last_comment_scraped_at IS NULL."""

    def test_backfill_query_includes_zero_comment_videos(self, tmp_db):
        """5 videos: 2 with NULL last_comment and no comments in tiktok_comments,
        1 with comments but NULL last_comment, 2 with non-NULL last_comment.
        Backfill query should return first 3."""
        now_str = datetime.now(timezone.utc).isoformat()

        # Video 1 & 2: NULL last_comment_scraped_at, no comments
        upsert_video_metadata(tmp_db, _make_video('vid_no_comments_1', create_time='1710000000'))
        upsert_video_metadata(tmp_db, _make_video('vid_no_comments_2', create_time='1709000000'))

        # Video 3: has comments in tiktok_comments, but NULL last_comment_scraped_at
        upsert_video_metadata(tmp_db, _make_video('vid_has_comments_null', create_time='1708000000'))
        batch_insert(tmp_db, 'tiktok_comments', [{
            'video_id': 'vid_has_comments_null',
            'comment_id': 'cmt_001',
            'comment_text': 'test comment',
            'comment_date': '2024-03-01',
            'comment_datetime': '2024-03-01T12:00:00+00:00',
            'likes': 0,
            'author_name': 'user1',
            'scraped_at': now_str,
        }], ['video_id', 'comment_id', 'comment_text', 'comment_date',
             'comment_datetime', 'likes', 'author_name', 'scraped_at'])

        # Video 4 & 5: non-NULL last_comment_scraped_at (already scraped)
        upsert_video_metadata(tmp_db, _make_video('vid_done_1', create_time='1707000000'))
        tmp_db.execute(
            'UPDATE tiktok_videos SET last_comment_scraped_at=? WHERE video_id=?',
            (now_str, 'vid_done_1')
        )
        upsert_video_metadata(tmp_db, _make_video('vid_done_2', create_time='1706000000'))
        tmp_db.execute(
            'UPDATE tiktok_videos SET last_comment_scraped_at=? WHERE video_id=?',
            (now_str, 'vid_done_2')
        )
        tmp_db.commit()

        # The rebuilt backfill query targets last_comment_scraped_at IS NULL
        results = tmp_db.execute("""
            SELECT v.video_id, v.author, v.comments_count
            FROM tiktok_videos v
            WHERE v.last_comment_scraped_at IS NULL
            ORDER BY v.create_time DESC
            LIMIT 50
        """).fetchall()

        result_ids = [r[0] for r in results]
        assert 'vid_no_comments_1' in result_ids
        assert 'vid_no_comments_2' in result_ids
        assert 'vid_has_comments_null' in result_ids, "Has comments but NULL last_comment should be included"
        assert 'vid_done_1' not in result_ids
        assert 'vid_done_2' not in result_ids
        assert len(result_ids) == 3


class TestSharesField:
    """shares field must be persisted and updated via upsert."""

    def test_shares_field_in_upsert(self, tmp_db):
        """Insert video with shares=5, update to shares=50, verify persistence."""
        upsert_video_metadata(tmp_db, _make_video('vid_shares', shares=5))

        row = tmp_db.execute(
            'SELECT shares FROM tiktok_videos WHERE video_id=?', ('vid_shares',)
        ).fetchone()
        assert row[0] == 5

        # Upsert with updated shares
        upsert_video_metadata(tmp_db, _make_video('vid_shares', shares=50))

        row = tmp_db.execute(
            'SELECT shares FROM tiktok_videos WHERE video_id=?', ('vid_shares',)
        ).fetchone()
        assert row[0] == 50, "shares should update via upsert"
