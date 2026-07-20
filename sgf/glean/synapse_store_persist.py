#!/usr/bin/env python3
"""
synapse_store_persist.py — Stage 10 of the GLEAN pipeline (v3.2)

Persist compiled synapses, frames, entities, and groups into the
Synapedia v3.0 schema.  Replaces the old synapse_store.py.

Writes to THREE destinations:

  1. synapse_store_{corpus}.db   — ABox: synapses, spokes, frames, groups, links
  2. custom_lexicon_{corpus}.db  — Domain TBox: minted (doc.*) entities
  3. ghost_registry.db           — Pending metonymic shifts

Backward-compatible: runs the v3.2 migration on open if older columns
are missing.  The old `document` and `entity` tables are kept for
document-level tracking.

Usage (via compile_document.py):
    from synapse_store_persist import persist_all

    persist_all(
        syn_db_path="synapse_store_corp_001.db",
        custom_db_path="custom_lexicon_corp_001.db",
        ghost_db_path="ghost_registry.db",
        doc_id="beethoven_001",
        entity_map=entity_map,
        synapses_framed=framed,
        groups=groups,
        source_path="beethoven.txt",
        source_text=text,
    )
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sgflib import ROLES


# =============================================================================
# Constants
# =============================================================================

# Synapedia table names (Layer 3 ABox)
SYNAPSE_TABLE = "synapedia_synapse"
SPOKE_TABLE = "synapedia_spoke"
ENTRY_SYNAPSE_TABLE = "synapedia_entry_synapse"
GROUP_TABLE = "synapedia_group"
GROUP_MEMBER_TABLE = "synapedia_group_member"
LINK_TABLE = "synapedia_link"

# GLEAN-specific tracking tables (kept for backward compat)
DOCUMENT_TABLE = "document"
ENTITY_TABLE = "entity"

# Valid link types (from the 29 primitives)
VALID_LINK_TYPES = frozenset({
    "PRECEDES", "CAUSES", "ENABLES", "SUPPORTS", "CONTRADICTS",
    "ELABORATES", "SUPERSEDES", "DEPENDS_ON",
})


# =============================================================================
# Schema SQL
# =============================================================================

SYNAPSE_STORE_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

-- GLEAN-specific: track which documents were compiled
CREATE TABLE IF NOT EXISTS document (
    doc_id          TEXT PRIMARY KEY,
    source_path     TEXT,
    char_length     INTEGER,
    ingested_at     INTEGER NOT NULL,
    fact_to_fluff   REAL,
    notes           TEXT
);

-- GLEAN-specific: document-local entity map
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
    specificity     TEXT DEFAULT 'general',
    maturity_tier   TEXT,
    rewritten_to_standard INTEGER NOT NULL DEFAULT 0,
    matched_canonical_id TEXT,
    nexus_namespace TEXT DEFAULT 'synapedia',
    custom_lexicon_id TEXT,
    ref_count       INTEGER DEFAULT 0,
    PRIMARY KEY (doc_id, ent_id),
    FOREIGN KEY (doc_id) REFERENCES document(doc_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_entity_doc ON entity(doc_id);
CREATE INDEX IF NOT EXISTS idx_entity_canonical ON entity(lexicon_canonical_id);

-- Synapedia v3.0 compatible: event hub
CREATE TABLE IF NOT EXISTS synapedia_synapse (
    synapse_id          TEXT PRIMARY KEY,
    verb_lemma          TEXT NOT NULL,
    verb_canonical_id   TEXT,
    plane               TEXT NOT NULL DEFAULT 'claim',
    epistemic_status    TEXT DEFAULT 'SOURCED',
    derivation_tag      TEXT DEFAULT 'EXPRESSED',
    pov                 TEXT,
    trust_level         TEXT DEFAULT 'provisional',
    source_span         TEXT,
    frame_json          TEXT,
    doc_id              TEXT,
    source_clause_id    INTEGER,
    source_sentence_id  INTEGER,
    source_span_start   INTEGER,
    source_span_end     INTEGER,
    polarity            TEXT NOT NULL DEFAULT 'positive',
    statement_type      TEXT NOT NULL DEFAULT 'factual',
    created_at          INTEGER NOT NULL,
    FOREIGN KEY (doc_id) REFERENCES document(doc_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_syn_doc ON synapedia_synapse(doc_id);
CREATE INDEX IF NOT EXISTS idx_syn_verb ON synapedia_synapse(verb_canonical_id);

-- Synapedia v3.0 compatible: event participants
CREATE TABLE IF NOT EXISTS synapedia_spoke (
    synapse_id          TEXT NOT NULL,
    spoke_index         INTEGER NOT NULL,
    role                TEXT NOT NULL,
    target_id           TEXT,
    target_type         TEXT DEFAULT 'concept',
    target_lemma        TEXT,
    literal_value       TEXT,
    source_span         TEXT,
    pov                 TEXT,
    target_ent_id       TEXT,
    target_canonical_id TEXT,
    target_surface      TEXT,
    PRIMARY KEY (synapse_id, spoke_index),
    FOREIGN KEY (synapse_id) REFERENCES synapedia_synapse(synapse_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_spoke_role ON synapedia_spoke(role);
CREATE INDEX IF NOT EXISTS idx_spoke_target ON synapedia_spoke(target_id);

-- Synapedia v3.0 compatible: entry-to-event linking
CREATE TABLE IF NOT EXISTS synapedia_entry_synapse (
    entry_id    INTEGER NOT NULL,
    synapse_id  TEXT NOT NULL,
    relation    TEXT NOT NULL DEFAULT 'has_event',
    PRIMARY KEY (entry_id, synapse_id),
    FOREIGN KEY (synapse_id) REFERENCES synapedia_synapse(synapse_id) ON DELETE CASCADE
);

-- Synapedia v3.0 compatible: groups
CREATE TABLE IF NOT EXISTS synapedia_group (
    group_id        TEXT PRIMARY KEY,
    parent_group_id TEXT,
    group_label     TEXT,
    group_type      TEXT
);

-- Synapedia v3.0 compatible: group membership
CREATE TABLE IF NOT EXISTS synapedia_group_member (
    group_id        TEXT NOT NULL,
    member_id       TEXT NOT NULL,
    member_type     TEXT NOT NULL DEFAULT 'synapse',
    position_index  INTEGER,
    PRIMARY KEY (group_id, member_id),
    FOREIGN KEY (group_id) REFERENCES synapedia_group(group_id) ON DELETE CASCADE
);

-- Synapedia v3.0 compatible: links (PRECEDES, CAUSES, etc.)
CREATE TABLE IF NOT EXISTS synapedia_link (
    source_id       TEXT NOT NULL,
    source_type     TEXT NOT NULL DEFAULT 'synapse',
    link_type       TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    target_type     TEXT NOT NULL DEFAULT 'synapse',
    confidence      REAL DEFAULT 1.0,
    valid_from      TEXT,
    valid_until     TEXT,
    PRIMARY KEY (source_id, link_type, target_id)
);
CREATE INDEX IF NOT EXISTS idx_link_source ON synapedia_link(source_id, source_type);
CREATE INDEX IF NOT EXISTS idx_link_target ON synapedia_link(target_id, target_type);

-- Audit log (optional, for debugging the lookup cascade)
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
# Helpers
# =============================================================================

def _deterministic_synapse_id(verb: str, doc_id: str, clause_idx: int) -> str:
    """Generate a deterministic synapse_id from content."""
    raw = f"{doc_id}:{verb}:{clause_idx}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"syn.{h}"


def _is_metonymic_entity(ent: dict) -> bool:
    """Check if an entity was created from a metonymic shift."""
    return ent.get("metonymic_ghost", False) or \
           (ent.get("lexicon_canonical_id", "") or "").startswith("dyn.")


# =============================================================================
# Migration
# =============================================================================

def _migrate_v32(conn: sqlite3.Connection) -> None:
    """Idempotent migration from v1.2 to v3.2 schema.

    Adds columns that may not exist if the DB was created by the old
    synapse_store.py.  Safe to run multiple times.
    """
    cur = conn.cursor()

    additions = [
        # synapse table
        ("synapedia_synapse", "frame_json", "TEXT"),
        ("synapedia_synapse", "verb_lemma", "TEXT"),
        ("synapedia_synapse", "verb_canonical_id", "TEXT"),
        ("synapedia_synapse", "plane", "TEXT NOT NULL DEFAULT 'claim'"),
        ("synapedia_synapse", "epistemic_status", "TEXT DEFAULT 'SOURCED'"),
        ("synapedia_synapse", "derivation_tag", "TEXT DEFAULT 'EXPRESSED'"),
        ("synapedia_synapse", "pov", "TEXT"),
        ("synapedia_synapse", "source_span", "TEXT"),
        ("synapedia_synapse", "doc_id", "TEXT"),
        # spoke table
        ("synapedia_spoke", "target_id", "TEXT"),
        ("synapedia_spoke", "target_type", "TEXT DEFAULT 'concept'"),
        ("synapedia_spoke", "target_lemma", "TEXT"),
        ("synapedia_spoke", "literal_value", "TEXT"),
        ("synapedia_spoke", "source_span", "TEXT"),
        ("synapedia_spoke", "pov", "TEXT"),
        # entity table
        ("entity", "nexus_namespace", "TEXT DEFAULT 'synapedia'"),
        ("entity", "custom_lexicon_id", "TEXT"),
        ("entity", "ref_count", "INTEGER DEFAULT 0"),
    ]

    for table, col, decl in additions:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower() and \
               "no such table" not in str(e).lower():
                raise

    conn.commit()


# =============================================================================
# Custom Lexicon Schema
# =============================================================================

CUSTOM_LEXICON_SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS entry (
    entry_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_id    TEXT NOT NULL UNIQUE,
    lemma           TEXT NOT NULL,
    pos_ud          TEXT DEFAULT 'NOUN',
    gloss           TEXT DEFAULT '',
    source_type     TEXT DEFAULT 'custom',
    definition_tier TEXT DEFAULT 'GHOST',
    is_instance     INTEGER DEFAULT 0,
    ref_count       INTEGER DEFAULT 0,
    type_id         TEXT,
    type_confidence REAL DEFAULT 0.0,
    corpus          TEXT NOT NULL,
    promoted        INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS alias (
    entry_id    INTEGER NOT NULL,
    alias       TEXT NOT NULL,
    source      TEXT DEFAULT 'glean',
    PRIMARY KEY (entry_id, alias)
);

CREATE TABLE IF NOT EXISTS rdf_source (
    entry_id        INTEGER NOT NULL,
    rdf_uri         TEXT NOT NULL,
    rdf_source_file TEXT,
    imported_at     TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (entry_id, rdf_uri)
);
"""


# =============================================================================
# Ghost Registry Schema
# =============================================================================

GHOST_REGISTRY_SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS ghost (
    ghost_id                TEXT PRIMARY KEY,
    surface_form            TEXT NOT NULL,
    context                 TEXT,
    doc_id                  TEXT NOT NULL,
    clause_id               INTEGER,
    detected_pattern        TEXT,
    source_canonical_id     TEXT,
    frequency               INTEGER DEFAULT 1,
    created_at              TEXT DEFAULT (datetime('now')),
    resolved_to_canonical_id TEXT,
    resolved_at             TEXT
);
"""


# =============================================================================
# Persist all
# =============================================================================

def persist_all(
    syn_db_path: str,
    custom_db_path: Optional[str],
    ghost_db_path: Optional[str],
    doc_id: str,
    entity_map: dict,
    synapses_framed: List[dict],
    groups: List[dict],
    source_path: Optional[str] = None,
    source_text: str = "",
    accuracy_mode: str = "standard",
) -> Dict[str, int]:
    """Main entry point: write all GLEAN output to the three databases.

    Parameters
    ----------
    syn_db_path : str
        Path to synapse_store_{corpus}.db (ABox).
    custom_db_path : str or None
        Path to custom_lexicon_{corpus}.db (domain TBox).  If None,
        minted entities are not written to a custom lexicon.
    ghost_db_path : str or None
        Path to ghost_registry.db.  If None, ghosts are not written.
    doc_id : str
        Stable document identifier.
    entity_map : dict
        The entity_map.json from entity_census.
    synapses_framed : list[dict]
        The synapses_framed.json from framing.py.
    groups : list[dict]
        The groups.json from synapse_grouper.py.
    source_path : str or None
        Original file path of the source document.
    source_text : str
        Full text of the source document.
    accuracy_mode : str
        'casual', 'standard', or 'rigorous'.

    Returns
    -------
    dict
        Counts of written rows: {synapses, spokes, groups, members, links,
        minted_entities, ghosts}.
    """
    counts: Dict[str, int] = {
        "synapses": 0,
        "spokes": 0,
        "groups": 0,
        "members": 0,
        "links": 0,
        "minted_entities": 0,
        "ghosts": 0,
    }

    # ── 1. Open synapse store ───────────────────────────────────────
    syn_path = Path(syn_db_path).expanduser()
    syn_path.parent.mkdir(parents=True, exist_ok=True)
    syn_conn = sqlite3.connect(str(syn_path))
    syn_conn.execute("PRAGMA foreign_keys = ON")
    syn_conn.executescript(SYNAPSE_STORE_SCHEMA)
    _migrate_v32(syn_conn)
    cur_syn = syn_conn.cursor()

    # ── 2. Open custom lexicon (optional) ──────────────────────────
    cur_custom = None
    custom_conn = None
    if custom_db_path:
        c_path = Path(custom_db_path).expanduser()
        c_path.parent.mkdir(parents=True, exist_ok=True)
        custom_conn = sqlite3.connect(str(c_path))
        custom_conn.executescript(CUSTOM_LEXICON_SCHEMA)
        cur_custom = custom_conn.cursor()

    # ── 3. Open ghost registry (optional) ──────────────────────────
    cur_ghost = None
    ghost_conn = None
    if ghost_db_path:
        g_path = Path(ghost_db_path).expanduser()
        g_path.parent.mkdir(parents=True, exist_ok=True)
        ghost_conn = sqlite3.connect(str(g_path))
        ghost_conn.executescript(GHOST_REGISTRY_SCHEMA)
        cur_ghost = ghost_conn.cursor()

    # ═════════════════════════════════════════════════════════════════
    # STEP A: Write document record
    # ═════════════════════════════════════════════════════════════════
    cur_syn.execute("""
        INSERT OR REPLACE INTO document
            (doc_id, source_path, char_length, ingested_at)
        VALUES (?, ?, ?, ?)
    """, (doc_id, source_path or "", len(source_text), int(time.time())))

    # ═════════════════════════════════════════════════════════════════
    # STEP B: Write entities
    # ═════════════════════════════════════════════════════════════════
    for ent in entity_map.get("entities", []):
        nexus_ns = ent.get("nexus_namespace", "synapedia")
        cid = ent.get("lexicon_canonical_id") or ""

        # Write to GLEAN entity table
        cur_syn.execute("""
            INSERT OR REPLACE INTO entity
                (doc_id, ent_id, preferred_canonical, type_hint, pos,
                 aliases_json, anonymous, chain_json,
                 lexicon_canonical_id, lookup_decision_level,
                 lookup_confidence, minted,
                 specificity, maturity_tier,
                 rewritten_to_standard, matched_canonical_id,
                 nexus_namespace, custom_lexicon_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ent.get("specificity") or "general",
            ent.get("maturity_tier"),
            1 if ent.get("rewritten_to_standard") else 0,
            ent.get("matched_canonical_id"),
            nexus_ns,
            ent.get("custom_lexicon_id"),
        ))

        # Write minted entities to custom lexicon
        if ent.get("minted") and cur_custom is not None and cid:
            is_inst = 1 if ent.get("pos") == "name" else 0
            cur_custom.execute("""
                INSERT OR IGNORE INTO entry
                    (canonical_id, lemma, pos_ud, gloss, source_type,
                     definition_tier, is_instance, corpus)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cid,
                ent["preferred_canonical"],
                "PROPN" if is_inst else "NOUN",
                ent.get("context_text", "") or "",
                "custom",
                "INFERRED" if not _is_metonymic_entity(ent) else "PROVISIONAL",
                is_inst,
                doc_id.rsplit("_", 1)[0] if "_" in doc_id else doc_id,
            ))
            counts["minted_entities"] += 1

        # Write metonymic entities as ghosts
        if _is_metonymic_entity(ent) and cur_ghost is not None:
            ghost_id = f"ghost.{hashlib.sha256(f'{cid}:{doc_id}'.encode()).hexdigest()[:12]}"
            cur_ghost.execute("""
                INSERT OR IGNORE INTO ghost
                    (ghost_id, surface_form, context, doc_id, clause_id,
                     detected_pattern, source_canonical_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                ghost_id,
                ent["preferred_canonical"],
                ent.get("context_text", ""),
                doc_id,
                0,
                ent.get("metonymic_pattern", ""),
                ent.get("lexicon_canonical_id", ""),
            ))
            counts["ghosts"] += 1

    syn_conn.commit()
    if cur_custom is not None:
        custom_conn.commit()
    if cur_ghost is not None:
        ghost_conn.commit()

    # ═════════════════════════════════════════════════════════════════
    # STEP C: Write synapses + spokes + frames
    # ═════════════════════════════════════════════════════════════════
    for clause_idx, syn in enumerate(synapses_framed):
        verb_lemma = syn.get("predicate_lemma") or syn.get("predicate_surface", "")
        pred_surface = syn.get("predicate_surface", "")

        # Generate synapse_id deterministically if not present
        synapse_id = syn.get("synapse_id") or _deterministic_synapse_id(
            verb_lemma, doc_id, clause_idx
        )

        # Frame data as JSON
        frame = syn.get("frame", {})
        frame_json = json.dumps(frame) if frame else None

        # Bundle source_span
        source_span_json = json.dumps({
            "start": syn.get("source_span_start"),
            "end": syn.get("source_span_end"),
            "sentence": syn.get("source_sentence_id"),
            "clause": syn.get("source_clause_id"),
            "doc_id": doc_id,
        }) if syn.get("source_span_start") is not None else None

        # Determine epistemic_status from frame
        ep_status = "SOURCED"
        if frame:
            st = frame.get("statement_type", "")
            if st == "counterfactual":
                ep_status = "INFERRED"
            elif st == "reported_claim":
                ep_status = "SOURCED"
            elif st == "speculative":
                ep_status = "PROVISIONAL"

        cur_syn.execute("""
            INSERT INTO synapedia_synapse
                (synapse_id, verb_lemma, verb_canonical_id, plane,
                 epistemic_status, derivation_tag, pov, trust_level,
                 source_span, frame_json, doc_id, source_clause_id,
                 source_sentence_id, source_span_start, source_span_end,
                 polarity, statement_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            synapse_id,
            verb_lemma,
            syn.get("predicate_canonical_id"),
            "claim",
            ep_status,
            "EXPRESSED",
            frame.get("point_of_view") if frame else None,
            "provisional",
            source_span_json,
            frame_json,
            doc_id,
            syn.get("source_clause_id"),
            syn.get("source_sentence_id"),
            syn.get("source_span_start"),
            syn.get("source_span_end"),
            syn.get("polarity", "positive"),
            syn.get("statement_type", "factual"),
            int(time.time()),
        ))
        counts["synapses"] += 1

        # Write spokes
        for i, spoke in enumerate(syn.get("spokes", [])):
            role = spoke["role"]
            if role not in ROLES:
                raise ValueError(
                    f"synapse {synapse_id} uses role {role!r}, "
                    f"which is not in the closed inventory. "
                    f"Valid roles: {ROLES}"
                )

            target_cid = spoke.get("target_canonical_id")
            target_ent_id = spoke.get("target_ent_id")
            target_surface = spoke.get("target_surface", "")

            # Determine target_type
            if target_cid and target_cid.startswith("lit."):
                target_type = "TYPED_LITERAL"
            elif target_cid and target_cid.startswith("en."):
                target_type = "LEXICON_ENTRY"
            elif target_cid and (target_cid.startswith("doc.") or
                                 target_cid.startswith("dyn.") or
                                 target_cid.startswith("corp.")):
                target_type = "INSTANCE"
            elif target_ent_id:
                target_type = "DOCUMENT_ENTITY"
            else:
                target_type = "GHOST"

            # literal_value for dates/numbers
            lit_value = None
            if target_type == "TYPED_LITERAL":
                lit_value = target_cid.split(".", 2)[-1] if target_cid else target_surface

            cur_syn.execute("""
                INSERT INTO synapedia_spoke
                    (synapse_id, spoke_index, role, target_id, target_type,
                     target_lemma, literal_value, source_span, pov,
                     target_ent_id, target_canonical_id, target_surface)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                synapse_id, i, role,
                target_cid or target_ent_id,
                target_type,
                target_surface,
                lit_value,
                None,  # source_span per spoke (optional)
                None,  # pov per spoke (optional)
                target_ent_id,
                target_cid,
                target_surface,
            ))
            counts["spokes"] += 1

    syn_conn.commit()

    # ═════════════════════════════════════════════════════════════════
    # STEP D: Write groups + group members + links
    # ═════════════════════════════════════════════════════════════════
    for g in groups:
        group_id = g["group_id"]
        group_label = g.get("group_label", g.get("cohesion_value", ""))
        group_type = g.get("group_type", "STAR")
        parent_group_id = g.get("parent_group_id")

        cur_syn.execute("""
            INSERT OR REPLACE INTO synapedia_group
                (group_id, parent_group_id, group_label, group_type)
            VALUES (?, ?, ?, ?)
        """, (group_id, parent_group_id, group_label, group_type))
        counts["groups"] += 1

        for idx, synapse_id in enumerate(g.get("synapse_ids", [])):
            cur_syn.execute("""
                INSERT OR IGNORE INTO synapedia_group_member
                    (group_id, member_id, member_type, position_index)
                VALUES (?, ?, 'synapse', ?)
            """, (group_id, synapse_id, idx + 1))
            counts["members"] += 1

    # Write links (PRECEDES between consecutive synapses in same sentence)
    links = _compute_precedes_links(synapses_framed, doc_id)
    for link in links:
        try:
            cur_syn.execute("""
                INSERT OR IGNORE INTO synapedia_link
                    (source_id, source_type, link_type, target_id,
                     target_type, confidence)
                VALUES (?, 'synapse', ?, ?, 'synapse', ?)
            """, (link["source"], link["link_type"], link["target"],
                  link.get("confidence", 1.0)))
            counts["links"] += 1
        except sqlite3.IntegrityError:
            pass

    syn_conn.commit()

    # ═════════════════════════════════════════════════════════════════
    # Clean up
    # ═════════════════════════════════════════════════════════════════
    syn_conn.close()
    if custom_conn is not None:
        custom_conn.close()
    if ghost_conn is not None:
        ghost_conn.close()

    return counts


# =============================================================================
# Internal: compute PRECEDES links
# =============================================================================

def _compute_precedes_links(
    synapses: List[dict], doc_id: str
) -> List[dict]:
    """Generate PRECEDES links between consecutive synapses in the same sentence."""
    sent_groups: Dict[int, List[tuple]] = {}
    for syn in synapses:
        sent_id = syn.get("source_sentence_id", 0)
        clause_id = syn.get("source_clause_id", 0)
        syn_id = syn.get("synapse_id")
        if not syn_id:
            continue
        sent_groups.setdefault(sent_id, []).append((clause_id, syn_id))

    links = []
    for sent_id, clauses in sent_groups.items():
        clauses.sort(key=lambda x: x[0])
        for i in range(len(clauses) - 1):
            links.append({
                "source": clauses[i][1],
                "link_type": "PRECEDES",
                "target": clauses[i + 1][1],
                "confidence": 1.0,
            })
    return links


# =============================================================================
# CLI entry point (for testing)
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Persist GLEAN output to Synapedia v3.0 schema."
    )
    parser.add_argument("--syn-db", required=True)
    parser.add_argument("--custom-db", default=None)
    parser.add_argument("--ghost-db", default=None)
    parser.add_argument("--doc-id", required=True)
    parser.add_argument("--entity-map", required=True)
    parser.add_argument("--synapses", required=True)
    parser.add_argument("--groups", required=True)
    parser.add_argument("--source", default=None)
    parser.add_argument("--accuracy-mode", default="standard")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    with open(args.entity_map, "r") as f:
        entity_map = json.load(f)
    with open(args.synapses, "r") as f:
        synapses = json.load(f)
        if isinstance(synapses, dict) and "synapses" in synapses:
            synapses = synapses["synapses"]
    with open(args.groups, "r") as f:
        groups = json.load(f)

    source_text = ""
    if args.source:
        with open(args.source, "r") as f:
            source_text = f.read()

    counts = persist_all(
        syn_db_path=args.syn_db,
        custom_db_path=args.custom_db,
        ghost_db_path=args.ghost_db,
        doc_id=args.doc_id,
        entity_map=entity_map,
        synapses_framed=synapses,
        groups=groups,
        source_path=args.source,
        source_text=source_text,
        accuracy_mode=args.accuracy_mode,
    )

    print()
    print("Persist complete — row counts:")
    for k, v in counts.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()