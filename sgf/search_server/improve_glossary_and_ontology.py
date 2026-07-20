#!/usr/bin/env python3
"""
improve_glossary_and_ontology.py — Unified entry enrichment pipeline.

Enriches entries with gloss, microgloss, bow, ontology (IS_A, HAS_PART,
HAS_ATTRIBUTE), events, and instance identity — all in a single LLM call.

Also mints missing parent entries via synapedia_mint to prevent dangling
IS-A references, and creates SynapseGroups and event links for instances.

Usage:
    python improve_glossary_and_ontology.py --db <synapedia.db> --lemmas <lemma1,lemma2>
    python improve_glossary_and_ontology.py --db <synapedia.db> --all [--limit-lemmas N]
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sqlite3
import subprocess
import sys
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Import shared minting module
# ---------------------------------------------------------------------------
from synapedia_mint import mint_missing_parents, insert_event_group, insert_event_links, entry_exists

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TEMP_DIR = Path("./temp")
TEMP_DIR.mkdir(exist_ok=True)

EMBED_SERVICE_URL = "http://localhost:18401"
DEFAULT_LLM_SOURCE = "cloud"

CHARS_PER_TOKEN = 4
MAX_TOKENS_PER_PROMPT = 800_000
MAX_ENTRIES_PER_LLM_CALL = 20
LLM_SUBPROCESS_TIMEOUT = 600

# The 15 closed thematic roles (SGF Core 1.0)
VALID_ROLES = frozenset({
    "HAS_AGENT", "HAS_PATIENT", "HAS_THEME", "HAS_EXPERIENCER",
    "HAS_RECIPIENT", "HAS_BENEFICIARY", "HAS_TIME", "HAS_LOCATION",
    "HAS_SOURCE", "HAS_DESTINATION", "HAS_MANNER", "HAS_INSTRUMENT",
    "HAS_CAUSE", "HAS_REASON", "HAS_ATTRIBUTE",
})

logger = logging.getLogger("improve_glossary")

# ── Prompt ────────────────────────────────────────
PROMPT_TEMPLATE = """You are enriching entries in the Synapedia lexical ontology.

## BIG PICTURE
Synapedia is a structured semantic network used for vector-based search and
structural ontology alignment. Each entry has a lemma, part-of-speech, and a
short gloss. The gloss is embedded into a vector for cosine similarity matching.
The ontology provides structural slots (IS_A, HAS_PART, HAS_ATTRIBUTE) that
enable deterministic alignment (SOAM) between systems. Events (VerbHub + 15
thematic roles) provide the X-axis disambiguation for named entities.

## YOUR TASK
For each entry below, you must produce:
- new_gloss: a 3-5 sentence precision definition
- new_microgloss: 2-4 underscore-separated compressed definition
- bow: 5-15 comma-separated related terms

Depending on the entry type, you must also produce ontology and event fields:

## FOR TYPES (common nouns, no [INSTANCE] marker)
Include:
- is_a_parents: For each parent, provide the lemma AND a short gloss in the
  format "parent_lemma: short gloss". Separate multiple parents with commas.
  Example: "hand_tool: a hand-powered tool for applying torque, tool: an implement"
- has_part: comma-separated list of direct parts (e.g., "handle, blade")
- has_attribute: comma-separated attribute=value pairs (e.g., "material=steel")
- purpose: a single VerbHub phrase describing its function (e.g., "apply torque to fasteners")
- Do NOT include events, event_group, or links for types.

## FOR INSTANCES (proper nouns, marked [INSTANCE])
Only include events if the entity has well-known defining events that
differentiate it from other similar entities (e.g., biographical events,
historical milestones, key works). Do NOT invent events. Do NOT add events
for common nouns (types).

Include:
- is_instance_of: comma-separated categories (e.g., "composer, musician, German")
- has_attribute: comma-separated attribute=value pairs (e.g., "language=German, era=Baroque")

If the entity has defining events, also include:
- event_group: A short label for the collection of events (e.g., "Career of Bach")
  Then list events with this format:
  event_1:
    epistemic_status: CONSTITUTIVE  (or SOURCED, INFERRED)
    verb: compose
    HAS_AGENT: Johann Sebastian Bach
    HAS_PATIENT: Mass in B Minor
    HAS_TIME: 1740s

  (Repeat event_2, event_3 as needed)

  After all events, you may optionally include links between them:
  link_1:
    source: event_1
    link_type: PRECEDES
    target: event_2

## FOR VERBS (entries with POS=VERB)
Include:
- role_contract: required roles, permitted roles, excluded roles
- event_frame: an example event showing the verb in context
- is_a_parents: optional, only if the verb is a subtype of another verb

## EVENT FORMAT (for instances and verbs)
Each event must be a block with:
  verb: the action verb (e.g., "compose")
  epistemic_status: CONSTITUTIVE, SOURCED, or INFERRED (default CONSTITUTIVE)
  ROLE_NAME: participant lemma

Valid roles: HAS_AGENT, HAS_PATIENT, HAS_THEME, HAS_EXPERIENCER, HAS_RECIPIENT,
HAS_BENEFICIARY, HAS_TIME, HAS_LOCATION, HAS_SOURCE, HAS_DESTINATION, HAS_MANNER,
HAS_INSTRUMENT, HAS_CAUSE, HAS_REASON, HAS_ATTRIBUTE

## THE 3-5 SENTENCE PRECISION FRAMEWORK
Each new_gloss must consist of 3-5 sentences:

1. Core Identity & Genus (15-20 words): "The word [Lemma] is a [POS] that denotes [Primary Essential Meaning]."
2. Specific Differentiation (15-25 words): "It specifically characterizes [Applicable Domain/Phenomena] that [Core Behavior/Attribute]."
3. (Optional) Conceptual Neighborhood (10-15 words): "Its conceptual neighbors include [2-3 related concepts]."
4. (Optional) Core Equivalents or Close Relatives (10-15 words): "Core conceptual equivalents or close relatives include [2-4 terms]."
5. (Optional) Domain Context (10-15 words): "The conceptual domain of this term frequently intersects with topics regarding [BOW items]."

Total length: 40-80 words.

## RULES
- Do NOT change the lemma or POS.
- new_gloss must NOT contain the lemma word itself (except in sentence 1).
- new_microgloss must NOT contain the lemma word.
- bow must NOT contain the lemma word.
- Use only ASCII characters.
- All lemmas in ontology fields should be in canonical form (singular, base).
- For instances, use is_instance_of, NOT is_a_parents.
- For verbs, use role_contract and event_frame, NOT is_instance_of.
- Only include events, event_group, and links for instances that genuinely
  have well-known defining events. Do NOT hallucinate events.

## OUTPUT FORMAT
For each entry, output ONE <answer> block:

<answer entry_id="{{entry_id}}">
new_gloss: ...
new_microgloss: ...
bow: ...
is_a_parents: ... (for types, include glosses)
is_instance_of: ... (for instances)
has_part: ... (optional)
has_attribute: ... (optional)
purpose: ... (optional, for types)
event_group: ... (optional, for instances)
event_1: (optional, for instances)
  epistemic_status: CONSTITUTIVE
  verb: ...
  HAS_AGENT: ...
link_1: (optional)
  source: event_1
  link_type: PRECEDES
  target: event_2
</answer>

## EXAMPLES

TYPE (screwdriver):
<answer entry_id="9999">
new_gloss: The word "screwdriver" is a noun that denotes a hand tool used for driving screws.
new_microgloss: hand_tool_for_screws
bow: bit, torque driver, fastener, assembly, hardware, carpentry
is_a_parents: hand_tool: a hand-powered tool for driving fasteners, tool: an implement used to perform work
has_part: handle, blade
has_attribute: material=metal, head_type=flat_or_phillips
purpose: drive screws into material
</answer>

INSTANCE (Mount Everest):
<answer entry_id="67890">
new_gloss: The name "Mount Everest" is a proper noun that denotes the highest mountain on Earth.
new_microgloss: highest_mountain_on_earth
bow: Himalayas, peak, climbing, Nepal, Tibet
is_instance_of: mountain, peak, landmark
has_attribute: height=8848m, location=Himalayas
event_group: History of Mount Everest
event_1:
  epistemic_status: CONSTITUTIVE
  verb: first_ascent
  HAS_THEME: Mount Everest
  HAS_TIME: 1953-05-29
  HAS_AGENT: Edmund Hillary
  HAS_AGENT: Tenzing Norgay
event_2:
  epistemic_status: CONSTITUTIVE
  verb: be_located_in
  HAS_THEME: Mount Everest
  HAS_LOCATION: Himalayas
link_1:
  source: event_1
  link_type: PRECEDES
  target: event_2
</answer>

## FINAL REMINDER
Only output the <answer> blocks. No extra text. No emojis.

---

## ENTRIES TO IMPROVE

{entries_section}

---
"""

# ===================================================================
# DATABASE HELPERS
# ===================================================================

def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def fetch_entries_by_ids(db_path: str, entry_ids: List[int]) -> List[Dict]:
    if not entry_ids:
        return []
    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    rows = []
    batch_size = 500
    for i in range(0, len(entry_ids), batch_size):
        batch = entry_ids[i:i+batch_size]
        placeholders = ','.join('?' * len(batch))
        cur.execute(f"""SELECT entry_id, lemma, pos_ud, gloss, microgloss,
                               canonical_id, is_instance, source_type, definition_tier
                        FROM synapedia_entry WHERE entry_id IN ({placeholders})""", batch)
        rows.extend(cur.fetchall())
    conn.close()
    return [dict(r) for r in rows]


def fetch_entries_by_lemma(db_path: str, lemmas: List[str]) -> List[Dict]:
    if not lemmas:
        return []
    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    lower_lemmas = [l.lower() for l in lemmas]
    placeholders = ','.join('?' * len(lower_lemmas))
    cur.execute(f"""SELECT entry_id, lemma, pos_ud, gloss, microgloss,
                           canonical_id, is_instance, source_type, definition_tier
                    FROM synapedia_entry
                    WHERE LOWER(lemma) IN ({placeholders}) AND improved_at IS NULL""", lower_lemmas)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fetch_all_entries_needing_improvement(db_path: str, limit: int = None) -> List[Dict]:
    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    query = """SELECT entry_id, lemma, pos_ud, gloss, microgloss,
                      canonical_id, is_instance, source_type, definition_tier
               FROM synapedia_entry
               WHERE (LENGTH(microgloss) < 5 OR microgloss IS NULL OR improved_at IS NULL)
               ORDER BY entry_id"""
    if limit:
        query += f" LIMIT {limit}"
    cur.execute(query)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ===================================================================
# LEMMA-GROUP HANDLING
# ===================================================================

def get_lemma_centrality(db_path: str) -> Dict[str, int]:
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT LOWER(parent_lemma) AS lemma, COUNT(*) AS cnt
        FROM synapedia_is_a
        GROUP BY LOWER(parent_lemma)
        ORDER BY cnt DESC
    """)
    centrality = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()
    return centrality


def get_all_lemmas_with_counts(db_path: str, priority: bool = False,
                                 order_by_count: bool = False,
                                 order_by_centrality: bool = False,
                                 centrality_map: Optional[Dict[str, int]] = None,
                                 min_entries: int = 1) -> List[Tuple[str, int, int, int]]:
    conn = get_connection(db_path)
    cur = conn.cursor()
    priority_order = {'wordnet': 0, 'wiktionary': 1, 'wikipedia': 2}
    order_cases = " ".join(
        f"WHEN source_type = '{st}' THEN {pri}"
        for st, pri in priority_order.items()
    ) if priority else ""

    if priority:
        query = f"""
            SELECT LOWER(lemma) AS lemma_lower,
                   COUNT(*) AS cnt,
                   MIN(CASE source_type {order_cases} ELSE 3 END) AS pri
            FROM synapedia_entry
            WHERE improved_at IS NULL
            GROUP BY LOWER(lemma)
            HAVING cnt >= ?
        """
    else:
        query = """
            SELECT LOWER(lemma) AS lemma_lower,
                   COUNT(*) AS cnt,
                   3 AS pri
            FROM synapedia_entry
            WHERE improved_at IS NULL
            GROUP BY LOWER(lemma)
            HAVING cnt >= ?
        """

    cur.execute(query, (min_entries,))
    results = [(row[0], row[1], row[2]) for row in cur.fetchall()]
    conn.close()

    enhanced = []
    for lemma_lower, cnt, pri in results:
        centrality = centrality_map.get(lemma_lower, 0) if centrality_map else 0
        enhanced.append((lemma_lower, cnt, pri, centrality))

    if order_by_centrality and centrality_map:
        enhanced.sort(key=lambda x: (x[2], -x[3], -x[1]))
    elif order_by_count:
        enhanced.sort(key=lambda x: (x[2], -x[1]))
    else:
        enhanced.sort(key=lambda x: (x[2], x[0]))

    return enhanced


def get_unimproved_ids_for_lemma(db_path: str, lemma_lower: str) -> List[int]:
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("""SELECT entry_id FROM synapedia_entry
                   WHERE LOWER(lemma) = ? AND improved_at IS NULL""", (lemma_lower,))
    ids = [row[0] for row in cur.fetchall()]
    conn.close()
    return ids


# ===================================================================
# LLM INTERACTION
# ===================================================================

def estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def build_entries_section(entries: List[Dict]) -> str:
    lines = []
    for e in entries:
        is_inst = e.get('is_instance', 0) or 0
        inst_marker = " [INSTANCE]" if is_inst else ""
        lines.append(f"entry_id: {e['entry_id']}")
        lines.append(f"lemma: {e['lemma']}")
        lines.append(f"pos: {e['pos_ud']}{inst_marker}")
        lines.append(f"current_gloss: {e['gloss'] or ''}")
        lines.append(f"current_microgloss: {e['microgloss'] or ''}")
        lines.append("")
    return "\n".join(lines)


def call_llm(prompt_text: str, source: str = DEFAULT_LLM_SOURCE,
             model: Optional[str] = None, max_retries: int = 3) -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    rand = uuid.uuid4().hex[:6]
    prompt_path = TEMP_DIR / f"{ts}_{rand}_prompt.txt"
    response_path = TEMP_DIR / f"{ts}_{rand}_response.txt"
    prompt_path.write_text(prompt_text, encoding="utf-8")
    for attempt in range(1, max_retries + 1):
        cmd = [sys.executable, "llm_wrapper.py",
               "--in-file", str(prompt_path),
               "--out-file", str(response_path),
               "--source", source]
        if model:
            cmd.extend(["--model", model])
        try:
            subprocess.run(cmd, check=True, timeout=LLM_SUBPROCESS_TIMEOUT)
            return response_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("LLM attempt %d/%d failed: %s", attempt, max_retries, e)
            if attempt < max_retries:
                time.sleep(2 ** attempt)
            else:
                raise
    raise RuntimeError("LLM call failed after all retries.")


def parse_response(text: str) -> Dict[int, Dict[str, Any]]:
    entries = {}
    pos = 0
    while True:
        tag_start = text.find('<answer entry_id="', pos)
        if tag_start == -1:
            break
        id_start = tag_start + len('<answer entry_id="')
        id_end = text.find('"', id_start)
        if id_end == -1:
            break
        try:
            entry_id = int(text[id_start:id_end])
        except ValueError:
            pos = id_end
            continue
        ans_end = text.find('</answer>', id_end)
        if ans_end == -1:
            break
        block = text[id_end + 1 : ans_end].strip()
        fields = _parse_answer_block(block)
        if fields:
            entries[entry_id] = fields
        pos = ans_end + 9
    return entries


def _parse_answer_block(block: str) -> Dict[str, Any]:
    """
    Parse an <answer> block into structured fields.

    Handles:
    - is_a_parents / is_instance_of: lemmas only or lemma: gloss format
    - event_group: group label
    - event_1, event_2, ...: events with verb, epistemic_status, and roles
    - link_1, link_2, ...: links between events with source, link_type, target
    """
    fields: Dict[str, Any] = {}
    current_event = None
    current_event_key = None
    links = []

    for line in block.split('\n'):
        line = line.strip()
        if not line:
            continue

        # Event group label
        if line.lower().startswith('event_group:'):
            fields['event_group'] = line.split(':', 1)[1].strip()
            continue

        # Event start
        event_match = re.match(r'^event_(\d+):\s*$', line, re.IGNORECASE)
        if event_match:
            if current_event and current_event_key:
                fields[current_event_key] = current_event
            current_event_key = f"event_{event_match.group(1)}"
            current_event = {"verb": "", "roles": {}, "epistemic_status": "CONSTITUTIVE"}
            continue

        # Link start
        link_match = re.match(r'^link_(\d+):\s*$', line, re.IGNORECASE)
        if link_match:
            if current_event and current_event_key:
                fields[current_event_key] = current_event
                current_event = None
                current_event_key = None
            current_link = {"link_index": link_match.group(1)}
            links.append(current_link)
            continue

        if ':' in line:
            colon_idx = line.index(':')
            key = line[:colon_idx].strip().lower()
            value = line[colon_idx + 1:].strip()

            if current_event is not None:
                if key == 'verb':
                    current_event["verb"] = value
                elif key == 'epistemic_status':
                    current_event["epistemic_status"] = value.upper()
                elif key.upper() in VALID_ROLES:
                    role_key = key.upper()
                    if role_key in current_event["roles"]:
                        current_event["roles"][role_key] += ", " + value
                    else:
                        current_event["roles"][role_key] = value
                else:
                    current_event["roles"][key.upper()] = value
            elif links and key in ('source', 'link_type', 'target'):
                links[-1][key] = value
            else:
                if key == 'bow':
                    terms = [t.strip() for t in value.split(',')]
                    fields[key] = ', '.join(terms)
                elif key in ('is_a_parents', 'is_instance_of'):
                    items = _parse_parent_list(value)
                    fields[key] = items
                elif key == 'has_part':
                    items = [t.strip() for t in value.split(',') if t.strip()]
                    fields[key] = items
                elif key == 'has_attribute':
                    attrs = [a.strip() for a in value.split(',') if a.strip()]
                    fields[key] = attrs
                elif key == 'purpose':
                    fields[key] = value
                elif key in ('new_gloss', 'new_microgloss'):
                    fields[key] = value

    if current_event and current_event_key:
        fields[current_event_key] = current_event

    if links:
        # Validate each link has source, link_type, target
        valid_links = [l for l in links if 'source' in l and 'link_type' in l and 'target' in l]
        if valid_links:
            fields['links'] = valid_links

    return fields


def _parse_parent_list(value: str) -> List:
    """
    Parse a parent list that may be in one of two formats:

    Format 1 (lemmas only): "hand_tool, tool"
    Format 2 (lemma + gloss): "hand_tool: a hand-powered tool, tool: an implement"

    Returns a list of dicts with 'lemma' and 'gloss' keys.
    """
    items = []
    for part in value.split(','):
        part = part.strip()
        if not part:
            continue
        colon_idx = part.find(':')
        if colon_idx > 0:
            lemma = part[:colon_idx].strip()
            gloss = part[colon_idx + 1:].strip().strip('"').strip("'")
            items.append({"lemma": lemma, "gloss": gloss})
        else:
            items.append({"lemma": part, "gloss": ""})
    return items


# ===================================================================
# CANONICAL ID RESOLUTION
# ===================================================================

def resolve_to_canonical_id(entry_lemma: str, pos: Optional[str] = None,
                              search_server_url: str = "http://localhost:8400") -> Optional[str]:
    try:
        import requests
        payload: Dict[str, Any] = {"lemma": entry_lemma}
        if pos:
            payload["pos"] = pos
        resp = requests.post(f"{search_server_url}/lookup/lemma",
                             json=payload, timeout=10)
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                for r in results:
                    cid = r.get("canonical_id", "")
                    if cid and r.get("lemma", "").lower() == entry_lemma.lower():
                        return cid
                return results[0].get("canonical_id")
    except Exception as e:
        logger.warning("Failed to resolve '%s' to canonical ID: %s", entry_lemma, e)
    return None


# ===================================================================
# ONTOLOGY INSERTION
# ===================================================================

def insert_ontology_relations(db_path: str, entry_id: int, fields: Dict[str, Any],
                                is_instance_flag: bool = False,
                                search_server_url: str = "http://localhost:8400",
                                fallback_parent: Optional[str] = None,
                                cur: Optional[sqlite3.Cursor] = None) -> None:
    if cur is not None:
        _cur = cur
        _commit = False
    else:
        conn = get_connection(db_path)
        _cur = conn.cursor()
        _commit = True

    is_instance = is_instance_flag or bool(fields.get('is_instance_of'))
    if is_instance:
        parent_field = fields.get('is_instance_of', [])
        relation_table = "synapedia_has_instance"
        parent_col = "instance_lemma"
        canonical_col = "instance_canonical_id"
    else:
        parent_field = fields.get('is_a_parents', [])
        relation_table = "synapedia_is_a"
        parent_col = "parent_lemma"
        canonical_col = "parent_canonical_id"

    parents_inserted = False
    inserted_parents = []
    if parent_field:
        for parent_entry in parent_field:
            if isinstance(parent_entry, dict):
                parent_lemma = parent_entry.get("lemma", "").strip()
                parent_gloss = parent_entry.get("gloss", "")
            else:
                parent_lemma = parent_entry.strip()
                parent_gloss = ""
            if not parent_lemma:
                continue
            parent_cid = resolve_to_canonical_id(parent_lemma, "NOUN", search_server_url)
            try:
                _cur.execute(f"""
                    INSERT OR IGNORE INTO {relation_table}
                        ({parent_col}, synapedia_entry_id, {canonical_col},
                         relation_source, trust_level)
                    VALUES (?, ?, ?, 'llm', 'provisional')
                """, (parent_lemma, entry_id, parent_cid))
                parents_inserted = True
                inserted_parents.append(parent_lemma)
                logger.info("     ✅ Added %s: '%s' → cid=%s", relation_table, parent_lemma, parent_cid or "UNRESOLVED")
            except sqlite3.IntegrityError:
                logger.info("     ⏭️ Skipped %s: '%s' (already exists)", relation_table, parent_lemma)

    if not parents_inserted and fallback_parent:
        fallback_cid = resolve_to_canonical_id(fallback_parent, "NOUN", search_server_url)
        logger.warning("     ⚠️ No parent from LLM. Using fallback: '%s' (cid=%s)", fallback_parent, fallback_cid)
        try:
            _cur.execute(f"""
                INSERT OR IGNORE INTO {relation_table}
                    ({parent_col}, synapedia_entry_id, {canonical_col},
                     relation_source, trust_level)
                VALUES (?, ?, ?, 'llm', 'fallback')
            """, (fallback_parent, entry_id, fallback_cid))
            logger.info("     ✅ Added fallback parent: '%s'", fallback_parent)
        except sqlite3.IntegrityError:
            logger.info("     ⏭️ Fallback '%s' already exists, skipped", fallback_parent)

    # HAS_PART
    has_part = fields.get('has_part', [])
    if has_part:
        for part_lemma in has_part:
            part_lemma = part_lemma.strip()
            if not part_lemma:
                continue
            part_cid = resolve_to_canonical_id(part_lemma, "NOUN", search_server_url)
            _cur.execute("""
                INSERT OR IGNORE INTO synapedia_has_part
                    (synapedia_entry_id, part_lemma, part_canonical_id,
                     relation_source, trust_level)
                VALUES (?, ?, ?, 'llm', 'provisional')
            """, (entry_id, part_lemma, part_cid))
            logger.info("     ✅ Added HAS_PART: '%s' → cid=%s", part_lemma, part_cid or "UNRESOLVED")

    # HAS_ATTRIBUTE
    has_attr = fields.get('has_attribute', [])
    if has_attr:
        for attr_entry in has_attr:
            attr_entry = attr_entry.strip()
            if not attr_entry:
                continue
            if '=' in attr_entry:
                key, value = attr_entry.split('=', 1)
                key = key.strip()
                value = value.strip()
            else:
                key = attr_entry
                value = ""
            _cur.execute("""
                INSERT OR IGNORE INTO synapedia_has_attribute
                    (synapedia_entry_id, attribute_key, attribute_value,
                     relation_source, trust_level)
                VALUES (?, ?, ?, 'llm', 'provisional')
            """, (entry_id, key, value))
            logger.info("     ✅ Added HAS_ATTRIBUTE: %s=%s", key, value)

    if _commit:
        conn.commit()
        conn.close()


# ===================================================================
# EVENT (SYNAPSE) INSERTION
# ===================================================================

def generate_synapse_id(verb_lemma: str, entry_id: int, event_index: int,
                        namespace: str = "synapedia") -> str:
    raw = f"{namespace}:{entry_id}:{verb_lemma}:{event_index}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"{namespace}.syn.{h}"


def insert_event_synapse(db_path: str, entry_id: int,
                          event: Dict[str, Any],
                          event_index: int,
                          search_server_url: str = "http://localhost:8400",
                          cur: Optional[sqlite3.Cursor] = None) -> Optional[str]:
    verb = event.get("verb", "").strip()
    if not verb:
        logger.warning("  ⚠️ Event %d has no verb. Skipping.", event_index)
        return None

    roles = event.get("roles", {})
    if not roles:
        logger.warning("  ⚠️ Event %d has no roles. Skipping.", event_index)
        return None

    epistemic_status = event.get("epistemic_status", "CONSTITUTIVE")

    verb_cid = resolve_to_canonical_id(verb, "VERB", search_server_url)
    synapse_id = generate_synapse_id(verb, entry_id, event_index)

    if cur is not None:
        _cur = cur
        _commit = False
    else:
        conn = get_connection(db_path)
        _cur = conn.cursor()
        _commit = True

    try:
        _cur.execute("""
            INSERT INTO synapedia_synapse
                (synapse_id, verb_lemma, verb_canonical_id, plane,
                 epistemic_status, trust_level)
            VALUES (?, ?, ?, 'ontological', ?, 'provisional')
        """, (synapse_id, verb, verb_cid, epistemic_status))
        logger.info("     ✅ Synapse %s: verb='%s' cid=%s status=%s", synapse_id, verb, verb_cid or "UNRESOLVED", epistemic_status)
    except sqlite3.IntegrityError:
        logger.warning("     ⏭️ Synapse %s already exists. Skipping.", synapse_id)
        if _commit:
            conn.close()
        return synapse_id

    for role, participant_lemma in roles.items():
        participants = [p.strip() for p in participant_lemma.split(',') if p.strip()]
        for participant in participants:
            target_cid = resolve_to_canonical_id(participant, "NOUN", search_server_url)
            target_type = "concept"
            literal_value = None
            if re.match(r'^\d{4}-\d{2}-\d{2}$', participant) or \
               re.match(r'^\d{4}$', participant) or \
               re.match(r'^[\d.]+$', participant):
                target_type = "literal"
                literal_value = participant
                target_cid = None

            try:
                _cur.execute("""
                    INSERT INTO synapedia_spoke
                        (synapse_id, role, target_id, target_type, target_lemma, literal_value)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (synapse_id, role, target_cid, target_type, participant, literal_value))
                logger.info("       Spoke: %s = '%s' (type=%s, cid=%s)", role, participant, target_type, target_cid or "UNRESOLVED")
            except sqlite3.IntegrityError:
                pass

    try:
        _cur.execute("""
            INSERT INTO synapedia_entry_synapse
                (entry_id, synapse_id, relation)
            VALUES (?, ?, 'has_event')
        """, (entry_id, synapse_id))
    except sqlite3.IntegrityError:
        pass

    if _commit:
        conn.commit()
        conn.close()
    return synapse_id


# ===================================================================
# FALLBACK PARENT DETECTION
# ===================================================================

def get_existing_parent(db_path: str, entry_id: int,
                         cur: Optional[sqlite3.Cursor] = None) -> Optional[str]:
    if cur is not None:
        cur.execute("""
            SELECT parent_lemma FROM synapedia_is_a
            WHERE synapedia_entry_id = ? AND relation_source = 'wordnet'
            LIMIT 1
        """, (entry_id,))
        row = cur.fetchone()
        return row[0] if row else None
    else:
        conn = get_connection(db_path)
        c = conn.cursor()
        c.execute("""
            SELECT parent_lemma FROM synapedia_is_a
            WHERE synapedia_entry_id = ? AND relation_source = 'wordnet'
            LIMIT 1
        """, (entry_id,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else None


def guess_fallback_parent(lemma: str, pos_ud: str) -> str:
    parts = lemma.split()
    if len(parts) >= 2:
        return parts[-1].lower()
    pos_upper = pos_ud.upper() if pos_ud else "NOUN"
    generic_parents = {
        "NOUN": "entity",
        "VERB": "action",
        "ADJ": "quality",
        "ADV": "manner",
        "PROPN": "entity",
    }
    return generic_parents.get(pos_upper, "entity")


# ===================================================================
# MAIN UPDATE FUNCTION (with detailed verbose logging)
# ===================================================================

def update_db_and_embed(db_path: str, embed_service_url: str,
                        search_server_url: str,
                        results: Dict[int, Dict[str, Any]],
                        generate_events: bool = True,
                        avoid_floating_nodes: bool = True) -> int:
    import requests
    conn = get_connection(db_path)
    cur = conn.cursor()
    updated_ids = []
    total_events = 0
    minted_ids = []
    total_parents = 0
    total_parts = 0
    total_attrs = 0
    total_fallbacks = 0

    logger.info("")
    logger.info("╔══════════════════════════════════════════════════════════════╗")
    logger.info("║          BEGINNING UPDATE OF %d ENTRIES                    ║", len(results))
    logger.info("╚══════════════════════════════════════════════════════════════╝")
    logger.info("")

    for entry_idx, (entry_id, fields) in enumerate(results.items()):
        logger.info("")
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info("  ENTRY %d/%d — ID: %d", entry_idx + 1, len(results), entry_id)
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info("")

        new_gloss = fields.get('new_gloss', '')
        new_microgloss = fields.get('new_microgloss', '')
        bow = fields.get('bow', '')
        if not new_gloss:
            logger.warning("  ⚠️ SKIPPING: no new_gloss provided by LLM")
            continue

        if bow:
            new_embedding_text = new_gloss + "\nRelated terms: " + bow
        else:
            new_embedding_text = new_gloss

        # Fetch current entry state
        cur.execute("SELECT lemma, pos_ud, is_instance, gloss, microgloss, bow, canonical_id FROM synapedia_entry WHERE entry_id = ?",
                    (entry_id,))
        row = cur.fetchone()
        if not row:
            logger.warning("  ⚠️ Entry %d not found in DB. Skipping.", entry_id)
            continue
        lemma = row[0]
        pos_ud = row[1]
        is_instance = row[2] == 1
        old_gloss = row[3] or ''
        old_microgloss = row[4] or ''
        old_bow = row[5] or ''
        canonical_id = row[6] or '(none)'

        if not is_instance and pos_ud == "PROPN":
            is_instance = True

        # ── HEADER ──
        logger.info("  📋 IDENTITY:")
        logger.info("     Lemma:       %s", lemma)
        logger.info("     POS:         %s", pos_ud)
        logger.info("     Instance:    %s", "YES" if is_instance else "No")
        logger.info("     Canonical:   %s", canonical_id)
        logger.info("")

        # ── GLOSS ──
        logger.info("  📝 GLOSS UPDATE:")
        if old_gloss:
            logger.info("     OLD (%d chars): %s", len(old_gloss), old_gloss[:120] + ("..." if len(old_gloss) > 120 else ""))
        else:
            logger.info("     OLD: (none)")
        logger.info("     NEW (%d chars): %s", len(new_gloss), new_gloss[:120] + ("..." if len(new_gloss) > 120 else ""))
        logger.info("")

        # ── MICROGLOSS ──
        logger.info("  🏷️ MICROGLOSS:")
        logger.info("     OLD: %s", old_microgloss if old_microgloss else "(none)")
        logger.info("     NEW: %s", new_microgloss if new_microgloss else "(none)")
        logger.info("")

        # ── BOW ──
        logger.info("  📚 BAG OF WORDS:")
        if old_bow:
            old_terms = [t.strip() for t in old_bow.split(',') if t.strip()]
            logger.info("     OLD (%d terms): %s", len(old_terms), old_bow[:120])
        else:
            logger.info("     OLD: (none)")
        if bow:
            new_terms = [t.strip() for t in bow.split(',') if t.strip()]
            logger.info("     NEW (%d terms): %s", len(new_terms), bow[:120])
        else:
            logger.info("     NEW: (none)")
        logger.info("")

        # ── EXECUTE UPDATE ──
        cur.execute("""UPDATE synapedia_entry
                       SET gloss = ?, microgloss = ?, bow = ?, embedding_text = ?,
                           embedding_text_version = 'v3-precision',
                           improved_at = datetime('now')
                       WHERE entry_id = ?""",
                   (new_gloss, new_microgloss, bow, new_embedding_text, entry_id))
        updated_ids.append(entry_id)
        logger.info("  ✅ GLOSS SAVED TO DATABASE")
        logger.info("")

        # ── FALLBACK PARENT ──
        fallback_parent = None
        if avoid_floating_nodes:
            existing = get_existing_parent(db_path, entry_id, cur=cur)
            if existing:
                logger.info("  🔗 EXISTING WORDNET PARENT: '%s' (will be preserved)", existing)
            fallback_parent = existing or guess_fallback_parent(lemma, pos_ud)
            if not existing:
                logger.info("  ⚠️ FALLBACK GUESS: '%s' (from POS=%s heuristic)", fallback_parent, pos_ud)
        logger.info("")

        # ── ONTOLOGY ──
        parent_info = fields.get('is_a_parents', [])
        instance_info = fields.get('is_instance_of', [])
        has_part = fields.get('has_part', [])
        has_attr = fields.get('has_attribute', [])
        purpose = fields.get('purpose', '')

        all_parents = parent_info or instance_info
        logger.info("  🏗️ ONTOLOGY FROM LLM:")

        if all_parents:
            logger.info("     PARENTS (%d):", len(all_parents))
            for pi, p in enumerate(all_parents):
                p_lemma = p.get("lemma") if isinstance(p, dict) else p
                p_gloss = p.get("gloss", "") if isinstance(p, dict) else ""
                parent_type = "IS_A" if not is_instance else "IS_INSTANCE_OF"
                logger.info("       %d. %s '%s'", pi+1, parent_type, p_lemma)
                if p_gloss:
                    logger.info("          Gloss: %s", p_gloss[:80])
        else:
            logger.info("     PARENTS: (none provided by LLM)")

        if has_part:
            logger.info("     PARTS (%d): %s", len(has_part), ", ".join(has_part))
        else:
            logger.info("     PARTS: (none)")

        if has_attr:
            logger.info("     ATTRIBUTES (%d):", len(has_attr))
            for a in has_attr:
                logger.info("       • %s", a)
        else:
            logger.info("     ATTRIBUTES: (none)")

        if purpose:
            logger.info("     PURPOSE: %s", purpose[:80])
        else:
            logger.info("     PURPOSE: (none)")
        logger.info("")

        # ── INSERT ONTOLOGY ──
        insert_ontology_relations(
            db_path, entry_id, fields,
            is_instance_flag=is_instance,
            search_server_url=search_server_url,
            fallback_parent=fallback_parent,
            cur=cur
        )
        if all_parents:
            total_parents += len(all_parents)
        if has_part:
            total_parts += len(has_part)
        if has_attr:
            total_attrs += len(has_attr)
        if fallback_parent and not (all_parents and any(
            (isinstance(p, dict) and p.get("lemma") == fallback_parent) or 
            (not isinstance(p, dict) and p == fallback_parent) 
            for p in all_parents)):
            total_fallbacks += 1

        # ── MINT MISSING PARENTS ──
        if parent_info:
            logger.info("  🔍 CHECKING %d IS-A PARENTS FOR MISSING ENTRIES:", len(parent_info))
            for pi, p in enumerate(parent_info):
                p_lemma = p.get("lemma") if isinstance(p, dict) else p
                p_gloss = p.get("gloss", "") if isinstance(p, dict) else ""
                conn2 = get_connection(db_path)
                cur2 = conn2.cursor()
                cur2.execute("SELECT 1 FROM synapedia_entry WHERE LOWER(lemma) = ? LIMIT 1", (p_lemma.lower(),))
                exists = cur2.fetchone() is not None
                conn2.close()
                if exists:
                    logger.info("     %d. '%s' → ALREADY EXISTS (skipping mint)", pi+1, p_lemma)
                else:
                    logger.info("     %d. '%s' → DOES NOT EXIST (will mint)", pi+1, p_lemma)
                    if p_gloss:
                        logger.info("        Gloss: %s", p_gloss[:80])
            new_minted = mint_missing_parents(
                db_path=db_path,
                child_entry_id=entry_id,
                parent_info=parent_info,
                is_instance=False,
                embed_service_url=embed_service_url,
                max_mint=5,
                cur=cur,
            )
            if new_minted:
                logger.info("     ✅ MINTED %d NEW ENTRIES: IDs=%s", len(new_minted), new_minted)
                for mid in new_minted:
                    cur3 = conn.cursor()
                    cur3.execute("SELECT lemma, canonical_id FROM synapedia_entry WHERE entry_id = ?", (mid,))
                    mrow = cur3.fetchone()
                    if mrow:
                        logger.info("        → Entry %d: lemma='%s' cid='%s'", mid, mrow[0], mrow[1])
            else:
                logger.info("     → No new entries needed minting")
            minted_ids.extend(new_minted)

        if instance_info:
            logger.info("  🔍 CHECKING %d IS_INSTANCE_OF PARENTS FOR MISSING ENTRIES:", len(instance_info))
            for pi, p in enumerate(instance_info):
                p_lemma = p.get("lemma") if isinstance(p, dict) else p
                conn2 = get_connection(db_path)
                cur2 = conn2.cursor()
                cur2.execute("SELECT 1 FROM synapedia_entry WHERE LOWER(lemma) = ? LIMIT 1", (p_lemma.lower(),))
                exists = cur2.fetchone() is not None
                conn2.close()
                logger.info("     %d. '%s' → %s", pi+1, p_lemma, "EXISTS" if exists else "WILL MINT")
            new_minted = mint_missing_parents(
                db_path=db_path,
                child_entry_id=entry_id,
                parent_info=instance_info,
                is_instance=True,
                embed_service_url=embed_service_url,
                max_mint=5,
                cur=cur,
            )
            if new_minted:
                logger.info("     ✅ MINTED %d NEW INSTANCE PARENTS: IDs=%s", len(new_minted), new_minted)
            else:
                logger.info("     → No new instance parents needed minting")
            minted_ids.extend(new_minted)

        # ── EVENTS ──
        event_keys = []
        if generate_events:
            for i in range(1, 10):
                event_key = f"event_{i}"
                event = fields.get(event_key)
                if not event:
                    break
                verb = event.get("verb", "")
                status = event.get("epistemic_status", "CONSTITUTIVE")
                roles = event.get("roles", {})
                logger.info("  🎭 EVENT %d:", i)
                logger.info("     verb='%s' status=%s", verb, status)
                for role, participant in roles.items():
                    logger.info("       %s = %s", role, participant)
                sid = insert_event_synapse(
                    db_path, entry_id, event, i,
                    search_server_url=search_server_url,
                    cur=cur
                )
                if sid:
                    fields[f"synapse_{event_key}"] = sid
                    event_keys.append(event_key)
                    total_events += 1

        purpose = fields.get('purpose', '')
        if purpose and not is_instance:
            purpose_event = {
                "verb": purpose.split()[0] if purpose.split() else "use",
                "roles": {"HAS_PURPOSE": purpose}
            }
            logger.info("  🎯 PURPOSE EVENT:")
            logger.info("     verb='%s' purpose='%s'", purpose_event["verb"], purpose[:80])
            sid = insert_event_synapse(
                db_path, entry_id, purpose_event, 0,
                search_server_url=search_server_url,
                cur=cur
            )
            if sid:
                if not fields.get('event_group'):
                    fields['event_group'] = f"Purpose of {lemma}"
                fields["synapse_purpose"] = sid
                total_events += 1

        # ── EVENT GROUP ──
        event_group_label = fields.get('event_group')
        if event_group_label and event_keys:
            group_type = "CHAIN" if fields.get('links') else "STAR"
            logger.info("  📦 EVENT GROUP: '%s' (type=%s, %d events)", event_group_label, group_type, len(event_keys))
            insert_event_group(
                db_path=db_path,
                entry_id=entry_id,
                group_label=event_group_label,
                event_keys=event_keys,
                fields=fields,
                group_type=group_type,
                cur=cur,
            )

        # ── LINKS ──
        if 'links' in fields and fields['links']:
            logger.info("  🔗 EVENT LINKS (%d):", len(fields['links']))
            for lk in fields['links']:
                logger.info("     %s --[%s]--> %s", lk.get('source'), lk.get('link_type'), lk.get('target'))
            insert_event_links(
                db_path=db_path,
                links=fields['links'],
                fields=fields,
                cur=cur,
            )

    conn.commit()
    conn.close()
    logger.info("")
    logger.info("╔══════════════════════════════════════════════════════════════╗")
    logger.info("║                    DB COMMIT COMPLETE                       ║")
    logger.info("╚══════════════════════════════════════════════════════════════╝")
    logger.info("")

    updated_ids.extend(minted_ids)

    if not updated_ids:
        logger.warning("  ⚠️ No entries were updated!")
        return 1

    logger.info("  📊 SUMMARY:")
    logger.info("     Entries updated:    %d", len(updated_ids) - len(minted_ids))
    logger.info("     New entries minted: %d", len(minted_ids))
    logger.info("     IS-A parents:       %d", total_parents)
    logger.info("     HAS-PART:           %d", total_parts)
    logger.info("     HAS-ATTRIBUTE:      %d", total_attrs)
    logger.info("     Events stored:      %d", total_events)
    logger.info("     Fallback parents:   %d", total_fallbacks)
    logger.info("")

    logger.info("  📡 CALLING EMBED SERVICE for %d entries...", len(updated_ids))
    try:
        resp = requests.post(f"{embed_service_url}/recompute",
                             json={"entry_ids": updated_ids},
                             timeout=60 * len(updated_ids) // 100 + 30)
        if resp.status_code == 200:
            logger.info("  ✅ Embed service: %d entries recomputed successfully", len(updated_ids))
            logger.info("")
            logger.info("  ✓ DONE. All entries improved successfully.")
            return 0
        else:
            logger.warning("  ⚠️ Embed service returned %d: %s", resp.status_code, resp.text)
            return 3
    except Exception as e:
        logger.error("  ❌ Embed service call failed: %s", e)
        return 3


# ===================================================================
# LEMMA GROUP PROCESSING
# ===================================================================

def improve_lemma_group(db_path: str, lemma_lower: str, entry_ids: List[int],
                        embed_service_url: str, search_server_url: str,
                        llm_source: str, model: Optional[str],
                        generate_events: bool = True,
                        avoid_floating_nodes: bool = True,
                        dry_run: bool = False) -> int:
    if not entry_ids:
        return 0

    batches = [entry_ids[i:i+MAX_ENTRIES_PER_LLM_CALL]
               for i in range(0, len(entry_ids), MAX_ENTRIES_PER_LLM_CALL)]

    all_results: Dict[int, Dict[str, Any]] = {}
    total_errors = 0

    for batch_idx, batch_ids in enumerate(batches):
        entries = fetch_entries_by_ids(db_path, batch_ids)
        if not entries:
            continue
        if dry_run:
            logger.info("DRY RUN: Would improve %d entries for lemma '%s' (batch %d/%d)",
                        len(entries), lemma_lower, batch_idx+1, len(batches))
            continue

        entries_section = build_entries_section(entries)
        prompt = PROMPT_TEMPLATE.format(entries_section=entries_section)
        tokens = estimate_tokens(prompt)
        if tokens > MAX_TOKENS_PER_PROMPT:
            logger.warning("Batch %d for lemma '%s' too large (%d tokens). Skipping.",
                           batch_idx+1, lemma_lower, tokens)
            total_errors += 1
            continue

        logger.info("Lemma '%s' batch %d/%d: %d entries, ~%d tokens. Calling LLM...",
                    lemma_lower, batch_idx+1, len(batches), len(entries), tokens)
        try:
            response = call_llm(prompt, source=llm_source, model=model)
        except Exception as e:
            logger.error("LLM call failed for lemma '%s' batch %d: %s",
                         lemma_lower, batch_idx+1, e)
            total_errors += 1
            continue

        batch_results = parse_response(response)
        if not batch_results:
            logger.error("No <answer> blocks for lemma '%s' batch %d.", lemma_lower, batch_idx+1)
            total_errors += 1
            continue

        logger.info("Lemma '%s' batch %d/%d: got %d answers.",
                    lemma_lower, batch_idx+1, len(batches), len(batch_results))
        all_results.update(batch_results)

    if dry_run:
        return 0 if total_errors == 0 else 1

    if not all_results:
        logger.warning("No results for lemma '%s' (all batches failed).", lemma_lower)
        return 1

    return update_db_and_embed(
        db_path, embed_service_url, search_server_url,
        all_results,
        generate_events=generate_events,
        avoid_floating_nodes=avoid_floating_nodes
    )


# ===================================================================
# MAIN
# ===================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Unified entry enrichment: gloss + ontology + events + instance identity.",
        epilog=(
            "Examples:\n"
            "  python improve_glossary_and_ontology.py --db synapedia.db --entry-ids 24601,56369\n"
            "  python improve_glossary_and_ontology.py --db synapedia.db --lemmas \"wrench\"\n"
            "  python improve_glossary_and_ontology.py --db synapedia.db --all\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--db', required=True, help='Path to synapedia.db')
    parser.add_argument('--entry-ids', help='comma-separated list of entry_ids')
    parser.add_argument('--from-stdin', action='store_true', help='Read entry_ids from stdin')
    parser.add_argument('--lemmas', help='comma-separated list of lemmas')
    parser.add_argument('--lemmas-file', help='file containing one lemma per line')
    parser.add_argument('--all', action='store_true', help='Loop over all unimproved lemma groups')
    parser.add_argument('--priority', action='store_true', default=True,
                        help='Order by WordNet/Wiktionary/Wikipedia (default: True)')
    parser.add_argument('--order-by-count', action='store_true', default=True,
                        help='Process lemmas with most entries first (default: True)')
    parser.add_argument('--centrality', action='store_true', default=True,
                        help='Prioritize lemmas that are IS-A parents of many others (default: True)')
    parser.add_argument('--min-entries', type=int, default=2,
                        help='Skip lemma groups with fewer entries (default 2)')
    parser.add_argument('--limit-lemmas', type=int, default=0,
                        help='Stop after N lemma groups')
    parser.add_argument('--llm-source', default=DEFAULT_LLM_SOURCE)
    parser.add_argument('--model', default=None)
    parser.add_argument('--embed-service', default=EMBED_SERVICE_URL)
    parser.add_argument('--search-server', default="http://localhost:8400",
                        help='Search server URL for canonical ID resolution')
    parser.add_argument('--generate-events', action='store_true', default=True,
                        help='Generate event Synapses for proper nouns and verbs')
    parser.add_argument('--avoid-floating-nodes', action='store_true', default=True,
                        help='Ensure every entry gets at least one parent link')
    parser.add_argument('--mint-missing', action='store_true', default=True,
                        help='Mint entries for missing parent concepts (default: True)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    # ========== Setup logging for all modes ==========
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    # =================================================

    # ── Mode 1: Single batch ──
    if args.entry_ids or args.from_stdin or args.lemmas or args.lemmas_file:
        entry_ids = []
        if args.entry_ids:
            entry_ids = [int(x.strip()) for x in args.entry_ids.split(',')]
        elif args.from_stdin:
            for line in sys.stdin:
                line = line.strip()
                if line and line.isdigit():
                    entry_ids.append(int(line))
        elif args.lemmas or args.lemmas_file:
            lemma_list = []
            if args.lemmas:
                lemma_list = [l.strip() for l in args.lemmas.split(',') if l.strip()]
            if args.lemmas_file:
                with open(args.lemmas_file) as f:
                    lemma_list.extend(line.strip() for line in f if line.strip())
            all_ids = []
            conn = get_connection(args.db)
            cur = conn.cursor()
            batch_size = 500
            for i in range(0, len(lemma_list), batch_size):
                batch = [l.lower() for l in lemma_list[i:i+batch_size]]
                placeholders = ','.join('?' * len(batch))
                cur.execute(f"""SELECT entry_id FROM synapedia_entry
                               WHERE LOWER(lemma) IN ({placeholders})""", batch)
                all_ids.extend(row[0] for row in cur.fetchall())
            unimproved = []
            for i in range(0, len(all_ids), batch_size):
                batch = all_ids[i:i+batch_size]
                ph = ','.join('?' * len(batch))
                cur.execute(f"""SELECT entry_id FROM synapedia_entry
                               WHERE entry_id IN ({ph}) AND improved_at IS NULL""", batch)
                unimproved.extend(row[0] for row in cur.fetchall())
            conn.close()
            if not unimproved:
                print("All requested entries already improved.")
                sys.exit(0)
            entry_ids = unimproved
            logger.info("Found %d unimproved entries", len(entry_ids))

        if not entry_ids:
            print("No entry IDs to process.")
            sys.exit(2)

        entries = fetch_entries_by_ids(args.db, entry_ids)
        if not entries:
            print("No entries found.")
            sys.exit(2)
        entries_section = build_entries_section(entries)
        prompt = PROMPT_TEMPLATE.format(entries_section=entries_section)
        tokens = estimate_tokens(prompt)
        if tokens > MAX_TOKENS_PER_PROMPT:
            logger.error("Prompt too large (%d tokens). Use --all for lemma-by-lemma processing.", tokens)
            sys.exit(1)
        if args.dry_run:
            logger.info("DRY RUN: Would improve %d entries.", len(entries))
            sys.exit(0)
        logger.info("Calling LLM with %d entries (~%d tokens)...", len(entries), tokens)
        try:
            response = call_llm(prompt, source=args.llm_source, model=args.model)
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            sys.exit(1)
        results = parse_response(response)
        if not results:
            logger.error("No <answer> blocks found.")
            sys.exit(1)
        ec = update_db_and_embed(
            args.db, args.embed_service, args.search_server, results,
            generate_events=args.generate_events,
            avoid_floating_nodes=args.avoid_floating_nodes
        )
        sys.exit(ec)

    # ── Mode 2: Looping --all ──
    elif args.all:
        centrality_map = get_lemma_centrality(args.db)
        logger.info("Computed centrality map: %d lemmas are IS-A parents.",
                    len(centrality_map))

        lemmas = get_all_lemmas_with_counts(
            args.db,
            priority=args.priority,
            order_by_count=args.order_by_count,
            order_by_centrality=args.centrality,
            centrality_map=centrality_map,
            min_entries=args.min_entries
        )
        if not lemmas:
            print("No lemma groups with at least {} unimproved entries.".format(args.min_entries))
            sys.exit(0)
        logger.info("Will improve up to %d lemma groups (priority=%s, order_by_count=%s, centrality=%s, min_entries=%d)",
                    len(lemmas), args.priority, args.order_by_count, args.centrality, args.min_entries)
        total_improved = 0
        total_errors = 0
        count = 0
        for lemma_lower, cnt, pri, cent in lemmas:
            if args.limit_lemmas > 0 and count >= args.limit_lemmas:
                break
            count += 1
            entry_ids = get_unimproved_ids_for_lemma(args.db, lemma_lower)
            if not entry_ids:
                continue
            ec = improve_lemma_group(
                args.db, lemma_lower, entry_ids,
                args.embed_service, args.search_server,
                args.llm_source, args.model,
                generate_events=args.generate_events,
                avoid_floating_nodes=args.avoid_floating_nodes,
                dry_run=args.dry_run
            )
            if ec == 0:
                total_improved += len(entry_ids)
                logger.info("Lemma '%s': improved %d entries (total: %d).",
                            lemma_lower, len(entry_ids), total_improved)
            else:
                total_errors += 1
                logger.error("Lemma '%s' failed (exit %d).", lemma_lower, ec)
        logger.info("Done. Improved %d entries across %d lemmas. Errors: %d",
                    total_improved, count - total_errors, total_errors)
        sys.exit(0 if total_errors == 0 else 1)

    else:
        parser.error("Provide one of: --entry-ids, --from-stdin, --lemmas, --lemmas-file, --all")


if __name__ == '__main__':
    main()