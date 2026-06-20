"""build_lemma_forms.py -- populate lemma_form from wiktionary_source.

For every entry in wiktionary_source, parse forms_json and write one
row per (form, lemma, pos_simple) triple to the lemma_form table.
Forms point back to the entry's word as the lemma.

Idempotent. Re-running it skips rows already present (PRIMARY KEY
collision -> INSERT OR IGNORE).

Usage:
    python build_lemma_forms.py --target sgf_lexicon.db

What this enables:
    - `--lemma-restrict burned` resolves to all senses of `burn`.
    - Query-side preprocessing in the search server can stem/lemmatize
      query terms before the lemma_restrict filter fires.
    - Future type-coercion rules can check whether an unknown form has
      a known lemma before giving up.

Notes:
    - Forms are entry-level in Wiktionary; one entry has many senses,
      all sharing the same forms list. We de-dupe per
      (form, lemma, pos_simple) so the table stays compact.
    - We do NOT include the lemma as a form of itself (no
      `burn -> burn` row); that would just bloat the table.
    - tag-less forms are still loaded; the tags column may be NULL.
"""
import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import pos_converter


def ensure_lemma_form_table(conn):
    """Create the table + indexes if missing. Same DDL as schema.sql."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS lemma_form (
            form           TEXT    NOT NULL,
            lemma          TEXT    NOT NULL,
            pos_simple     TEXT    NOT NULL,
            tags_json      TEXT,
            source_entry_id INTEGER,
            PRIMARY KEY (form, lemma, pos_simple)
        );
        CREATE INDEX IF NOT EXISTS idx_lemma_form_form  ON lemma_form(form);
        CREATE INDEX IF NOT EXISTS idx_lemma_form_lemma ON lemma_form(lemma);
    """)


def parse_forms_blob(blob):
    """Yield (form_lower, tags_json_str_or_None) for each parsed entry.

    Defensive: returns an empty iterator on malformed JSON or unexpected
    shapes rather than raising.
    """
    if not blob:
        return
    try:
        arr = json.loads(blob)
    except (json.JSONDecodeError, TypeError):
        return
    if not isinstance(arr, list):
        return
    for item in arr:
        if not isinstance(item, dict):
            continue
        form = item.get("form")
        if not form or not isinstance(form, str):
            continue
        form_l = form.strip().lower()
        if not form_l:
            continue
        tags = item.get("tags")
        tags_str = (json.dumps(tags, ensure_ascii=False)
                    if isinstance(tags, list) else None)
        yield form_l, tags_str


def build(conn, dry_run=False):
    """Walk distinct (source_entry_id, word, pos, forms_json) rows
    in wiktionary_source and INSERT OR IGNORE one lemma_form row per
    (form, lemma, pos_simple) triple."""
    ensure_lemma_form_table(conn)

    cur = conn.cursor()
    # DISTINCT to avoid scanning the same entry once per sense.
    cur.execute("""
        SELECT DISTINCT source_entry_id, word, pos, forms_json
          FROM wiktionary_source
         WHERE forms_json IS NOT NULL AND forms_json != ''
    """)
    rows = cur.fetchall()
    print(f"Entries with forms_json: {len(rows):,}")

    write_cur = conn.cursor()
    inserted = 0
    skipped_self = 0
    skipped_dup = 0
    parsed_forms = 0
    t0 = time.time()
    last_report = t0
    batch = []
    BATCH_SIZE = 5000

    for (entry_id, word, pos_raw, forms_json) in rows:
        word_l = (word or "").strip().lower()
        if not word_l:
            continue
        pos_simple = pos_converter.to_simple(pos_raw)
        for form_l, tags_str in parse_forms_blob(forms_json):
            parsed_forms += 1
            if form_l == word_l:
                skipped_self += 1
                continue
            batch.append((form_l, word_l, pos_simple, tags_str, entry_id))
            if len(batch) >= BATCH_SIZE:
                if not dry_run:
                    write_cur.executemany("""
                        INSERT OR IGNORE INTO lemma_form
                            (form, lemma, pos_simple, tags_json,
                             source_entry_id)
                        VALUES (?, ?, ?, ?, ?)
                    """, batch)
                    skipped_dup += len(batch) - write_cur.rowcount
                    inserted += write_cur.rowcount
                batch = []

                now = time.time()
                if now - last_report >= 2.0:
                    elapsed = now - t0
                    rate = inserted / elapsed if elapsed > 0 else 0
                    print(f"  inserted {inserted:,} rows  ({rate:,.0f}/s)")
                    last_report = now

    if batch and not dry_run:
        write_cur.executemany("""
            INSERT OR IGNORE INTO lemma_form
                (form, lemma, pos_simple, tags_json, source_entry_id)
            VALUES (?, ?, ?, ?, ?)
        """, batch)
        skipped_dup += len(batch) - write_cur.rowcount
        inserted += write_cur.rowcount

    if not dry_run:
        conn.commit()

    elapsed = time.time() - t0
    print()
    print("=" * 60)
    print("LEMMA_FORM LOAD COMPLETE")
    print("=" * 60)
    print(f"  forms parsed              : {parsed_forms:,}")
    print(f"  skipped (self-form)       : {skipped_self:,}")
    print(f"  inserted this run         : {inserted:,}")
    print(f"  skipped (already present) : {skipped_dup:,}")

    cur.execute("SELECT COUNT(*) FROM lemma_form")
    total = cur.fetchone()[0]
    print(f"  total rows in lemma_form  : {total:,}")
    print(f"  elapsed                   : {elapsed:.1f}s")
    print("=" * 60)
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--target", default="sgf_lexicon.db")
    p.add_argument("--dry-run", action="store_true",
                   help="Parse and count; do not write.")
    args = p.parse_args()

    db_path = Path(args.target)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        return build(conn, dry_run=args.dry_run)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
