#!/usr/bin/env python3
"""
synapse_store.py — Stage 10 of the GLEAN pipeline

Persist compiled synapses, frames, entities, and groups into a SQLite
database. Also exposes a SynapseStore class with simple read/write
helpers used by the rest of the pipeline.

Schema:

  document         — one row per ingested document
  entity           — one row per entity in the document's entity_map
  synapse          — one row per compiled synapse
  synapse_spoke    — many rows per synapse (the role -> entity edges)
  synapse_frame    — one row per synapse with rhetorical/POV/modality data
  synapse_group    — many rows; synapse-to-group membership
  group_def        — one row per group with its cohesion signal

Idempotent: re-running on the same doc_id replaces prior rows for that doc.

CLI:
    python synapse_store.py init                  # create the schema
    python synapse_store.py status                # show row counts
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sgflib import load_config, ROLES


# =============================================================================
# Schema
# =============================================================================

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS document (
    doc_id          TEXT PRIMARY KEY,
    source_path     TEXT,
    char_length     INTEGER,
    ingested_at     INTEGER NOT NULL,
    fact_to_fluff   REAL,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS entity (
    doc_id          TEXT NOT NULL,
    ent_id          TEXT NOT NULL,
    preferred_canonical TEXT NOT NULL,
    type_hint       TEXT,
    pos             TEXT,
    aliases_json    TEXT,
    anonymous       INTEGER NOT NULL DEFAULT 0,
    chain_json      TEXT,
    lexicon_canonical_id TEXT,
    lookup_decision_level INTEGER,
    lookup_confidence REAL,
    minted          INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (doc_id, ent_id),
    FOREIGN KEY (doc_id) REFERENCES document(doc_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_entity_doc ON entity(doc_id);
CREATE INDEX IF NOT EXISTS idx_entity_canonical
    ON entity(lexicon_canonical_id);

CREATE TABLE IF NOT EXISTS synapse (
    synapse_id          TEXT PRIMARY KEY,
    doc_id              TEXT NOT NULL,
    source_clause_id    INTEGER NOT NULL,
    source_sentence_id  INTEGER,
    source_span_start   INTEGER,
    source_span_end     INTEGER,
    predicate_surface   TEXT NOT NULL,
    predicate_canonical_id TEXT,
    predicate_confidence REAL,
    polarity            TEXT NOT NULL DEFAULT 'positive',
    statement_type      TEXT NOT NULL DEFAULT 'factual',
    created_at          INTEGER NOT NULL,
    FOREIGN KEY (doc_id) REFERENCES document(doc_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_synapse_doc ON synapse(doc_id);
CREATE INDEX IF NOT EXISTS idx_synapse_predicate
    ON synapse(predicate_canonical_id);

CREATE TABLE IF NOT EXISTS synapse_spoke (
    synapse_id          TEXT NOT NULL,
    spoke_index         INTEGER NOT NULL,
    role                TEXT NOT NULL,
    target_ent_id       TEXT,
    target_canonical_id TEXT,
    target_surface      TEXT,
    PRIMARY KEY (synapse_id, spoke_index),
    FOREIGN KEY (synapse_id) REFERENCES synapse(synapse_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_spoke_role ON synapse_spoke(role);
CREATE INDEX IF NOT EXISTS idx_spoke_target_ent ON synapse_spoke(target_ent_id);
CREATE INDEX IF NOT EXISTS idx_spoke_target_cid
    ON synapse_spoke(target_canonical_id);

CREATE TABLE IF NOT EXISTS synapse_frame (
    synapse_id          TEXT PRIMARY KEY,
    rhetorical_mode     TEXT,
    hedging_level       TEXT,
    hedging_words       TEXT,
    point_of_view       TEXT,
    pov_entity_id       TEXT,
    statement_type      TEXT,
    temporal_anchor     TEXT,
    verb_tense          TEXT,
    verb_aspect         TEXT,
    verb_mood           TEXT,
    verb_voice          TEXT,
    verb_polarity       TEXT,
    verb_modality       TEXT,
    verb_features_json  TEXT,
    framing_method      TEXT,    -- 'deterministic' or 'llm:<model>'
    FOREIGN KEY (synapse_id) REFERENCES synapse(synapse_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS group_def (
    group_id            TEXT PRIMARY KEY,
    doc_id              TEXT NOT NULL,
    cohesion_signal     TEXT NOT NULL,
    cohesion_value      TEXT,
    FOREIGN KEY (doc_id) REFERENCES document(doc_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS synapse_group (
    group_id            TEXT NOT NULL,
    synapse_id          TEXT NOT NULL,
    PRIMARY KEY (group_id, synapse_id),
    FOREIGN KEY (group_id) REFERENCES group_def(group_id) ON DELETE CASCADE,
    FOREIGN KEY (synapse_id) REFERENCES synapse(synapse_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_sg_synapse ON synapse_group(synapse_id);

-- Cascade audit log (optional but useful for debugging the lookup cascade)
CREATE TABLE IF NOT EXISTS lookup_audit (
    audit_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id              TEXT NOT NULL,
    target              TEXT NOT NULL,
    context             TEXT,
    decision_level      INTEGER NOT NULL,
    decision_reason     TEXT,
    canonical_id        TEXT,
    confidence          REAL,
    audited_at          INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_doc ON lookup_audit(doc_id);
"""


# =============================================================================
# Store class
# =============================================================================

class SynapseStore:
    """Open or create a synapse SQLite store. Use one instance per process."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    # -------------------------------------------------------------
    # Document-level
    # -------------------------------------------------------------

    def upsert_document(self, doc_id: str, source_path: str | None,
                        char_length: int, fact_to_fluff: float | None = None,
                        notes: str | None = None):
        self._conn.execute("""
            INSERT INTO document (doc_id, source_path, char_length, ingested_at,
                                  fact_to_fluff, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
                source_path = excluded.source_path,
                char_length = excluded.char_length,
                ingested_at = excluded.ingested_at,
                fact_to_fluff = excluded.fact_to_fluff,
                notes = excluded.notes
        """, (doc_id, source_path, char_length, int(time.time()),
              fact_to_fluff, notes))
        self._conn.commit()

    def clear_document(self, doc_id: str):
        """Delete all rows associated with a doc_id. CASCADE handles
        spokes, frames, groups, etc."""
        self._conn.execute("DELETE FROM document WHERE doc_id = ?", (doc_id,))
        self._conn.commit()

    # -------------------------------------------------------------
    # Entity
    # -------------------------------------------------------------

    def upsert_entity(self, doc_id: str, ent: dict):
        self._conn.execute("""
            INSERT INTO entity (doc_id, ent_id, preferred_canonical, type_hint,
                                pos, aliases_json, anonymous, chain_json,
                                lexicon_canonical_id, lookup_decision_level,
                                lookup_confidence, minted)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_id, ent_id) DO UPDATE SET
                preferred_canonical = excluded.preferred_canonical,
                type_hint = excluded.type_hint,
                pos = excluded.pos,
                aliases_json = excluded.aliases_json,
                anonymous = excluded.anonymous,
                chain_json = excluded.chain_json,
                lexicon_canonical_id = excluded.lexicon_canonical_id,
                lookup_decision_level = excluded.lookup_decision_level,
                lookup_confidence = excluded.lookup_confidence,
                minted = excluded.minted
        """, (
            doc_id,
            ent["ent_id"],
            ent["preferred_canonical"],
            ent.get("type_hint"),
            ent.get("pos"),
            json.dumps(ent.get("aliases", [])),
            1 if ent.get("anonymous") else 0,
            json.dumps(ent.get("chain", [])),
            ent.get("lexicon_canonical_id"),
            ent.get("lookup_decision_level", 0),
            ent.get("lookup_confidence", 0.0),
            1 if ent.get("minted") else 0,
        ))

    def commit(self):
        self._conn.commit()

    # -------------------------------------------------------------
    # Synapse
    # -------------------------------------------------------------

    def insert_synapse(self, syn: dict):
        self._conn.execute("""
            INSERT INTO synapse (synapse_id, doc_id, source_clause_id,
                                 source_sentence_id, source_span_start,
                                 source_span_end, predicate_surface,
                                 predicate_canonical_id, predicate_confidence,
                                 polarity, statement_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            syn["synapse_id"],
            syn["doc_id"],
            syn["source_clause_id"],
            syn.get("source_sentence_id"),
            syn.get("source_span_start"),
            syn.get("source_span_end"),
            syn["predicate_surface"],
            syn.get("predicate_canonical_id"),
            syn.get("predicate_confidence", 0.0),
            syn.get("polarity", "positive"),
            syn.get("statement_type", "factual"),
            int(time.time()),
        ))
        for i, spoke in enumerate(syn.get("spokes", [])):
            role = spoke["role"]
            if role not in ROLES:
                raise ValueError(
                    f"synapse {syn['synapse_id']!r} uses role {role!r}, "
                    f"which is not in the closed inventory. The 15 valid "
                    f"roles are: {ROLES}"
                )
            self._conn.execute("""
                INSERT INTO synapse_spoke (synapse_id, spoke_index, role,
                                           target_ent_id, target_canonical_id,
                                           target_surface)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                syn["synapse_id"], i, role,
                spoke.get("target_ent_id"),
                spoke.get("target_canonical_id"),
                spoke.get("target_surface"),
            ))

    def insert_frame(self, synapse_id: str, frame: dict, method: str):
        self._conn.execute("""
            INSERT INTO synapse_frame (synapse_id, rhetorical_mode,
                                       hedging_level, hedging_words,
                                       point_of_view, pov_entity_id,
                                       statement_type, temporal_anchor,
                                       verb_tense, verb_aspect, verb_mood,
                                       verb_voice, verb_polarity, verb_modality,
                                       verb_features_json, framing_method)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(synapse_id) DO UPDATE SET
                rhetorical_mode = excluded.rhetorical_mode,
                hedging_level = excluded.hedging_level,
                hedging_words = excluded.hedging_words,
                point_of_view = excluded.point_of_view,
                pov_entity_id = excluded.pov_entity_id,
                statement_type = excluded.statement_type,
                temporal_anchor = excluded.temporal_anchor,
                verb_tense = excluded.verb_tense,
                verb_aspect = excluded.verb_aspect,
                verb_mood = excluded.verb_mood,
                verb_voice = excluded.verb_voice,
                verb_polarity = excluded.verb_polarity,
                verb_modality = excluded.verb_modality,
                verb_features_json = excluded.verb_features_json,
                framing_method = excluded.framing_method
        """, (
            synapse_id,
            frame.get("rhetorical_mode"),
            frame.get("hedging_level"),
            frame.get("hedging_words"),
            frame.get("point_of_view"),
            frame.get("pov_entity_id"),
            frame.get("statement_type"),
            frame.get("temporal_anchor"),
            frame.get("verb_tense"),
            frame.get("verb_aspect"),
            frame.get("verb_mood"),
            frame.get("verb_voice"),
            frame.get("verb_polarity"),
            frame.get("verb_modality"),
            json.dumps(frame.get("verb_features", {})),
            method,
        ))

    # -------------------------------------------------------------
    # Groups
    # -------------------------------------------------------------

    def insert_group(self, group_id: str, doc_id: str,
                     cohesion_signal: str, cohesion_value: str,
                     synapse_ids: list[str]):
        self._conn.execute("""
            INSERT OR REPLACE INTO group_def (group_id, doc_id,
                                              cohesion_signal, cohesion_value)
            VALUES (?, ?, ?, ?)
        """, (group_id, doc_id, cohesion_signal, cohesion_value))
        for sid in synapse_ids:
            self._conn.execute("""
                INSERT OR IGNORE INTO synapse_group (group_id, synapse_id)
                VALUES (?, ?)
            """, (group_id, sid))

    # -------------------------------------------------------------
    # Audit
    # -------------------------------------------------------------

    def log_lookup(self, doc_id: str, target: str, context: str,
                   decision_level: int, decision_reason: str,
                   canonical_id: str | None, confidence: float):
        self._conn.execute("""
            INSERT INTO lookup_audit (doc_id, target, context, decision_level,
                                      decision_reason, canonical_id,
                                      confidence, audited_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (doc_id, target, context, decision_level, decision_reason,
              canonical_id, confidence, int(time.time())))

    # -------------------------------------------------------------
    # Read-side helpers
    # -------------------------------------------------------------

    def status(self) -> dict:
        c = self._conn.execute
        out = {
            "documents": c("SELECT COUNT(*) FROM document").fetchone()[0],
            "entities": c("SELECT COUNT(*) FROM entity").fetchone()[0],
            "synapses": c("SELECT COUNT(*) FROM synapse").fetchone()[0],
            "spokes": c("SELECT COUNT(*) FROM synapse_spoke").fetchone()[0],
            "frames": c("SELECT COUNT(*) FROM synapse_frame").fetchone()[0],
            "groups": c("SELECT COUNT(*) FROM group_def").fetchone()[0],
        }
        return out

    def close(self):
        self._conn.close()


# =============================================================================
# CLI
# =============================================================================

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Initialize the schema")
    sub.add_parser("status", help="Show row counts")

    args = p.parse_args()
    cfg = load_config()
    store = SynapseStore(cfg.synapse_store_path)
    try:
        if args.cmd == "init":
            print(f"Schema initialized at {store.db_path}")
        elif args.cmd == "status":
            s = store.status()
            print(f"Synapse store: {store.db_path}")
            for k, v in s.items():
                print(f"  {k:<12} {v:,}")
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
