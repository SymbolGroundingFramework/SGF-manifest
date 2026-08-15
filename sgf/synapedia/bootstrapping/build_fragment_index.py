#!/usr/bin/env python3
"""
build_fragment_index.py — Build fragment and alias index tables for Synapedia Search v3.

Creates three index tables that enable fast lemma lookup without loading
all embeddings into RAM:

  1. lemma_fragment: Exact word fragments from every lemma
  2. lemma_fragment_stemmed: Porter-stemmed word fragments  
  3. lemma_alias: Rule-based aliases + synonym aliases (enabled by default)

Improvements over v1:
  - ASCII-folding for accented lemmas (cliché -> cliche)
  - Punctuation-stripped aliases (C++ -> cplusplus, .NET -> net)
  - Full-word synonym aliases from Wiktionary (synonyms_json) — enabled by default
  - Special aliases for programming languages (C# -> csharp, F# -> fsharp)
  - Alias types ('rule' vs 'synonym') for stats/reporting
  - --self-test mode for virtual query simulation

Usage:
    # Full rebuild with synonyms (RECOMMENDED)
    python build_fragment_index.py --db synapedia.db

    # Fast rebuild without synonyms
    python build_fragment_index.py --db synapedia.db --no-synonyms

    # Incremental update (synonyms off unless --include-synonyms is passed)
    python build_fragment_index.py --db synapedia.db --entry-ids 12345,67890

    # Stats
    python build_fragment_index.py --db synapedia.db --stats

    # Self-test on tiny in-memory corpus
    python build_fragment_index.py --self-test
"""

import argparse
import json
import re
import sqlite3
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# =====================================================================
# Porter stemmer (inline from bm25_score.py)
# =====================================================================

_VOWELS = set("aeiou")


def _is_consonant(word, i):
    ch = word[i]
    if ch in _VOWELS:
        return False
    if ch == "y":
        return True if i == 0 else not _is_consonant(word, i - 1)
    return True


def _measure(stem):
    m = 0
    n = len(stem)
    i = 0
    while i < n and _is_consonant(stem, i):
        i += 1
    while i < n:
        while i < n and not _is_consonant(stem, i):
            i += 1
        if i >= n:
            break
        while i < n and _is_consonant(stem, i):
            i += 1
        m += 1
    return m


def _contains_vowel(stem):
    for i in range(len(stem)):
        if not _is_consonant(stem, i):
            return True
    return False


def _ends_double_consonant(word):
    n = len(word)
    if n < 2:
        return False
    if word[-1] != word[-2]:
        return False
    return _is_consonant(word, n - 1)


def _ends_cvc(word):
    n = len(word)
    if n < 3:
        return False
    if not _is_consonant(word, n - 3):
        return False
    if _is_consonant(word, n - 2):
        return False
    if not _is_consonant(word, n - 1):
        return False
    if word[-1] in ("w", "x", "y"):
        return False
    return True


def porter_stem(word):
    if len(word) <= 2:
        return word

    if word.endswith("sses"):
        word = word[:-2]
    elif word.endswith("ies"):
        word = word[:-2]
    elif word.endswith("ss"):
        pass
    elif word.endswith("s"):
        word = word[:-1]

    flag_1b = False
    if word.endswith("eed"):
        stem = word[:-3]
        if _measure(stem) > 0:
            word = word[:-1]
    elif word.endswith("ed"):
        stem = word[:-2]
        if _contains_vowel(stem):
            word = stem
            flag_1b = True
    elif word.endswith("ing"):
        stem = word[:-3]
        if _contains_vowel(stem):
            word = stem
            flag_1b = True

    if flag_1b:
        if word.endswith(("at", "bl", "iz")):
            word = word + "e"
        elif _ends_double_consonant(word) and not word.endswith(("l", "s", "z")):
            word = word[:-1]
        elif _measure(word) == 1 and _ends_cvc(word):
            word = word + "e"

    if word.endswith("y"):
        stem = word[:-1]
        if _contains_vowel(stem):
            word = stem + "i"

    step2_map = [
        ("ational", "ate"), ("tional", "tion"), ("enci", "ence"),
        ("anci", "ance"), ("izer", "ize"), ("abli", "able"),
        ("alli", "al"), ("entli", "ent"), ("eli", "e"),
        ("ousli", "ous"), ("ization", "ize"), ("ation", "ate"),
        ("ator", "ate"), ("alism", "al"), ("iveness", "ive"),
        ("fulness", "ful"), ("ousness", "ous"), ("aliti", "al"),
        ("iviti", "ive"), ("biliti", "ble"),
    ]
    for suffix, replacement in step2_map:
        if word.endswith(suffix):
            stem = word[:-len(suffix)]
            if _measure(stem) > 0:
                word = stem + replacement
            break

    step3_map = [
        ("icate", "ic"), ("ative", ""), ("alize", "al"),
        ("iciti", "ic"), ("ical", "ic"), ("ful", ""), ("ness", ""),
    ]
    for suffix, replacement in step3_map:
        if word.endswith(suffix):
            stem = word[:-len(suffix)]
            if _measure(stem) > 0:
                word = stem + replacement
            break

    step4_suffixes = [
        "al", "ance", "ence", "er", "ic", "able", "ible", "ant",
        "ement", "ment", "ent", "ion", "ou", "ism", "ate", "iti",
        "ous", "ive", "ize",
    ]
    for suffix in sorted(step4_suffixes, key=len, reverse=True):
        if word.endswith(suffix):
            stem = word[:-len(suffix)]
            if _measure(stem) > 1:
                if suffix == "ion":
                    if stem and stem[-1] in ("s", "t"):
                        word = stem
                else:
                    word = stem
            break

    if word.endswith("e"):
        stem = word[:-1]
        m = _measure(stem)
        if m > 1 or (m == 1 and not _ends_cvc(stem)):
            word = stem

    if _measure(word) > 1 and _ends_double_consonant(word) and word.endswith("l"):
        word = word[:-1]

    return word


# =====================================================================
# Alias generation (improved)
# =====================================================================

TITLES = frozenset([
    "dr.", "dr", "mr.", "mr", "mrs.", "mrs", "ms.", "ms",
    "president", "saint", "st.", "st", "sir", "lord", "lady",
    "prof.", "prof", "professor", "reverend", "rev.", "rev",
    "captain", "capt.", "general", "gen.", "admiral", "adm.",
    "senator", "sen.", "governor", "gov.", "representative", "rep.",
    "judge", "chancellor", "ambassador", "amb.",
])

SUFFIXES = [
    ", jr.", ", jr", ", sr.", ", sr", ", iii", ", ii", ", iv",
    ", ph.d.", ", phd", ", md", ", esq.", ", esq",
    ", j.d.", ", m.d.", ", ph.d", ", d.d.s.",
]

MINOR_WORDS = frozenset([
    "the", "a", "an", "of", "in", "on", "at", "for", "and",
    "to", "with", "by", "from", "de", "la", "le", "del", "van", "von",
])

# Special programming-language aliases
PROGRAMMING_LANG_ALIASES = {
    "c++": "cplusplus",
    "c#": "csharp",
    "f#": "fsharp",
    "r#": "rsharp",
    "objective-c": "objectivec",
}


def _ascii_fold(text: str) -> str:
    """NFKD + ASCII ignore → strips diacritics."""
    s = unicodedata.normalize('NFKD', text)
    return s.encode('ascii', 'ignore').decode('ascii')


def generate_aliases(lemma: str) -> List[str]:
    """
    Generate all plausible alias variants for a given lemma.

    Returns a list of unique alias strings (lowercased, stripped).
    Each alias is at least 2 characters long.
    """
    text = _ascii_fold(lemma).lower().strip()
    if not text or len(text) < 2:
        return []

    aliases = set()
    aliases.add(text)  # Always include the original

    # Special programming-language aliases
    if text in PROGRAMMING_LANG_ALIASES:
        aliases.add(PROGRAMMING_LANG_ALIASES[text])

    # 1. Handle "The" prefix
    if text.startswith("the "):
        aliases.add(text[4:])

    # 2. Handle commas (inverted names)
    if "," in text:
        parts = text.split(",", 1)
        aliases.add(f"{parts[1].strip()} {parts[0].strip()}")

    # 3. Handle periods in abbreviations
    if "." in text:
        no_periods = text.replace(".", "")
        aliases.add(no_periods)
        no_spaces = no_periods.replace(" ", "")
        if len(no_spaces) >= 2:
            aliases.add(no_spaces)

    # 4. Handle common titles (prefix and suffix)
    words = text.split()
    for title in TITLES:
        if text.startswith(title + " "):
            without_title = text[len(title) + 1:]
            if len(without_title) >= 2:
                aliases.add(without_title)
        if text.endswith(", " + title):
            without_suffix = text[:-(len(title) + 2)]
            if len(without_suffix) >= 2:
                aliases.add(without_suffix)

    # 5. Handle suffixes: Jr., Sr., III, etc.
    for suffix in SUFFIXES:
        if text.endswith(suffix):
            without_suffix = text[:-len(suffix)]
            if len(without_suffix) >= 2:
                aliases.add(without_suffix)

    # 6. Generate acronym from first letters
    significant_words = [w for w in words if w not in MINOR_WORDS]
    if len(significant_words) >= 2:
        acronym = "".join(w[0] for w in significant_words if w[0].isalpha())
        if len(acronym) >= 2:
            aliases.add(acronym)

    # 7. Expand single-letter initials
    if len(words) >= 3:
        for i, w in enumerate(words):
            if len(w) == 1 and w.isalpha():
                break
        else:
            abbr = []
            for w in words:
                if w not in MINOR_WORDS:
                    abbr.append(w[0] if w else "")
            if len(abbr) >= 2:
                abbreviated = " ".join(abbr)
                if abbreviated != text and len(abbreviated) >= 2:
                    aliases.add(abbreviated)

    # 8. Handle apostrophes: "O'Brien" → "obrien"
    if "'" in text:
        aliases.add(text.replace("'", ""))

    # 9. Handle hyphens: "long-term" → "longterm", "long term"
    if "-" in text:
        aliases.add(text.replace("-", ""))
        aliases.add(text.replace("-", " "))

    # 10. Pure alphanumeric stripped form (handles C++, 3D, .NET)
    stripped = re.sub(r"[^a-z0-9]+", "", text)
    if len(stripped) >= 2 and stripped != text:
        aliases.add(stripped)

    # Filter: minimum 2 chars, strip whitespace
    return [a.strip() for a in aliases if len(a.strip()) >= 2]


def tokenize_lemma(lemma: str) -> List[str]:
    """Split lemma into lowercase word fragments."""
    if not lemma:
        return []
    text = lemma.lower().strip()
    text = text.replace("-", " ")
    words = re.split(r'[^a-z0-9\']+', text)
    return [w.strip("'") for w in words if w.strip("'") and len(w.strip("'")) >= 2]


# =====================================================================
# Database helpers
# =====================================================================

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS lemma_fragment (
    fragment TEXT NOT NULL,
    entry_id INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (fragment, entry_id)
);

CREATE TABLE IF NOT EXISTS lemma_fragment_stemmed (
    stem TEXT NOT NULL,
    entry_id INTEGER NOT NULL,
    original_fragment TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (stem, entry_id)
);

CREATE TABLE IF NOT EXISTS lemma_alias (
    alias TEXT NOT NULL,
    entry_id INTEGER NOT NULL,
    alias_type TEXT DEFAULT 'rule',
    PRIMARY KEY (alias, entry_id)
);

CREATE INDEX IF NOT EXISTS idx_lemma_fragment ON lemma_fragment(fragment);
CREATE INDEX IF NOT EXISTS idx_lemma_fragment_stemmed ON lemma_fragment_stemmed(stem);
CREATE INDEX IF NOT EXISTS idx_lemma_alias ON lemma_alias(alias);
"""


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


# =====================================================================
# Core indexing functions
# =====================================================================

def _parse_synonyms(synonyms_json: str, max_synonyms: int) -> List[str]:
    """Parse a JSON array of synonyms; return capped list of clean strings."""
    if not synonyms_json:
        return []
    try:
        data = json.loads(synonyms_json)
        if not isinstance(data, list):
            return []
        out = []
        for item in data:
            if isinstance(item, str):
                s = item.strip().lower()
                if s and len(s) >= 2 and s not in out:
                    out.append(s)
            elif isinstance(item, dict):
                s = str(item.get('synonym', '')).strip().lower()
                if s and len(s) >= 2 and s not in out:
                    out.append(s)
            if len(out) >= max_synonyms:
                break
        return out
    except (json.JSONDecodeError, TypeError):
        return []


def index_entries(conn: sqlite3.Connection, entry_ids: List[int],
                  include_synonyms: bool = True, max_synonyms: int = 10) -> Dict[str, int]:
    """
    Index specific entries into the fragment and alias tables.

    Args:
        conn: Open SQLite connection to synapedia.db
        entry_ids: List of entry IDs to index
        include_synonyms: If True, read synonyms_json and add as aliases (default True)
        max_synonyms: Max synonyms per entry to add

    Returns:
        Dict with counts: {"fragments": N, "stems": N, "aliases": N}
    """
    cur = conn.cursor()
    counts = {"fragments": 0, "stems": 0, "aliases": 0}

    if not entry_ids:
        return counts

    placeholders = ",".join("?" * len(entry_ids))
    if include_synonyms:
        cur.execute(f"""
            SELECT entry_id, lemma, synonyms_json FROM synapedia_entry
            WHERE entry_id IN ({placeholders})
        """, entry_ids)
    else:
        cur.execute(f"""
            SELECT entry_id, lemma, NULL FROM synapedia_entry
            WHERE entry_id IN ({placeholders})
        """, entry_ids)

    rows = cur.fetchall()
    if not rows:
        return counts

    fragment_rows = []
    stem_rows = []
    alias_rows = []

    for entry_id, lemma, synonyms_json in rows:
        if not lemma:
            continue

        words = tokenize_lemma(lemma)

        for pos, word in enumerate(words):
            fragment_rows.append((word, entry_id, pos))
            stem = porter_stem(word)
            stem_rows.append((stem, entry_id, word, pos))

        # Rule-based aliases
        for alias in generate_aliases(lemma):
            alias_rows.append((alias, entry_id, "rule"))

        # Synonym aliases (default on)
        if include_synonyms:
            for syn in _parse_synonyms(synonyms_json, max_synonyms):
                alias_rows.append((syn, entry_id, "synonym"))

    # Batch inserts
    if fragment_rows:
        cur.executemany("""
            INSERT OR IGNORE INTO lemma_fragment (fragment, entry_id, position)
            VALUES (?, ?, ?)
        """, fragment_rows)
        counts["fragments"] = cur.rowcount

    if stem_rows:
        cur.executemany("""
            INSERT OR IGNORE INTO lemma_fragment_stemmed (stem, entry_id, original_fragment, position)
            VALUES (?, ?, ?, ?)
        """, stem_rows)
        counts["stems"] = cur.rowcount

    if alias_rows:
        cur.executemany("""
            INSERT OR IGNORE INTO lemma_alias (alias, entry_id, alias_type)
            VALUES (?, ?, ?)
        """, alias_rows)
        counts["aliases"] = cur.rowcount

    conn.commit()
    return counts


def remove_entries(conn: sqlite3.Connection, entry_ids: List[int]) -> None:
    if not entry_ids:
        return
    cur = conn.cursor()
    placeholders = ",".join("?" * len(entry_ids))
    cur.execute(f"DELETE FROM lemma_fragment WHERE entry_id IN ({placeholders})", entry_ids)
    cur.execute(f"DELETE FROM lemma_fragment_stemmed WHERE entry_id IN ({placeholders})", entry_ids)
    cur.execute(f"DELETE FROM lemma_alias WHERE entry_id IN ({placeholders})", entry_ids)
    conn.commit()


# =====================================================================
# Full rebuild
# =====================================================================

def full_rebuild(conn: sqlite3.Connection, batch_size: int = 5000,
                 include_synonyms: bool = True, max_synonyms: int = 10) -> Dict[str, int]:
    cur = conn.cursor()
    conn.executescript(SCHEMA_SQL)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM synapedia_entry WHERE lemma IS NOT NULL AND lemma != ''")
    total = cur.fetchone()[0]
    print(f"Total entries to index: {total:,}")

    if total == 0:
        return {"fragments": 0, "stems": 0, "aliases": 0}

    t0 = time.time()
    offset = 0
    total_counts = {"fragments": 0, "stems": 0, "aliases": 0}

    while offset < total:
        cur.execute("""
            SELECT entry_id, lemma FROM synapedia_entry
            WHERE lemma IS NOT NULL AND lemma != ''
            ORDER BY entry_id
            LIMIT ? OFFSET ?
        """, (batch_size, offset))

        rows = cur.fetchall()
        if not rows:
            break

        entry_ids = [r[0] for r in rows]
        counts = index_entries(conn, entry_ids,
                               include_synonyms=include_synonyms,
                               max_synonyms=max_synonyms)

        for k, v in counts.items():
            total_counts[k] += v

        offset += batch_size
        elapsed = time.time() - t0
        rate = offset / elapsed if elapsed > 0 else 0
        print(f"  {offset:,}/{total:,} entries | "
              f"{total_counts['fragments']:,} fragments | "
              f"{total_counts['stems']:,} stems | "
              f"{total_counts['aliases']:,} aliases | "
              f"{rate:,.0f} entries/s", end="\r")

    elapsed = time.time() - t0
    print(f"\n  Done in {elapsed:.1f}s ({total / elapsed if elapsed else 0:,.0f} entries/s)")
    return total_counts


# =====================================================================
# Stats
# =====================================================================

def print_stats(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    print("\n=== Index Table Statistics ===\n")

    for table in ["lemma_fragment", "lemma_fragment_stemmed", "lemma_alias"]:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        cur.execute(f"SELECT COUNT(DISTINCT entry_id) FROM {table}")
        entries = cur.fetchone()[0]
        print(f"  {table}: {count:,} rows, {entries:,} unique entries")

    cur.execute("SELECT COUNT(*) FROM synapedia_entry WHERE lemma IS NOT NULL AND lemma != ''")
    total_entries = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT entry_id) FROM lemma_fragment")
    frag_entries = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT entry_id) FROM lemma_alias")
    alias_entries = cur.fetchone()[0]

    print(f"\n  Total entries with lemmas: {total_entries:,}")
    print(f"  Entries with fragments:    {frag_entries:,} ({frag_entries/total_entries*100:.1f}%)")
    print(f"  Entries with aliases:      {alias_entries:,} ({alias_entries/total_entries*100:.1f}%)")

    try:
        cur.execute("SELECT alias_type, COUNT(*) FROM lemma_alias GROUP BY alias_type")
        print("\n  Alias types:")
        for atype, cnt in cur.fetchall():
            print(f"    {atype:<12} {cnt:>12,}")
    except sqlite3.OperationalError:
        pass

    print("\n  Most common fragments:")
    cur.execute("""
        SELECT fragment, COUNT(DISTINCT entry_id) as cnt
        FROM lemma_fragment
        GROUP BY fragment
        ORDER BY cnt DESC
        LIMIT 20
    """)
    for row in cur.fetchall():
        print(f"    {row[0]:25s}: {row[1]:>8,} entries")

    print("\n  Most common aliases:")
    cur.execute("""
        SELECT alias, COUNT(DISTINCT entry_id) as cnt
        FROM lemma_alias
        GROUP BY alias
        ORDER BY cnt DESC
        LIMIT 20
    """)
    for row in cur.fetchall():
        print(f"    {row[0]:25s}: {row[1]:>8,} entries")

    print("\n  Sample aliases that differ from lemma:")
    cur.execute("""
        SELECT a.alias, e.lemma
        FROM lemma_alias a
        JOIN synapedia_entry e ON e.entry_id = a.entry_id
        WHERE a.alias != LOWER(TRIM(e.lemma))
          AND a.alias NOT LIKE '% %'
          AND LENGTH(a.alias) >= 3
        LIMIT 20
    """)
    for row in cur.fetchall():
        print(f"    {row[0]:25s} ← {row[1]}")


# =====================================================================
# Self-test / virtual simulation
# =====================================================================

def run_self_test() -> None:
    """
    Build a tiny in-memory index and run queries to demonstrate behavior
    on happy paths and edge cases.
    """
    print("=== SELF TEST / VIRTUAL SIMULATION ===")
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_SQL)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE synapedia_entry (
            entry_id INTEGER PRIMARY KEY,
            lemma TEXT,
            synonyms_json TEXT
        )
    """)

    test_entries = [
        (1, "bank", '["financial institution", "river bank"]'),
        (2, "United States of America", '["USA", "US"]'),
        (3, "C++", '["C plus plus"]'),
        (4, "U.S.A.", '["USA"]'),
        (5, "long-term", '[]'),
        (6, "cliché", '[]'),
        (7, "New York", '["NYC", "Big Apple"]'),
        (8, "Martin Luther King, Jr.", '[]'),
        (9, "The Beatles", '[]'),
        (10, "3D", '[]'),
        (11, "O'Brien", '[]'),
        (12, "Objective-C", '[]'),
        (13, "C#", '["C sharp"]'),
        (14, ".NET", '["dotnet"]'),
    ]
    cur.executemany("INSERT INTO synapedia_entry VALUES (?,?,?)", test_entries)
    conn.commit()

    ids = [e[0] for e in test_entries]
    counts = index_entries(conn, ids, include_synonyms=True, max_synonyms=10)
    print(f"Indexed: {counts}")

    def alias_hit(query):
        cur.execute("SELECT DISTINCT entry_id FROM lemma_alias WHERE alias = ?", (query,))
        return sorted(r[0] for r in cur.fetchall())

    def fragment_hit(query):
        tokens = query.lower().split()
        if not tokens:
            return []
        rarest = None
        best = 10**9
        for t in tokens:
            cur.execute("SELECT COUNT(DISTINCT entry_id) FROM lemma_fragment WHERE fragment=?", (t,))
            cnt = cur.fetchone()[0]
            if cnt > 0 and cnt < best:
                best = cnt
                rarest = t
        if rarest is None:
            return []
        cur.execute("SELECT entry_id FROM lemma_fragment WHERE fragment=?", (rarest,))
        ids = [r[0] for r in cur.fetchall()]
        for t in tokens:
            if t != rarest:
                cur.execute("SELECT entry_id FROM lemma_fragment WHERE fragment=?", (t,))
                tok_ids = {r[0] for r in cur.fetchall()}
                ids = [i for i in ids if i in tok_ids]
                if not ids:
                    break
        return sorted(ids)

    queries = [
        "bank", "USA", "united states", "c++", "u.s.a.", "longterm",
        "cliche", "new york city", "martin luther king", "the beatles",
        "3d", "c plus plus", "obrien", "objectivec", "csharp", "dotnet",
    ]

    print(f"\n{'Query':<22} {'Alias hits':<18} {'Fragment hits':<18}")
    print("-" * 58)
    for q in queries:
        a = alias_hit(q)
        f = fragment_hit(q)
        print(f"{q:<22} {str(a):<18} {str(f):<18}")

    conn.close()
    print("\nSelf-test complete.\n")


# =====================================================================
# CLI
# =====================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Build fragment and alias index tables for Synapedia Search v3"
    )
    parser.add_argument("--db", default="synapedia.db", help="Path to synapedia.db")
    parser.add_argument("--entry-ids", help="Comma-separated list of entry IDs to index incrementally")
    parser.add_argument("--remove-ids", help="Comma-separated list of entry IDs to remove from index")
    parser.add_argument("--stats", action="store_true", help="Print coverage statistics")
    parser.add_argument("--batch", type=int, default=5000, help="Batch size for full rebuild")
    parser.add_argument("--include-synonyms", dest="include_synonyms", action="store_true",
                        default=True,
                        help="Include synonym aliases (default: True)")
    parser.add_argument("--no-synonyms", dest="include_synonyms", action="store_false",
                        help="Disable synonym aliases for a faster rebuild")
    parser.add_argument("--max-synonyms", type=int, default=10,
                        help="Max synonyms per entry (default: 10)")
    parser.add_argument("--self-test", action="store_true",
                        help="Run virtual simulation on an in-memory corpus and exit")
    args = parser.parse_args()

    if args.self_test:
        run_self_test()
        return 0

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}", file=sys.stderr)
        return 1

    conn = get_connection(str(db_path))
    t0 = time.time()

    if args.stats:
        print_stats(conn)
        conn.close()
        return 0

    if args.remove_ids:
        entry_ids = [int(x.strip()) for x in args.remove_ids.split(",") if x.strip()]
        remove_entries(conn, entry_ids)
        print(f"Removed {len(entry_ids)} entries from index tables")
        conn.close()
        return 0

    if args.entry_ids:
        entry_ids = [int(x.strip()) for x in args.entry_ids.split(",") if x.strip()]
        counts = index_entries(conn, entry_ids,
                               include_synonyms=args.include_synonyms,
                               max_synonyms=args.max_synonyms)
        elapsed = time.time() - t0
        print(f"\nIncremental update for {len(entry_ids)} entries:")
        print(f"  Fragments: {counts['fragments']:,}")
        print(f"  Stems:      {counts['stems']:,}")
        print(f"  Aliases:    {counts['aliases']:,}")
        print(f"  Time:       {elapsed:.2f}s")
        conn.close()
        return 0

    # Full rebuild
    print(f"Building fragment/alias index for {db_path}")
    print(f"  Tables: lemma_fragment, lemma_fragment_stemmed, lemma_alias")
    if args.include_synonyms:
        print(f"  Synonyms:  enabled (default, max {args.max_synonyms} per entry)")
    else:
        print("  Synonyms:  disabled (--no-synonyms)")
    print()

    conn.executescript(SCHEMA_SQL)
    conn.commit()

    print("Clearing existing index data...")
    for table in ["lemma_fragment", "lemma_fragment_stemmed", "lemma_alias"]:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        cur.execute(f"DELETE FROM {table}")
        print(f"  {table}: {count:,} rows cleared")

    total_counts = full_rebuild(conn, args.batch,
                                include_synonyms=args.include_synonyms,
                                max_synonyms=args.max_synonyms)

    print(f"\n=== Rebuild Complete ===")
    print(f"  Total fragments: {total_counts['fragments']:,}")
    print(f"  Total stems:     {total_counts['stems']:,}")
    print(f"  Total aliases:   {total_counts['aliases']:,}")

    cur = conn.cursor()
    cur.execute("SELECT alias_type, COUNT(*) FROM lemma_alias GROUP BY alias_type")
    for atype, cnt in cur.fetchall():
        print(f"    {atype:<12} {cnt:>12,}")

    print_stats(conn)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())