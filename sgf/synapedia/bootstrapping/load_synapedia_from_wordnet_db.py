#!/usr/bin/env python3
"""
load_synapedia_from_wordnet_db.py — Fixed version with UD POS columns, event tables, attribute key-value, AND synonyms.

Reads wordnet.db and populates synapedia.db with:
  - WordNet entries (lemma, pos_original, pos_ud, gloss, etc.)
  - Synset mappings
  - Synonyms derived from synset membership (all words in a synset)
  - Relations (IS-A, HAS-PART, HAS-MEMBER, HAS-INSTANCE, ANTONYM, DERIVATION)
  - Event tables (synapse, spoke, entry_synapse, link, equivalence, ghost, group, group_member)
  - Marks embedding_text_needs_rebuild = 1 for later processing.

NO microgloss, canonical ID, or embedding text generation (delegated to microgloss_v7_final.py).

CHANGES IN THIS VERSION:
  - Added `synonyms_json TEXT` column to `synapedia_entry`.
  - After synset mappings are built, populates `synonyms_json` from
    synset membership (JSON array of other lemmas in the same synset).
  - So `bank` (sense 1) and `depository financial institution` (same synset)
    appear as synonyms.

Usage:
    python load_synapedia_from_wordnet_db.py --wordnet-db wordnet.db --synapedia-db synapedia.db --reset
"""

import argparse
import json
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

# ── NSM Primes ────────────────────────────────────────────────────────
NSM_PRIMES = {
    "i","you","someone","people","person","something","thing","body",
    "kind","part","this","the_same","other","another","one","two",
    "some","all","much","many","little","few","good","bad","big",
    "small","think","know","want","don't_want","feel","see","hear",
    "say","words","true","do","happen","move","be_somewhere",
    "there_is","be_someone","mine","live","die","when","time","now",
    "before","after","a_long_time","a_short_time","for_some_time",
    "moment","where","place","here","above","below","far","near",
    "side","inside","touch","contact","not","maybe","can","because",
    "if","very","more","like","as","way",
}

# ── Relation bucket mapping ──────────────────────────────────────────
# FIXED: is_a and has_instance now invert=True (source=hypernym, target=hyponym)
REL_BUCKET = {
    "is_a": ("is_a", True),          # source=hypernym, target=hyponym → child=target, parent=source
    "has_part": ("has_part", False), # source=whole, target=part → child=source, part=target
    "has_member": ("has_member", False),
    "has_instance": ("has_instance", True),  # instance is a subtype → same direction as is_a
    "antonym_of": ("antonym_of", False),      # symmetric, no direction
    "derivation": ("derivation", False),       # symmetric
}

# ── POS original full name map (WordNet short → full English) ───────
POS_FULL = {
    "n": "noun",
    "v": "verb",
    "a": "adjective",
    "s": "adjective",
    "r": "adverb",
    "prep": "preposition",
    "conj": "conjunction",
    "interj": "interjection",
    "pron": "pronoun",
    "det": "determiner",
    "num": "numeral",
    "article": "article",
    "part": "particle",
}

# ── UD mapping for WordNet short POS ─────────────────────────────────
WN_SHORT_TO_UD = {
    "n": "NOUN",
    "v": "VERB",
    "a": "ADJ",
    "s": "ADJ",
    "r": "ADV",
}

def wn_pos_to_ud(pos_short: str) -> str:
    """Map WordNet short POS to Universal Dependencies tag."""
    return WN_SHORT_TO_UD.get(pos_short, "NOUN")


# ── Schema (FIXED: added synonyms_json, canonical_entry_id is TEXT, etc.) ───
SCHEMA_SQL = """
DROP TABLE IF EXISTS synapedia_entry;
DROP TABLE IF EXISTS synapedia_source_xref;
DROP TABLE IF EXISTS wordnet_synset_mapping;
DROP TABLE IF EXISTS synapedia_is_a;
DROP TABLE IF EXISTS synapedia_has_part;
DROP TABLE IF EXISTS synapedia_has_member;
DROP TABLE IF EXISTS synapedia_has_purpose;
DROP TABLE IF EXISTS synapedia_has_attribute;
DROP TABLE IF EXISTS synapedia_layer;
DROP TABLE IF EXISTS synapedia_has_instance;
DROP TABLE IF EXISTS synapedia_antonym_of;
DROP TABLE IF EXISTS synapedia_derivation;
DROP TABLE IF EXISTS synapedia_prime;
DROP TABLE IF EXISTS synapedia_mergesource;
DROP TABLE IF EXISTS synapedia_synapse;
DROP TABLE IF EXISTS synapedia_spoke;
DROP TABLE IF EXISTS synapedia_entry_synapse;
DROP TABLE IF EXISTS synapedia_link;
DROP TABLE IF EXISTS synapedia_equivalence;
DROP TABLE IF EXISTS synapedia_ghost;
DROP TABLE IF EXISTS synapedia_group;
DROP TABLE IF EXISTS synapedia_group_member;
DROP TABLE IF EXISTS synapedia_verb_registry;

CREATE TABLE synapedia_entry (
    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    lemma TEXT NOT NULL,
    pos_original TEXT NOT NULL,
    pos_ud TEXT NOT NULL,
    gloss TEXT NOT NULL DEFAULT '',
    microgloss TEXT,
    canonical_id TEXT,
    source_type TEXT NOT NULL DEFAULT 'wordnet',
    definition_tier TEXT NOT NULL DEFAULT 'CORE_ONTOLOGY',
    language TEXT NOT NULL DEFAULT 'en',
    is_prime INTEGER NOT NULL DEFAULT 0,
    is_molecule INTEGER NOT NULL DEFAULT 0,
    is_instance INTEGER NOT NULL DEFAULT 0,
    ref_count INTEGER NOT NULL DEFAULT 0,
    example_sentences TEXT,
    categories_json TEXT,
    -- NEW: synonyms derived from synset membership
    synonyms_json TEXT,
    synset_offset INTEGER,
    word_index INTEGER,
    lex_id INTEGER,
    lex_domain TEXT,
    freq_count INTEGER DEFAULT 0,
    ili TEXT,
    is_microgloss_provisional INTEGER DEFAULT 1,
    microgloss_source TEXT DEFAULT 'algorithm',
    embedding_text TEXT,
    embedding_text_version TEXT,
    embedding_text_needs_rebuild INTEGER DEFAULT 1,
    -- FIX: Added embedding, bow, improved_at
    embedding BLOB,
    bow TEXT DEFAULT '',
    improved_at TEXT,
    is_variant INTEGER DEFAULT 0,
    is_preferred INTEGER DEFAULT 0,
    preferred_entry_id INTEGER,
    valid_from TEXT,
    valid_until TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE synapedia_source_xref (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    synapedia_id INTEGER NOT NULL,
    source_db TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    merged_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source_db, source_id),
    FOREIGN KEY (synapedia_id) REFERENCES synapedia_entry(entry_id)
);

CREATE TABLE wordnet_synset_mapping (
    synapedia_id INTEGER PRIMARY KEY,
    synset_offset INTEGER NOT NULL,
    word_index INTEGER NOT NULL,
    lemma TEXT NOT NULL,
    pos TEXT NOT NULL,
    lex_id INTEGER,
    source_synset_id TEXT,
    FOREIGN KEY (synapedia_id) REFERENCES synapedia_entry(entry_id)
);

CREATE TABLE synapedia_is_a (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    synapedia_entry_id INTEGER NOT NULL,
    parent_lemma TEXT NOT NULL,
    parent_gloss TEXT,
    parent_pos TEXT,
    parent_canonical_id TEXT,
    logical_gate TEXT DEFAULT 'AND',
    match_score REAL DEFAULT 1.0,
    relation_source TEXT DEFAULT 'wordnet',
    trust_level TEXT DEFAULT 'verified',
    valid_from TEXT,
    valid_until TEXT,
    FOREIGN KEY (synapedia_entry_id) REFERENCES synapedia_entry(entry_id)
);

CREATE TABLE synapedia_has_part (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    synapedia_entry_id INTEGER NOT NULL,
    part_lemma TEXT NOT NULL,
    part_gloss TEXT,
    part_pos TEXT,
    part_canonical_id TEXT,
    logical_gate TEXT DEFAULT 'AND',
    match_score REAL DEFAULT 1.0,
    relation_source TEXT DEFAULT 'wordnet',
    trust_level TEXT DEFAULT 'verified',
    valid_from TEXT,
    valid_until TEXT,
    FOREIGN KEY (synapedia_entry_id) REFERENCES synapedia_entry(entry_id)
);

CREATE TABLE synapedia_has_member (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    synapedia_entry_id INTEGER NOT NULL,
    member_lemma TEXT NOT NULL,
    member_gloss TEXT,
    member_pos TEXT,
    member_canonical_id TEXT,
    logical_gate TEXT DEFAULT 'AND',
    match_score REAL DEFAULT 1.0,
    relation_source TEXT DEFAULT 'wordnet',
    trust_level TEXT DEFAULT 'verified',
    valid_from TEXT,
    valid_until TEXT,
    FOREIGN KEY (synapedia_entry_id) REFERENCES synapedia_entry(entry_id)
);

CREATE TABLE synapedia_has_purpose (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    synapedia_entry_id INTEGER NOT NULL,
    purpose_lemma TEXT,
    purpose_gloss TEXT,
    purpose_pos TEXT,
    purpose_canonical_id TEXT,
    match_score REAL,
    logical_gate TEXT DEFAULT 'AND',
    relation_source TEXT DEFAULT 'llm',
    trust_level TEXT DEFAULT 'verified',
    FOREIGN KEY (synapedia_entry_id) REFERENCES synapedia_entry(entry_id)
);

-- FIX: Changed to attribute_key + attribute_value + trust_level
CREATE TABLE synapedia_has_attribute (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    synapedia_entry_id INTEGER NOT NULL,
    attribute_key TEXT NOT NULL,
    attribute_value TEXT NOT NULL DEFAULT '',
    logical_gate TEXT DEFAULT 'AND',
    relation_source TEXT DEFAULT 'llm',
    trust_level TEXT DEFAULT 'verified',
    FOREIGN KEY (synapedia_entry_id) REFERENCES synapedia_entry(entry_id)
);

CREATE TABLE synapedia_layer (
    synapedia_entry_id INTEGER PRIMARY KEY,
    built_at TEXT,
    model TEXT,
    source TEXT,
    suggested_microgloss TEXT,
    suggested_gloss TEXT,
    comments TEXT,
    quality_score REAL,
    FOREIGN KEY (synapedia_entry_id) REFERENCES synapedia_entry(entry_id)
);

CREATE TABLE synapedia_has_instance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    synapedia_entry_id INTEGER NOT NULL,
    instance_lemma TEXT NOT NULL,
    instance_gloss TEXT,
    instance_pos TEXT,
    instance_canonical_id TEXT,
    logical_gate TEXT DEFAULT 'AND',
    match_score REAL DEFAULT 1.0,
    relation_source TEXT DEFAULT 'wordnet',
    trust_level TEXT DEFAULT 'verified',
    valid_from TEXT,
    valid_until TEXT,
    FOREIGN KEY (synapedia_entry_id) REFERENCES synapedia_entry(entry_id)
);

CREATE TABLE synapedia_antonym_of (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    synapedia_entry_id INTEGER NOT NULL,
    antonym_lemma TEXT NOT NULL,
    antonym_gloss TEXT,
    antonym_pos TEXT,
    antonym_canonical_id TEXT,
    logical_gate TEXT DEFAULT 'AND',
    match_score REAL DEFAULT 1.0,
    relation_source TEXT DEFAULT 'wordnet',
    trust_level TEXT DEFAULT 'verified',
    valid_from TEXT,
    valid_until TEXT,
    FOREIGN KEY (synapedia_entry_id) REFERENCES synapedia_entry(entry_id)
);

CREATE TABLE synapedia_derivation (
    from_entry_id INTEGER NOT NULL,
    to_entry_id INTEGER NOT NULL,
    relation TEXT NOT NULL DEFAULT 'derivationally_related',
    relation_source TEXT NOT NULL DEFAULT 'wordnet',
    valid_from TEXT,
    valid_until TEXT,
    PRIMARY KEY (from_entry_id, to_entry_id, relation),
    FOREIGN KEY (from_entry_id) REFERENCES synapedia_entry(entry_id),
    FOREIGN KEY (to_entry_id) REFERENCES synapedia_entry(entry_id)
);

CREATE TABLE synapedia_prime (
    entry_id INTEGER NOT NULL,
    prime_type TEXT NOT NULL DEFAULT 'nsm',
    version INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (entry_id, prime_type, version),
    FOREIGN KEY (entry_id) REFERENCES synapedia_entry(entry_id)
);

CREATE TABLE synapedia_mergesource (
    merge_id INTEGER PRIMARY KEY AUTOINCREMENT,
    synapedia_entry_id INTEGER NOT NULL,
    source_db TEXT NOT NULL DEFAULT 'wordnet',
    source_id INTEGER NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    merged_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (synapedia_entry_id) REFERENCES synapedia_entry(entry_id)
);

-- FIX: New event tables
CREATE TABLE synapedia_synapse (
    synapse_id TEXT PRIMARY KEY,
    verb_lemma TEXT NOT NULL,
    verb_canonical_id TEXT,
    plane TEXT NOT NULL DEFAULT 'ontological',
    epistemic_status TEXT DEFAULT 'CONSTITUTIVE',
    pov TEXT,
    trust_level TEXT DEFAULT 'provisional',
    source_span TEXT,
    derivation_tag TEXT DEFAULT 'EXPRESSED',
    valid_from TEXT,
    valid_until TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE synapedia_spoke (
    synapse_id TEXT NOT NULL,
    role TEXT NOT NULL,
    target_id TEXT,
    target_type TEXT DEFAULT 'concept',
    target_lemma TEXT,
    literal_value TEXT,
    source_span TEXT,
    pov TEXT,
    FOREIGN KEY (synapse_id) REFERENCES synapedia_synapse(synapse_id),
    PRIMARY KEY (synapse_id, role, target_id, target_lemma)
);

CREATE TABLE synapedia_entry_synapse (
    entry_id INTEGER NOT NULL,
    synapse_id TEXT NOT NULL,
    relation TEXT NOT NULL DEFAULT 'has_event',
    PRIMARY KEY (entry_id, synapse_id),
    FOREIGN KEY (entry_id) REFERENCES synapedia_entry(entry_id),
    FOREIGN KEY (synapse_id) REFERENCES synapedia_synapse(synapse_id)
);

CREATE TABLE synapedia_link (
    source_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    link_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    valid_from TEXT,
    valid_until TEXT,
    PRIMARY KEY (source_id, link_type, target_id)
);

CREATE TABLE synapedia_equivalence (
    source_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    relation TEXT NOT NULL,
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    provenance TEXT,
    PRIMARY KEY (source_id, source_type, relation, target_id)
);

CREATE TABLE synapedia_ghost (
    ghost_id TEXT PRIMARY KEY,
    surface_form TEXT NOT NULL,
    source_span TEXT,
    context TEXT,
    ref_count INTEGER DEFAULT 1,
    epistemic_status TEXT DEFAULT 'GHOST',
    resolved_to_entry_id INTEGER,
    resolved_at TEXT,
    FOREIGN KEY (resolved_to_entry_id) REFERENCES synapedia_entry(entry_id)
);

CREATE TABLE synapedia_group (
    group_id TEXT PRIMARY KEY,
    parent_group_id TEXT,
    group_label TEXT,
    group_type TEXT,
    FOREIGN KEY (parent_group_id) REFERENCES synapedia_group(group_id)
);

CREATE TABLE synapedia_group_member (
    group_id TEXT NOT NULL,
    member_id TEXT NOT NULL,
    member_type TEXT NOT NULL,
    position_index INTEGER,
    PRIMARY KEY (group_id, member_id),
    FOREIGN KEY (group_id) REFERENCES synapedia_group(group_id)
);

CREATE TABLE synapedia_verb_registry (
    verb_lemma TEXT PRIMARY KEY,
    canonical_id TEXT UNIQUE NOT NULL,
    is_generic INTEGER NOT NULL DEFAULT 0,
    description TEXT
);
"""

INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_entry_lemma ON synapedia_entry(lemma, pos_ud);
CREATE INDEX IF NOT EXISTS idx_entry_canonical ON synapedia_entry(canonical_id);
CREATE INDEX IF NOT EXISTS idx_entry_source ON synapedia_entry(source_type);
CREATE INDEX IF NOT EXISTS idx_entry_synset ON synapedia_entry(synset_offset);
CREATE INDEX IF NOT EXISTS idx_entry_tier ON synapedia_entry(definition_tier);
CREATE INDEX IF NOT EXISTS idx_xref_synapedia ON synapedia_source_xref(synapedia_id);
CREATE INDEX IF NOT EXISTS idx_xref_source ON synapedia_source_xref(source_db, source_id);
CREATE INDEX IF NOT EXISTS idx_wn_synset ON wordnet_synset_mapping(synset_offset, pos);
CREATE INDEX IF NOT EXISTS idx_wn_lemma ON wordnet_synset_mapping(lemma, pos);
CREATE INDEX IF NOT EXISTS idx_is_a_child ON synapedia_is_a(synapedia_entry_id);
CREATE INDEX IF NOT EXISTS idx_has_part_whole ON synapedia_has_part(synapedia_entry_id);
CREATE INDEX IF NOT EXISTS idx_has_member_whole ON synapedia_has_member(synapedia_entry_id);
CREATE INDEX IF NOT EXISTS idx_has_purpose_source ON synapedia_has_purpose(synapedia_entry_id);
CREATE INDEX IF NOT EXISTS idx_has_attr_source ON synapedia_has_attribute(synapedia_entry_id);
CREATE INDEX IF NOT EXISTS idx_layer_source ON synapedia_layer(synapedia_entry_id);
CREATE INDEX IF NOT EXISTS idx_has_instance_concept ON synapedia_has_instance(synapedia_entry_id);
CREATE INDEX IF NOT EXISTS idx_antonym_src ON synapedia_antonym_of(synapedia_entry_id);
CREATE INDEX IF NOT EXISTS idx_deriv_from ON synapedia_derivation(from_entry_id);
CREATE INDEX IF NOT EXISTS idx_deriv_to ON synapedia_derivation(to_entry_id);
-- FIX: New indexes for event tables
CREATE INDEX IF NOT EXISTS idx_synapse_verb ON synapedia_synapse(verb_lemma);
CREATE INDEX IF NOT EXISTS idx_spoke_synapse ON synapedia_spoke(synapse_id);
CREATE INDEX IF NOT EXISTS idx_entry_synapse_entry ON synapedia_entry_synapse(entry_id);
CREATE INDEX IF NOT EXISTS idx_entry_synapse_syn ON synapedia_entry_synapse(synapse_id);
CREATE INDEX IF NOT EXISTS idx_link_source ON synapedia_link(source_id, source_type);
CREATE INDEX IF NOT EXISTS idx_link_target ON synapedia_link(target_id, target_type);
CREATE INDEX IF NOT EXISTS idx_equivalence_source ON synapedia_equivalence(source_id, source_type);
CREATE INDEX IF NOT EXISTS idx_ghost_resolved ON synapedia_ghost(resolved_to_entry_id);
CREATE INDEX IF NOT EXISTS idx_group_member_group ON synapedia_group_member(group_id);
"""


# ── Helpers ──────────────────────────────────────────────────────────

def connect(db_path, attach_wn=None):
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-8000000")
    if attach_wn:
        conn.execute(f"ATTACH DATABASE '{str(attach_wn)}' AS wn")
    return conn


def get_example_text(examples_json, _logged_error=[False]):
    if not examples_json or examples_json == "[]":
        return ""
    try:
        exs = json.loads(examples_json)
        if not exs:
            return ""
        first = exs[0]
        if isinstance(first, dict):
            return first.get("text", "") or first.get("english", "")
        return str(first)
    except (json.JSONDecodeError, TypeError) as e:
        if not _logged_error[0]:
            print(f"WARNING: Malformed examples JSON: {e}", file=sys.stderr)
            print(f"  First 200 chars: {str(examples_json)[:200]}", file=sys.stderr)
            _logged_error[0] = True
        return ""


# ── Main ─────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wordnet-db", required=True)
    ap.add_argument("--synapedia-db", default="synapedia.db")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    wn_path = Path(args.wordnet_db).resolve()
    syn_path = Path(args.synapedia_db).resolve()

    if not wn_path.exists():
        print(f"Error: wordnet.db not found at {wn_path}", file=sys.stderr)
        return 1

    print(f"WordNet DB: {wn_path} ({wn_path.stat().st_size:,} bytes)")
    print(f"Synapedia DB: {syn_path}")

    syn_conn = connect(syn_path, attach_wn=wn_path)
    c = syn_conn.cursor()

    if args.reset:
        print("Resetting Synapedia schema...")
        syn_conn.executescript(SCHEMA_SQL)
        syn_conn.commit()
    else:
        syn_conn.executescript(SCHEMA_SQL)
        syn_conn.commit()

    # Seed verb registry
    c.execute("""INSERT OR IGNORE INTO synapedia_verb_registry
        VALUES ('RELATES_TO','en.relates_to.generic_relation.verb.synapedia',1,'Generic compound relation verb')""")
    syn_conn.commit()

    # ═════ Step 1: Entries ═══════════════════════════════════

    print("Reading WordNet entries...")
    wn_entries = c.execute("""
        SELECT id, lemma, pos, gloss, is_prime, ili, examples
        FROM wn.wordnet_entry ORDER BY id
    """).fetchall()
    print(f"  {len(wn_entries)} entries read")

    entry_map = {}
    entry_info = {}
    prime_rows = []
    merge_rows = []

    total_inserted = 0
    print("Inserting entries (no microgloss)...")

    for eid, lemma, pos_short, gloss, is_prime_flag, ili, examples_json in wn_entries:
        pos_original = POS_FULL.get(pos_short, pos_short)
        pos_ud = wn_pos_to_ud(pos_short)
        is_prime_val = 1 if lemma.lower().replace(" ", "_") in NSM_PRIMES or is_prime_flag else 0
        example_text = get_example_text(examples_json)

        c.execute("""
            INSERT INTO synapedia_entry
                (lemma, pos_original, pos_ud, gloss, source_type, definition_tier, language,
                 is_prime, is_molecule, is_instance, example_sentences, synset_offset, ili,
                 embedding_text_needs_rebuild)
            VALUES (?, ?, ?, ?, 'wordnet', 'CORE_ONTOLOGY', 'en', ?, 0, 0, ?, NULL, ?, 1)
        """, (lemma, pos_original, pos_ud, gloss if gloss else "",
              is_prime_val,
              examples_json if examples_json and examples_json != "[]" else None,
              ili))
        syn_id = c.lastrowid
        entry_map[eid] = syn_id
        entry_info[eid] = (lemma, pos_short)

        c.execute("""
            INSERT OR IGNORE INTO synapedia_source_xref (synapedia_id, source_db, source_id)
            VALUES (?, 'wordnet', ?)
        """, (syn_id, eid))

        if is_prime_val:
            prime_rows.append((syn_id, "nsm", 1))
        merge_rows.append((syn_id, "wordnet", eid, 0))
        total_inserted += 1

        if total_inserted % 10000 == 0:
            syn_conn.commit()
            print(f"  entries: {total_inserted}/{len(wn_entries)}", end="\r")

    syn_conn.commit()
    print(f"\n  Inserted {total_inserted} entries.")
    if prime_rows:
        c.executemany("INSERT OR IGNORE INTO synapedia_prime (entry_id, prime_type, version) VALUES (?,?,?)", prime_rows)
        syn_conn.commit()
        print(f"  Inserted {len(prime_rows)} primes.")
    if merge_rows:
        c.executemany("INSERT OR IGNORE INTO synapedia_mergesource (synapedia_entry_id, source_db, source_id, priority) VALUES (?,?,?,?)", merge_rows)
        syn_conn.commit()
        print(f"  Inserted {len(merge_rows)} merge sources.")

    # ═════ Step 2: Synset mappings ══════════════════════════

    print("Reading synset members...")
    synset_members = c.execute("""
        SELECT synset_id, entry_id, word_index
        FROM wn.wordnet_synset_member ORDER BY synset_id, word_index
    """).fetchall()

    synset_data = {}
    for row in c.execute("SELECT id, oewn_id, offset FROM wn.wordnet_synset"):
        synset_data[row[0]] = (row[2], row[1])

    mapping_rows = []
    for sid, eid, wi in synset_members:
        synapedia_id = entry_map.get(eid)
        if synapedia_id is None:
            continue
        offset, oewn_id = synset_data.get(sid, (None, None))
        if offset is None:
            continue
        lemma, pos_short = entry_info[eid]
        mapping_rows.append((synapedia_id, offset, wi, lemma, pos_short, None, oewn_id))

    if mapping_rows:
        cols = ["synapedia_id","synset_offset","word_index","lemma","pos","lex_id","source_synset_id"]
        c.executemany(f"""
            INSERT INTO wordnet_synset_mapping ({','.join(f'"{c}"' for c in cols)})
            VALUES ({','.join('?'*len(cols))})
        """, mapping_rows)
        syn_conn.commit()
    print(f"  Inserted {len(mapping_rows)} mappings.")

    print("Building indexes after raw WordNet data import...")
    syn_conn.executescript(INDEX_SQL)
    syn_conn.commit()

    # ═════ Step 2b: Populate synonyms from synset membership ═════
    print("Populating WordNet synonyms from synset membership...")
    c.execute("""
        WITH synset_synonyms AS (
            SELECT wsm.synapedia_id AS entry_id,
                   json_group_array(DISTINCT e2.lemma) AS synonyms
            FROM wordnet_synset_mapping wsm
            JOIN wordnet_synset_mapping wsm2
              ON wsm.synset_offset = wsm2.synset_offset
             AND wsm.pos = wsm2.pos
             AND wsm.synapedia_id != wsm2.synapedia_id
            JOIN synapedia_entry e2 ON e2.entry_id = wsm2.synapedia_id
            GROUP BY wsm.synapedia_id
            HAVING COUNT(DISTINCT e2.lemma) > 0
        )
        UPDATE synapedia_entry
        SET synonyms_json = (
            SELECT synonyms FROM synset_synonyms
            WHERE synset_synonyms.entry_id = synapedia_entry.entry_id
        )
        WHERE entry_id IN (SELECT entry_id FROM synset_synonyms)
          AND (synonyms_json IS NULL OR synonyms_json = '')
    """)
    syn_conn.commit()
    print(f"  Updated {c.rowcount} entries with WordNet synonyms.")

    # ═════ Step 3: Relations ════════════════════════════════

    print("Reading relations...")
    relations = c.execute("""
        SELECT source_synset_id, target_synset_id, rel_type
        FROM wn.wordnet_relation
    """).fetchall()
    print(f"  {len(relations)} relations read.")

    synset_to_entries = defaultdict(list)
    for sid, eid, wi in synset_members:
        ap = entry_map.get(eid)
        if ap:
            synset_to_entries[sid].append(ap)

    c.execute("CREATE TEMP TABLE IF NOT EXISTS tmp_entry_info (entry_id INTEGER, lemma TEXT, pos_original TEXT, gloss TEXT, canonical_id TEXT)")
    c.execute("DELETE FROM tmp_entry_info")
    c.execute("""
        INSERT INTO tmp_entry_info
        SELECT entry_id, lemma, pos_original, gloss, canonical_id FROM synapedia_entry
    """)
    syn_conn.commit()

    is_a_rows, has_part_rows, has_member_rows = [], [], []
    has_instance_rows, antonym_rows, deriv_rows = [], [], []
    bucket_counts = defaultdict(int)
    skipped_no_parent = 0

    for src_syn_id, tgt_syn_id, rel_type in relations:
        if rel_type not in REL_BUCKET:
            continue
        bucket, invert = REL_BUCKET[rel_type]

        src_entries = synset_to_entries.get(src_syn_id, [])
        tgt_entries = synset_to_entries.get(tgt_syn_id, [])

        if not src_entries or not tgt_entries:
            continue

        if invert:
            child_entries = tgt_entries
            parent_entries = src_entries
        else:
            child_entries = src_entries
            parent_entries = tgt_entries

        parent_rep = parent_entries[0]
        parent_row = c.execute(
            "SELECT lemma, pos_original, gloss, canonical_id FROM tmp_entry_info WHERE entry_id = ?",
            (parent_rep,)
        ).fetchone()
        if not parent_row:
            skipped_no_parent += 1
            continue

        parent_lemma, parent_pos_original, parent_gloss, parent_canon = parent_row
        if not parent_lemma:
            skipped_no_parent += 1
            continue

        for child_ap in child_entries:
            if child_ap == parent_rep:
                continue
            row = (child_ap, parent_lemma, parent_gloss, parent_pos_original, parent_canon)
            if bucket == "is_a":
                is_a_rows.append(row)
            elif bucket == "has_part":
                has_part_rows.append(row)
            elif bucket == "has_member":
                has_member_rows.append(row)
            elif bucket == "has_instance":
                has_instance_rows.append(row)
            elif bucket == "antonym_of":
                antonym_rows.append(row)
            elif bucket == "derivation":
                deriv_rows.append((child_ap, parent_rep, "derivationally_related", "wordnet"))
            bucket_counts[bucket] += 1

    c.execute("DROP TABLE IF EXISTS tmp_entry_info")

    def bulk_insert(table, rows, cols):
        if not rows:
            return
        ph = ','.join('?'*len(cols))
        cn = ','.join(f'"{c}"' for c in cols)
        c.executemany(f"INSERT INTO {table} ({cn}) VALUES ({ph})", rows)
        syn_conn.commit()

    print("\nRelation bucket counts:")
    for b, cnt in sorted(bucket_counts.items()):
        print(f"  {b}: {cnt}")

    bulk_insert("synapedia_is_a", is_a_rows,
                ["synapedia_entry_id","parent_lemma","parent_gloss","parent_pos","parent_canonical_id"])
    bulk_insert("synapedia_has_part", has_part_rows,
                ["synapedia_entry_id","part_lemma","part_gloss","part_pos","part_canonical_id"])
    bulk_insert("synapedia_has_member", has_member_rows,
                ["synapedia_entry_id","member_lemma","member_gloss","member_pos","member_canonical_id"])
    bulk_insert("synapedia_has_instance", has_instance_rows,
                ["synapedia_entry_id","instance_lemma","instance_gloss","instance_pos","instance_canonical_id"])
    bulk_insert("synapedia_antonym_of", antonym_rows,
                ["synapedia_entry_id","antonym_lemma","antonym_gloss","antonym_pos","antonym_canonical_id"])
    if deriv_rows:
        c.executemany("INSERT OR IGNORE INTO synapedia_derivation (from_entry_id, to_entry_id, relation, relation_source) VALUES (?,?,?,?)", deriv_rows)
        syn_conn.commit()

    print(f"\n  is_a={len(is_a_rows)}, has_part={len(has_part_rows)}, "
          f"has_member={len(has_member_rows)}, has_instance={len(has_instance_rows)}, "
          f"antonym={len(antonym_rows)}, derivation={len(deriv_rows)}")
    if skipped_no_parent:
        print(f"  skipped (no parent): {skipped_no_parent}")

    print("Building indexes...")
    syn_conn.executescript(INDEX_SQL)
    syn_conn.commit()

    print("\nFinal Synapedia counts:")
    tables = [
        "synapedia_entry","synapedia_source_xref","wordnet_synset_mapping",
        "synapedia_is_a","synapedia_has_part","synapedia_has_member",
        "synapedia_has_purpose","synapedia_has_attribute","synapedia_layer",
        "synapedia_has_instance","synapedia_antonym_of","synapedia_derivation",
        "synapedia_prime","synapedia_mergesource","synapedia_verb_registry",
        "synapedia_synapse","synapedia_spoke","synapedia_entry_synapse",
        "synapedia_link","synapedia_equivalence","synapedia_ghost",
        "synapedia_group","synapedia_group_member",
    ]
    for t in tables:
        cnt = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {cnt:,}")

    # Also report how many entries now have synonyms
    syn_count = c.execute("SELECT COUNT(*) FROM synapedia_entry WHERE synonyms_json IS NOT NULL AND synonyms_json != ''").fetchone()[0]
    print(f"  synapedia_entry with synonyms: {syn_count:,}")

    syn_conn.execute("DETACH DATABASE wn")
    syn_conn.close()
    print(f"\nDone in {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())