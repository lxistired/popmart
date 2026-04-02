---
phase: 09-export
plan: 01
subsystem: export-layer
tags: [export, metadata, tdd, per-post-averages]
dependency_graph:
  requires: [07-01]
  provides: [metadata-driven-exports, data-coverage, ugc-amplification]
  affects: [website-charts, analysis-layer]
tech_stack:
  added: []
  patterns: [metadata-driven-metrics, data-confidence-levels, pop-mart-exclusion]
key_files:
  created: []
  modified:
    - phase2_overseas/export_json.py
    - phase2_overseas/tests/test_export_json.py
decisions:
  - "All volume metrics use tiktok_videos.comments_count / instagram_posts.comments_count metadata, never COUNT of comment rows"
  - "Pop Mart brand excluded from IP share calculations (ip_share + ip_share_trend)"
  - "data_confidence derived from sample count n: >=10 high, >=5 medium, <5 low"
  - "export_comment_quality deleted, replaced by export_data_coverage"
  - "UGC amplification only computed for months with both official and UGC data"
  - "Fixed deprecated datetime.utcnow/utcfromtimestamp to timezone-aware equivalents"
metrics:
  duration: 11min
  completed: 2026-04-02
---

# Phase 9 Plan 1: Export Layer Rewrite (Metadata-Driven Per-Post Averages) Summary

All export_json.py functions rewritten to use metadata comments_count (from tiktok_videos and instagram_posts tables) instead of counting comment rows. Added n/data_confidence fields to every monthly data point. Deleted export_comment_quality, added export_data_coverage and export_ugc_amplification. TDD approach: 11 tests failed in RED, all 21 pass in GREEN.

## Task Results

| Task | Name | Commit | Key Changes |
|------|------|--------|-------------|
| 1 | Rewrite tests (TDD RED) | 27d7d21 | test_export_json.py: init_db fixture, new assertions for metadata format, 11 failing tests |
| 2 | Rewrite export functions (TDD GREEN) | 231864e | export_json.py: 8 functions rewritten, 1 deleted, 3 added, all 21 tests pass |

## What Changed

### Functions Rewritten (8)
1. **export_overview** -- Added data_freshness (MAX scraped_at per platform) and coverage dict
2. **export_ip_share** -- SUM(metadata comments_count) per IP, Pop Mart excluded, new key names (tiktok_comments_meta, instagram_comments_meta, total_engagement)
3. **export_tiktok_trend** -- Monthly AVG(comments_count) with n and data_confidence (was weekly COUNT of comment rows)
4. **export_instagram_trend** -- Monthly AVG(comments_count) with n and data_confidence (was weekly COUNT of comment rows)
5. **export_brand_trend** -- avg_comments_per_post replaces density/total_comments, added n and data_confidence
6. **export_ip_share_trend** -- engagement from SUM(metadata comments_count), Pop Mart excluded, 'engagement' replaces 'count'
7. **export_cross_platform_index** -- density = SUM(metadata comments_count) / COUNT(*), not COUNT(comment rows) / COUNT(*)
8. **export_official_engagement** -- metadata-direct queries (no LEFT JOIN on comment tables), added avg_views and avg_likes

### Functions Deleted (1)
- **export_comment_quality** -- Removed entirely (was comment likes tier analysis)

### Functions Added (3)
- **_data_confidence(n)** -- Helper: n>=10 "high", n>=5 "medium", else "low"
- **export_data_coverage(conn)** -- Platform coverage stats (total_posts, date_range, monthly_counts, coverage_pct)
- **export_ugc_amplification(conn)** -- Monthly UGC/official avg_views ratio trend

### write_all Updates
- Removed 'comment-quality.json'
- Added 'data-coverage.json' and 'ugc-amplification.json'
- Sorted export dict keys alphabetically

### Test Changes
- test_db fixture now uses `init_db(conn)` from shared.db for production schema parity
- Added v5 (official 2024-05) and v6 (UGC 2024-03) test data
- All export test assertions rewritten for new output format
- Added test_export_data_coverage, test_export_ugc_amplification, test_no_export_comment_quality
- Deleted test_export_comment_quality
- Total: 21 tests (9 classify_ip + 12 export)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed deprecated datetime usage**
- **Found during:** Task 2
- **Issue:** `datetime.utcnow()` and `datetime.utcfromtimestamp()` are deprecated in Python 3.13
- **Fix:** Replaced with `datetime.now(tz=timezone.utc)` and `datetime.fromtimestamp(ts, tz=timezone.utc)`
- **Files modified:** phase2_overseas/export_json.py
- **Commit:** 231864e

**2. [Rule 2 - Missing] Added v6 test data for UGC amplification coverage**
- **Found during:** Task 1
- **Issue:** Plan specified testing UGC amplification ratio but existing test data had no month with both UGC and official videos (v4 in 2024-03 official, v1/v2/v3 in 2024-04 UGC)
- **Fix:** Added v6 (UGC, Labubu, 2024-03) so amplification_ratio can be calculated for 2024-03
- **Files modified:** phase2_overseas/tests/test_export_json.py
- **Commit:** 27d7d21

## Verification Results

- `python -m pytest tests/test_export_json.py -v`: 21 passed, 0 failed
- `python -m pytest tests/ -v`: 68 passed, 2 pre-existing failures in test_instagram_ts.py (unrelated)
- `grep -c "comment_quality" export_json.py`: 0 references
- `grep -c "comments_count" export_json.py`: 47 metadata column references
- Pop Mart exclusion confirmed in export_ip_share and export_ip_share_trend

## Known Stubs

None. All functions are fully implemented with real SQL queries against production schema.

## Self-Check: PASSED

- FOUND: phase2_overseas/export_json.py
- FOUND: phase2_overseas/tests/test_export_json.py
- FOUND: .planning/phases/09-export/09-01-SUMMARY.md
- FOUND: commit 27d7d21 (Task 1 RED)
- FOUND: commit 231864e (Task 2 GREEN)
