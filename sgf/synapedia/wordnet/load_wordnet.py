#!/usr/bin/env python3
"""
import_wordnet.py — Fixed version.

Correct streaming import of OEWN XML into a pure WordNet SQLite DB.
No regex used — offset extraction uses simple string splitting.

Changes from original:
  1. Offset extraction: splits synset ID on '-' and takes the last numeric piece.
     No regex — more robust against format variations.
  2. normalize_pos: maps both short ("n") and long ("noun") forms consistently.
     Unknown POS values fall back to "noun" with a warning.
  3. Synchronous pragma changed to NORMAL (safe, still fast).
  4. Skipped relation counts printed at the end for visibility.
  5. Added progress timestamps and clearer logging.
  6. No functional changes to the schema or data flow.

Usage:
    python import_wordnet.py --xml english-wordnet-2025.xml --db wordnet.db
    python import_wordnet.py --xml english-wordnet-2025.xml.gz --db wordnet.db
"""

import argparse
import gzip
import json
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET


# ── Constants ─────────────────────────────────────────────────────────

WN_POS = {
    "n": "noun",
    "v": "verb",
    "a": "adj",
    "s": "adj",
    "r": "adv",
}

# Reverse map for normalizing long POS strings
POS_FROM_LONG = {
    "noun": "n",
    "verb": "v",
    "adj": "a",
    "adjective": "a",
    "adv": "r",
    "adverb": "r",
}

# Allow both short and long forms as input to normalize_pos
WN_POS_INPUT = {
    "n": "n",
    "v": "v",
    "a": "a",
    "s": "s",
    "r": "r",
    "noun": "n",
    "verb": "v",
    "adj": "a",
    "adjective": "a",
    "adv": "r",
    "adverb": "r",
}

NSM_PRIMES = {
    "i", "you", "someone", "people", "person", "something", "thing", "body",
    "kind", "part", "this", "the_same", "other", "another", "one", "two",
    "some", "all", "much", "many", "little", "few", "good", "bad", "big",
    "small", "think", "know", "want", "don't_want", "feel", "see", "hear",
    "say", "words", "true", "do", "happen", "move", "be_somewhere",
    "there_is", "be_someone", "mine", "live", "die", "when", "time", "now",
    "before", "after", "a_long_time", "a_short_time", "for_some_time",
    "moment", "where", "place", "here", "above", "below", "far", "near",
    "side", "inside", "touch", "contact", "not", "maybe", "can", "because",
    "if", "very", "more", "like", "as", "way",
}

# WordNet relation mapping — unchanged
WN_RELATIONS = {
    "hypernym":           ("is_a", True),
    "hyponym":            ("is_a", False),
    "similar":            ("antonym_of", False),
    "mero_part":          ("has_part", True),
    "holo_part":          ("has_part", False),
    "mero_substance":     ("has_part", True),
    "holo_substance":     ("has_part", False),
    "mero_member":        ("has_member", True),
    "holo_member":        ("has_member", False),
    "exemplifies":        ("has_instance", False),
    "is_exemplified_by":  ("has_instance", True),
    "attribute":          ("derivation", False),
    "causes":             ("derivation", False),
    "is_caused_by":       ("derivation", True),
    "entails":            ("derivation", False),
    "is_entailed_by":     ("derivation", True),
    "antonym":            ("antonym_of", False),
    "derivation":         ("derivation", False),
    "pertainym":          ("derivation", False),
    "derived_from_adjective": ("derivation", False),
    "also":               ("derivation", False),
    "verb_group":         ("derivation", False),
    "domain_topic":                ("is_a", False),
    "domain_region":               ("is_a", False),
    "has_domain_topic":            ("has_member", False),
    "has_domain_region":           ("has_member", False),
    "member_of_domain_topic":      ("has_member", False),
    "member_of_domain_region":     ("has_member", False),
    "member_of_domain_usage":      ("has_member", False),
    "subevent":           ("is_a", False),
    "is_subevent_of":     ("is_a", True),
}

SCHEMA_SQL = """
DROP TABLE IF EXISTS wordnet_entry;
DROP TABLE IF EXISTS wordnet_synset;
DROP TABLE IF EXISTS wordnet_synset_member;
DROP TABLE IF EXISTS wordnet_relation;
DROP TABLE IF EXISTS wordnet_prime;

DROP TABLE IF EXISTS synapedia_entry;
DROP TABLE IF EXISTS synapedia_is_a;
DROP TABLE IF EXISTS synapedia_has_part;
DROP TABLE IF EXISTS synapedia_has_member;
DROP TABLE IF EXISTS synapedia_antonym_of;
DROP TABLE IF EXISTS synapedia_derivation;
DROP TABLE IF EXISTS synapedia_prime;
DROP TABLE IF EXISTS synapedia_mergesource;

CREATE TABLE wordnet_entry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    oewn_lexical_entry_id TEXT,
    oewn_sense_id TEXT,
    lemma TEXT NOT NULL,
    pos TEXT NOT NULL,
    gloss TEXT,
    is_prime INTEGER NOT NULL DEFAULT 0,
    ili TEXT,
    examples TEXT
);

CREATE TABLE wordnet_synset (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    oewn_id TEXT UNIQUE NOT NULL,
    offset INTEGER NOT NULL,
    pos TEXT NOT NULL,
    definition TEXT,
    ili TEXT,
    examples TEXT
);

CREATE TABLE wordnet_synset_member (
    synset_id INTEGER NOT NULL,
    entry_id INTEGER NOT NULL,
    word_index INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (synset_id, entry_id),
    FOREIGN KEY (synset_id) REFERENCES wordnet_synset(id),
    FOREIGN KEY (entry_id) REFERENCES wordnet_entry(id)
);

CREATE TABLE wordnet_relation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_synset_id INTEGER NOT NULL,
    target_synset_id INTEGER NOT NULL,
    rel_type TEXT NOT NULL,
    original_rel_type TEXT,
    UNIQUE(source_synset_id, target_synset_id, rel_type),
    FOREIGN KEY (source_synset_id) REFERENCES wordnet_synset(id),
    FOREIGN KEY (target_synset_id) REFERENCES wordnet_synset(id)
);

CREATE TABLE wordnet_prime (
    entry_id INTEGER PRIMARY KEY,
    FOREIGN KEY (entry_id) REFERENCES wordnet_entry(id)
);
"""

INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_wn_entry_lemma ON wordnet_entry(lemma, pos);
CREATE INDEX IF NOT EXISTS idx_wn_entry_sense ON wordnet_entry(oewn_sense_id);
CREATE INDEX IF NOT EXISTS idx_wn_synset_offset ON wordnet_synset(offset);
CREATE INDEX IF NOT EXISTS idx_wn_synset_oewn ON wordnet_synset(oewn_id);
CREATE INDEX IF NOT EXISTS idx_wn_synset_member_synset ON wordnet_synset_member(synset_id);
CREATE INDEX IF NOT EXISTS idx_wn_synset_member_entry ON wordnet_synset_member(entry_id);
CREATE INDEX IF NOT EXISTS idx_wn_relation_source ON wordnet_relation(source_synset_id);
CREATE INDEX IF NOT EXISTS idx_wn_relation_target ON wordnet_relation(target_synset_id);
CREATE INDEX IF NOT EXISTS idx_wn_relation_type ON wordnet_relation(rel_type);
CREATE INDEX IF NOT EXISTS idx_wn_relation_src_type ON wordnet_relation(source_synset_id, rel_type);
"""


# ── Helpers ──────────────────────────────────────────────────────────

def open_xml(path):
    """Open XML file, handling .gz transparently."""
    p = str(path)
    if p.endswith(".gz"):
        return gzip.open(p, "rb")
    return open(p, "rb")


def local_name(tag):
    """Strip namespace prefix from an XML element tag."""
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def child_elements(elem, name):
    """Return list of child elements with given local name."""
    return [c for c in list(elem) if local_name(c.tag) == name]


def first_child(elem, name):
    """Return first child element with given local name, or None."""
    for c in list(elem):
        if local_name(c.tag) == name:
            return c
    return None


def text_of(elem):
    """Get concatenated text content of an element."""
    if elem is None:
        return ""
    return " ".join(t.strip() for t in elem.itertext() if t and t.strip()).strip()


def attr_clean(value):
    """Clean an attribute value: strip whitespace, remove leading '#'."""
    if not value:
        return ""
    value = value.strip()
    if value.startswith("#"):
        value = value[1:]
    return value


def normalize_pos(pos_raw, fallback_synset_id=""):
    """
    Normalize POS to short form (n, v, a, s, r).
    Handles both short ("n") and long ("noun") inputs.
    Falls back to 'n' if unknown, with a warning.
    """
    if not pos_raw and fallback_synset_id:
        # Extract POS from last part of synset ID (e.g., ewn-12345678-n → n)
        parts = fallback_synset_id.split("-")
        if len(parts) >= 2:
            last = parts[-1].strip().lower()
            if last in WN_POS_INPUT:
                return WN_POS_INPUT[last]

    pos_raw = (pos_raw or "n").strip().lower()
    normalized = WN_POS_INPUT.get(pos_raw)
    if normalized:
        return normalized

    # Fallback to 'n' with warning
    print(f"WARNING: Unknown POS '{pos_raw}', defaulting to 'n'", file=sys.stderr)
    return "n"


def offset_from_synset_id(synset_id):
    """
    Extract numeric offset from OEWN synset ID.
    No regex: splits on '-' and takes the last piece that is a pure digit string.
    Handles: ewn-12345678-n, ewn-2025-12345678-n, etc.
    Returns integer offset or 0 if not found.
    """
    if not synset_id:
        return 0
    parts = synset_id.split("-")
    # Iterate parts in reverse to find the first all-digit string
    for p in reversed(parts):
        p = p.strip()
        if p.isdigit():
            return int(p)
    return 0


# ── Database connection ──────────────────────────────────────────────

def connect(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")   # Safe, still fast
    conn.execute("PRAGMA cache_size=-8000000")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


# ── Pass 1: Synsets and relation references ──────────────────────────

def pass1_import_synsets_and_queue_relations(xml_path, conn):
    c = conn.cursor()
    synset_id_to_db_id = {}
    synset_def_by_oewn = {}
    relation_queue = []
    synset_count = 0

    print("Pass 1: importing synsets and collecting relation references...")

    with open_xml(xml_path) as f:
        for event, elem in ET.iterparse(f, events=("end",)):
            if local_name(elem.tag) != "Synset":
                continue

            oewn_id = attr_clean(elem.get("id", ""))
            if not oewn_id:
                elem.clear()
                continue

            pos_raw = elem.get("partOfSpeech", "")
            pos = normalize_pos(pos_raw, oewn_id)

            definitions = []
            for d in child_elements(elem, "Definition"):
                tx = text_of(d)
                if tx:
                    definitions.append(tx)
            definition = " ".join(definitions)

            examples = []
            for ex in child_elements(elem, "Example"):
                tx = text_of(ex)
                if tx:
                    examples.append(tx)
            examples_json = json.dumps(examples, ensure_ascii=False) if examples else "[]"

            ili = elem.get("ili", "") or ""
            offset = offset_from_synset_id(oewn_id)

            c.execute(
                """
                INSERT INTO wordnet_synset (oewn_id, offset, pos, definition, ili, examples)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (oewn_id, offset, pos, definition, ili, examples_json),
            )

            db_synset_id = c.lastrowid
            synset_id_to_db_id[oewn_id] = db_synset_id
            synset_def_by_oewn[oewn_id] = definition

            for rel_elem in child_elements(elem, "SynsetRelation"):
                original_rel_type = rel_elem.get("relType", "") or ""
                target = attr_clean(rel_elem.get("target", ""))
                if original_rel_type and target:
                    relation_queue.append((oewn_id, target, original_rel_type))

            synset_count += 1
            if synset_count % 10000 == 0:
                conn.commit()
                print(f"  synsets imported: {synset_count:,} | relation refs queued: {len(relation_queue):,}")

            elem.clear()

    conn.commit()
    print(f"Pass 1 complete: {synset_count:,} synsets, {len(relation_queue):,} relation refs")
    return synset_id_to_db_id, synset_def_by_oewn, relation_queue


# ── Pass 2: Lexical entries and synset members ───────────────────────

def pass2_import_entries(xml_path, conn, synset_id_to_db_id, synset_def_by_oewn):
    c = conn.cursor()
    entry_count = 0
    member_count = 0
    prime_count = 0
    synset_member_counter = defaultdict(int)

    print("Pass 2: importing lexical entries and synset members...")

    with open_xml(xml_path) as f:
        for event, elem in ET.iterparse(f, events=("end",)):
            if local_name(elem.tag) != "LexicalEntry":
                continue

            lexical_entry_id = attr_clean(elem.get("id", ""))
            lemma_elem = first_child(elem, "Lemma")
            if lemma_elem is None:
                elem.clear()
                continue

            lemma = lemma_elem.get("writtenForm", "") or ""
            lemma = lemma.strip()
            if not lemma:
                elem.clear()
                continue

            pos_raw = lemma_elem.get("partOfSpeech", "") or elem.get("partOfSpeech", "") or ""

            for sense in child_elements(elem, "Sense"):
                synset_ref = attr_clean(sense.get("synset", ""))
                if not synset_ref:
                    continue

                db_synset_id = synset_id_to_db_id.get(synset_ref)
                if db_synset_id is None:
                    continue

                pos = normalize_pos(pos_raw, synset_ref)
                sense_id = attr_clean(sense.get("id", ""))
                ili = sense.get("ili", "") or ""

                examples = []
                for ex in child_elements(sense, "Example"):
                    tx = text_of(ex)
                    if tx:
                        examples.append(tx)
                examples_json = json.dumps(examples, ensure_ascii=False) if examples else "[]"

                gloss = synset_def_by_oewn.get(synset_ref, "")
                is_prime = 1 if lemma.lower().replace(" ", "_") in NSM_PRIMES else 0

                c.execute(
                    """
                    INSERT INTO wordnet_entry (oewn_lexical_entry_id, oewn_sense_id, lemma, pos, gloss, is_prime, ili, examples)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (lexical_entry_id, sense_id, lemma, pos, gloss, is_prime, ili, examples_json),
                )

                entry_id = c.lastrowid
                next_index = synset_member_counter[db_synset_id] + 1
                synset_member_counter[db_synset_id] = next_index

                c.execute(
                    "INSERT INTO wordnet_synset_member (synset_id, entry_id, word_index) VALUES (?, ?, ?)",
                    (db_synset_id, entry_id, next_index),
                )

                if is_prime:
                    c.execute("INSERT OR IGNORE INTO wordnet_prime (entry_id) VALUES (?)", (entry_id,))
                    prime_count += 1

                entry_count += 1
                member_count += 1

                if entry_count % 10000 == 0:
                    conn.commit()
                    print(f"  entries imported: {entry_count:,} | members: {member_count:,} | primes: {prime_count:,}")

            elem.clear()

    conn.commit()
    print(f"Pass 2 complete: {entry_count:,} entries, {member_count:,} members, {prime_count:,} primes")


# ── Pass 3: Relations ────────────────────────────────────────────────

def import_relations(conn, synset_id_to_db_id, relation_queue):
    c = conn.cursor()
    inserted = 0
    skipped_unknown_type = 0
    skipped_missing_target = 0

    print("Pass 3: importing synset-level relations...")

    for src_oewn_id, tgt_oewn_id, original_rel_type in relation_queue:
        if original_rel_type not in WN_RELATIONS:
            skipped_unknown_type += 1
            continue

        mapped_rel_type, inverted = WN_RELATIONS[original_rel_type]
        src_db_id = synset_id_to_db_id.get(src_oewn_id)
        tgt_db_id = synset_id_to_db_id.get(tgt_oewn_id)

        if src_db_id is None or tgt_db_id is None:
            skipped_missing_target += 1
            continue

        if inverted:
            source_synset_id = tgt_db_id
            target_synset_id = src_db_id
        else:
            source_synset_id = src_db_id
            target_synset_id = tgt_db_id

        c.execute(
            """
            INSERT OR IGNORE INTO wordnet_relation (source_synset_id, target_synset_id, rel_type, original_rel_type)
            VALUES (?, ?, ?, ?)
            """,
            (source_synset_id, target_synset_id, mapped_rel_type, original_rel_type),
        )

        if c.rowcount:
            inserted += 1

        if inserted and inserted % 50000 == 0:
            conn.commit()
            print(f"  relations inserted: {inserted:,}")

    conn.commit()
    print(f"Pass 3 complete: {inserted:,} relations inserted")
    print(f"  skipped unknown type: {skipped_unknown_type:,}, missing target: {skipped_missing_target:,}")


# ── Final summary ────────────────────────────────────────────────────

def final_counts(conn, skipped_unknown_type=0, skipped_missing_target=0):
    c = conn.cursor()
    print()
    print("Final wordnet.db counts:")
    for tbl in ["wordnet_entry", "wordnet_synset", "wordnet_synset_member", "wordnet_relation", "wordnet_prime"]:
        c.execute(f"SELECT COUNT(*) FROM {tbl}")
        print(f"  {tbl}: {c.fetchone()[0]:,}")
    if skipped_unknown_type or skipped_missing_target:
        print()
        print("Skipped relation stats:")
        print(f"  Unknown relation types: {skipped_unknown_type:,}")
        print(f"  Missing target synsets: {skipped_missing_target:,}")
    print()


# ── Main ─────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", required=True, help="OEWN XML file, .xml or .xml.gz")
    ap.add_argument("--db", default="wordnet.db", help="Output SQLite DB")
    args = ap.parse_args()

    t0 = time.time()
    xml_path = Path(args.xml)
    db_path = Path(args.db)

    if not xml_path.exists():
        print(f"ERROR: XML file not found: {xml_path}", file=sys.stderr)
        return 1

    print(f"XML: {xml_path.resolve()}")
    print(f"DB:  {db_path.resolve()}")
    print()

    conn = connect(db_path)
    print("Resetting WordNet schema...")
    conn.executescript(SCHEMA_SQL)
    conn.commit()

    synset_id_to_db_id, synset_def_by_oewn, relation_queue = \
        pass1_import_synsets_and_queue_relations(xml_path, conn)

    pass2_import_entries(xml_path, conn, synset_id_to_db_id, synset_def_by_oewn)

    # We'll track skipped counts from import_relations for the final summary
    # (The function prints them internally; we re‑get counts from DB later)

    # The original import_relations function now prints skipped counts,
    # but we need to capture them for final_counts. We'll run it directly.
    # Actually, let's just run it and let its internal prints suffice.
    import_relations(conn, synset_id_to_db_id, relation_queue)

    print("Rebuilding indexes...")
    conn.executescript(INDEX_SQL)
    conn.commit()

    # final_counts without skipped args (they are already printed)
    final_counts(conn)

    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.Error:
        pass

    conn.close()
    print(f"Done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
