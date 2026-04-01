"""
db_migrate.py — Add missing UNIQUE indexes to overseas_data.db time-series tables.
Run once during Phase 1 setup. Safe to re-run (all operations are IF NOT EXISTS).

Auto-fix: instagram_comments rows with empty comment_id get a synthetic ID
derived from (shortcode, comment_datetime, rowid) to enable UNIQUE index creation
while preserving all existing timestamp data.
"""
import sys
import os
import hashlib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from shared.db import get_conn, ensure_unique_indexes


def fix_empty_comment_ids(conn):
    """Assign synthetic comment_ids to instagram_comments rows where comment_id is empty.

    These rows were created by a prior Playwright scrape that captured timestamps
    but not comment IDs. We derive a deterministic synthetic ID so the UNIQUE
    index on (shortcode, comment_id) can be applied without losing any data.

    Synthetic ID format: 'synth_<sha1(shortcode+comment_datetime+rowid)[:12]>'
    """
    empty_rows = conn.execute(
        "SELECT id, shortcode, comment_datetime FROM instagram_comments WHERE comment_id = ''"
    ).fetchall()

    if not empty_rows:
        print("[OK] No empty comment_ids in instagram_comments — no fix needed")
        return 0

    print(f"[INFO] Found {len(empty_rows)} instagram_comments rows with empty comment_id")
    print("[INFO] Assigning synthetic IDs derived from (shortcode, comment_datetime, rowid)...")

    updated = 0
    for row_id, shortcode, comment_datetime in empty_rows:
        key = f"{shortcode}|{comment_datetime}|{row_id}"
        synthetic_id = "synth_" + hashlib.sha1(key.encode()).hexdigest()[:12]
        conn.execute(
            "UPDATE instagram_comments SET comment_id = ? WHERE id = ?",
            (synthetic_id, row_id)
        )
        updated += 1

    conn.commit()
    print(f"[OK] Assigned synthetic comment_ids to {updated} rows")
    return updated


def check_duplicates(conn):
    """Check for duplicate rows that would block UNIQUE index creation.
    Returns True if safe to proceed, False if duplicates exist."""
    checks = [
        ("amazon_review_dates",
         "SELECT asin, review_date_raw, review_title, COUNT(*) c "
         "FROM amazon_review_dates GROUP BY asin, review_date_raw, review_title HAVING c > 1"),
        ("tiktok_comments",
         "SELECT comment_id, COUNT(*) c FROM tiktok_comments "
         "GROUP BY comment_id HAVING c > 1"),
        ("instagram_comments",
         "SELECT shortcode, comment_id, COUNT(*) c FROM instagram_comments "
         "GROUP BY shortcode, comment_id HAVING c > 1"),
    ]
    safe = True
    for table, sql in checks:
        rows = conn.execute(sql).fetchall()
        if rows:
            print(f"[ERROR] Duplicates found in {table}: {rows[:5]}")
            safe = False
        else:
            print(f"[OK] No duplicates in {table}")
    return safe


def report_row_counts(conn):
    tables = [
        "amazon_snapshots", "similarweb_traffic", "tiktok_data", "instagram_data",
        "amazon_review_dates", "tiktok_videos", "tiktok_comments",
        "instagram_posts", "instagram_comments"
    ]
    print("\n--- Row counts (BEFORE migration) ---")
    counts = {}
    for t in tables:
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            counts[t] = n
            print(f"  {t}: {n}")
        except Exception as e:
            print(f"  {t}: ERROR ({e})")
    return counts


def verify_indexes(conn):
    targets = [
        ("amazon_review_dates", "uq_amazon_review"),
        ("tiktok_comments", "uq_tiktok_comment"),
        ("instagram_comments", "uq_ig_comment"),
    ]
    print("\n--- Index verification (AFTER migration) ---")
    for table, idx_name in targets:
        idxs = {r[1] for r in conn.execute(f"PRAGMA index_list({table})")}
        if idx_name in idxs:
            print(f"  [OK] {table}.{idx_name} exists")
        else:
            print(f"  [FAIL] {table}.{idx_name} NOT FOUND")


def main():
    print(f"Connecting to: {os.path.abspath(os.path.join(BASE_DIR, 'overseas_data.db'))}")
    conn = get_conn()

    counts_before = report_row_counts(conn)

    # Fix empty comment_ids before duplicate check (Rule 1 auto-fix)
    print("\n--- Pre-migration fix: empty comment_ids ---")
    fix_empty_comment_ids(conn)

    print("\n--- Duplicate check ---")
    if not check_duplicates(conn):
        print("\n[ABORT] Duplicates found. Resolve manually before running migration.")
        sys.exit(1)

    print("\n--- Running ensure_unique_indexes() ---")
    ensure_unique_indexes(conn)
    print("[OK] Migration complete")

    verify_indexes(conn)

    counts_after = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    for t in ["amazon_snapshots", "similarweb_traffic", "tiktok_data", "instagram_data"]}
    print("\n--- Snapshot table row counts (must be unchanged) ---")
    for t, n in counts_after.items():
        before = counts_before.get(t, "?")
        status = "OK" if n == before else "CHANGED!"
        print(f"  {t}: {n} (was {before}) [{status}]")

    # Also verify instagram_comments row count preserved
    ig_after = conn.execute("SELECT COUNT(*) FROM instagram_comments").fetchone()[0]
    ig_before = counts_before.get("instagram_comments", "?")
    ig_status = "OK" if ig_after == ig_before else "CHANGED!"
    print(f"  instagram_comments: {ig_after} (was {ig_before}) [{ig_status}]")

    conn.close()
    print("\n[DONE] db_migrate.py completed successfully")


if __name__ == "__main__":
    main()
