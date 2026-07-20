#!/usr/bin/env python3
"""
load_synapedia_from_wiktionary — Load Wiktionary data into Synapedia.

Reads from wiktionary_raw.db (created by load_wiktionary_to_db.py)
and populates synapedia_entry with English entries.

- Only imports entries with language = 'en'
- Skips redirects
- Maps Wiktionary POS to UD tags
- Preserves gloss, examples, categories, synonyms, etc.
- Leaves canonical_id NULL (to be filled later by microgloss_v7_final.py)

Usage:
    python load_synapedia_from_wiktionary --wiktionary-db wiktionary.db --synapedia-db synapedia.db
"""

import argparse
import json
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

# ── POS mapping from Wiktionary (long form) to UD ────────────────────
WIKT_TO_UD = {
    "noun": "NOUN",
    "verb": "VERB",
    "adjective": "ADJ",
    "adverb": "ADV",
    "pronoun": "PRON",
    "preposition": "ADP",
    "conjunction": "CCONJ",
    "interjection": "INTJ",
    "determiner": "DET",
    "article": "DET",
    "numeral": "NUM",
    "particle": "PART",
    "proper_noun": "PROPN",
    "adposition": "ADP",
    "symbol": "SYM",
    "punctuation": "PUNCT",
    "character": "X",
    "letter": "X",
    "affix": "X",
    "prefix": "X",
    "suffix": "X",
    "infix": "X",
    "circumfix": "X",
    "interfix": "X",
    "contraction": "X",
    "abbreviation": "X",
    "initialism": "X",
    "acronym": "X",
    "phrase": "X",
    "idiom": "X",
    "proverb": "X",
    "unknown": "X",
}

def wiktionary_pos_to_ud(pos_str):
    """Map Wiktionary POS (may be comma-joined) to UD tag. Returns first known UD."""
    if not pos_str:
        return "NOUN"
    for p in pos_str.split(","):
        p = p.strip().lower()
        if p in WIKT_TO_UD:
            return WIKT_TO_UD[p]
    return "NOUN"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiktionary-db", required=True)
    ap.add_argument("--synapedia-db", default="synapedia.db")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--batch", type=int, default=5000)
    args = ap.parse_args()

    t0 = time.time()
    wik_path = Path(args.wiktionary_db).resolve()
    syn_path = Path(args.synapedia_db).resolve()

    if not wik_path.exists():
        print(f"Error: Wiktionary DB not found: {wik_path}", file=sys.stderr)
        return 1

    wik_conn = sqlite3.connect(str(wik_path))
    wik_conn.row_factory = sqlite3.Row
    syn_conn = sqlite3.connect(str(syn_path))
    syn_conn.execute("PRAGMA foreign_keys=OFF")
    syn_conn.execute("PRAGMA journal_mode=WAL")
    syn_conn.execute("PRAGMA synchronous=NORMAL")
    syn_conn.execute("PRAGMA cache_size=-8000000")
    syn_cur = syn_conn.cursor()

    print(f"Wiktionary DB: {wik_path}")
    print(f"Synapedia DB:  {syn_path}")
    print()

    # ── Verify schema has canonical_id TEXT ──────────────────────────
    syn_cur.execute("PRAGMA table_info(synapedia_entry)")
    cols = {r[1] for r in syn_cur.fetchall()}
    if 'canonical_id' not in cols:
        print("ERROR: synapedia_entry table missing canonical_id column.", file=sys.stderr)
        print("Run load_synapedia_from_wordnet_db.py first to create the schema.", file=sys.stderr)
        return 1

    # ── Load entries from wiktionary_raw.db ──────────────────────────
    limit_clause = f"LIMIT {args.limit}" if args.limit else ""
    wik_cur = wik_conn.execute(f"""
        SELECT e.id, e.word, e.pos, e.lang_code,
               s.gloss, s.examples_json, s.categories_json, s.synonyms_json,
               s.sense_index
        FROM wiktionary_entry e
        LEFT JOIN wiktionary_sense s ON e.id = s.entry_id
        WHERE e.lang_code = 'en' AND e.is_redirect = 0
        ORDER BY e.id, s.sense_index
        {limit_clause}
    """)

    rows = wik_cur.fetchall()
    total_rows = len(rows)
    print(f"Total Wiktionary entries+senses to import: {total_rows:,}")

    # ── Group by entry_id to combine senses ──────────────────────────
    entry_groups = defaultdict(list)
    for r in rows:
        entry_groups[r['id']].append(r)

    imported_entries = 0
    imported_senses = 0
    skipped_no_gloss = 0

    for eid, senses in entry_groups.items():
        first = senses[0]
        lemma = first['word']
        pos_wik = first['pos']
        pos_ud = wiktionary_pos_to_ud(pos_wik)

        glosses = []
        all_examples = []
        all_categories = []
        all_synonyms = []

        for s in senses:
            gloss = s['gloss'] or ''
            if not gloss.strip():
                skipped_no_gloss += 1
                continue
            glosses.append(gloss)

            if s['examples_json']:
                try:
                    exs = json.loads(s['examples_json'])
                    if isinstance(exs, list):
                        all_examples.extend(exs)
                except json.JSONDecodeError:
                    pass

            if s['categories_json']:
                try:
                    cats = json.loads(s['categories_json'])
                    if isinstance(cats, list):
                        all_categories.extend(cats)
                except json.JSONDecodeError:
                    pass

            if s['synonyms_json']:
                try:
                    syns = json.loads(s['synonyms_json'])
                    if isinstance(syns, list):
                        all_synonyms.extend(syns)
                except json.JSONDecodeError:
                    pass

        if not glosses:
            continue

        primary_gloss = glosses[0]
        notes = "; ".join(glosses[1:]) if len(glosses) > 1 else None

        examples_json = json.dumps(all_examples, ensure_ascii=False) if all_examples else None
        categories_json = json.dumps(all_categories, ensure_ascii=False) if all_categories else None
        synonyms_json = json.dumps(all_synonyms, ensure_ascii=False) if all_synonyms else None

        # Insert with canonical_id = NULL (will be filled later)
        syn_cur.execute("""
            INSERT INTO synapedia_entry
                (lemma, pos_original, pos_ud, gloss, source_type, definition_tier, language,
                 is_prime, is_molecule, is_instance, example_sentences, categories_json,
                 embedding_text_needs_rebuild)
            VALUES (?, ?, ?, ?, 'wiktionary', 'LEXICAL_EXTENSION', 'en',
                    0, 0, 0, ?, ?, 1)
        """, (
            lemma,
            pos_wik,
            pos_ud,
            primary_gloss,
            examples_json,
            categories_json,
        ))

        syn_id = syn_cur.lastrowid
        imported_entries += 1
        imported_senses += len(glosses)

        if imported_entries % args.batch == 0:
            syn_conn.commit()
            elapsed = time.time() - t0
            print(f"  imported {imported_entries:,} entries ({imported_senses:,} senses) – {elapsed:.1f}s", end="\r")

    syn_conn.commit()
    elapsed = time.time() - t0
    print(f"\n\nImport complete in {elapsed:.1f}s")
    print(f"  Entries imported: {imported_entries:,}")
    print(f"  Senses processed: {imported_senses:,}")
    print(f"  Skipped (no gloss): {skipped_no_gloss:,}")

    syn_cur.execute("SELECT COUNT(*) FROM synapedia_entry")
    total_in_syn = syn_cur.fetchone()[0]
    print(f"  Total in synapedia_entry: {total_in_syn:,}")

    wik_conn.close()
    syn_conn.close()
    print("\nDone (canonical_id and microgloss will be set by microgloss_v7_final.py).")
    return 0

if __name__ == "__main__":
    sys.exit(main())