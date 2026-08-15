#!/usr/bin/env python3
"""
import_wikipedia_to_synapedia.py — Load Wikipedia data from wikipedia.db into Synapedia.

Reads from wikipedia.db (created by load_wikipedia_to_db.py) and populates
synapedia_entry with titles and summaries.

- Only imports entries not already present (dedup by lemma + pos_ud)
- Wikipedia articles are imported as NOUN (they are entities/concepts)
- Uses title_clean if available, otherwise title
- Leaves canonical_id NULL (to be filled later by microgloss.py)

Usage:
    python import_wikipedia_to_synapedia.py --wikipedia-db wikipedia.db --synapedia-db synapedia.db
    python import_wikipedia_to_synapedia.py --wikipedia-db wikipedia.db --synapedia-db synapedia.db --limit 10000
"""

import argparse
import sqlite3
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wikipedia-db", required=True)
    parser.add_argument("--synapedia-db", default="synapedia.db")
    parser.add_argument("--limit", type=int, default=None, help="Import only N articles")
    parser.add_argument("--batch", type=int, default=5000, help="Commit batch size")
    args = parser.parse_args()

    wiki_path = Path(args.wikipedia_db).resolve()
    syn_path = Path(args.synapedia_db).resolve()

    if not wiki_path.exists():
        print(f"Error: Wikipedia DB not found: {wiki_path}", file=sys.stderr)
        return 1

    # ── Connect ──
    wiki_conn = sqlite3.connect(str(wiki_path))
    wiki_conn.row_factory = sqlite3.Row

    syn_conn = sqlite3.connect(str(syn_path))
    syn_conn.execute("PRAGMA foreign_keys=OFF")
    syn_conn.execute("PRAGMA journal_mode=WAL")
    syn_conn.execute("PRAGMA synchronous=NORMAL")
    syn_conn.execute("PRAGMA cache_size=-16000000")
    syn_cur = syn_conn.cursor()

    # Verify schema
    syn_cur.execute("PRAGMA table_info(synapedia_entry)")
    cols = {r[1] for r in syn_cur.fetchall()}
    if 'canonical_id' not in cols:
        print("ERROR: canonical_id column missing in synapedia_entry.", file=sys.stderr)
        print("Run load_synapedia_from_wordnet_db.py first.", file=sys.stderr)
        return 1

    print(f"Wikipedia DB: {wiki_path}")
    print(f"Synapedia DB: {syn_path}")
    print()

    # ── Load articles ──
    t0 = time.time()
    batch_size = args.batch

    # Get total count
    if args.limit:
        wiki_cur = wiki_conn.execute("""
            SELECT id, title, abstract, title_clean
            FROM articles
            ORDER BY id
            LIMIT ?
        """, (args.limit,))
    else:
        wiki_cur = wiki_conn.execute("""
            SELECT id, title, abstract, title_clean
            FROM articles
            ORDER BY id
        """)

    rows = wiki_cur.fetchall()
    total = len(rows)
    print(f"Total articles to import: {total:,}")

    imported = 0
    skipped_dedup = 0
    skipped_empty = 0

    for r in rows:
        title = r['title']
        abstract = r['abstract']
        title_clean = r['title_clean']

        if not title or not abstract:
            skipped_empty += 1
            continue

        # Use title_clean if available, otherwise title
        lemma = title_clean if title_clean else title

        # Wikipedia articles are entities/concepts → NOUN
        pos_ud = "NOUN"
        pos_original = "noun"

        # Dedup: skip if (lemma, pos_ud) already exists
        syn_cur.execute(
            "SELECT 1 FROM synapedia_entry WHERE lemma = ? AND pos_ud = ? LIMIT 1",
            (lemma, pos_ud)
        )
        if syn_cur.fetchone():
            skipped_dedup += 1
            continue

        # Insert with canonical_id = NULL (filled later by microgloss.py)
        syn_cur.execute("""
            INSERT INTO synapedia_entry
                (lemma, pos_original, pos_ud, gloss, source_type, definition_tier, language,
                 is_prime, is_molecule, is_instance, embedding_text_needs_rebuild)
            VALUES (?, ?, ?, ?, 'wikipedia', 'CORE_KNOWLEDGE', 'en',
                    0, 0, 0, 1)
        """, (lemma, pos_original, pos_ud, abstract))

        imported += 1

        if imported % batch_size == 0:
            syn_conn.commit()
            elapsed = time.time() - t0
            rate = imported / max(elapsed, 0.001)
            print(f"  imported {imported:,}/{total:,} | {rate:,.0f}/s | {elapsed:.0f}s", end="\r")

    syn_conn.commit()
    elapsed = time.time() - t0
    rate = imported / max(elapsed, 0.001)

    print(f"\n{'='*60}")
    print(f"IMPORT COMPLETE")
    print(f"{'='*60}")
    print(f"  Imported:       {imported:>10,}")
    print(f"  Skipped (dup):  {skipped_dedup:>10,}")
    print(f"  Skipped (empty):{skipped_empty:>10,}")
    print(f"  Time:           {elapsed:>10.0f}s")
    print(f"  Rate:           {rate:>10,.0f} entries/s")

    syn_cur.execute("SELECT COUNT(*) FROM synapedia_entry")
    total_in_syn = syn_cur.fetchone()[0]
    print(f"  Total in DB:    {total_in_syn:>10,} entries")

    wiki_conn.close()
    syn_conn.close()
    print("\nNext: Run microgloss.py to generate microgloss and canonical IDs:")
    print("  python microgloss.py --target synapedia.db --namespace core --force")
    return 0


if __name__ == "__main__":
    sys.exit(main())