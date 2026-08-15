#!/usr/bin/env python3
"""
create_empty_db.py — Create an empty Synapedia database with the full schema.

Run this once before importing WordNet, Wiktionary, or Wikipedia.
Creates all tables, indexes, and seeds the verb registry.

Usage:
    python create_empty_db.py synapedia.db
"""

import argparse
import sqlite3
import sys


def create_schema(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    cur = conn.cursor()

    # Core entry table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS synapedia_entry (
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
            synonyms_json TEXT,                        -- NEW: synonyms from WordNet/Wiktionary
            synset_offset INTEGER, word_index INTEGER, lex_id INTEGER,
            lex_domain TEXT, freq_count INTEGER DEFAULT 0, ili TEXT,
            is_microgloss_provisional INTEGER DEFAULT 1,
            microgloss_source TEXT DEFAULT 'algorithm',
            embedding_text TEXT,
            embedding_text_version TEXT,
            embedding_text_needs_rebuild INTEGER DEFAULT 1,
            embedding BLOB,
            bow TEXT DEFAULT '',
            improved_at TEXT,
            is_variant INTEGER DEFAULT 0,
            is_preferred INTEGER DEFAULT 0,
            preferred_entry_id INTEGER,
            valid_from TEXT, valid_until TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # Binary core relations
    cur.execute("""
        CREATE TABLE IF NOT EXISTS synapedia_is_a (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            synapedia_entry_id INTEGER NOT NULL,
            parent_lemma TEXT NOT NULL,
            parent_gloss TEXT, parent_pos TEXT, parent_canonical_id TEXT,
            logical_gate TEXT DEFAULT 'AND',
            match_score REAL DEFAULT 1.0,
            relation_source TEXT DEFAULT 'wordnet',
            trust_level TEXT DEFAULT 'verified',
            valid_from TEXT, valid_until TEXT,
            FOREIGN KEY (synapedia_entry_id) REFERENCES synapedia_entry(entry_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS synapedia_has_part (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            synapedia_entry_id INTEGER NOT NULL,
            part_lemma TEXT NOT NULL,
            part_gloss TEXT, part_pos TEXT, part_canonical_id TEXT,
            logical_gate TEXT DEFAULT 'AND',
            match_score REAL DEFAULT 1.0,
            relation_source TEXT DEFAULT 'wordnet',
            trust_level TEXT DEFAULT 'verified',
            valid_from TEXT, valid_until TEXT,
            FOREIGN KEY (synapedia_entry_id) REFERENCES synapedia_entry(entry_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS synapedia_has_member (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            synapedia_entry_id INTEGER NOT NULL,
            member_lemma TEXT NOT NULL,
            member_gloss TEXT, member_pos TEXT, member_canonical_id TEXT,
            logical_gate TEXT DEFAULT 'AND',
            match_score REAL DEFAULT 1.0,
            relation_source TEXT DEFAULT 'wordnet',
            trust_level TEXT DEFAULT 'verified',
            valid_from TEXT, valid_until TEXT,
            FOREIGN KEY (synapedia_entry_id) REFERENCES synapedia_entry(entry_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS synapedia_has_instance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            synapedia_entry_id INTEGER NOT NULL,
            instance_lemma TEXT NOT NULL,
            instance_gloss TEXT, instance_pos TEXT, instance_canonical_id TEXT,
            logical_gate TEXT DEFAULT 'AND',
            match_score REAL DEFAULT 1.0,
            relation_source TEXT DEFAULT 'wordnet',
            trust_level TEXT DEFAULT 'verified',
            valid_from TEXT, valid_until TEXT,
            FOREIGN KEY (synapedia_entry_id) REFERENCES synapedia_entry(entry_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS synapedia_antonym_of (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            synapedia_entry_id INTEGER NOT NULL,
            antonym_lemma TEXT NOT NULL,
            antonym_gloss TEXT, antonym_pos TEXT, antonym_canonical_id TEXT,
            logical_gate TEXT DEFAULT 'AND',
            match_score REAL DEFAULT 1.0,
            relation_source TEXT DEFAULT 'wordnet',
            trust_level TEXT DEFAULT 'verified',
            valid_from TEXT, valid_until TEXT,
            FOREIGN KEY (synapedia_entry_id) REFERENCES synapedia_entry(entry_id)
        )
    """)

    # Attribute and purpose caches
    cur.execute("""
        CREATE TABLE IF NOT EXISTS synapedia_has_attribute (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            synapedia_entry_id INTEGER NOT NULL,
            attribute_key TEXT NOT NULL,
            attribute_value TEXT NOT NULL DEFAULT '',
            logical_gate TEXT DEFAULT 'AND',
            relation_source TEXT DEFAULT 'llm',
            trust_level TEXT DEFAULT 'verified',
            FOREIGN KEY (synapedia_entry_id) REFERENCES synapedia_entry(entry_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS synapedia_has_purpose (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            synapedia_entry_id INTEGER NOT NULL,
            purpose_lemma TEXT, purpose_gloss TEXT, purpose_pos TEXT,
            purpose_canonical_id TEXT, match_score REAL,
            logical_gate TEXT DEFAULT 'AND',
            relation_source TEXT DEFAULT 'llm',
            trust_level TEXT DEFAULT 'verified',
            FOREIGN KEY (synapedia_entry_id) REFERENCES synapedia_entry(entry_id)
        )
    """)

    # Event tables (Synapse model)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS synapedia_synapse (
            synapse_id TEXT PRIMARY KEY,
            verb_lemma TEXT NOT NULL,
            verb_canonical_id TEXT,
            plane TEXT NOT NULL DEFAULT 'ontological',
            epistemic_status TEXT DEFAULT 'CONSTITUTIVE',
            pov TEXT, trust_level TEXT DEFAULT 'provisional',
            source_span TEXT, derivation_tag TEXT DEFAULT 'EXPRESSED',
            valid_from TEXT, valid_until TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS synapedia_spoke (
            synapse_id TEXT NOT NULL,
            role TEXT NOT NULL,
            target_id TEXT, target_type TEXT DEFAULT 'concept',
            target_lemma TEXT, literal_value TEXT,
            source_span TEXT, pov TEXT,
            FOREIGN KEY (synapse_id) REFERENCES synapedia_synapse(synapse_id),
            PRIMARY KEY (synapse_id, role, target_id, target_lemma)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS synapedia_entry_synapse (
            entry_id INTEGER NOT NULL,
            synapse_id TEXT NOT NULL,
            relation TEXT NOT NULL DEFAULT 'has_event',
            PRIMARY KEY (entry_id, synapse_id),
            FOREIGN KEY (entry_id) REFERENCES synapedia_entry(entry_id),
            FOREIGN KEY (synapse_id) REFERENCES synapedia_synapse(synapse_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS synapedia_link (
            source_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            link_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            target_type TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            valid_from TEXT, valid_until TEXT,
            PRIMARY KEY (source_id, link_type, target_id)
        )
    """)

    # Group containers
    cur.execute("""
        CREATE TABLE IF NOT EXISTS synapedia_group (
            group_id TEXT PRIMARY KEY,
            parent_group_id TEXT, group_label TEXT, group_type TEXT,
            FOREIGN KEY (parent_group_id) REFERENCES synapedia_group(group_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS synapedia_group_member (
            group_id TEXT NOT NULL,
            member_id TEXT NOT NULL,
            member_type TEXT NOT NULL,
            position_index INTEGER,
            PRIMARY KEY (group_id, member_id),
            FOREIGN KEY (group_id) REFERENCES synapedia_group(group_id)
        )
    """)

    # Identity mapping (no destructive merge)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS synapedia_equivalence (
            source_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            relation TEXT NOT NULL,
            target_id TEXT NOT NULL,
            target_type TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            provenance TEXT,
            PRIMARY KEY (source_id, source_type, relation, target_id)
        )
    """)

    # Ghost protocol
    cur.execute("""
        CREATE TABLE IF NOT EXISTS synapedia_ghost (
            ghost_id TEXT PRIMARY KEY,
            surface_form TEXT NOT NULL,
            source_span TEXT, context TEXT,
            ref_count INTEGER DEFAULT 1,
            epistemic_status TEXT DEFAULT 'GHOST',
            resolved_to_entry_id INTEGER,
            resolved_at TEXT,
            FOREIGN KEY (resolved_to_entry_id) REFERENCES synapedia_entry(entry_id)
        )
    """)

    # Auxiliary tables
    cur.execute("""
        CREATE TABLE IF NOT EXISTS synapedia_verb_registry (
            verb_lemma TEXT PRIMARY KEY,
            canonical_id TEXT UNIQUE NOT NULL,
            is_generic INTEGER NOT NULL DEFAULT 0,
            description TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS synapedia_prime (
            entry_id INTEGER NOT NULL,
            prime_type TEXT NOT NULL DEFAULT 'nsm',
            version INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (entry_id, prime_type, version),
            FOREIGN KEY (entry_id) REFERENCES synapedia_entry(entry_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS synapedia_mergesource (
            merge_id INTEGER PRIMARY KEY AUTOINCREMENT,
            synapedia_entry_id INTEGER NOT NULL,
            source_db TEXT NOT NULL DEFAULT 'wordnet',
            source_id INTEGER NOT NULL,
            priority INTEGER NOT NULL DEFAULT 0,
            merged_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (synapedia_entry_id) REFERENCES synapedia_entry(entry_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS synapedia_source_xref (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            synapedia_id INTEGER NOT NULL,
            source_db TEXT NOT NULL,
            source_id INTEGER NOT NULL,
            merged_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(source_db, source_id),
            FOREIGN KEY (synapedia_id) REFERENCES synapedia_entry(entry_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS synapedia_derivation (
            from_entry_id INTEGER NOT NULL,
            to_entry_id INTEGER NOT NULL,
            relation TEXT NOT NULL DEFAULT 'derivationally_related',
            relation_source TEXT NOT NULL DEFAULT 'wordnet',
            valid_from TEXT, valid_until TEXT,
            PRIMARY KEY (from_entry_id, to_entry_id, relation),
            FOREIGN KEY (from_entry_id) REFERENCES synapedia_entry(entry_id),
            FOREIGN KEY (to_entry_id) REFERENCES synapedia_entry(entry_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS synapedia_layer (
            synapedia_entry_id INTEGER PRIMARY KEY,
            built_at TEXT, model TEXT, source TEXT,
            suggested_microgloss TEXT, suggested_gloss TEXT,
            comments TEXT, quality_score REAL,
            FOREIGN KEY (synapedia_entry_id) REFERENCES synapedia_entry(entry_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wordnet_synset_mapping (
            synapedia_id INTEGER PRIMARY KEY,
            synset_offset INTEGER NOT NULL,
            word_index INTEGER NOT NULL,
            lemma TEXT NOT NULL,
            pos TEXT NOT NULL,
            lex_id INTEGER, source_synset_id TEXT,
            FOREIGN KEY (synapedia_id) REFERENCES synapedia_entry(entry_id)
        )
    """)

    # Indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entry_lemma ON synapedia_entry(lemma, pos_ud)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entry_canonical ON synapedia_entry(canonical_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entry_source ON synapedia_entry(source_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entry_synset ON synapedia_entry(synset_offset)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entry_tier ON synapedia_entry(definition_tier)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_is_a_child ON synapedia_is_a(synapedia_entry_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_has_part_whole ON synapedia_has_part(synapedia_entry_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_has_member_whole ON synapedia_has_member(synapedia_entry_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_has_instance_concept ON synapedia_has_instance(synapedia_entry_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_antonym_src ON synapedia_antonym_of(synapedia_entry_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_has_attr_source ON synapedia_has_attribute(synapedia_entry_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_has_purpose_source ON synapedia_has_purpose(synapedia_entry_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_link_source ON synapedia_link(source_id, source_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_link_target ON synapedia_link(target_id, target_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_xref_synapedia ON synapedia_source_xref(synapedia_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_xref_source ON synapedia_source_xref(source_db, source_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_spoke_synapse ON synapedia_spoke(synapse_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_synapse_verb ON synapedia_synapse(verb_lemma)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entry_synapse_entry ON synapedia_entry_synapse(entry_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entry_synapse_syn ON synapedia_entry_synapse(synapse_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_equivalence_source ON synapedia_equivalence(source_id, source_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ghost_resolved ON synapedia_ghost(resolved_to_entry_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_deriv_from ON synapedia_derivation(from_entry_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_deriv_to ON synapedia_derivation(to_entry_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_layer_source ON synapedia_layer(synapedia_entry_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_group_member_group ON synapedia_group_member(group_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_wn_synset ON wordnet_synset_mapping(synset_offset, pos)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_wn_lemma ON wordnet_synset_mapping(lemma, pos)")

    # Seed the verb registry
    cur.execute("""
        INSERT OR IGNORE INTO synapedia_verb_registry (verb_lemma, canonical_id, is_generic, description)
        VALUES ('RELATES_TO', 'en.relates_to.generic_relation.verb', 1, 'Generic compound verb for citizenship, employment, ownership, etc.')
    """)

    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Create an empty Synapedia database with the full schema.")
    parser.add_argument("db", help="Path to the new database file (e.g., synapedia.db)")
    args = parser.parse_args()

    print(f"Creating empty database: {args.db}")
    create_schema(args.db)
    print("Done. All tables, indexes, and verb registry seeded.")
    print("Ready to run import_wordnet.py, import_wiktionary_to_synapedia.py, etc.")


if __name__ == "__main__":
    sys.exit(main())
