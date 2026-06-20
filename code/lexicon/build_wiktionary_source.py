#!/usr/bin/env python3
"""
build_wiktionary_source.py

Stage 1 of the SGF lexicon build.

Creates sgf_lexicon.db and populates a single denormalized table called
wiktionary_source by JOINing the essential fields from a Wiktextract-derived
wiktionary_lexicon.db (produced by load_wiktionary_jsonl.py).

What gets pulled per sense:
    From entries:  id, word, pos, lang_code, etymology_text
    From senses:   id, sense_index, glosses_json, raw_glosses_json,
                   tags_json, categories_json, topics_json,
                   examples_json, linkages_json
    From forms:    aggregated into forms_json (entry-level)

One row per sense. Forms are entry-level so they repeat across senses of
the same entry; that is intentional for downstream simplicity.

Usage:
    python build_wiktionary_source.py \\
        --source wiktionary_lexicon.db \\
        --target sgf_lexicon.db \\
        [--lang-code en]

Resume-safe: rerunning skips senses whose source_sense_id is already
present in wiktionary_source.
"""

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

DEFAULT_LANG_CODE = "en"
COMMIT_EVERY = 2000

SOURCE_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA temp_store = MEMORY;
PRAGMA cache_size = -200000;

CREATE TABLE IF NOT EXISTS wiktionary_source (
    -- Identity (source-side IDs preserved as keys)
    source_sense_id     INTEGER PRIMARY KEY,
    source_entry_id     INTEGER NOT NULL,

    -- Entry-level fields
    word                TEXT NOT NULL,
    pos                 TEXT NOT NULL,
    lang_code           TEXT NOT NULL,
    etymology_text      TEXT,
    forms_json          TEXT,        -- aggregated list of forms for this entry

    -- Sense-level fields
    sense_index         INTEGER NOT NULL,
    glosses_json        TEXT,
    raw_glosses_json    TEXT,
    tags_json           TEXT,
    categories_json     TEXT,
    topics_json         TEXT,
    examples_json       TEXT,
    linkages_json       TEXT,

    -- Convenience: the LEAF gloss extracted by extract_first_gloss().
    -- For nested senses, this is the last element of the gloss list (the
    -- actual sense definition), not the first (which would be the parent
    -- heading like "A placename:"). Column name is historical -- the
    -- function used to return arr[0]. See extract_first_gloss() docstring.
    first_gloss         TEXT,

    -- Bookkeeping
    loaded_at           INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ws_word_pos ON wiktionary_source(word, pos);
CREATE INDEX IF NOT EXISTS idx_ws_word ON wiktionary_source(word);
CREATE INDEX IF NOT EXISTS idx_ws_lang ON wiktionary_source(lang_code);
CREATE INDEX IF NOT EXISTS idx_ws_entry ON wiktionary_source(source_entry_id);

CREATE TABLE IF NOT EXISTS build_meta (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);
"""


def ensure_source_indexes(src_conn: sqlite3.Connection) -> None:
    """
    Make sure the Wiktionary source DB has the indexes our JOINs depend on.
    load_lexicon.py creates idx_senses_entry and idx_forms_entry already;
    this is defensive and idempotent.
    """
    src_conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_senses_entry ON senses(entry_id);
        CREATE INDEX IF NOT EXISTS idx_forms_entry ON forms(entry_id);
    """)
    src_conn.commit()


def extract_first_gloss(raw_glosses_json: str | None, glosses_json: str | None) -> str | None:
    """
    Pick the actual sense definition out of Wiktextract's gloss list.

    Wiktextract stores each sense's gloss as a JSON LIST of breadcrumbs
    walking from the root sense heading down to the leaf sense. For a
    nested entry like:

        1. A placename:
           1.1 Several other locations in the United States, ...
               1.1.1 A small city, the county seat of Daviess County, Indiana.

    Wiktextract emits the leaf row with:

        glosses_json = [
            "A placename:",
            "Several other locations in the United States, ...",
            "A small city, the county seat of Daviess County, Indiana."
        ]

    The LAST element is the actual sense. Earlier elements are the parent
    headings. We want the leaf, not the root.

    An earlier version of this function returned arr[0] which produced
    huge data loss: 44 of Washington's 53 senses all collapsed to the
    literal string "A placename:", and 8 of Blue's noun senses all
    collapsed to "Blue clothing" despite each having distinct leaf
    content (uniform, sports team, umpire, sporting colors, etc.).

    raw_glosses_json is preferred over glosses_json because it preserves
    the leading parenthetical labels like "(archaic)" and "(politics)"
    that the microgloss stage needs.
    """
    for blob in (raw_glosses_json, glosses_json):
        if not blob:
            continue
        try:
            arr = json.loads(blob)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(arr, list) or not arr:
            continue
        # Walk the list backwards and return the last non-empty string.
        # This is the leaf sense; earlier elements are parent headings.
        for item in reversed(arr):
            if isinstance(item, str) and item.strip():
                return item.strip()
    return None


def fetch_forms_for_entry(src_conn: sqlite3.Connection, entry_id: int) -> str | None:
    """
    Aggregate all forms for an entry into a JSON array of
    {form, tags} dicts. Returns None if the entry has no forms.
    """
    cur = src_conn.cursor()
    cur.execute(
        """
        SELECT form, tags_json
        FROM forms
        WHERE entry_id = ? AND form IS NOT NULL AND form != ''
        ORDER BY form_index
        """,
        (entry_id,),
    )
    rows = cur.fetchall()
    if not rows:
        return None
    out = []
    for form, tags_json in rows:
        item = {"form": form}
        if tags_json:
            try:
                item["tags"] = json.loads(tags_json)
            except (json.JSONDecodeError, TypeError):
                pass
        out.append(item)
    return json.dumps(out, ensure_ascii=False)


def load_source(
    src_conn: sqlite3.Connection,
    tgt_conn: sqlite3.Connection,
    lang_code: str,
) -> tuple[int, int]:
    """
    JOIN entries + senses, aggregate forms per entry, and write one row
    per sense into wiktionary_source. Resume-safe.

    Returns (inserted, skipped_already_loaded).
    """
    src_cur = src_conn.cursor()
    tgt_cur = tgt_conn.cursor()
    forms_cache: dict[int, str | None] = {}  # entry_id -> forms_json

    # Build skip-set so reruns do not duplicate work.
    tgt_cur.execute("SELECT source_sense_id FROM wiktionary_source")
    already: set[int] = {row[0] for row in tgt_cur.fetchall()}
    if already:
        print(f"  resume: {len(already):,} senses already in wiktionary_source; will skip")

    query = """
        SELECT
            e.id              AS entry_id,
            e.word            AS word,
            e.pos             AS pos,
            e.lang_code       AS lang_code,
            e.etymology_text  AS etymology_text,
            s.id              AS sense_id,
            s.sense_index     AS sense_index,
            s.glosses_json    AS glosses_json,
            s.raw_glosses_json AS raw_glosses_json,
            s.tags_json       AS tags_json,
            s.categories_json AS categories_json,
            s.topics_json     AS topics_json,
            s.examples_json   AS examples_json,
            s.links_json      AS linkages_json
        FROM entries e
        JOIN senses s ON s.entry_id = e.id
        WHERE e.lang_code = ?
        ORDER BY e.id, s.sense_index
    """

    inserted = 0
    skipped = 0
    t_start = time.time()

    src_cur.execute(query, (lang_code,))
    while True:
        row = src_cur.fetchone()
        if row is None:
            break

        (entry_id, word, pos, src_lang_code, etymology_text,
         sense_id, sense_index, glosses_json, raw_glosses_json,
         tags_json, categories_json, topics_json,
         examples_json, linkages_json) = row

        if sense_id in already:
            skipped += 1
            continue

        # Forms are entry-level; cache them so we don't re-query per sense.
        if entry_id not in forms_cache:
            forms_cache[entry_id] = fetch_forms_for_entry(src_conn, entry_id)
        forms_json = forms_cache[entry_id]

        first_gloss = extract_first_gloss(raw_glosses_json, glosses_json)

        tgt_cur.execute("""
            INSERT INTO wiktionary_source (
                source_sense_id, source_entry_id,
                word, pos, lang_code, etymology_text, forms_json,
                sense_index, glosses_json, raw_glosses_json,
                tags_json, categories_json, topics_json,
                examples_json, linkages_json,
                first_gloss, loaded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sense_id, entry_id,
            word, pos, src_lang_code, etymology_text, forms_json,
            sense_index, glosses_json, raw_glosses_json,
            tags_json, categories_json, topics_json,
            examples_json, linkages_json,
            first_gloss, int(time.time()),
        ))

        inserted += 1
        if inserted % COMMIT_EVERY == 0:
            tgt_conn.commit()
            elapsed = time.time() - t_start
            rate = inserted / elapsed if elapsed > 0 else 0
            print(f"  loaded {inserted:,} senses ({rate:,.0f}/s, {len(forms_cache):,} entries cached)")

    tgt_conn.commit()
    return inserted, skipped


def write_meta(tgt_conn: sqlite3.Connection, key: str, value: str) -> None:
    cur = tgt_conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO build_meta (key, value) VALUES (?, ?)",
        (key, value),
    )
    tgt_conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Load Wiktionary essentials into sgf_lexicon.db.wiktionary_source")
    parser.add_argument("--source", default="wiktionary_lexicon.db", help="Path to Wiktextract SQLite DB (default: wiktionary_lexicon.db, produced by load_wiktionary_jsonl.py)")
    parser.add_argument("--target", default="sgf_lexicon.db", help="Path to output SGF lexicon DB")
    parser.add_argument("--lang-code", default=DEFAULT_LANG_CODE, help="Language to load (default: en)")
    args = parser.parse_args()

    src_path = Path(args.source)
    tgt_path = Path(args.target)

    if not src_path.exists():
        print(f"Source DB not found: {src_path}", file=sys.stderr)
        return 1

    print(f"Source: {src_path.resolve()}")
    print(f"Target: {tgt_path.resolve()}")
    print(f"Lang:   {args.lang_code}")
    print()

    src_conn = sqlite3.connect(src_path)
    tgt_conn = sqlite3.connect(tgt_path)

    try:
        print("Ensuring source indexes ...")
        ensure_source_indexes(src_conn)
        src_conn.execute("PRAGMA query_only = ON")

        print("Initializing target schema ...")
        tgt_conn.executescript(SOURCE_SCHEMA)
        tgt_conn.commit()

        write_meta(tgt_conn, "wiktionary_source_started_at", str(int(time.time())))
        write_meta(tgt_conn, "wiktionary_source_lang_code", args.lang_code)
        write_meta(tgt_conn, "wiktionary_source_db", str(src_path.resolve()))

        print("Loading senses ...")
        inserted, skipped = load_source(src_conn, tgt_conn, args.lang_code)

        write_meta(tgt_conn, "wiktionary_source_inserted", str(inserted))
        write_meta(tgt_conn, "wiktionary_source_skipped", str(skipped))
        write_meta(tgt_conn, "wiktionary_source_completed_at", str(int(time.time())))

        # Summary
        cur = tgt_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM wiktionary_source")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(DISTINCT source_entry_id) FROM wiktionary_source")
        entry_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM wiktionary_source WHERE forms_json IS NOT NULL")
        with_forms = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM wiktionary_source WHERE etymology_text IS NOT NULL")
        with_etym = cur.fetchone()[0]

        print()
        print("=" * 60)
        print("wiktionary_source LOAD COMPLETE")
        print("=" * 60)
        print(f"  total senses          : {total:,}")
        print(f"  distinct entries      : {entry_count:,}")
        print(f"  inserted this run     : {inserted:,}")
        print(f"  skipped (already)     : {skipped:,}")
        print(f"  rows with forms       : {with_forms:,}")
        print(f"  rows with etymology   : {with_etym:,}")
        print(f"  output db             : {tgt_path.resolve()}")
        print("=" * 60)

    finally:
        src_conn.close()
        tgt_conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
