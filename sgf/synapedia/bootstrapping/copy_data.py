#!/usr/bin/env python3
"""
copy_columns_from_old_db.py — OPTIMIZED

Uses indexes and a single-pass CTE to avoid 740K subquery executions.
"""

import argparse
import sqlite3
import sys
import time
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", required=True)
    ap.add_argument("--old", required=True)
    args = ap.parse_args()

    new_path = Path(args.new).resolve()
    old_path = Path(args.old).resolve()
    if not new_path.exists() or not old_path.exists():
        print("One or both DB files not found.", file=sys.stderr)
        return 1

    t0 = time.time()
    print(f"New DB: {new_path}")
    print(f"Old DB: {old_path}")

    new_conn = sqlite3.connect(str(new_path))
    new_conn.execute("PRAGMA journal_mode=WAL")
    new_conn.execute("PRAGMA synchronous=NORMAL")
    new_cur = new_conn.cursor()

    # Attach old DB
    new_cur.execute(f"ATTACH DATABASE '{str(old_path)}' AS old")

    # --- Create indexes on both databases if they don't exist ---
    print("Creating indexes...")
    for db in ("", "old."):
        prefix = db
        # Composite index on xref: source_db + source_id → synapedia_id
        new_cur.execute(f"""
            CREATE INDEX IF NOT EXISTS {prefix}idx_xref_lookup 
            ON synapedia_source_xref(source_db, source_id, synapedia_id)
        """)
        # Index on xref: synapedia_id → source_id (for the reverse lookup)
        new_cur.execute(f"""
            CREATE INDEX IF NOT EXISTS {prefix}idx_xref_entry 
            ON synapedia_source_xref(synapedia_id, source_db, source_id)
        """)
        # Index on entry: entry_id (already PK, but ensure it's fast)
        new_cur.execute(f"""
            CREATE INDEX IF NOT EXISTS {prefix}idx_entry_id 
            ON synapedia_entry(entry_id)
        """)
    new_conn.commit()

    # Count matching entries
    new_cur.execute("""
        SELECT COUNT(*)
        FROM synapedia_source_xref nx
        JOIN old.synapedia_source_xref ox
            ON nx.source_db = ox.source_db AND nx.source_id = ox.source_id
        WHERE nx.source_db = 'wordnet'
    """)
    match_count = new_cur.fetchone()[0]
    print(f"Matched WordNet entries: {match_count:,}")
    if match_count == 0:
        print("ERROR: No matches found.", file=sys.stderr)
        return 1

    # --- Single-pass UPDATE using a CTE that maps new entry_id → old entry_id ---
    print("Copying columns (single pass)...")
    new_cur.execute("""
        UPDATE synapedia_entry
        SET
            microgloss      = old_entries.microgloss,
            canonical_id    = old_entries.canonical_id,
            embedding_text  = old_entries.embedding_text,
            embedding       = old_entries.embedding
        FROM (
            -- This CTE builds the mapping: new entry_id → old entry row
            SELECT DISTINCT
                nsx.synapedia_id AS new_entry_id,
                ose.microgloss,
                ose.canonical_id,
                ose.embedding_text,
                ose.embedding
            FROM synapedia_source_xref nsx
            JOIN old.synapedia_source_xref osx
                ON nsx.source_db = osx.source_db AND nsx.source_id = osx.source_id
            JOIN old.synapedia_entry ose
                ON osx.synapedia_id = ose.entry_id
            WHERE nsx.source_db = 'wordnet'
              AND osx.source_db = 'wordnet'
        ) AS old_entries
        WHERE synapedia_entry.entry_id = old_entries.new_entry_id
    """)
    new_conn.commit()

    updated = new_cur.execute("SELECT changes()").fetchone()[0]
    print(f"Updated {updated:,} rows")

    # Verify
    for col in ("microgloss", "embedding"):
        new_cur.execute(f"""
            SELECT COUNT(*) FROM synapedia_entry n
            JOIN synapedia_source_xref x ON n.entry_id = x.synapedia_id
            WHERE x.source_db = 'wordnet' AND n.{col} IS NOT NULL
        """)
        cnt = new_cur.fetchone()[0]
        print(f"WordNet entries with {col}: {cnt:,}")

    new_cur.execute("DETACH DATABASE old")
    new_conn.close()

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s")
    return 0

if __name__ == "__main__":
    sys.exit(main())