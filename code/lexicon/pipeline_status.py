#!/usr/bin/env python3
"""
pipeline_status.py

One-screen status report for the SGF lexicon build pipeline.

Shows progress at every stage, with a frequency-tier breakdown that
lets you see "top 1K lemmas: 100% done; top 10K: 87% done; long tail: 12%".

USAGE:
    python pipeline_status.py --target sgf_lexicon.db

    # Only check a specific embedding method:
    python pipeline_status.py --target sgf_lexicon.db --embedding-method bge-small-en-v1
"""

import argparse
import sqlite3
import sys
from pathlib import Path


# Frequency tiers we report on
TIERS = [
    ("top 1K",     1,        1_000),
    ("top 10K",    1,       10_000),
    ("top 50K",    1,       50_000),
    ("top 100K",   1,      100_000),
    ("top 500K",   1,      500_000),
    ("any rank",   1,  10_000_000),
]


def table_exists(conn, name):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    )
    return cur.fetchone() is not None


def safe_count(conn, sql, params=()):
    try:
        return conn.execute(sql, params).fetchone()[0]
    except sqlite3.OperationalError:
        return None


def print_section(title):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def stage_wiktionary_source(conn):
    print_section("Stage 1 — wiktionary_source")
    if not table_exists(conn, "wiktionary_source"):
        print("  wiktionary_source table does not exist yet")
        return
    n = safe_count(conn, "SELECT COUNT(*) FROM wiktionary_source")
    print(f"  rows                : {n:,}")


def stage_sgf_lexicon(conn):
    print_section("Stage 2 — sgf_lexicon (skeleton)")
    if not table_exists(conn, "sgf_lexicon"):
        print("  sgf_lexicon table does not exist yet")
        return
    n = safe_count(conn, "SELECT COUNT(*) FROM sgf_lexicon")
    print(f"  rows                : {n:,}")

    # POS distribution
    cur = conn.execute("""
        SELECT pos_simple, COUNT(*) FROM sgf_lexicon GROUP BY pos_simple
        ORDER BY COUNT(*) DESC
    """)
    print("  by POS:")
    for pos, count in cur:
        print(f"      {pos:<8} {count:>10,}")


def stage_lemma_frequency(conn):
    print_section("Stage 2.5 — lemma_frequency")
    if not table_exists(conn, "lemma_frequency"):
        print("  lemma_frequency table does not exist yet")
        return
    n = safe_count(conn, "SELECT COUNT(*) FROM lemma_frequency")
    print(f"  rows                : {n:,}")

    matched = safe_count(conn, """
        SELECT COUNT(DISTINCT sl.lemma)
        FROM sgf_lexicon sl
        JOIN lemma_frequency lf ON lf.lemma = LOWER(sl.lemma)
    """)
    total = safe_count(conn, "SELECT COUNT(DISTINCT lemma) FROM sgf_lexicon")
    if matched is not None and total:
        pct = 100.0 * matched / total
        print(f"  distinct lemmas     : {total:,}")
        print(f"  with frequency rank : {matched:,} ({pct:.1f}%)")


def stage_microgloss(conn):
    print_section("Stage 3 — microgloss")
    if not table_exists(conn, "sgf_lexicon"):
        return
    total = safe_count(conn, "SELECT COUNT(*) FROM sgf_lexicon")
    if not total:
        return

    cur = conn.execute("""
        SELECT COALESCE(microgloss_version, '(none)'), COUNT(*)
        FROM sgf_lexicon
        GROUP BY microgloss_version
        ORDER BY COUNT(*) DESC
    """)
    print(f"  total rows          : {total:,}")
    print("  by microgloss version:")
    for ver, count in cur:
        pct = 100.0 * count / total
        print(f"      {ver:<10}  {count:>10,}  ({pct:.1f}%)")


def stage_embedding_text(conn):
    print_section("Stage 4 — embedding_text")
    total = safe_count(conn, "SELECT COUNT(*) FROM sgf_lexicon WHERE microgloss IS NOT NULL")
    done = safe_count(conn, "SELECT COUNT(*) FROM sgf_lexicon WHERE embedding_text IS NOT NULL")
    if total is None:
        return
    pct = 100.0 * done / total if total else 0
    print(f"  rows with microgloss      : {total:,}")
    print(f"  rows with embedding_text  : {done:,} ({pct:.1f}%)")

    # Frequency-tier breakdown
    if table_exists(conn, "lemma_frequency"):
        print("  by frequency tier:")
        for label, lo, hi in TIERS:
            t = safe_count(conn, """
                SELECT COUNT(*) FROM sgf_lexicon sl
                JOIN lemma_frequency lf ON lf.lemma = LOWER(sl.lemma)
                WHERE sl.microgloss IS NOT NULL
                  AND lf.frequency_rank BETWEEN ? AND ?
            """, (lo, hi))
            d = safe_count(conn, """
                SELECT COUNT(*) FROM sgf_lexicon sl
                JOIN lemma_frequency lf ON lf.lemma = LOWER(sl.lemma)
                WHERE sl.embedding_text IS NOT NULL
                  AND lf.frequency_rank BETWEEN ? AND ?
            """, (lo, hi))
            if t:
                pp = 100.0 * d / t
                print(f"      {label:<10} {d:>10,} / {t:>10,}  ({pp:.1f}%)")


def stage_embeddings(conn, method_filter=None):
    print_section("Stage 5 — sense_embedding (embeddings)")
    if not table_exists(conn, "sense_embedding"):
        print("  sense_embedding table does not exist yet")
        return

    cur = conn.execute("""
        SELECT embedding_method, COUNT(*) FROM sense_embedding
        GROUP BY embedding_method ORDER BY embedding_method
    """)
    methods = cur.fetchall()
    if not methods:
        print("  no embedding rows yet")
        return

    total_emb_text = safe_count(
        conn, "SELECT COUNT(*) FROM sgf_lexicon WHERE embedding_text IS NOT NULL"
    )

    for method, count in methods:
        if method_filter and method != method_filter:
            continue
        pct = 100.0 * count / total_emb_text if total_emb_text else 0
        print()
        print(f"  method: {method}")
        print(f"      total embedded       : {count:,}  "
              f"({pct:.1f}% of {total_emb_text:,} eligible)")

        if table_exists(conn, "lemma_frequency"):
            print(f"      by frequency tier:")
            for label, lo, hi in TIERS:
                t = safe_count(conn, """
                    SELECT COUNT(*) FROM sgf_lexicon sl
                    JOIN lemma_frequency lf ON lf.lemma = LOWER(sl.lemma)
                    WHERE sl.embedding_text IS NOT NULL
                      AND lf.frequency_rank BETWEEN ? AND ?
                """, (lo, hi))
                d = safe_count(conn, """
                    SELECT COUNT(*) FROM sense_embedding se
                    JOIN sgf_lexicon sl ON sl.wiktionary_source_id = se.wiktionary_source_id
                    JOIN lemma_frequency lf ON lf.lemma = LOWER(sl.lemma)
                    WHERE se.embedding_method = ?
                      AND lf.frequency_rank BETWEEN ? AND ?
                """, (method, lo, hi))
                if t:
                    pp = 100.0 * d / t
                    print(f"          {label:<10} {d:>10,} / {t:>10,}  ({pp:.1f}%)")


def stage_fingerprints(conn, method_filter=None):
    print_section("Stage 6 — content_fingerprint")
    if not table_exists(conn, "sense_embedding"):
        return

    cur = conn.execute("""
        SELECT embedding_method,
               COUNT(*) AS total,
               SUM(CASE WHEN content_fingerprint IS NOT NULL THEN 1 ELSE 0 END) AS done
        FROM sense_embedding
        GROUP BY embedding_method
        ORDER BY embedding_method
    """)
    methods = cur.fetchall()
    if not methods:
        print("  no embeddings to fingerprint yet")
        return

    for method, total, done in methods:
        if method_filter and method != method_filter:
            continue
        pct = 100.0 * done / total if total else 0
        print(f"  {method:<30} {done:,} / {total:,}  ({pct:.1f}%)")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--target", default="sgf_lexicon.db")
    p.add_argument("--embedding-method", default=None,
                   help="Filter Stage 5/6 to a specific embedding method")
    args = p.parse_args()

    db_path = Path(args.target)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    print(f"SGF Lexicon Pipeline Status")
    print(f"DB: {db_path.resolve()}")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA query_only = ON")
    try:
        stage_wiktionary_source(conn)
        stage_sgf_lexicon(conn)
        stage_lemma_frequency(conn)
        stage_microgloss(conn)
        stage_embedding_text(conn)
        stage_embeddings(conn, args.embedding_method)
        stage_fingerprints(conn, args.embedding_method)
    finally:
        conn.close()
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
