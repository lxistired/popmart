---
phase: 08-scrapers
plan: 02
subsystem: scraper
tags: [instagram, drissionpage, incremental, backfill, upsert, sqlite]

# Dependency graph
requires:
  - phase: 07-schema
    provides: upsert_post_metadata, init_db(conn=None), last_comment_scraped_at column
provides:
  - Session-scoped checkpoint reset for Instagram scraper
  - _needs_comment_refresh() helper for comment staleness detection
  - backfill_comments() function for zero-comment posts (SCRP-01)
  - Per-post immediate save pattern (no batch accumulation)
affects: [08-scrapers, 09-charts, 11-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns: [session-scoped-checkpoint, needs-comment-refresh, per-post-upsert-then-update]

key-files:
  created:
    - phase2_overseas/tests/test_instagram_incremental.py
  modified:
    - phase2_overseas/instagram_browser.py

key-decisions:
  - "Per-post immediate save replaces batch accumulation to prevent data loss on crash"
  - "Session-scoped checkpoint: completed_tags/accounts reset to empty each run, checkpoint only used for crash recovery"
  - "_needs_comment_refresh uses 90-day recency + 7-day staleness window for comment re-scraping"

patterns-established:
  - "Session-scoped checkpoint: load checkpoint for crash recovery, but reset completed sets at run start"
  - "_needs_comment_refresh(conn, shortcode): NULL -> True, stale+recent -> True, fresh -> False"
  - "Per-post save: upsert_post_metadata + batch_insert comments + UPDATE last_comment_scraped_at immediately"

requirements-completed: [INFRA-12, INFRA-13, INFRA-14, SCRP-01, SCRP-03]

# Metrics
duration: 6min
completed: 2026-04-02
---

# Phase 8 Plan 2: Instagram Three-Layer Skip Fix + Comment Backfill Summary

**Rebuilt instagram_browser.py with session-scoped checkpoint, comment refresh targeting via _needs_comment_refresh(), shared upsert_post_metadata, and backfill_comments() for 60 zero-comment posts**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-02T05:46:55Z
- **Completed:** 2026-04-02T05:53:33Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Fixed all three skip layers in Instagram scraper: checkpoint no longer permanently skips tags/accounts, existing posts with NULL comments get re-visited, shared upsert replaces local INSERT OR REPLACE
- Added _needs_comment_refresh() with 90-day recency + 7-day staleness window for intelligent comment re-scraping
- Added backfill_comments() function targeting posts with last_comment_scraped_at IS NULL, limited to 50 per run (SCRP-01)
- Replaced batch accumulation pattern with per-post immediate save to prevent data loss on crash
- 7 new tests covering all three layers + backfill logic, all passing alongside 19 existing DB tests

## Task Commits

Each task was committed atomically:

1. **Task 1: Write tests for Instagram three-layer skip fix** - `84abef5` (test)
2. **Task 2: Rebuild instagram_browser.py with three-layer fix + backfill** - `bbba144` (feat)

## Files Created/Modified
- `phase2_overseas/tests/test_instagram_incremental.py` - 7 tests for checkpoint reset, upsert replacement, comment refresh targeting, backfill query + limit
- `phase2_overseas/instagram_browser.py` - Rebuilt with session-scoped checkpoint, _needs_comment_refresh(), backfill_comments(), shared upsert_post_metadata

## Decisions Made
- Per-post immediate save replaces batch-every-5 accumulation pattern: upsert_post_metadata + batch_insert comments + UPDATE last_comment_scraped_at happen immediately after each post scrape, preventing data loss on crash/interrupt
- Session-scoped checkpoint: completed_tags and completed_accounts are reset to empty sets at each run start; checkpoint file is still saved during the run for crash recovery within a session
- _needs_comment_refresh window: posts within 90 days get re-scraped if last comment scrape was > 7 days ago; posts older than 90 days only get scraped if last_comment_scraped_at is NULL

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- 2 pre-existing test failures in test_instagram_ts.py (test_session_load_no_network, test_delay_range_set) are unrelated to this plan's changes -- they test the legacy instagram_ts.py module. Not fixed per scope boundary rule.

## Known Stubs

None - all functions are fully wired to real data sources.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Instagram scraper is now fully incremental: re-discovers posts on every run, refreshes stale comments, backfills zero-comment posts
- Ready for daily pipeline execution (Phase 11)
- backfill_comments() will process the 60 historically zero-comment posts over 2 runs (50 per run limit)

## Self-Check: PASSED

- All 2 created/modified files exist on disk
- Both task commits (84abef5, bbba144) found in git log
- 7 new tests pass, 19 existing DB tests pass

---
*Phase: 08-scrapers*
*Completed: 2026-04-02*
