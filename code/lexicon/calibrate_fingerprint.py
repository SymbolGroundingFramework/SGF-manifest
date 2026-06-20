#!/usr/bin/env python3
"""
calibrate_fingerprint.py

Empirical calibration of the SGF content_fingerprint thresholds against
the real SGF Core Lexicon.

Run this AFTER compute_embeddings.py and compute_sense_fingerprints.py have
finished for the requested --embedding-method. It picks representative
concept pairs across several relatedness tiers and measures their
Hamming distances.

The output is a calibration table that becomes the basis for setting
"almost certainly same meaning" / "likely related" / etc. thresholds in
the consuming application (GLEAN, etc.).

Categories tested:
  1. SAME CONCEPT, MINOR SURFACE DIFFERENCE
       (encyclopedia vs encyclopaedia; color vs colour)
  2. CLOSE COUSINS WITHIN A TAXONOMY
       (tabby vs calico; oak vs maple)
  3. SIBLINGS UNDER COMMON ANCESTOR
       (cat vs dog; lion vs tiger)
  4. HOMOGRAPHS (same lemma, different sense)
  5. UNRELATED CONCEPTS

Usage:
  python calibrate_fingerprint.py --target sgf_lexicon.db \\
      --embedding-method bge-large-en-v1
"""

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compute_sense_fingerprints import hamming_distance, decode_fingerprint


TEST_PAIRS = [
    # SAME CONCEPT, SURFACE VARIATION
    ("same-concept", "encyclopedia", "encyclopaedia", "spelling variants"),
    ("same-concept", "color", "colour", "American vs British"),
    ("same-concept", "organize", "organise", "American vs British"),
    ("same-concept", "theater", "theatre", "American vs British"),

    # CLOSE COUSINS
    ("close-cousin", "oak", "maple", "both deciduous trees"),
    ("close-cousin", "violin", "viola", "both bowed string instruments"),
    ("close-cousin", "soccer", "rugby", "both team field sports"),
    ("close-cousin", "tabby", "calico", "both cat patterns"),
    ("close-cousin", "salmon", "trout", "both salmonid fishes"),

    # SIBLINGS
    ("sibling", "cat", "dog", "both domestic mammals"),
    ("sibling", "lion", "tiger", "both large felines"),
    ("sibling", "guitar", "piano", "both musical instruments"),
    ("sibling", "doctor", "lawyer", "both professionals"),
    ("sibling", "river", "lake", "both bodies of water"),

    # DOMAIN COUSINS
    ("domain-cousin", "tree", "flower", "both plants"),
    ("domain-cousin", "computer", "smartphone", "both electronics"),
    ("domain-cousin", "novel", "poem", "both literary works"),

    # HOMOGRAPHS
    ("homograph", "bank", "bank", "financial vs river edge"),
    ("homograph", "bat", "bat", "animal vs sports tool"),
    ("homograph", "spring", "spring", "season vs coil"),
    ("homograph", "match", "match", "fire stick vs contest"),

    # UNRELATED
    ("unrelated", "cat", "volcano", "animal vs geology"),
    ("unrelated", "bank", "symphony", "finance vs music"),
    ("unrelated", "encyclopedia", "shoe", "reference work vs footwear"),
    ("unrelated", "river", "calculus", "geography vs math"),
    ("unrelated", "lion", "algebra", "animal vs math"),
]


def find_fingerprint(conn, embedding_method, lemma, sense_index=0):
    """Look up canonical_id + fingerprint for a lemma under the given method."""
    cur = conn.cursor()
    cur.execute("""
        SELECT sl.canonical_id, se.content_fingerprint, se.embedding_dim
        FROM sgf_lexicon sl
        JOIN sense_embedding se ON se.wiktionary_source_id = sl.wiktionary_source_id
        WHERE sl.lemma = ?
          AND se.embedding_method = ?
          AND se.content_fingerprint IS NOT NULL
        ORDER BY sl.wiktionary_source_id
        LIMIT 1 OFFSET ?
    """, (lemma, embedding_method, sense_index))
    row = cur.fetchone()
    return row if row else (None, None, None)


def chars_match(a, b):
    if len(a) != len(b):
        return 0
    return sum(1 for x, y in zip(a, b) if x == y)


def run_calibration(db_path, embedding_method):
    conn = sqlite3.connect(db_path)

    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM sense_embedding
        WHERE embedding_method = ? AND content_fingerprint IS NOT NULL
    """, (embedding_method,))
    n_fp = cur.fetchone()[0]
    if n_fp == 0:
        print(f"No fingerprints found for method {embedding_method!r}.", file=sys.stderr)
        print("Run compute_embeddings.py + compute_sense_fingerprints.py first.", file=sys.stderr)
        return 1

    print("Empirical fingerprint calibration")
    print("=" * 80)
    print(f"  source DB        : {db_path}")
    print(f"  embedding-method : {embedding_method}")
    print(f"  fingerprints     : {n_fp:,} rows under this method")
    print("=" * 80)
    print()

    results = {}
    missing = []
    bits = None  # set on first hit
    homograph_counter = {}

    for category, lemma_a, lemma_b, hint in TEST_PAIRS:
        if category == "homograph":
            idx_a = homograph_counter.get(lemma_a, 0)
            homograph_counter[lemma_a] = idx_a + 2
            cid_a, fp_a, dim_a = find_fingerprint(conn, embedding_method, lemma_a, idx_a)
            cid_b, fp_b, dim_b = find_fingerprint(conn, embedding_method, lemma_b, idx_a + 1)
        else:
            cid_a, fp_a, dim_a = find_fingerprint(conn, embedding_method, lemma_a)
            cid_b, fp_b, dim_b = find_fingerprint(conn, embedding_method, lemma_b)

        if not fp_a or not fp_b:
            missing.append((category, lemma_a, lemma_b, hint))
            continue

        if bits is None:
            bits = dim_a

        cmatch = chars_match(fp_a, fp_b)
        try:
            hdist = hamming_distance(fp_a, fp_b)
        except Exception:
            hdist = -1

        results.setdefault(category, []).append({
            "lemma_a": lemma_a, "lemma_b": lemma_b, "hint": hint,
            "cid_a": cid_a, "cid_b": cid_b,
            "char_match": cmatch, "hamming": hdist,
        })

    category_order = [
        "same-concept", "close-cousin", "sibling",
        "domain-cousin", "homograph", "unrelated",
    ]

    print(f"{'Category':<18}{'Lemma A':<20}{'Lemma B':<20}{'CharMatch':>10}{'HamDist':>10}")
    print("-" * 80)
    for cat in category_order:
        if cat not in results:
            continue
        for r in results[cat]:
            print(f"{cat:<18}{r['lemma_a']:<20}{r['lemma_b']:<20}"
                  f"{r['char_match']:>10}{r['hamming']:>10}")
        if results[cat]:
            hams = [r['hamming'] for r in results[cat]]
            chars = [r['char_match'] for r in results[cat]]
            print(f"{'':<18}{'    summary':<40}"
                  f"{'char ' + str(min(chars)) + '-' + str(max(chars)):<15}"
                  f"{'ham ' + str(min(hams)) + '-' + str(max(hams))}")
            print()

    if missing:
        print("\n" + "=" * 80)
        print("PAIRS NOT FOUND IN LEXICON")
        print("=" * 80)
        for category, lemma_a, lemma_b, hint in missing:
            print(f"  [{category}] {lemma_a} / {lemma_b} ({hint})")
        print()

    print("=" * 80)
    print("RECOMMENDED THRESHOLDS (based on this corpus)")
    print("=" * 80)
    if bits:
        print(f"  fingerprint width: {bits} bits")

    if "same-concept" in results and results["same-concept"]:
        max_ham = max(r['hamming'] for r in results['same-concept'])
        print(f"  same-concept   max Hamming distance: {max_ham}")
    if "close-cousin" in results and results["close-cousin"]:
        hams = [r['hamming'] for r in results['close-cousin']]
        print(f"  close-cousin   Hamming range:        {min(hams)}-{max(hams)}")
    if "sibling" in results and results["sibling"]:
        hams = [r['hamming'] for r in results['sibling']]
        print(f"  sibling        Hamming range:        {min(hams)}-{max(hams)}")
    if "unrelated" in results and results["unrelated"]:
        min_unrel = min(r['hamming'] for r in results['unrelated'])
        print(f"  unrelated      min Hamming distance: {min_unrel}")
    print()
    print("Treat thresholds as candidate-generation hints, not as identity proofs.")
    print()

    conn.close()
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--target", default="sgf_lexicon.db")
    p.add_argument("--embedding-method", required=True,
                   help="Which embedder's fingerprints to calibrate")
    args = p.parse_args()

    db_path = Path(args.target)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    return run_calibration(db_path, args.embedding_method)


if __name__ == "__main__":
    sys.exit(main())
