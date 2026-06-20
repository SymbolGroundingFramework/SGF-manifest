#!/usr/bin/env python3
"""
load_wiktionary_jsonl.py  --  Stage 0 of the SGF lexicon pipeline.

Streams a Wiktextract JSONL dump into a raw SQLite database that the
rest of the pipeline reads from.

Usage:
    python load_wiktionary_jsonl.py
        (uses defaults: source=kaikki.org-dictionary-English.jsonl,
                        target=wiktionary_lexicon.db)

    python load_wiktionary_jsonl.py --source simple-extract.jsonl
        (use a different input file; output stays wiktionary_lexicon.db)

    python load_wiktionary_jsonl.py --source simple-extract.jsonl --target simple.db
        (override both)

Downstream scripts default to --source wiktionary_lexicon.db, so if you
change --target here, you must pass the same path as --source to the
next stage.

Where to get the JSONL: see README.md, section 3 of Setup.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB_PATH = "wiktionary_lexicon.db"
DEFAULT_JSONL_PATH = "kaikki.org-dictionary-English.jsonl"
BATCH_SIZE = 10000

LINKAGE_FIELDS = [
    "synonyms",
    "antonyms",
    "hypernyms",
    "hyponyms",
    "holonyms",
    "meronyms",
    "derived",
    "related",
    "coordinate_terms",
    "troponyms",
]

def dumps(obj):
    return json.dumps(obj, ensure_ascii=False) if obj is not None else None

def init_db(conn):
    cur = conn.cursor()

    cur.executescript("""
    PRAGMA journal_mode = WAL;
    PRAGMA synchronous = NORMAL;
    PRAGMA temp_store = MEMORY;
    PRAGMA cache_size = -200000;
    PRAGMA foreign_keys = ON;

    DROP TABLE IF EXISTS linkages;
    DROP TABLE IF EXISTS translations;
    DROP TABLE IF EXISTS sounds;
    DROP TABLE IF EXISTS forms;
    DROP TABLE IF EXISTS senses;
    DROP TABLE IF EXISTS entries;

    CREATE TABLE entries (
        id INTEGER PRIMARY KEY,
        source_line INTEGER NOT NULL,
        word TEXT,
        pos TEXT,
        lang TEXT,
        lang_code TEXT,
        etymology_text TEXT,
        etymology_number INTEGER,
        head_templates_json TEXT,
        categories_json TEXT,
        topics_json TEXT,
        redirect TEXT,
        raw_json TEXT NOT NULL
    );

    CREATE TABLE senses (
        id INTEGER PRIMARY KEY,
        entry_id INTEGER NOT NULL,
        sense_index INTEGER NOT NULL,
        glosses_json TEXT,
        raw_glosses_json TEXT,
        tags_json TEXT,
        categories_json TEXT,
        topics_json TEXT,
        examples_json TEXT,
        links_json TEXT,
        alt_of_json TEXT,
        form_of_json TEXT,
        classifiers_json TEXT,
        sense_json TEXT NOT NULL,
        FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE
    );

    CREATE TABLE forms (
        id INTEGER PRIMARY KEY,
        entry_id INTEGER NOT NULL,
        form_index INTEGER NOT NULL,
        form TEXT,
        tags_json TEXT,
        raw_tags_json TEXT,
        topics_json TEXT,
        ipa TEXT,
        source TEXT,
        form_json TEXT NOT NULL,
        FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE
    );

    CREATE TABLE sounds (
        id INTEGER PRIMARY KEY,
        entry_id INTEGER NOT NULL,
        sound_index INTEGER NOT NULL,
        ipa TEXT,
        enpr TEXT,
        audio TEXT,
        ogg_url TEXT,
        mp3_url TEXT,
        wav_url TEXT,
        tags_json TEXT,
        text TEXT,
        sound_json TEXT NOT NULL,
        FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE
    );

    CREATE TABLE translations (
        id INTEGER PRIMARY KEY,
        entry_id INTEGER NOT NULL,
        sense_id INTEGER,
        translation_index INTEGER NOT NULL,
        lang TEXT,
        lang_code TEXT,
        word TEXT,
        roman TEXT,
        sense TEXT,
        tags_json TEXT,
        topics_json TEXT,
        translation_json TEXT NOT NULL,
        FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE,
        FOREIGN KEY (sense_id) REFERENCES senses(id) ON DELETE SET NULL
    );

    CREATE TABLE linkages (
        id INTEGER PRIMARY KEY,
        entry_id INTEGER NOT NULL,
        sense_id INTEGER,
        linkage_type TEXT NOT NULL,
        linkage_index INTEGER NOT NULL,
        word TEXT,
        sense TEXT,
        roman TEXT,
        tags_json TEXT,
        topics_json TEXT,
        linkage_json TEXT NOT NULL,
        FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE,
        FOREIGN KEY (sense_id) REFERENCES senses(id) ON DELETE SET NULL
    );

    CREATE INDEX idx_entries_word ON entries(word);
    CREATE INDEX idx_entries_lang_pos ON entries(lang_code, pos);
    CREATE INDEX idx_senses_entry ON senses(entry_id);
    CREATE INDEX idx_forms_entry ON forms(entry_id);
    CREATE INDEX idx_sounds_entry ON sounds(entry_id);
    CREATE INDEX idx_translations_entry ON translations(entry_id);
    CREATE INDEX idx_translations_word ON translations(word);
    CREATE INDEX idx_linkages_entry ON linkages(entry_id);
    CREATE INDEX idx_linkages_word ON linkages(word);
    """)
    conn.commit()

def insert_entry(cur, line_no, obj):
    cur.execute("""
        INSERT INTO entries (
            source_line, word, pos, lang, lang_code, etymology_text,
            etymology_number, head_templates_json, categories_json,
            topics_json, redirect, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        line_no,
        obj.get("word"),
        obj.get("pos"),
        obj.get("lang"),
        obj.get("lang_code"),
        obj.get("etymology_text"),
        obj.get("etymology_number"),
        dumps(obj.get("head_templates")),
        dumps(obj.get("categories")),
        dumps(obj.get("topics")),
        obj.get("redirect"),
        dumps(obj),
    ))
    return cur.lastrowid

def insert_senses(cur, entry_id, obj):
    sense_id_map = {}
    senses = obj.get("senses", [])
    for i, sense in enumerate(senses):
        cur.execute("""
            INSERT INTO senses (
                entry_id, sense_index, glosses_json, raw_glosses_json, tags_json,
                categories_json, topics_json, examples_json, links_json,
                alt_of_json, form_of_json, classifiers_json, sense_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry_id,
            i,
            dumps(sense.get("glosses")),
            dumps(sense.get("raw_glosses")),
            dumps(sense.get("tags")),
            dumps(sense.get("categories")),
            dumps(sense.get("topics")),
            dumps(sense.get("examples")),
            dumps(sense.get("links")),
            dumps(sense.get("alt_of")),
            dumps(sense.get("form_of")),
            dumps(sense.get("classifiers")),
            dumps(sense),
        ))
        sense_id = cur.lastrowid
        sense_id_map[i] = sense_id

        for linkage_type in LINKAGE_FIELDS:
            for j, item in enumerate(sense.get(linkage_type, [])):
                cur.execute("""
                    INSERT INTO linkages (
                        entry_id, sense_id, linkage_type, linkage_index, word,
                        sense, roman, tags_json, topics_json, linkage_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    entry_id,
                    sense_id,
                    linkage_type,
                    j,
                    item.get("word"),
                    item.get("sense"),
                    item.get("roman"),
                    dumps(item.get("tags")),
                    dumps(item.get("topics")),
                    dumps(item),
                ))
    return sense_id_map

def insert_forms(cur, entry_id, obj):
    for i, form in enumerate(obj.get("forms", [])):
        cur.execute("""
            INSERT INTO forms (
                entry_id, form_index, form, tags_json, raw_tags_json,
                topics_json, ipa, source, form_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry_id,
            i,
            form.get("form"),
            dumps(form.get("tags")),
            dumps(form.get("raw_tags")),
            dumps(form.get("topics")),
            form.get("ipa"),
            form.get("source"),
            dumps(form),
        ))

def insert_sounds(cur, entry_id, obj):
    for i, sound in enumerate(obj.get("sounds", [])):
        cur.execute("""
            INSERT INTO sounds (
                entry_id, sound_index, ipa, enpr, audio, ogg_url, mp3_url,
                wav_url, tags_json, text, sound_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry_id,
            i,
            sound.get("ipa"),
            sound.get("enpr"),
            sound.get("audio"),
            sound.get("ogg_url"),
            sound.get("mp3_url"),
            sound.get("wav_url"),
            dumps(sound.get("tags")),
            sound.get("text"),
            dumps(sound),
        ))

def insert_translations(cur, entry_id, sense_id_map, obj):
    for i, tr in enumerate(obj.get("translations", [])):
        sense_index = tr.get("_sense_index")
        sense_id = sense_id_map.get(sense_index) if isinstance(sense_index, int) else None

        cur.execute("""
            INSERT INTO translations (
                entry_id, sense_id, translation_index, lang, lang_code, word,
                roman, sense, tags_json, topics_json, translation_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry_id,
            sense_id,
            i,
            tr.get("lang"),
            tr.get("code") or tr.get("lang_code"),
            tr.get("word"),
            tr.get("roman"),
            tr.get("sense"),
            dumps(tr.get("tags")),
            dumps(tr.get("topics")),
            dumps(tr),
        ))

def insert_entry_level_linkages(cur, entry_id, obj):
    for linkage_type in LINKAGE_FIELDS:
        for j, item in enumerate(obj.get(linkage_type, [])):
            cur.execute("""
                INSERT INTO linkages (
                    entry_id, sense_id, linkage_type, linkage_index, word,
                    sense, roman, tags_json, topics_json, linkage_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry_id,
                None,
                linkage_type,
                j,
                item.get("word"),
                item.get("sense"),
                item.get("roman"),
                dumps(item.get("tags")),
                dumps(item.get("topics")),
                dumps(item),
            ))

def load_jsonl(conn, jsonl_path):
    cur = conn.cursor()
    inserted = 0
    skipped = 0

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue

            entry_id = insert_entry(cur, line_no, obj)
            sense_id_map = insert_senses(cur, entry_id, obj)
            insert_forms(cur, entry_id, obj)
            insert_sounds(cur, entry_id, obj)
            insert_translations(cur, entry_id, sense_id_map, obj)
            insert_entry_level_linkages(cur, entry_id, obj)

            inserted += 1
            if inserted % BATCH_SIZE == 0:
                conn.commit()
                print(f"Committed {inserted:,} entries...")

    conn.commit()
    return inserted, skipped

def main():
    p = argparse.ArgumentParser(
        description="Load a Wiktextract JSONL dump into wiktionary_lexicon.db.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "The default --source is kaikki.org-dictionary-English.jsonl, the\n"
            "filename used by the verified walkthrough. If you downloaded a\n"
            "different file (e.g. simple-extract.jsonl), either rename it to\n"
            "the default or pass --source explicitly.\n"
        ),
    )
    p.add_argument(
        "--source",
        default=DEFAULT_JSONL_PATH,
        help=f"Path to the Wiktextract JSONL dump (default: {DEFAULT_JSONL_PATH})",
    )
    p.add_argument(
        "--target",
        default=DEFAULT_DB_PATH,
        help=f"Path to the output SQLite DB (default: {DEFAULT_DB_PATH})",
    )
    # Legacy positional support: if you used to call this with a bare
    # path, it still works.
    p.add_argument("positional_source", nargs="?", default=None,
                   help=argparse.SUPPRESS)
    args = p.parse_args()

    source = args.positional_source if args.positional_source else args.source
    jsonl_path = Path(source)
    db_path = Path(args.target)

    if not jsonl_path.exists():
        print(f"JSONL file not found: {jsonl_path}", file=sys.stderr)
        print("", file=sys.stderr)
        print("See README.md section 3 of Setup for download links.", file=sys.stderr)
        print("If you downloaded simple-extract.jsonl, pass it explicitly:", file=sys.stderr)
        print(f"  python {Path(__file__).name} --source simple-extract.jsonl", file=sys.stderr)
        sys.exit(1)

    print(f"Source:  {jsonl_path}")
    print(f"Target:  {db_path}")
    print()

    conn = sqlite3.connect(db_path)
    try:
        init_db(conn)
        inserted, skipped = load_jsonl(conn, jsonl_path)
        print(f"Done. Inserted {inserted:,} entries, skipped {skipped:,} bad lines.")
        print(f"SQLite DB created at: {db_path.resolve()}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
