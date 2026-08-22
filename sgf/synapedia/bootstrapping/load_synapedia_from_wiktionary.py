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
- Supports parallel worker processing via multiprocessing

Usage:
    python load_synapedia_from_wiktionary.py --wiktionary-db wiktionary.db --synapedia-db synapedia.db --workers 4
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from collections import defaultdict
from multiprocessing import Pool, cpu_count
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

def transform_entry_group_chunk(chunk):
    """
    Worker function: Processes a chunk of entry groups (list of (eid, senses_list)).
    Returns (records_list, imported_entries, imported_senses, skipped_no_gloss).
    """
    records = []
    imported_entries = 0
    imported_senses = 0
    skipped_no_gloss = 0

    for eid, senses in chunk:
        if not senses:
            continue
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
        examples_json = json.dumps(all_examples, ensure_ascii=False) if all_examples else None
        categories_json = json.dumps(all_categories, ensure_ascii=False) if all_categories else None
        synonyms_json = json.dumps(all_synonyms, ensure_ascii=False) if all_synonyms else None

        records.append((
            lemma,
            pos_wik,
            pos_ud,
            primary_gloss,
            examples_json,
            categories_json,
            synonyms_json,
        ))
        imported_entries += 1
        imported_senses += len(glosses)

    return records, imported_entries, imported_senses, skipped_no_gloss

def chunk_entry_groups(wik_conn, chunk_size=1000, limit=None):
    """
    Generator that fetches rows from wiktionary_raw.db lazily and yields chunks of entry groups.
    """
    limit_clause = f"LIMIT {limit}" if limit else ""
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

    current_group = []
    current_eid = None
    chunk = []

    for row in wik_cur:
        r_dict = {
            'id': row['id'],
            'word': row['word'],
            'pos': row['pos'],
            'lang_code': row['lang_code'],
            'gloss': row['gloss'],
            'examples_json': row['examples_json'],
            'categories_json': row['categories_json'],
            'synonyms_json': row['synonyms_json'],
            'sense_index': row['sense_index'],
        }
        eid = r_dict['id']

        if current_eid is None:
            current_eid = eid

        if eid != current_eid:
            chunk.append((current_eid, current_group))
            current_group = [r_dict]
            current_eid = eid
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []
        else:
            current_group.append(r_dict)

    if current_group:
        chunk.append((current_eid, current_group))
    if chunk:
        yield chunk

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiktionary-db", required=True)
    ap.add_argument("--synapedia-db", default="synapedia.db")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--batch", type=int, default=5000)
    ap.add_argument("--workers", "-j", type=int, default=cpu_count(),
                    help=f"Number of parallel worker processes (default: {cpu_count()})")
    args = ap.parse_args()

    t0 = time.time()
    wik_path = Path(args.wiktionary_db).resolve()
    syn_path = Path(args.synapedia_db).resolve()

    if not wik_path.exists():
        print(f"Error: Wiktionary DB not found: {wik_path}", file=sys.stderr)
        return 1

    wik_conn = sqlite3.connect(str(wik_path), check_same_thread=False)
    wik_conn.row_factory = sqlite3.Row
    syn_conn = sqlite3.connect(str(syn_path))
    syn_conn.execute("PRAGMA foreign_keys=OFF")
    syn_conn.execute("PRAGMA journal_mode=WAL")
    syn_conn.execute("PRAGMA synchronous=NORMAL")
    syn_conn.execute("PRAGMA cache_size=-8000000")
    syn_cur = syn_conn.cursor()

    print(f"Wiktionary DB: {wik_path}")
    print(f"Synapedia DB:  {syn_path}")
    print(f"Workers:        {args.workers}")
    print()

    # ── Verify schema has canonical_id TEXT ──────────────────────────
    syn_cur.execute("PRAGMA table_info(synapedia_entry)")
    cols = {r[1] for r in syn_cur.fetchall()}
    if 'canonical_id' not in cols:
        print("ERROR: synapedia_entry table missing canonical_id column.", file=sys.stderr)
        print("Run load_synapedia_from_wordnet_db.py first to create the schema.", file=sys.stderr)
        return 1

    imported_entries = 0
    imported_senses = 0
    skipped_no_gloss = 0
    batch_records = []

    insert_sql = """
        INSERT INTO synapedia_entry
            (lemma, pos_original, pos_ud, gloss, source_type, definition_tier, language,
             is_prime, is_molecule, is_instance, example_sentences, categories_json,
             synonyms_json, embedding_text_needs_rebuild)
        VALUES (?, ?, ?, ?, 'wiktionary', 'LEXICAL_EXTENSION', 'en',
                0, 0, 0, ?, ?, ?, 1)
    """

    chunk_stream = chunk_entry_groups(wik_conn, chunk_size=1000, limit=args.limit)

    if args.workers > 1:
        with Pool(processes=args.workers) as pool:
            for recs, n_entries, n_senses, n_skipped in pool.imap(transform_entry_group_chunk, chunk_stream, chunksize=1):
                batch_records.extend(recs)
                imported_entries += n_entries
                imported_senses += n_senses
                skipped_no_gloss += n_skipped

                if len(batch_records) >= args.batch:
                    syn_cur.executemany(insert_sql, batch_records)
                    syn_conn.commit()
                    batch_records = []
                    elapsed = time.time() - t0
                    print(f"  imported {imported_entries:,} entries ({imported_senses:,} senses) – {elapsed:.1f}s", end="\r")
    else:
        for chunk in chunk_stream:
            recs, n_entries, n_senses, n_skipped = transform_entry_group_chunk(chunk)
            batch_records.extend(recs)
            imported_entries += n_entries
            imported_senses += n_senses
            skipped_no_gloss += n_skipped

            if len(batch_records) >= args.batch:
                syn_cur.executemany(insert_sql, batch_records)
                syn_conn.commit()
                batch_records = []
                elapsed = time.time() - t0
                print(f"  imported {imported_entries:,} entries ({imported_senses:,} senses) – {elapsed:.1f}s", end="\r")

    if batch_records:
        syn_cur.executemany(insert_sql, batch_records)
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