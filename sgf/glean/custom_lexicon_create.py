#!/usr/bin/env python3
"""
custom_lexicon_create.py — Create an empty custom lexicon database.

The custom lexicon is Layer 2 (domain TBox) in the three-layer architecture.
It stores entities scoped to a specific namespace — document entities,
dynamic metonymic instances, corpus-level entities, or any named scope.

The namespace parameter controls:
  1. The filename (if not explicitly provided): {namespace}.db
  2. The canonical ID prefix: {namespace}.{lemma}.{type}.{domain}

Examples:
    python custom_lexicon_create.py --namespace alpha
        -> Creates alpha.db with IDs like alpha.acme_corp.organization.legal

    python custom_lexicon_create.py --namespace doc --db D:/data/custom_lexicon.db
        -> Creates custom_lexicon.db with IDs like doc.acme_corp.organization.docloc

    python custom_lexicon_create.py --namespace dyn --db beethoven_metonymic.db
        -> Creates beethoven_metonymic.db with IDs like dyn.bach.corpus_of_music.inferred

Usage:
    python custom_lexicon_create.py --namespace alpha
    python custom_lexicon_create.py --namespace corp --db D:/corpora/legal/corpus.db
    python custom_lexicon_create.py --namespace doc --db my_doc_lexicon.db --seed-ontology my_ontology.ttl
"""

import argparse
import sqlite3
import sys
from pathlib import Path


def create_schema(db_path: str, namespace: str) -> None:
    """Create an empty custom lexicon database with the full schema.

    The namespace becomes the prefix for all canonical IDs stored in this DB.
    For example, namespace='alpha' produces IDs like:
        alpha.{lemma}.{microgloss}.{pos}.{domain}
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    cur = conn.cursor()

    # Store the namespace so downstream tools can read it
    cur.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    cur.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('namespace', ?)",
                (namespace,))
    cur.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('version', '3.2')")

    # ── Entry table ──────────────────────────────────────────────────
    # The canonical_id column uses the namespace as prefix.
    # Example for namespace='alpha':  alpha.acme_corp.organization.legal
    cur.execute("""
        CREATE TABLE IF NOT EXISTS entry (
            entry_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_id    TEXT NOT NULL UNIQUE,
            lemma           TEXT NOT NULL,
            pos_ud          TEXT DEFAULT 'NOUN',
            gloss           TEXT DEFAULT '',
            source_type     TEXT DEFAULT 'custom',
            definition_tier TEXT DEFAULT 'INFERRED',
            is_instance     INTEGER DEFAULT 0,
            ref_count       INTEGER DEFAULT 0,
            type_id         TEXT,       -- e.g., en.organization.social_group.noun.core
            type_confidence REAL DEFAULT 0.0,
            namespace       TEXT NOT NULL,  -- 'alpha', 'doc', 'dyn', 'corp', etc.
            promoted        INTEGER DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now'))
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_entry_lemma ON entry(lemma, pos_ud)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entry_canonical ON entry(canonical_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entry_namespace ON entry(namespace)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entry_type ON entry(type_id)")

    # ── Alias table ──────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS alias (
            entry_id    INTEGER NOT NULL,
            alias       TEXT NOT NULL,
            source      TEXT DEFAULT 'glean',
            PRIMARY KEY (entry_id, alias),
            FOREIGN KEY (entry_id) REFERENCES entry(entry_id) ON DELETE CASCADE
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_alias_alias ON alias(alias)")

    # ── RDF source table ─────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rdf_source (
            entry_id        INTEGER NOT NULL,
            rdf_uri         TEXT NOT NULL,
            rdf_source_file TEXT,
            imported_at     TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (entry_id, rdf_uri),
            FOREIGN KEY (entry_id) REFERENCES entry(entry_id) ON DELETE CASCADE
        )
    """)

    # ── IS_A links to core Synapedia ─────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS is_a_link (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id        INTEGER NOT NULL,
            parent_lemma    TEXT NOT NULL,
            parent_canonical_id TEXT,
            relation_source TEXT DEFAULT 'glean',
            trust_level     TEXT DEFAULT 'provisional',
            FOREIGN KEY (entry_id) REFERENCES entry(entry_id) ON DELETE CASCADE
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_is_a_child ON is_a_link(entry_id)")

    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Create an empty custom lexicon database for a named namespace."
    )
    parser.add_argument("--namespace", required=True,
                        help="Namespace prefix (e.g., 'alpha', 'doc', 'dyn', 'corp'). "
                             "Becomes both the ID prefix and the default filename.")
    parser.add_argument("--db", default=None,
                        help="Path to the database file. "
                             "Default: {namespace}.db in the current directory.")
    parser.add_argument("--seed-ontology", default=None,
                        help="Optional RDF/OWL file to import initially")
    args = parser.parse_args()

    namespace = args.namespace.strip().lower()
    if not namespace:
        print("Error: namespace cannot be empty.", file=sys.stderr)
        return 1
    if not namespace.replace("_", "").isalnum():
        print("Error: namespace must contain only letters, digits, and underscores.",
              file=sys.stderr)
        return 1

    # Determine filename: if --db is given, use it; otherwise {namespace}.db
    db_path = Path(args.db) if args.db else Path(f"{namespace}.db")

    if db_path.exists():
        print(f"Error: Database already exists at {db_path}", file=sys.stderr)
        return 1

    print(f"Creating custom lexicon database:")
    print(f"  Namespace: {namespace}")
    print(f"  File:      {db_path.resolve()}")
    print(f"  ID prefix: {namespace}.{{lemma}}.{{microgloss}}.{{pos}}.{{domain}}")

    create_schema(str(db_path), namespace)
    print("  Schema created.")

    if args.seed_ontology:
        print(f"  Seed ontology import not yet implemented: {args.seed_ontology}")
        print("  Run custom_lexicon_import_rdf.py separately.")

    print()
    print(f"Ready for use. Point sgf.toml [custom_lexicon].path to this file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())