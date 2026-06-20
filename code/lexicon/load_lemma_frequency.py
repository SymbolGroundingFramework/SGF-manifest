#!/usr/bin/env python3
"""
load_lemma_frequency.py

Stage 2.5 of the SGF lexicon build pipeline.

Populates the lemma_frequency table with real-world English usage
frequency, sourced by default from the OpenSubtitles 2018 English
unigram counts (hermitdave/FrequencyWords on GitHub).

The lemma_frequency table drives the --top-n and --min-freq priority
flags in compute_embeddings.py and compute_sense_fingerprints.py, letting you
process the most common words first and leave the long tail for later.

Sources:
    --source opensubtitles  (default)
        Downloads en_full.txt from hermitdave/FrequencyWords.
        ~30 MB, ~1M lemmas, real conversational + written usage.

    --source glosses
        Self-contained fallback: tokenizes sgf_lexicon.gloss to build a
        rough usage count. Correlates ~0.4-0.5 with real usage. Use only
        if the OpenSubtitles download is blocked.

    --source file --path some_file.txt
        Load from a local file in the same two-column format that
        FrequencyWords ships: "<lemma> <count>" per line.

USAGE
-----
    python load_lemma_frequency.py --target sgf_lexicon.db
    python load_lemma_frequency.py --target sgf_lexicon.db --source glosses
    python load_lemma_frequency.py --target sgf_lexicon.db --source file --path my_freq.txt

The table is rebuilt on every run (idempotent).
"""

import argparse
import re
import sqlite3
import sys
import urllib.request
from collections import Counter
from pathlib import Path

OPENSUBTITLES_URL = (
    "https://raw.githubusercontent.com/hermitdave/FrequencyWords/"
    "master/content/2018/en/en_full.txt"
)

# Token pattern for gloss-frequency fallback: letters + apostrophes,
# matching the kind of word we'd want to rank.
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z']*[A-Za-z]|[A-Za-z]")

# Stopwords to skip in the gloss-frequency fallback.
STOPWORDS = frozenset("""
a an the and or but if of in on at to from with by for as is are was were be been being
this that these those it its his her him hers their theirs they them
one two three four five six seven eight nine ten
not no yes also too very more most less least much many few several some any all
which what who whom whose where when why how
do does did doing done can could will would shall should may might must
have has had having i you we us our ours your yours my mine me
""".split())


def ensure_table(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS lemma_frequency (
            lemma            TEXT PRIMARY KEY,
            frequency_rank   INTEGER,
            frequency_count  INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_lf_rank ON lemma_frequency(frequency_rank);
    """)
    conn.commit()


def load_from_opensubtitles(cache_path):
    """Download (if needed) and parse the OpenSubtitles 2018 English file.

    Returns list of (lemma, count) tuples in descending count order.
    """
    if not cache_path.exists():
        print(f"Downloading {OPENSUBTITLES_URL} ...")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(OPENSUBTITLES_URL, str(cache_path))
        print(f"  cached: {cache_path}")
    else:
        print(f"Using cached file: {cache_path}")
    return load_from_file(cache_path)


def load_from_file(path):
    """Parse a two-column 'lemma count' file. Returns list[(lemma, count)]."""
    print(f"Parsing {path} ...")
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            lemma = parts[0].lower()
            try:
                count = int(parts[1])
            except ValueError:
                continue
            if count <= 0:
                continue
            rows.append((lemma, count))
    rows.sort(key=lambda r: -r[1])
    print(f"  parsed {len(rows):,} lemmas")
    return rows


def load_from_glosses(conn):
    """Tokenize sgf_lexicon.gloss to build a rough usage count.

    Returns list[(lemma, count)] in descending count order.
    """
    print("Scanning sgf_lexicon.gloss for token counts ...")
    cur = conn.cursor()
    cur.execute("SELECT gloss FROM sgf_lexicon WHERE gloss IS NOT NULL")
    counter = Counter()
    n_rows = 0
    for (gloss,) in cur:
        n_rows += 1
        for tok in TOKEN_RE.findall(gloss):
            low = tok.lower()
            if low in STOPWORDS or len(low) < 2:
                continue
            counter[low] += 1
    print(f"  scanned {n_rows:,} glosses, {len(counter):,} distinct tokens")
    rows = sorted(counter.items(), key=lambda kv: -kv[1])
    return rows


def populate(conn, rows):
    """Write rows into lemma_frequency, assigning ranks 1..N."""
    print(f"Writing {len(rows):,} rows to lemma_frequency ...")
    conn.execute("DELETE FROM lemma_frequency")
    conn.executemany(
        "INSERT INTO lemma_frequency (lemma, frequency_rank, frequency_count) "
        "VALUES (?, ?, ?)",
        [(lemma, rank, count) for rank, (lemma, count) in enumerate(rows, start=1)]
    )
    conn.commit()
    print("  done.")


def coverage_report(conn):
    """Print how many sgf_lexicon lemmas have a frequency rank."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(DISTINCT lemma) FROM sgf_lexicon")
    total = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(DISTINCT sl.lemma)
        FROM sgf_lexicon sl
        JOIN lemma_frequency lf ON lf.lemma = LOWER(sl.lemma)
    """)
    matched = cur.fetchone()[0]
    pct = (100.0 * matched / total) if total else 0
    print()
    print("Coverage:")
    print(f"  distinct lemmas in sgf_lexicon : {total:,}")
    print(f"  with a frequency rank          : {matched:,} ({pct:.1f}%)")
    print(f"  without (sort to long tail)    : {total - matched:,} ({100 - pct:.1f}%)")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--target", default="sgf_lexicon.db")
    p.add_argument("--source", choices=["opensubtitles", "glosses", "file"],
                   default="opensubtitles")
    p.add_argument("--path", default=None,
                   help="With --source file, path to local 'lemma count' file")
    p.add_argument("--cache-dir", default="data",
                   help="Where to cache the OpenSubtitles download")
    args = p.parse_args()

    db_path = Path(args.target)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    print(f"Target: {db_path.resolve()}")
    print(f"Source: {args.source}")
    print()

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")

    try:
        ensure_table(conn)

        if args.source == "opensubtitles":
            cache_path = Path(args.cache_dir) / "en_full.txt"
            rows = load_from_opensubtitles(cache_path)
        elif args.source == "glosses":
            rows = load_from_glosses(conn)
        elif args.source == "file":
            if not args.path:
                print("--source file requires --path", file=sys.stderr)
                return 1
            rows = load_from_file(Path(args.path))
        else:
            print(f"Unknown source: {args.source}", file=sys.stderr)
            return 1

        if not rows:
            print("No frequency rows to load.", file=sys.stderr)
            return 1

        populate(conn, rows)
        coverage_report(conn)
    finally:
        conn.close()

    print()
    print("Done. Frequency table populated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
