#!/usr/bin/env python3
"""
build_sgf_lexicon.py

Stage 2 of the SGF lexicon build pipeline.

Reads from wiktionary_source (populated by build_wiktionary_source.py) and
projects each row into the sgf_lexicon table, populating only what can be
derived deterministically without an algorithm choice:

    wiktionary_source_id  -- FK back to wiktionary_source.source_sense_id
    lemma                 -- the headword
    pos_wiktionary        -- raw POS string from Wiktionary
    pos_simple            -- one of: noun, verb, adj, adv, name, other
    gloss                 -- the first (raw_gloss preferred, then gloss)

These columns are NULL after this stage and are filled by downstream steps:
    microgloss            -- filled by generate_microglosses.py
    canonical_id          -- filled by generate_microglosses.py
    embedding_text        -- filled by build_embedding_texts.py
    embed                 -- filled by compute_embeddings.py
    content_fingerprint   -- filled by compute_embeddings.py

Pipeline:
    make wiktionary_source   # already done
    make sgf_lexicon         # this script
    make microglosses        # generate_microglosses.py
    make embed_texts         # build_embedding_texts.py
    make embeddings          # compute_embeddings.py

Usage:
    python build_sgf_lexicon.py --target sgf_lexicon.db [--limit N]
"""

import argparse
import sqlite3
import sys
import time
from pathlib import Path

# Ensure sibling modules (pos_converter) resolve regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pos_converter import to_simple, to_spacy

COMMIT_EVERY = 5000

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA temp_store = MEMORY;
PRAGMA cache_size = -200000;

CREATE TABLE IF NOT EXISTS sgf_lexicon (
    wiktionary_source_id  INTEGER PRIMARY KEY,
    lemma                 TEXT NOT NULL,
    pos_wiktionary        TEXT NOT NULL,
    pos_spacy             TEXT NOT NULL,
    pos_simple            TEXT NOT NULL,
    gloss                 TEXT NOT NULL,

    -- Filled by generate_microglosses.py
    microgloss            TEXT,
    microgloss_version    TEXT,
    canonical_id          TEXT UNIQUE,

    -- Filled by build_embedding_texts.py
    embedding_text        TEXT,
    embedding_text_version TEXT,

    -- Bookkeeping
    minted_at             INTEGER NOT NULL,

    FOREIGN KEY (wiktionary_source_id) REFERENCES wiktionary_source(source_sense_id)
);

-- NOTE: per-embedder vectors and fingerprints live in the separate
-- sense_embedding table created by schema.sql (run via apply_schema.py).

CREATE INDEX IF NOT EXISTS idx_sgf_lemma_pos ON sgf_lexicon(lemma, pos_simple);
CREATE INDEX IF NOT EXISTS idx_sgf_lemma_spacy ON sgf_lexicon(lemma, pos_spacy);
CREATE INDEX IF NOT EXISTS idx_sgf_lemma ON sgf_lexicon(lemma);
CREATE INDEX IF NOT EXISTS idx_sgf_microgloss_null ON sgf_lexicon(wiktionary_source_id) WHERE microgloss IS NULL;
CREATE INDEX IF NOT EXISTS idx_sgf_canonical ON sgf_lexicon(canonical_id);

CREATE TABLE IF NOT EXISTS sense_embedding (
    wiktionary_source_id   INTEGER NOT NULL,
    embedding_method       TEXT    NOT NULL,
    embedding_dim          INTEGER NOT NULL,
    embed                  BLOB    NOT NULL,
    content_fingerprint    TEXT,
    fingerprint_method     TEXT,
    computed_at            INTEGER NOT NULL,
    PRIMARY KEY (wiktionary_source_id, embedding_method)
);
CREATE INDEX IF NOT EXISTS idx_se_method ON sense_embedding(embedding_method);
CREATE INDEX IF NOT EXISTS idx_se_method_fp ON sense_embedding(embedding_method, content_fingerprint);

CREATE TABLE IF NOT EXISTS lemma_frequency (
    lemma            TEXT PRIMARY KEY,
    frequency_rank   INTEGER,
    frequency_count  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_lf_rank ON lemma_frequency(frequency_rank);

CREATE TABLE IF NOT EXISTS build_meta (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);
"""


def project(tgt_conn: sqlite3.Connection, limit: int | None) -> tuple[int, int, int]:
    """
    Walk wiktionary_source rows that are not yet in sgf_lexicon. Insert a
    skeleton row per source sense with pos_wiktionary, pos_simple, and gloss.
    All other columns left NULL for downstream stages.

    Returns (inserted, skipped_no_gloss, skipped_already_projected).
    """
    read = tgt_conn.cursor()
    write = tgt_conn.cursor()

    # Build skip-set so reruns do not duplicate work.
    write.execute("SELECT wiktionary_source_id FROM sgf_lexicon")
    already: set[int] = {row[0] for row in write.fetchall()}
    if already:
        print(f"  resume: {len(already):,} rows already projected; will skip")

    read.execute("""
        SELECT source_sense_id, word, pos, first_gloss
        FROM wiktionary_source
        ORDER BY source_sense_id
    """)

    inserted = 0
    skipped_no_gloss = 0
    skipped_already = 0
    t_start = time.time()

    while True:
        row = read.fetchone()
        if row is None:
            break

        src_sense_id, lemma, pos_wiktionary, first_gloss = row

        if src_sense_id in already:
            skipped_already += 1
            continue

        if not lemma or not first_gloss:
            skipped_no_gloss += 1
            continue

        pos_simple = to_simple(pos_wiktionary)
        pos_spacy_val = to_spacy(pos_wiktionary)
        pos_wiktionary_clean = (pos_wiktionary or "").strip() or "unknown"

        write.execute("""
            INSERT INTO sgf_lexicon (
                wiktionary_source_id, lemma, pos_wiktionary,
                pos_spacy, pos_simple, gloss, minted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            src_sense_id, lemma, pos_wiktionary_clean,
            pos_spacy_val, pos_simple, first_gloss, int(time.time()),
        ))

        inserted += 1
        if inserted % COMMIT_EVERY == 0:
            tgt_conn.commit()
            elapsed = time.time() - t_start
            rate = inserted / elapsed if elapsed > 0 else 0
            print(f"  projected {inserted:,} rows ({rate:,.0f}/s)")

        if limit and inserted >= limit:
            print(f"  reached --limit={limit:,}; stopping")
            break

    tgt_conn.commit()
    return inserted, skipped_no_gloss, skipped_already


def write_meta(tgt_conn: sqlite3.Connection, key: str, value: str) -> None:
    cur = tgt_conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO build_meta (key, value) VALUES (?, ?)",
        (key, value),
    )
    tgt_conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Project wiktionary_source into the sgf_lexicon skeleton table.")
    parser.add_argument("--target", default="sgf_lexicon.db", help="SGF lexicon DB (must contain wiktionary_source)")
    parser.add_argument("--limit", type=int, default=None, help="Stop after N rows (testing)")
    args = parser.parse_args()

    tgt_path = Path(args.target)
    if not tgt_path.exists():
        print(f"Target DB not found: {tgt_path}", file=sys.stderr)
        print("Run build_wiktionary_source.py first.", file=sys.stderr)
        return 1

    print(f"Target: {tgt_path.resolve()}")
    print()

    tgt_conn = sqlite3.connect(tgt_path)
    try:
        cur = tgt_conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='wiktionary_source'")
        if cur.fetchone() is None:
            print("ERROR: wiktionary_source table not found.", file=sys.stderr)
            print("Run build_wiktionary_source.py first.", file=sys.stderr)
            return 1

        tgt_conn.executescript(SCHEMA)
        tgt_conn.commit()

        write_meta(tgt_conn, "sgf_lexicon_started_at", str(int(time.time())))

        print("Projecting skeleton rows ...")
        inserted, skipped_no_gloss, skipped_already = project(tgt_conn, args.limit)

        write_meta(tgt_conn, "sgf_lexicon_inserted", str(inserted))
        write_meta(tgt_conn, "sgf_lexicon_skipped_no_gloss", str(skipped_no_gloss))
        write_meta(tgt_conn, "sgf_lexicon_completed_at", str(int(time.time())))

        cur.execute("SELECT COUNT(*) FROM sgf_lexicon")
        total = cur.fetchone()[0]
        cur.execute("SELECT pos_simple, COUNT(*) FROM sgf_lexicon GROUP BY pos_simple ORDER BY 2 DESC")
        by_pos = cur.fetchall()
        cur.execute("SELECT pos_spacy, COUNT(*) FROM sgf_lexicon GROUP BY pos_spacy ORDER BY 2 DESC LIMIT 8")
        by_spacy = cur.fetchall()

        print()
        print("=" * 60)
        print("sgf_lexicon SKELETON LOAD COMPLETE")
        print("=" * 60)
        print(f"  total rows         : {total:,}")
        print(f"  inserted this run  : {inserted:,}")
        print(f"  skipped (no gloss) : {skipped_no_gloss:,}")
        print(f"  skipped (already)  : {skipped_already:,}")
        print()
        print("  POS distribution (simple):")
        for pos, count in by_pos:
            print(f"    {pos:<8} : {count:,}")
        print("  POS distribution (spaCy, top 8):")
        for pos, count in by_spacy:
            print(f"    {pos:<8} : {count:,}")
        print()
        print(f"  output db          : {tgt_path.resolve()}")
        print("=" * 60)
        print()
        print("Next steps:")
        print("  python load_lemma_frequency.py --target", tgt_path.name)
        print()
        print("  Then run the orchestrator with a config:")
        print("    python run_frontier.py --config bootstrap_no_llm.toml")
        print("    (see README -- Step 6)")

    finally:
        tgt_conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
