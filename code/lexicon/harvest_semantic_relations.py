#!/usr/bin/env python3
"""
harvest_semantic_relations.py -- Stage 11 -- semantic-relation harvest

For senses in scope (default: top frequency tier), harvest semantic
relations into the sense_semantic_relation table. The relation
vocabulary is:

  ONTOLOGICAL (relation_kind='ontological'):
    - IS_A
    - HAS_PART

  CORE SEMANTIC ROLES (relation_kind='core_role') -- event participants:
    - HAS_AGENT, HAS_PATIENT, HAS_THEME, HAS_EXPERIENCER,
      HAS_RECIPIENT, HAS_BENEFICIARY

  CONTEXT SEMANTIC ROLES (relation_kind='context_role') -- circumstances:
    - HAS_TIME, HAS_LOCATION, HAS_SOURCE, HAS_DESTINATION,
      HAS_MANNER, HAS_INSTRUMENT, HAS_CAUSE, HAS_REASON, HAS_ATTRIBUTE

  TODO V2 (lexicon as encyclopedia):
  This stage harvests sense-level type relations (IS_A, HAS_PART) and
  typical-event roles. It does NOT yet harvest descriptive synapses
  about each concept (e.g. "presidents lead countries, sign bills,
  veto legislation"). That is V2 work via a shared synapse_extractor
  factored out of GLEAN. The 17-name allowlist stays closed; V2 only
  adds *more synapses per sense*, not more relation types. See
  V2_VISION.md.

HOW THE LLM TARGETS GET RESOLVED TO WSIDS
-----------------------------------------
The LLM cannot know lexicon wsids. It produces a structured target
description per relation:

    target_lemma       : the surface lemma it thinks the target is
    target_pos         : noun / verb / adj / adv (best guess)
    target_description : a description of the target meaning -- can be
                         a short phrase or a full sentence; longer is
                         fine, embedders use all of it
    confidence         : 0.0-1.0
    rationale          : a short justification

The resolver then:

    1. Embeds target_description using the production embedder.
    2. Calls lexicon_search.topk() with lemma_restrict=target_lemma
       (and pos_restrict if pos was given).
    3. Takes the top-1 match. That wsid is the resolved target.
    4. Records the resolution method, the original description, and
       the cosine of the resolved match, so downstream consumers can
       distinguish high-confidence resolutions from fuzzy ones.

This embed-and-filter pattern is the same one the production search
server uses for cross-language retrieval. We use lexicon_search.py
in-process so the resolver and the production search server share
ONE implementation; no drift.

If lemma resolution finds zero candidates, we fall back to
unrestricted top-K and record target_resolution_method='lemma_only'
or 'unresolved' as appropriate.

LLM RESPONSE FORMAT
-------------------
Line-based key:value blocks (NOT JSON -- LLMs cannot do JSON reliably
over thousands of calls). Parsed by llm_kv_parser.parse_kv_blocks().
A malformed single block loses one relation; the rest are recovered.

HYBRID HARVEST
--------------
1. PATTERN PASS (deterministic, runs first, no LLM, no resolution):
   - Extract IS_A from "A type of X" patterns
   - Extract HAS_PART from "consisting of X, Y, Z"
   - Extract HAS_LOCATION from "Found in X"
   - These pattern-targets are stored as target_placeholder strings
     (not resolved to wsids).

2. LLM PASS (the structured prompt + in-process resolver):
   - Send sense + pattern-harvested hints to the LLM.
   - LLM returns key-value blocks with target_microgloss_hint etc.
   - Each LLM-produced relation has its target resolved to a wsid via
     embed-and-filter against the lexicon.

USAGE
-----
    python harvest_semantic_relations.py --target sgf_lexicon.db \\
        --llm-wrapper /path/to/llm.py \\
        [--top-lemmas 50000] \\
        [--patterns-only] [--limit N] [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import tempfile
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

# In-process search library (the canonical implementation also exposed
# by glean_search_server.py over HTTP). We use it directly here so the
# bootstrap doesn't require a running search server.
import lexicon_search

# Tolerant key-value parser for LLM responses.
import llm_kv_parser as kv


# ---------------------------------------------------------------------------
# Relation taxonomy -- imported from lexicon_metadata for single-source-of-truth.
# DO NOT redefine these locally; the canonical 17 names live in
# lexicon_metadata.VALID_SEMANTIC_RELATIONS.
# ---------------------------------------------------------------------------

from lexicon_metadata import (
    VALID_ONTOLOGICAL_RELATIONS as ONTOLOGICAL,
    VALID_CORE_ROLES as CORE_ROLES,
    VALID_CONTEXT_ROLES as CONTEXT_ROLES,
    VALID_SEMANTIC_RELATIONS as ALL_RELATIONS,
)


def kind_for(relation_type):
    if relation_type in ONTOLOGICAL:
        return "ontological"
    if relation_type in CORE_ROLES:
        return "core_role"
    if relation_type in CONTEXT_ROLES:
        return "context_role"
    return None


# ---------------------------------------------------------------------------
# Schema migration -- add the new resolver columns if missing
# ---------------------------------------------------------------------------

def ensure_ssr_columns(conn):
    """Idempotently add the new sense_semantic_relation columns if a
    pre-v3.2 DB is in play."""
    cur = conn.execute("PRAGMA table_info(sense_semantic_relation)")
    existing = {row[1] for row in cur.fetchall()}
    if not existing:
        print(
            "ERROR: sense_semantic_relation table missing. "
            "Run: python apply_schema.py",
            file=sys.stderr,
        )
        return False
    added = []
    for col, decl in [
        ("target_microgloss_hint",    "TEXT"),
        ("target_canonical_id_guess", "TEXT"),
        ("target_resolution_method",  "TEXT"),
        ("target_resolution_cosine",  "REAL"),
    ]:
        if col not in existing:
            conn.execute(f"ALTER TABLE sense_semantic_relation ADD COLUMN {col} {decl}")
            added.append(col)
    if added:
        conn.commit()
        print(f"  schema: added columns {added}")
    return True


# ---------------------------------------------------------------------------
# Pattern harvesting (deterministic, regex-based, legacy)
# ---------------------------------------------------------------------------
#
# These patterns are intentionally narrow and only fire on Wiktionary's
# stereotyped openings. They produce target_placeholder strings (not
# wsids); the resolver does not run on pattern relations. Regex is kept
# here only because it has been working in v1; new code does not use
# regex.

IS_A_PATTERNS = [
    re.compile(r"^A\s+(?:type|kind|sort|variety|form|species|genus|family|class|category)\s+of\s+(?P<target>[a-z][a-z\s-]+?)(?:[.,;]|$)", re.I),
    re.compile(r"^An?\s+(?P<target>[a-z][a-z\s-]+?)\s+(?:that|which|who|used|having)", re.I),
]

HAS_PART_PATTERNS = [
    re.compile(r"(?:consist(?:s|ing)|made\s+up|composed)\s+of\s+(?P<target>[a-z][a-z\s,;-]+?)(?:\.|$)", re.I),
    re.compile(r"(?:contain(?:s|ing)|hold(?:s|ing))\s+(?:a\s+|an\s+|the\s+)?(?P<target>[a-z][a-z\s,;-]+?)(?:\.|$)", re.I),
]

HAS_PART_TOKEN_BLOCKLIST = {
    "found", "made", "used", "called", "known", "located", "native",
    "originating", "growing", "living",
    "a", "an", "the", "and", "or", "with", "without", "of", "in", "on",
}

HAS_LOCATION_PATTERNS = [
    re.compile(r"\b(?:found|located|native|originating|growing|living)\s+in\s+(?P<target>[A-Za-z][A-Za-z\s,-]+?)(?:[.,;]|$)"),
]

HAS_INSTRUMENT_PATTERNS = [
    re.compile(r"\b(?:using|by\s+means\s+of|with\s+a)\s+(?P<target>[a-z][a-z\s-]+?)(?:[.,;]|$)", re.I),
]


def harvest_from_patterns(gloss):
    """Return list of (relation_type, target_string, confidence)."""
    out = []
    if not gloss:
        return out
    for pat in IS_A_PATTERNS:
        m = pat.search(gloss)
        if m:
            t = m.group("target").strip().rstrip(".,;").strip()
            t = t.split()[0]  # head noun only
            if t and len(t) > 1:
                out.append(("IS_A", t.lower(), 0.85))
                break
    for pat in HAS_PART_PATTERNS:
        m = pat.search(gloss)
        if m:
            t_raw = m.group("target").strip().rstrip(".,;").strip()
            for chunk in re.split(r"[,;]| and ", t_raw):
                chunk = chunk.strip()
                if not chunk or not (1 < len(chunk) < 30):
                    continue
                head = chunk.lower().split()[0]
                if head in HAS_PART_TOKEN_BLOCKLIST:
                    continue
                out.append(("HAS_PART", head, 0.80))
            break
    for pat in HAS_LOCATION_PATTERNS:
        m = pat.search(gloss)
        if m:
            t = m.group("target").strip().rstrip(".,;").strip()
            if t and len(t) > 1:
                out.append(("HAS_LOCATION", t.lower(), 0.80))
            break
    for pat in HAS_INSTRUMENT_PATTERNS:
        m = pat.search(gloss)
        if m:
            t = m.group("target").strip().rstrip(".,;").strip()
            if t and len(t) > 1:
                out.append(("HAS_INSTRUMENT", t.lower(), 0.75))
            break
    return out


# ---------------------------------------------------------------------------
# LLM prompt -- line-based key:value format, NOT JSON
# ---------------------------------------------------------------------------

LLM_SYSTEM = """\
You are extracting semantic relations from a lexicon entry.

You will be given a single sense (lemma, pos, gloss, microgloss).
Return relations using the line-based block format described below.
DO NOT USE JSON. DO NOT USE CODE FENCES.

WRAP YOUR ANSWER IN TAGS
------------------------
Wrap the structured part of your reply inside <answer>...</answer>
tags. Put any commentary, reasoning, caveats, or asides inside
<comments>...</comments> tags. The downstream parser only reads what
is inside <answer>; everything else is discarded. This lets you think
aloud freely without contaminating the structured output.

Example reply:

  <comments>
  This sense is a medical term. I'll focus on the disease relation.
  </comments>

  <answer>
  RELATION_1
  relation_type: IS_A
  ...
  </answer>

OUTPUT FORMAT (inside <answer>)
-------------------------------
For each relation you extract, write a block in this exact form:

RELATION_<N>
relation_type: <one of the role names below>
relation_kind: ontological | core_role | context_role
target_lemma: <the English lemma the target is, lowercase>
target_pos: noun | verb | adj | adv
target_description: <a clear description of the target's meaning>
confidence: <0.0 to 1.0>
rationale: <a short reason>

Separate blocks with a blank line.

HOW YOUR RELATIONS GET LINKED TO REAL LEXICON SENSES
----------------------------------------------------
You do NOT need to know the target's internal sense ID. The lexicon
will resolve your target to one of its own senses automatically:

  1. It filters its sense list to senses whose lemma matches
     target_lemma (and pos matches target_pos, when given).
  2. It embeds your target_description and picks the closest match
     among those filtered candidates.

This means two things for you:

  - target_lemma MUST be the English lemma you intend (e.g. "cancer",
    not "malignancy"). It is the FILTER.
  - target_description can be a sentence, a phrase, or a paraphrase --
    whatever helps an embedder land on the right meaning. Longer is
    fine. Do not include register tags (slang, archaic, etc).

RELATION VOCABULARY
-------------------

ONTOLOGICAL (relation_kind='ontological'):
  IS_A         : X is a type/subclass of TARGET
  HAS_PART     : X has TARGET as a component

CORE SEMANTIC ROLES (relation_kind='core_role') -- event participants:
  HAS_AGENT       : entity that deliberately initiates/performs/controls
                    e.g. (write) HAS_AGENT (author)
  HAS_PATIENT     : entity that undergoes structural change/destruction
                    e.g. (break) HAS_PATIENT (object_broken)
  HAS_THEME       : entity moved/located/possessed without internal change
                    e.g. (give) HAS_THEME (gift)
  HAS_EXPERIENCER : living entity with a psychological/sensory state
                    e.g. (love) HAS_EXPERIENCER (lover)
  HAS_RECIPIENT   : destination entity that changes possession
                    e.g. (give) HAS_RECIPIENT (recipient)
  HAS_BENEFICIARY : entity for whose advantage/sake the event is performed
                    e.g. (cook) HAS_BENEFICIARY (family)

CONTEXT SEMANTIC ROLES (relation_kind='context_role') -- circumstances:
  HAS_TIME       : when the event occurs
                    e.g. (sunrise) HAS_TIME (dawn)
  HAS_LOCATION   : where the event occurs / where the entity is
                    e.g. (concert) HAS_LOCATION (auditorium)
  HAS_SOURCE     : where motion or transfer originates
                    e.g. (export) HAS_SOURCE (origin_country)
  HAS_DESTINATION: where motion or transfer ends
                    e.g. (export) HAS_DESTINATION (target_country)
  HAS_MANNER     : the way the event is carried out
                    e.g. (whisper) HAS_MANNER (quiet_voice)
  HAS_INSTRUMENT : tool or means used to bring about the event
                    e.g. (cut) HAS_INSTRUMENT (knife)
  HAS_CAUSE      : inanimate / unintentional driver of the event
                    e.g. (house_burns_down) HAS_CAUSE (fire)
  HAS_REASON     : motivational purpose, legal mandate, or logical
                   justification driving an agent's choice
                    e.g. (study) HAS_REASON (exam_preparation)
  HAS_ATTRIBUTE  : a property the entity has
                    e.g. (strawberry) HAS_ATTRIBUTE (red.color),
                         (strawberry) HAS_ATTRIBUTE (sweet.flavor)

HAS_CAUSE vs HAS_REASON:
  cause is inanimate / unintentional; reason is motivational / intentional.
  A house burns down: HAS_CAUSE=fire.
  A person flees: HAS_REASON=self_preservation.

ALLOWLIST -- THESE 17 ARE THE ONLY VALID RELATION TYPES
-------------------------------------------------------
The canonical list (do NOT invent new ones):

  Ontological (2): IS_A, HAS_PART
  Core roles (6):  HAS_AGENT, HAS_PATIENT, HAS_THEME, HAS_EXPERIENCER,
                   HAS_RECIPIENT, HAS_BENEFICIARY
  Context roles (9): HAS_TIME, HAS_LOCATION, HAS_SOURCE, HAS_DESTINATION,
                     HAS_MANNER, HAS_INSTRUMENT, HAS_CAUSE, HAS_REASON,
                     HAS_ATTRIBUTE

DO NOT invent role names like HAS_PURPOSE, HAS_GOAL, HAS_FUNCTION,
HAS_RESULT, HAS_TYPE, HAS_CATEGORY, HAS_PROPERTY, HAS_QUALITY,
HAS_FEATURE, HAS_USE, HAS_USAGE, USED_FOR, RELATED_TO, etc. These are
ALL CONSIDERED HALLUCINATIONS and will be silently dropped.

  - Function/purpose: use HAS_REASON.
  - Property/quality/feature: use HAS_ATTRIBUTE.
  - Used-for / instrumental: use HAS_INSTRUMENT (or HAS_REASON if the
    sense is about the purpose, not the tool).
  - Generic 'related_to': do NOT emit anything; semantic relatedness
    without a specific role is not a relation in this lexicon.

If the meaning relationship you want to express does not fit one of
the 17 names above, OMIT THE RELATION rather than coin a new name.

RULES
-----
- Only include relations you are confident the gloss/microgloss imply.
- For abstract or function words, return zero relations.
- Maximum 8 relations per sense.
- Each relation MUST include: relation_type, relation_kind,
  target_lemma, target_description, confidence.
  target_pos and rationale are optional but helpful.
- If a key has no value, omit the line entirely.
"""


def build_llm_prompt(ctx, pattern_relations, prior_relations=None):
    lines = [LLM_SYSTEM, ""]
    lines.append("======= SENSE TO HARVEST =======")
    lines.append(f"LEMMA: {ctx['lemma']}")
    lines.append(f"POS: {ctx['pos_simple']}")
    lines.append(f"MICROGLOSS: {ctx.get('microgloss', '')}")
    lines.append(f"GLOSS: {ctx.get('gloss', '')}")
    if pattern_relations:
        lines.append("")
        lines.append("ALREADY-HARVESTED FROM PATTERNS (do not duplicate; deepen if relevant):")
        for rt, target, conf in pattern_relations:
            lines.append(f"  - {rt} -> {target!r} (conf {conf:.2f})")
    if prior_relations:
        lines.append("")
        lines.append("PRIOR LLM RELATIONS (this sense was harvested before -- propose ADDITIONAL or CORRECTED relations, do not duplicate the existing ones unless you can do strictly better):")
        for r in prior_relations:
            lines.append(
                f"  - {r.get('relation_type')} -> lemma={r.get('target_placeholder','?')!r} "
                f"description={(r.get('target_microgloss_hint') or '')[:80]!r} "
                f"conf={r.get('confidence', 0.0):.2f}"
            )
    lines.append("")
    lines.append("Emit your reply now. Wrap the structured part in <answer>...</answer>.")
    return "\n".join(lines)


def parse_llm_relations(raw):
    """Parse the LLM's KV response into a list of relation dicts.

    Returns: list of dicts, each containing the validated subset of
    keys we care about. Invalid blocks are silently dropped.
    """
    # Two-layer parse: extract <answer>...</answer> envelope, then
    # parse the KV blocks inside it. parse_llm_response handles both.
    blocks = kv.parse_llm_response(raw)
    out = []
    for b in blocks:
        relation_type = (b.get("relation_type") or "").strip().upper()
        if relation_type not in ALL_RELATIONS:
            continue
        relation_kind = (b.get("relation_kind") or "").strip().lower()
        if relation_kind not in ("ontological", "core_role", "context_role"):
            relation_kind = kind_for(relation_type)
        target_lemma = (b.get("target_lemma") or "").strip()
        if not target_lemma:
            continue
        target_pos = (b.get("target_pos") or "").strip().lower() or None
        # The LLM produces target_description (preferred) but accept
        # target_microgloss_hint as an alias for backwards-compat with
        # any custom prompts.
        target_description = (
            b.get("target_description")
            or b.get("target_microgloss_hint")
            or ""
        ).strip() or None
        confidence = kv.as_float(b.get("confidence"), default=0.5)
        rationale = (b.get("rationale") or "").strip()[:500]
        out.append({
            "relation_type": relation_type,
            "relation_kind": relation_kind,
            "target_lemma": target_lemma,
            "target_pos": target_pos,
            "target_description": target_description,
            "confidence": confidence,
            "rationale": rationale,
        })
    return out


# ---------------------------------------------------------------------------
# LLM wrapper subprocess call
# ---------------------------------------------------------------------------

def call_llm(llm_wrapper, prompt, tier="flash", temp=0.0, timeout_seconds=120):
    tmp = Path(tempfile.gettempdir())
    tag = f"{os.getpid()}_{secrets.token_hex(4)}"
    in_file = tmp / f"hsr_in_{tag}.txt"
    out_file = tmp / f"hsr_out_{tag}.txt"
    try:
        in_file.write_text(prompt, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(llm_wrapper),
             "--in-file", str(in_file), "--out-file", str(out_file),
             "--tier", tier, "--temp", str(temp)],
            capture_output=True, text=True, timeout=timeout_seconds,
        )
        if result.returncode != 0 or not out_file.exists():
            return None
        return out_file.read_text(encoding="utf-8")
    except (subprocess.TimeoutExpired, OSError, UnicodeDecodeError):
        return None
    finally:
        try:
            in_file.unlink(missing_ok=True)
            out_file.unlink(missing_ok=True)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Target resolver -- the heart of the new architecture
# ---------------------------------------------------------------------------

def resolve_target(lexicon_ctx, embedding_method, relation):
    """Given an LLM-produced relation dict, resolve its target to a
    lexicon wsid via embed-and-filter.

    Returns the input relation dict with these additional keys set:
        target_wsid              : int or None
        target_resolution_method : 'embed_filter_v1' / 'lemma_only' /
                                   'unresolved'
        target_resolution_cosine : float or None

    Resolution strategy:
      1. If target_lemma maps to >= 2 candidate senses AND we have a
         microgloss_hint, embed the hint and pick the top-1
         lemma-filtered match. Method: 'embed_filter_v1'.
      2. If target_lemma maps to exactly one candidate, take it.
         Method: 'lemma_only'.
      3. If target_lemma maps to zero candidates, leave wsid=None and
         keep target_lemma as target_placeholder. Method: 'unresolved'.

    The pos_restrict is applied when target_pos is given.
    """
    rel = dict(relation)
    target_lemma = rel.get("target_lemma") or ""
    target_pos = rel.get("target_pos")
    target_description = rel.get("target_description") or ""

    rel["target_wsid"] = None
    rel["target_resolution_method"] = "unresolved"
    rel["target_resolution_cosine"] = None

    if not target_lemma:
        return rel

    candidate_senses = lexicon_search.lookup_by_lemma(
        lexicon_ctx, target_lemma, pos=target_pos,
    )

    if len(candidate_senses) == 0:
        # Try without pos filter as a fallback
        if target_pos:
            candidate_senses = lexicon_search.lookup_by_lemma(
                lexicon_ctx, target_lemma, pos=None,
            )
        if len(candidate_senses) == 0:
            return rel  # unresolved

    if len(candidate_senses) == 1:
        rel["target_wsid"] = candidate_senses[0]["wsid"]
        rel["target_resolution_method"] = "lemma_only"
        rel["target_resolution_cosine"] = 1.0
        return rel

    # Polysemous lemma: use embed-and-filter
    if not target_description:
        # LLM gave us a lemma but no description -- can't disambiguate
        # cleanly. Best we can do is take the first sense and flag it.
        rel["target_wsid"] = candidate_senses[0]["wsid"]
        rel["target_resolution_method"] = "lemma_only"
        rel["target_resolution_cosine"] = None
        return rel

    if not lexicon_search.embedder_runtime_available():
        # No embedder; fallback to first lemma match
        rel["target_wsid"] = candidate_senses[0]["wsid"]
        rel["target_resolution_method"] = "lemma_only"
        rel["target_resolution_cosine"] = None
        return rel

    try:
        qv = lexicon_search.embed_text(target_description, embedding_method)
    except RuntimeError:
        rel["target_wsid"] = candidate_senses[0]["wsid"]
        rel["target_resolution_method"] = "lemma_only"
        rel["target_resolution_cosine"] = None
        return rel

    topk_results = lexicon_search.topk(
        lexicon_ctx, qv, embedding_method, k=1,
        lemma_restrict=target_lemma,
        pos_restrict=target_pos,
    )
    if not topk_results:
        return rel  # unresolved
    chosen_wsid, cos = topk_results[0]
    rel["target_wsid"] = chosen_wsid
    rel["target_resolution_method"] = "embed_filter_v1"
    rel["target_resolution_cosine"] = float(cos)
    return rel


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def persist_pattern_relations(conn, source_wsid, pattern_rels, now):
    """Write pattern-harvested relations (target as placeholder, no wsid)."""
    n = 0
    for rt, target, confidence in pattern_rels:
        kind = kind_for(rt)
        if kind is None:
            continue
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO sense_semantic_relation (
                    source_wsid, relation_type, relation_kind,
                    target_wsid, target_placeholder,
                    target_microgloss_hint, target_canonical_id_guess,
                    target_resolution_method, target_resolution_cosine,
                    confidence, source_method, llm_model, rationale, created_at
                ) VALUES (?, ?, ?, NULL, ?, NULL, NULL, 'pattern_v1', NULL,
                          ?, 'wiktionary_pattern', NULL, 'wiktionary_pattern', ?)
                """,
                (source_wsid, rt, kind, target, float(confidence), now),
            )
            n += 1
        except sqlite3.IntegrityError:
            pass
    return n


def persist_llm_relation(conn, source_wsid, rel, llm_model, now):
    """Write one LLM-derived (and resolved) relation.

    The DB column 'target_microgloss_hint' stores what the LLM gave us
    as target_description -- they're the same field under two names
    (the schema uses the older name; the LLM prompt uses the cleaner
    one).
    """
    try:
        target_wsid = rel.get("target_wsid")
        target_placeholder = (
            rel.get("target_lemma") if target_wsid is None else None
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO sense_semantic_relation (
                source_wsid, relation_type, relation_kind,
                target_wsid, target_placeholder,
                target_microgloss_hint, target_canonical_id_guess,
                target_resolution_method, target_resolution_cosine,
                confidence, source_method, llm_model, rationale, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, 'llm_v3', ?, ?, ?)
            """,
            (
                source_wsid, rel["relation_type"], rel["relation_kind"],
                target_wsid, target_placeholder,
                rel.get("target_description"),
                rel.get("target_resolution_method", "unresolved"),
                rel.get("target_resolution_cosine"),
                float(rel.get("confidence", 0.5)),
                llm_model, rel.get("rationale", ""), now,
            ),
        )
        return 1
    except sqlite3.IntegrityError:
        return 0


# ---------------------------------------------------------------------------
# Scope + loading
# ---------------------------------------------------------------------------

def select_scope(conn, top_lemmas, revisit=False):
    """Return list of wsids in scope (frequency-prioritized).

    By default, skip senses already at 'related' tier (already harvested).
    With revisit=True, include those senses so they can be refined.
    """
    if revisit:
        # Include all in-scope senses, regardless of current tier.
        cur = conn.execute(
            """
            SELECT DISTINCT sl.wiktionary_source_id
              FROM sgf_lexicon sl
              LEFT JOIN lemma_frequency lf ON lf.lemma = LOWER(sl.lemma)
             WHERE lf.frequency_rank IS NOT NULL AND lf.frequency_rank <= ?
             ORDER BY lf.frequency_rank ASC
            """,
            (top_lemmas,),
        )
    else:
        # Skip senses already at 'related' (idempotent default).
        cur = conn.execute(
            """
            SELECT DISTINCT sl.wiktionary_source_id
              FROM sgf_lexicon sl
              LEFT JOIN lemma_frequency lf ON lf.lemma = LOWER(sl.lemma)
             WHERE lf.frequency_rank IS NOT NULL AND lf.frequency_rank <= ?
               AND sl.maturity_tier != 'related'
             ORDER BY lf.frequency_rank ASC
            """,
            (top_lemmas,),
        )
    return [r[0] for r in cur.fetchall()]


def load_prior_relations(conn, wsid):
    """Load existing LLM-harvested relations for a sense (for revisit mode)."""
    out = []
    cur = conn.execute(
        """
        SELECT relation_type, target_placeholder, target_microgloss_hint,
               confidence
          FROM sense_semantic_relation
         WHERE source_wsid = ? AND source_method = 'llm_v3'
         ORDER BY confidence DESC
         LIMIT 12
        """,
        (wsid,),
    )
    for rt, placeholder, hint, conf in cur.fetchall():
        out.append({
            "relation_type": rt,
            "target_placeholder": placeholder,
            "target_microgloss_hint": hint,
            "confidence": conf or 0.0,
        })
    return out


def load_sense(conn, wsid):
    row = conn.execute(
        """
        SELECT lemma, pos_simple, gloss, microgloss
          FROM sgf_lexicon WHERE wiktionary_source_id = ?
        """,
        (wsid,),
    ).fetchone()
    if not row:
        return None
    return {"wsid": wsid, "lemma": row[0], "pos_simple": row[1],
            "gloss": row[2] or "", "microgloss": row[3] or ""}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", default="sgf_lexicon.db")
    p.add_argument("--llm-wrapper", help="Path to LLM wrapper script")
    p.add_argument("--top-lemmas", type=int, default=50000)
    p.add_argument("--tier", default="flash")
    p.add_argument("--temp", type=float, default=0.0)
    p.add_argument("--patterns-only", action="store_true",
                   help="Skip the LLM pass; do pattern-only harvesting")
    p.add_argument("--llm-only", action="store_true",
                   help="Skip the pattern pass; LLM only")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--embedding-method", default=None,
                   help="Embedder for target resolution (default: best available)")
    p.add_argument("--revisit", action="store_true",
                   help="Re-harvest senses already at 'related' tier; show "
                        "the LLM existing relations so it can add/refine")
    args = p.parse_args()

    db_path = Path(args.target)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 60000")

    if not ensure_ssr_columns(conn):
        return 1

    in_scope = select_scope(conn, args.top_lemmas, revisit=args.revisit)
    if args.limit is not None:
        in_scope = in_scope[: args.limit]

    print(f"Target:               {db_path.resolve()}")
    print(f"Top lemmas:           {args.top_lemmas:,}")
    print(f"Senses in scope:      {len(in_scope):,}")
    print(f"Patterns only:        {args.patterns_only}")
    print(f"LLM only:             {args.llm_only}")
    print()

    if not args.patterns_only and not args.llm_wrapper and not args.dry_run:
        print(
            "ERROR: --llm-wrapper required for LLM pass. "
            "Use --patterns-only to skip LLM.",
            file=sys.stderr,
        )
        return 1

    # Load the lexicon into memory for the target resolver. Skipped in
    # patterns-only mode since the resolver isn't needed.
    lexicon_ctx = None
    embedding_method = args.embedding_method
    if not args.patterns_only and not args.dry_run:
        print("Loading lexicon for in-process target resolution ...")
        lexicon_ctx = lexicon_search.load_lexicon(db_path, verbose=True)
        if embedding_method is None:
            embedding_method = lexicon_search.best_embedder_for_language(
                lexicon_ctx, "en",
            )
        print(f"  resolver embedding_method: {embedding_method}")
        if not lexicon_search.embedder_runtime_available():
            print("  WARNING: ONNX runtime not installed; resolver will "
                  "fall back to lemma_only when multiple senses share a lemma")
        print()

    n_pat = 0
    n_llm = 0
    n_resolved_embed = 0
    n_resolved_lemma_only = 0
    n_unresolved = 0
    t0 = time.time()

    for idx, wsid in enumerate(in_scope, 1):
        ctx = load_sense(conn, wsid)
        if ctx is None:
            continue

        pat_rels = []
        if not args.llm_only:
            pat_rels = harvest_from_patterns(ctx["gloss"])
            if pat_rels and not args.dry_run:
                n_pat += persist_pattern_relations(
                    conn, wsid, pat_rels, int(time.time()),
                )

        if not args.patterns_only:
            prior = load_prior_relations(conn, wsid) if args.revisit else None
            prompt = build_llm_prompt(ctx, pat_rels, prior_relations=prior)
            raw = call_llm(args.llm_wrapper, prompt, args.tier, args.temp)
            llm_rels = parse_llm_relations(raw) if raw else []
            for rel in llm_rels:
                resolved = resolve_target(lexicon_ctx, embedding_method, rel)
                method = resolved.get("target_resolution_method", "unresolved")
                if method == "embed_filter_v1":
                    n_resolved_embed += 1
                elif method == "lemma_only":
                    n_resolved_lemma_only += 1
                else:
                    n_unresolved += 1
                if not args.dry_run:
                    n_llm += persist_llm_relation(
                        conn, wsid, resolved, args.tier, int(time.time()),
                    )

        # Advance tier to 'related' once this sense has at least one
        # semantic relation.
        if not args.dry_run:
            conn.execute(
                """
                UPDATE sgf_lexicon
                   SET maturity_tier = 'related'
                 WHERE wiktionary_source_id = ?
                   AND maturity_tier IN ('raw','provisional','embedded_v1',
                                         'improved','embedded_v2','clustered')
                   AND EXISTS (
                     SELECT 1 FROM sense_semantic_relation
                      WHERE source_wsid = ?
                   )
                """,
                (wsid, wsid),
            )

        if idx % 100 == 0:
            conn.commit()
            elapsed = time.time() - t0
            rate = idx / max(elapsed, 0.001)
            remain = (len(in_scope) - idx) / max(rate, 0.001)
            print(
                f"  [{idx}/{len(in_scope)}] pat={n_pat} llm={n_llm}  "
                f"resolved={n_resolved_embed} (embed) "
                f"+{n_resolved_lemma_only} (lemma) "
                f"+{n_unresolved} (unres)  "
                f"{rate:.1f}/s  eta={remain/60:.1f}m"
            )
    conn.commit()

    print()
    print("=" * 60)
    print("HARVEST COMPLETE")
    print("=" * 60)
    print(f"  pattern relations:        {n_pat:,}")
    print(f"  LLM relations:            {n_llm:,}")
    print(f"    resolved via embed:     {n_resolved_embed:,}")
    print(f"    resolved via lemma:     {n_resolved_lemma_only:,}")
    print(f"    unresolved (no lemma):  {n_unresolved:,}")
    print(f"  elapsed:                  {(time.time()-t0)/60:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
