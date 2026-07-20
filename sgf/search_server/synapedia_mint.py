#!/usr/bin/env python3
"""
synapedia_mint.py — Shared module for minting new Synapedia entries.

Both mint_compound.py and improve_glossary_and_ontology.py import and use
this module to create new entries.  This ensures consistent column defaults,
canonical ID generation, provenance tracking, and embed service integration.

Lifecycle:
  Stage 1 (Mint):  Create a minimal stub with lemma, gloss, microgloss,
                    canonical ID, IS-A links, and embedding.
                    No HAS_PART, HAS_ATTRIBUTE, or events yet.
  Stage 2 (Improve): Enrich the stub on the next --all pass (full gloss,
                      ontology, events, better embedding).
  Stage 3 (Promote):  Promote to higher definition_tier after frequency check.

Usage:
    from synapedia_mint import mint_entry, entry_exists, build_canonical_id

    eid = mint_entry(
        db_path="synapedia.db",
        lemma="torque_screwdriver",
        gloss="a screwdriver that applies controlled torque to fasteners",
        is_a_parents=[{"lemma": "screwdriver", "gloss": "a tool for driving screws"}],
        embed_service_url="http://localhost:18401"
    )
"""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("synapedia_mint")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_DEFINITION_TIER = "INFERRED"
DEFAULT_SOURCE_TYPE = "llm_compound"
DEFAULT_NAMESPACE = "inferred"
DEFAULT_EMBED_SERVICE_URL = "http://localhost:18401"
MAX_MINT_PER_BATCH = 10  # safety valve

STOPWORDS = frozenset({
    "a", "an", "the", "of", "for", "in", "to", "and", "or", "is", "are",
    "by", "at", "with", "from", "that", "this", "it", "be", "was", "were",
    "has", "have", "had", "not", "no", "but", "on", "as", "into", "through",
    "during", "before", "after", "above", "below", "between", "out", "off",
    "over", "under", "again", "further", "then", "once", "here", "there",
    "when", "where", "why", "how", "all", "each", "every", "both", "few",
    "more", "most", "other", "some", "such", "only", "own", "same", "so",
    "than", "too", "very", "just", "because", "also", "if", "then", "else",
})

GENERIC = frozenset({
    "thing", "entity", "object", "item", "element", "component", "part",
    "piece", "unit", "member", "subset", "type", "kind", "sort", "category",
    "class", "group", "set", "collection", "system", "structure", "process",
    "action", "event", "state", "condition", "quality", "property", "attribute",
    "value", "concept", "idea", "notion", "term", "word", "name", "use",
    "thingy", "doohickey", "whatchamacallit", "gadget", "widget", "tool",
    "device", "implement", "instrument", "apparatus", "machine", "mechanism",
    "person", "people", "someone", "somebody", "place", "location", "time",
    "way", "method", "means", "function", "purpose", "result", "effect",
    "someone", "something", "somewhere", "sometime",
})

# POS mapping
POS_UD_TO_ORIGINAL = {
    "NOUN": "noun",
    "VERB": "verb",
    "ADJ": "adjective",
    "ADV": "adverb",
    "PROPN": "proper_noun",
    "PRON": "pronoun",
    "ADP": "adposition",
    "AUX": "auxiliary",
    "CCONJ": "conjunction",
    "SCONJ": "conjunction",
    "DET": "determiner",
    "INTJ": "interjection",
    "NUM": "numeral",
    "PART": "particle",
    "PUNCT": "punctuation",
    "SYM": "symbol",
    "X": "unknown",
}

# Valid thematic roles (SGF Core 1.0)
VALID_ROLES = frozenset({
    "HAS_AGENT", "HAS_PATIENT", "HAS_THEME", "HAS_EXPERIENCER",
    "HAS_RECIPIENT", "HAS_BENEFICIARY", "HAS_TIME", "HAS_LOCATION",
    "HAS_SOURCE", "HAS_DESTINATION", "HAS_MANNER", "HAS_INSTRUMENT",
    "HAS_CAUSE", "HAS_REASON", "HAS_ATTRIBUTE",
})

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _get_connection(db_path: str) -> sqlite3.Connection:
    """Get a WAL-mode connection with a busy timeout."""
    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _sanitize_id(segment: str) -> str:
    """Lower-case, replace non-alphanumerics with underscore, reduce runs."""
    segment = segment.lower().strip()
    segment = re.sub(r"[^a-z0-9_]", "_", segment)
    segment = re.sub(r"_+", "_", segment)
    segment = segment.strip("_")
    return segment or "unknown"


def _is_morphological_form(token: str, lemma: str) -> bool:
    """Check if token is a morphological variant of the lemma."""
    token_lower = token.lower().strip()
    lemma_lower = lemma.lower().strip()
    if token_lower == lemma_lower:
        return True
    # Common inflectional suffixes
    for suffix in ("s", "es", "ed", "ing", "er", "ers", "est", "ly"):
        if token_lower == lemma_lower + suffix:
            return True
        # Handle e-dropping: drive -> driving, make -> making
        if lemma_lower.endswith("e") and token_lower == lemma_lower[:-1] + suffix:
            return True
        # Handle y -> i: happy -> happier
        if lemma_lower.endswith("y") and token_lower == lemma_lower[:-1] + "i" + suffix:
            return True
    # Irregular forms (common ones)
    irregulars = {
        "ran": "run", "run": "run", "running": "run",
        "ate": "eat", "eaten": "eat", "eating": "eat",
        "went": "go", "gone": "go", "going": "go",
        "did": "do", "done": "do", "doing": "do",
        "saw": "see", "seen": "see", "seeing": "see",
        "said": "say", "saying": "say",
        "made": "make", "making": "make",
        "took": "take", "taken": "take", "taking": "take",
        "came": "come", "coming": "come",
        "gave": "give", "given": "give", "giving": "give",
        "mice": "mouse",
        "feet": "foot",
        "teeth": "tooth",
        "children": "child",
        "men": "man",
        "women": "woman",
    }
    if token_lower in irregulars:
        return irregulars[token_lower] == lemma_lower
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def entry_exists(db_path: str, lemma: str) -> bool:
    """
    Check if any entry with the given lemma exists (case-insensitive).

    Args:
        db_path: Path to synapedia.db
        lemma: The lemma to check

    Returns:
        True if at least one entry with this lemma exists
    """
    conn = _get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM synapedia_entry WHERE LOWER(lemma) = ? LIMIT 1",
        (lemma.strip().lower(),),
    )
    row = cur.fetchone()
    conn.close()
    return row is not None


def derive_microgloss(gloss: str, lemma: str, max_tokens: int = 4) -> str:
    """
    Extract 2-4 key tokens from gloss to form a microgloss.

    Filters stopwords, short words, generic terms, and morphological forms
    of the lemma. Falls back to the lemma slug if no tokens remain.

    Args:
        gloss: The gloss text to derive from
        lemma: The lemma (will be filtered out)
        max_tokens: Maximum number of tokens to include (default 4)

    Returns:
        Underscore-separated microgloss (e.g., "hand_powered_tool")
    """
    if not gloss:
        return _sanitize_id(lemma)

    # Lowercase, tokenize on non-alphanumeric
    text = gloss.lower()
    text = re.sub(r"[^a-z0-9' ]", " ", text)
    tokens = [t.strip("'") for t in text.split() if t.strip("'")]

    # Filter
    filtered = []
    for token in tokens:
        if len(token) <= 2:
            continue
        if token in STOPWORDS:
            continue
        if token in GENERIC:
            continue
        if _is_morphological_form(token, lemma):
            continue
        filtered.append(token)

    if not filtered:
        return _sanitize_id(lemma)

    return "_".join(filtered[:max_tokens])


def build_canonical_id(
    lemma: str,
    microgloss: str,
    pos_ud: str,
    namespace: str = DEFAULT_NAMESPACE,
) -> str:
    """
    Generate en.{lemma}.{microgloss}.{pos}.{namespace}

    Args:
        lemma: The surface form
        microgloss: Compressed definition (2-4 tokens)
        pos_ud: Universal Dependencies POS tag (e.g., "NOUN")
        namespace: Namespace suffix (default "inferred")

    Returns:
        Canonical ID string
    """
    lemma_clean = _sanitize_id(lemma)
    mg_clean = _sanitize_id(microgloss) if microgloss else lemma_clean
    pos_clean = _sanitize_id(pos_ud) if pos_ud else "unknown"
    ns_clean = _sanitize_id(namespace)
    return f"en.{lemma_clean}.{mg_clean}.{pos_clean}.{ns_clean}"







def _compute_embedding(entry_id: int, embed_service_url: str) -> bool:
    """
    Call the embed service to recompute the embedding for a single entry.

    This is called after the entry is committed.  Failures are logged but
    not raised — the entry exists without an embedding and will be picked
    up by the next batch embedding run.
    """
    try:
        import requests
        resp = requests.post(
            f"{embed_service_url}/recompute",
            json={"entry_ids": [entry_id]},
            timeout=60,
        )
        if resp.status_code == 200:
            logger.info("Embedding computed for entry %d", entry_id)
            return True
        else:
            logger.warning(
                "Embed service returned %d for entry %d: %s",
                resp.status_code, entry_id, resp.text,
            )
            return False
    except Exception as e:
        logger.error("Failed to call embed service for entry %d: %s", entry_id, e)
        return False

def mint_entry(
    db_path: str,
    lemma: str,
    gloss: str,
    pos_ud: str = "NOUN",
    microgloss: Optional[str] = None,
    canonical_id: Optional[str] = None,
    bow: str = "",
    embedding_text: Optional[str] = None,
    is_a_parents: Optional[List[Dict[str, str]]] = None,
    has_parts: Optional[List[Dict[str, str]]] = None,
    has_attributes: Optional[List[Dict[str, str]]] = None,
    is_instance_of: Optional[List[Dict[str, str]]] = None,
    events: Optional[List[Dict[str, Any]]] = None,
    is_instance: bool = False,
    source_entry_id: Optional[int] = None,
    embed_service_url: Optional[str] = None,
    trust_level: str = "provisional",
    source_type: str = DEFAULT_SOURCE_TYPE,
    definition_tier: str = DEFAULT_DEFINITION_TIER,
    max_mint_per_batch: int = MAX_MINT_PER_BATCH,
    dry_run: bool = False,
    cur: Optional[sqlite3.Cursor] = None,
) -> int:
    """
    ... (docstring unchanged) ...
    """
    if not lemma or not lemma.strip():
        raise ValueError("lemma must be non-empty")
    if not gloss or not gloss.strip():
        raise ValueError("gloss must be non-empty")

    lemma = lemma.strip()
    gloss = gloss.strip()

    # Duplicate detection
    if entry_exists(db_path, lemma):
        logger.info("Entry '%s' already exists; skipping mint.", lemma)
        return 0

    # Derive microgloss if not provided
    if not microgloss:
        microgloss = derive_microgloss(gloss, lemma)

    # Build canonical ID if not provided
    if not canonical_id:
        canonical_id = build_canonical_id(lemma, microgloss, pos_ud)

    # Build embedding_text if not provided
    if not embedding_text:
        embedding_text = f"{lemma}. {pos_ud}. {gloss}"
        if bow:
            embedding_text += f" Related terms: {bow}"

    # Determine POS original
    pos_original = POS_UD_TO_ORIGINAL.get(pos_ud.upper(), "unknown")

    if dry_run:
        logger.info(
            "DRY RUN: Would mint entry: lemma=%s, canonical_id=%s, gloss=%s, "
            "microgloss=%s, is_instance=%d, parents=%d",
            lemma, canonical_id, gloss, microgloss, is_instance,
            len(is_a_parents or []) + len(is_instance_of or []),
        )
        return 0

    # ------------------------------------------------------------------
    # Database writes — use existing cursor if provided, else open new connection
    # ------------------------------------------------------------------
    if cur is not None:
        # Use caller's cursor — caller manages commit/close
        own_conn = False
        _cur = cur
    else:
        conn = _get_connection(db_path)
        _cur = conn.cursor()
        own_conn = True

    try:
        # 1. Insert the entry
        _cur.execute(
            """
            INSERT INTO synapedia_entry
                (lemma, pos_original, pos_ud, gloss, microgloss, canonical_id,
                 source_type, definition_tier, language,
                 is_prime, is_molecule, is_instance,
                 embedding_text, embedding_text_version, embedding_text_needs_rebuild,
                 bow, improved_at, microgloss_source, is_microgloss_provisional)
            VALUES (?, ?, ?, ?, ?, ?,
                    ?, ?, ?,
                    0, 0, ?,
                    ?, 'v3-minted', 1,
                    ?, NULL, 'llm', 1)
            """,
            (
                lemma, pos_original, pos_ud, gloss, microgloss, canonical_id,
                source_type, definition_tier, "en",
                is_instance,
                embedding_text,
                bow,
            ),
        )
        entry_id = _cur.lastrowid

        # 2. Insert IS-A links (for types) or HAS_INSTANCE links (for instances)
        if is_instance and is_instance_of:
            relation_table = "synapedia_has_instance"
            lemma_col = "instance_lemma"
            gloss_col = "instance_gloss"
            canonical_col = "instance_canonical_id"
            parents = is_instance_of
        elif not is_instance and is_a_parents:
            relation_table = "synapedia_is_a"
            lemma_col = "parent_lemma"
            gloss_col = "parent_gloss"
            canonical_col = "parent_canonical_id"
            parents = is_a_parents
        else:
            parents = []

        for parent in parents:
            parent_lemma = parent.get("lemma", "").strip()
            parent_gloss = parent.get("gloss", "")
            if not parent_lemma:
                continue
            parent_cid = None
            try:
                import requests as _requests
                resp = _requests.post(
                    "http://localhost:8400/lookup/lemma",
                    json={"lemma": parent_lemma, "pos": "noun"},
                    timeout=5,
                )
                if resp.status_code == 200:
                    results = resp.json().get("results", [])
                    if results:
                        parent_cid = results[0].get("canonical_id")
            except Exception:
                pass

            _cur.execute(
                f"""
                INSERT OR IGNORE INTO {relation_table}
                    (synapedia_entry_id, {lemma_col}, {gloss_col}, {canonical_col},
                     relation_source, trust_level)
                VALUES (?, ?, ?, ?, 'llm_compound', ?)
                """,
                (entry_id, parent_lemma, parent_gloss, parent_cid, trust_level),
            )

        # 3. Insert HAS_PART links
        if has_parts:
            for part in has_parts:
                part_lemma = part.get("lemma", "").strip()
                part_gloss = part.get("gloss", "")
                if not part_lemma:
                    continue
                _cur.execute(
                    """
                    INSERT OR IGNORE INTO synapedia_has_part
                        (synapedia_entry_id, part_lemma, part_gloss, part_canonical_id,
                         relation_source, trust_level)
                    VALUES (?, ?, ?, NULL, 'llm_compound', ?)
                    """,
                    (entry_id, part_lemma, part_gloss, trust_level),
                )

        # 4. Insert HAS_ATTRIBUTE links
        if has_attributes:
            for attr in has_attributes:
                if isinstance(attr, str):
                    if "=" in attr:
                        key, value = attr.split("=", 1)
                        key = key.strip()
                        value = value.strip()
                    else:
                        key = attr.strip()
                        value = ""
                elif isinstance(attr, dict):
                    key = attr.get("key", "").strip()
                    value = attr.get("value", "").strip()
                else:
                    continue
                if not key:
                    continue
                _cur.execute(
                    """
                    INSERT OR IGNORE INTO synapedia_has_attribute
                        (synapedia_entry_id, attribute_key, attribute_value,
                         relation_source, trust_level)
                    VALUES (?, ?, ?, 'llm_compound', ?)
                    """,
                    (entry_id, key, value, trust_level),
                )

        # 5. Insert events (Synapse + Spoke + EntrySynapse)
        if events:
            for event_idx, event in enumerate(events):
                verb = event.get("verb", "").strip()
                roles = event.get("roles", {})
                if not verb or not roles:
                    continue

                raw = f"synapedia:{entry_id}:{verb}:{event_idx}"
                h = hashlib.sha256(raw.encode()).hexdigest()[:12]
                synapse_id = f"synapedia.syn.{h}"

                epistemic_status = event.get("epistemic_status", "CONSTITUTIVE")

                verb_cid = None
                try:
                    import requests as _requests
                    resp = _requests.post(
                        "http://localhost:8400/lookup/lemma",
                        json={"lemma": verb, "pos": "verb"},
                        timeout=5,
                    )
                    if resp.status_code == 200:
                        results = resp.json().get("results", [])
                        if results:
                            verb_cid = results[0].get("canonical_id")
                except Exception:
                    pass

                try:
                    _cur.execute(
                        """
                        INSERT INTO synapedia_synapse
                            (synapse_id, verb_lemma, verb_canonical_id, plane,
                             epistemic_status, trust_level)
                        VALUES (?, ?, ?, 'ontological', ?, ?)
                        """,
                        (synapse_id, verb, verb_cid, epistemic_status, trust_level),
                    )
                except sqlite3.IntegrityError:
                    continue

                for role, participant in roles.items():
                    role_upper = role.upper()
                    if role_upper not in VALID_ROLES:
                        continue
                    participants = [p.strip() for p in participant.split(",") if p.strip()]
                    for p_lemma in participants:
                        target_cid = None
                        target_type = "concept"
                        literal_value = None
                        if re.match(r"^\d{4}-\d{2}-\d{2}$", p_lemma) or \
                           re.match(r"^\d{4}$", p_lemma) or \
                           re.match(r"^[\d.]+$", p_lemma):
                            target_type = "literal"
                            literal_value = p_lemma
                        else:
                            try:
                                import requests as _requests
                                resp = _requests.post(
                                    "http://localhost:8400/lookup/lemma",
                                    json={"lemma": p_lemma, "pos": "noun"},
                                    timeout=5,
                                )
                                if resp.status_code == 200:
                                    results = resp.json().get("results", [])
                                    if results:
                                        target_cid = results[0].get("canonical_id")
                            except Exception:
                                pass

                        try:
                            _cur.execute(
                                """
                                INSERT INTO synapedia_spoke
                                    (synapse_id, role, target_id, target_type, target_lemma, literal_value)
                                VALUES (?, ?, ?, ?, ?, ?)
                                """,
                                (synapse_id, role_upper, target_cid, target_type, p_lemma, literal_value),
                            )
                        except sqlite3.IntegrityError:
                            pass

                try:
                    _cur.execute(
                        """
                        INSERT INTO synapedia_entry_synapse
                            (entry_id, synapse_id, relation)
                        VALUES (?, ?, 'has_event')
                        """,
                        (entry_id, synapse_id),
                    )
                except sqlite3.IntegrityError:
                    pass

        # 6. Provenance: source_xref
        try:
            _cur.execute(
                """
                INSERT INTO synapedia_source_xref
                    (synapedia_id, source_db, source_id)
                VALUES (?, ?, ?)
                """,
                (entry_id, source_type, entry_id),
            )
        except Exception:
            pass

        # 7. Provenance chain: mergesource (if source_entry_id provided)
        if source_entry_id:
            try:
                _cur.execute(
                    """
                    INSERT INTO synapedia_mergesource
                        (synapedia_entry_id, source_db, source_id, priority)
                    VALUES (?, 'llm_compound', ?, 0)
                    """,
                    (entry_id, source_entry_id),
                )
            except Exception:
                pass

        # Only commit if we own the connection
        if own_conn:
            conn.commit()
            logger.info(
                "Minted entry_id=%d, lemma='%s', canonical_id='%s', "
                "parents=%d, parts=%d, attributes=%d, events=%d",
                entry_id, lemma, canonical_id,
                len(parents), len(has_parts or []),
                len(has_attributes or []), len(events or []),
            )

    except Exception:
        if own_conn:
            conn.rollback()
        raise
    finally:
        if own_conn:
            conn.close()

    # ------------------------------------------------------------------
    # Embedding computation — ONLY if we own the connection (committed).
    # If called with `cur`, defer to caller.
    # ------------------------------------------------------------------
    if own_conn and embed_service_url:
        _compute_embedding(entry_id, embed_service_url)

    return entry_id

# ===================================================================
# SYNAPSE GROUP CREATION
# ===================================================================

def insert_event_group(
    db_path: str,
    entry_id: int,
    group_label: str,
    event_keys: List[str],
    fields: Dict[str, Any],
    group_type: str = "STAR",
    cur: Optional[sqlite3.Cursor] = None,  # NEW: optional cursor
) -> Optional[str]:
    """
    Create a SynapseGroup containing the given events as members.

    Looks up synapse IDs from fields using keys like "synapse_event_1".

    Args:
        db_path: Path to synapedia.db
        entry_id: The entry these events belong to
        group_label: Human-readable label (e.g., "Career of Bach")
        event_keys: List of field keys (e.g., ["event_1", "event_2"])
        fields: The parsed fields dict containing synapse_* entries
        group_type: "STAR" (hub-and-spoke) or "CHAIN" (sequential)
        cur: Optional cursor to use instead of opening a new connection

    Returns:
        group_id string, or None on failure
    """
    # Build a deterministic group_id from the label
    group_id = f"synapedia.group.{hashlib.sha256(group_label.encode()).hexdigest()[:12]}"

    if cur is not None:
        own_conn = False
        _cur = cur
    else:
        conn = _get_connection(db_path)
        _cur = conn.cursor()
        own_conn = True

    try:
        _cur.execute("""
            INSERT OR IGNORE INTO synapedia_group
                (group_id, parent_group_id, group_label, group_type)
            VALUES (?, NULL, ?, ?)
        """, (group_id, group_label, group_type))

        inserted_count = 0
        for idx, event_key in enumerate(event_keys):
            synapse_key = f"synapse_{event_key}"
            synapse_id = fields.get(synapse_key)
            if not synapse_id:
                continue
            try:
                _cur.execute("""
                    INSERT OR IGNORE INTO synapedia_group_member
                        (group_id, member_id, member_type, position_index)
                    VALUES (?, ?, 'synapse', ?)
                """, (group_id, synapse_id, idx + 1))
                inserted_count += 1
            except sqlite3.IntegrityError:
                pass

        if own_conn:
            conn.commit()  # type: ignore[name-defined]
            logger.info(
                "Created event group '%s' (type=%s) with %d members for entry %d",
                group_label, group_type, inserted_count, entry_id,
            )
        return group_id
    except Exception as e:
        if own_conn:
            conn.rollback()  # type: ignore[name-defined]
        logger.error("Failed to create event group '%s': %s", group_label, e)
        return None
    finally:
        if own_conn:
            conn.close()  # type: ignore[name-defined]


# ===================================================================
# EVENT LINK INSERTION
# ===================================================================

def insert_event_links(
    db_path: str,
    links: List[Dict[str, str]],
    fields: Dict[str, Any],
    cur: Optional[sqlite3.Cursor] = None,  # NEW: optional cursor
) -> None:
    """
    Insert links between events.

    Each link dict must have:
      'source': event key (e.g., "event_1")
      'link_type': one of PRECEDES, CAUSES, ENABLES, SUPPORTS, CONTRADICTS,
                   ELABORATES, SUPERSEDES, DEPENDS_ON
      'target': event key (e.g., "event_2")

    Looks up synapse IDs from fields using keys like "synapse_event_1".

    Args:
        db_path: Path to synapedia.db
        links: List of link dicts from the parsed LLM response
        fields: The parsed fields dict containing synapse_* entries
        cur: Optional cursor to use instead of opening a new connection
    """
    if cur is not None:
        own_conn = False
        _cur = cur
    else:
        conn = _get_connection(db_path)
        _cur = conn.cursor()
        own_conn = True

    inserted = 0
    skipped = 0
    try:
        for link in links:
            source_event = link.get("source", "").strip()
            link_type = link.get("link_type", "").strip()
            target_event = link.get("target", "").strip()

            if not source_event or not link_type or not target_event:
                skipped += 1
                continue

            source_synapse = fields.get(f"synapse_{source_event}")
            target_synapse = fields.get(f"synapse_{target_event}")

            if not source_synapse or not target_synapse:
                logger.warning(
                    "Missing synapse IDs for link: %s --[%s]--> %s",
                    source_event, link_type, target_event,
                )
                skipped += 1
                continue

            try:
                _cur.execute("""
                    INSERT OR IGNORE INTO synapedia_link
                        (source_id, source_type, link_type, target_id, target_type, confidence)
                    VALUES (?, 'synapse', ?, ?, 'synapse', 1.0)
                """, (source_synapse, link_type, target_synapse))
                inserted += 1
            except sqlite3.IntegrityError:
                skipped += 1

        if own_conn:
            conn.commit()  # type: ignore[name-defined]
            if inserted:
                logger.info("Inserted %d event links (skipped %d)", inserted, skipped)
    except Exception as e:
        if own_conn:
            conn.rollback()  # type: ignore[name-defined]
        logger.error("Failed to insert event links: %s", e)
    finally:
        if own_conn:
            conn.close()  # type: ignore[name-defined]


# ---------------------------------------------------------------------------
# Batch minting helper
# ---------------------------------------------------------------------------

def mint_missing_parents(
    db_path: str,
    child_entry_id: int,
    parent_info: List[Dict[str, str]],
    is_instance: bool = False,
    embed_service_url: Optional[str] = None,
    max_mint: int = MAX_MINT_PER_BATCH,
    cur: Optional[sqlite3.Cursor] = None,  # NEW: optional cursor
) -> List[int]:
    """
    Mint entries for missing parent concepts.

    Called by improve_glossary_and_ontology.py after the LLM returns
    is_a_parents or is_instance_of with glosses.  For each parent that
    doesn't exist in the DB, creates a minimal stub.

    When called from within an existing transaction, pass `cur` to reuse
    the same connection and avoid "database is locked" errors.

    Args:
        db_path: Path to synapedia.db
        child_entry_id: The entry that references these parents
        parent_info: List of dicts with 'lemma' and 'gloss' keys
        is_instance: True if these are IS_INSTANCE_OF links (proper nouns)
        embed_service_url: URL of embed service
        max_mint: Maximum number of parents to mint per call
        cur: Optional cursor to use instead of opening a new connection

    Returns:
        List of newly minted entry IDs
    """
    minted_ids = []
    mint_count = 0

    for parent in parent_info:
        if mint_count >= max_mint:
            logger.warning(
                "Reached max_mint_per_batch (%d) for child entry %d; "
                "remaining parents will be minted on next pass",
                max_mint, child_entry_id,
            )
            break

        parent_lemma = parent.get("lemma", "").strip()
        parent_gloss = parent.get("gloss", "")
        if not parent_lemma:
            continue

        if entry_exists(db_path, parent_lemma):
            continue

        # Determine if parent is an instance (capitalized = proper noun heuristic)
        parent_is_instance = parent_lemma[0].isupper() if parent_lemma else False

        try:
            new_id = mint_entry(
                db_path=db_path,
                lemma=parent_lemma,
                gloss=parent_gloss or f"A {parent_lemma} (inferred parent concept).",
                pos_ud="NOUN",
                is_instance=parent_is_instance,
                source_entry_id=child_entry_id,
                embed_service_url=embed_service_url,
                trust_level="provisional",
                cur=cur,  # NEW: pass cursor through
            )
            if new_id:
                minted_ids.append(new_id)
                mint_count += 1
        except Exception as e:
            logger.error(
                "Failed to mint parent '%s' for child entry %d: %s",
                parent_lemma, child_entry_id, e,
            )

    return minted_ids


# ---------------------------------------------------------------------------
# CLI entry point (for testing)
# ---------------------------------------------------------------------------

def main():
    """CLI entry point for testing the module directly."""
    import argparse

    parser = argparse.ArgumentParser(description="Mint a new Synapedia entry")
    parser.add_argument("--db", required=True, help="Path to synapedia.db")
    parser.add_argument("--lemma", required=True, help="Lemma of the new entry")
    parser.add_argument("--gloss", required=True, help="Gloss/definition")
    parser.add_argument("--pos", default="NOUN", help="POS tag (default NOUN)")
    parser.add_argument("--microgloss", default=None, help="Microgloss (auto-derived if not set)")
    parser.add_argument("--canonical-id", default=None, help="Canonical ID (auto-built if not set)")
    parser.add_argument("--parent", action="append", nargs=2, metavar=("LEMMA", "GLOSS"),
                        help="IS-A parent (can be specified multiple times)")
    parser.add_argument("--instance", action="store_true", help="Mark as instance (proper noun)")
    parser.add_argument("--embed", default=None, help="Embed service URL")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    parents = None
    if args.parent:
        parents = [{"lemma": p[0], "gloss": p[1]} for p in args.parent]

    eid = mint_entry(
        db_path=args.db,
        lemma=args.lemma,
        gloss=args.gloss,
        pos_ud=args.pos,
        microgloss=args.microgloss,
        canonical_id=args.canonical_id,
        is_a_parents=parents,
        is_instance=args.instance,
        embed_service_url=args.embed,
        dry_run=args.dry_run,
    )

    if eid:
        print(eid)
    else:
        print(0)


if __name__ == "__main__":
    main()