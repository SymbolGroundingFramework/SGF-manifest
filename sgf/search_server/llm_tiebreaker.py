#!/usr/bin/env python3
"""
llm_tiebreaker.py -- LLM-of-last-resort tie-breaker for ambiguous queries

SYNAPEDIA v7 ADAPTATION
=======================
The prompt now uses only fields that exist in synapedia_entry and are
loaded into memory: canonical_id, lemma, pos_ud, microgloss,
definition_tier, source_type. Fields like register, social_status,
temporal_status, specificity, audience_tier are NOT present in v7
and have been removed from the prompt.

The envelope contract (<answer> / <comments>) and parser (llm_kv_parser.py)
are unchanged.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

import llm_kv_parser as kv


def needs_tiebreak(candidates, margin_threshold):
    """True if the top-2 candidates are too close to trust cosine + rerank."""
    if not candidates or len(candidates) < 2:
        return False
    s1 = _best_score(candidates[0])
    s2 = _best_score(candidates[1])
    if s1 is None or s2 is None:
        return False
    return (s1 - s2) < margin_threshold


def _best_score(c):
    """Pick whichever score the latest layer produced (rerank > raw)."""
    if "rerank_score" in c:
        return float(c["rerank_score"])
    if "score" in c:
        return float(c["score"])
    if "raw_score" in c:
        return float(c["raw_score"])
    return None


def tiebreak(query_text, candidates, llm_wrapper, tier="flash", temp=0.0,
             timeout_seconds=60):
    """Ask the LLM to pick the single best candidate for the query.

    Returns the re-ordered candidate list with the LLM's pick at top.
    If the LLM call fails or returns an unparseable answer, the
    original list is returned unchanged.
    """
    if not candidates:
        return candidates
    if len(candidates) < 2:
        return candidates

    prompt = _build_prompt(query_text, candidates)
    raw = _call_llm(llm_wrapper, prompt, tier=tier, temp=temp,
                    timeout_seconds=timeout_seconds)
    if not raw:
        return candidates

    chosen_cid = _parse_choice(raw)
    if not chosen_cid:
        return candidates

    # Move the chosen candidate to the front.
    for i, c in enumerate(candidates):
        if c.get("canonical_id") == chosen_cid:
            if i == 0:
                candidates[0]["llm_tiebreak_picked"] = True
                return candidates
            picked = candidates.pop(i)
            picked["llm_tiebreak_picked"] = True
            return [picked] + candidates

    # LLM picked something not in the list (hallucination). Leave order.
    return candidates


# Metadata axes shown to the LLM for every candidate.
# Only fields that actually exist in synapedia_entry are included.
_METADATA_AXES_FOR_PROMPT = (
    "definition_tier",    # CORE_ONTOLOGY, CORE_KNOWLEDGE, LEXICAL_EXTENSION
    "source_type",        # wordnet, wikipedia, wiktionary
)


def _build_prompt(query_text, candidates):
    """Build the LLM tiebreak prompt. Generic, single-prompt, all-purpose."""
    lines = []
    lines.append(
        "You are a sense-disambiguation tiebreaker for a machine-"
        "readable lexicon. You receive a query (often a sentence or "
        "fragment in natural context) and a short list of candidate "
        "senses. The candidates have already been narrowed by an "
        "embedding model, a cross-encoder reranker, and a lexical "
        "BM25 pass. You are seeing this case because those stages "
        "could not separate the candidates confidently."
    )
    lines.append("")
    lines.append(
        "Pick the single sense the query most likely refers to. "
        "The query is a fragment of text in some context: it could "
        "be from a medical paper, a legal brief, a technical manual, "
        "a financial filing, a logistics report, a research article, "
        "a fantasy novel, a news story, a transcript of conversation, "
        "or anything else. Do not assume any particular genre. Read "
        "the query as it is, infer the kind of text you are looking "
        "at from its own cues, and pick the candidate that best fits "
        "that context."
    )
    lines.append("")
    lines.append(
        "Different queries hinge on different signals. A clinical "
        "sentence is settled by domain fit (specialist vs general "
        "terminology). A narrative sentence is settled by who or "
        "what is acting and on what. A legal sentence is settled by "
        "jurisdictional and technical fit. A conversational fragment "
        "may be settled by speaker, register, or regional cues. "
        "Weigh whichever signals the query actually carries. Draw "
        "on your full knowledge of how language is used across "
        "genres, fields, dialects, and historical periods."
    )
    lines.append("")
    lines.append(
        "The candidates below each include a microgloss (a concise "
        "disambiguating description) and structured metadata "
        "(definition_tier, source_type). The metadata indicates "
        "the authority of each source: CORE_ONTOLOGY (WordNet) is "
        "academic bedrock, CORE_KNOWLEDGE (Wikipedia) is "
        "encyclopedic, LEXICAL_EXTENSION (Wiktionary) is "
        "crowd-sourced. Use this to break ties when the query "
        "context demands authoritative terminology."
    )
    lines.append("")
    lines.append("OUTPUT FORMAT (machine-parsed; follow exactly):")
    lines.append(
        "Wrap your final pick between <answer>...</answer> tags. "
        "Put any reasoning between <comments>...</comments> tags. "
        "Downstream code parses the <answer> envelope and discards "
        "everything else, so you can reason freely in <comments> "
        "without breaking the parser."
    )
    lines.append("")
    lines.append("Inside <answer>...</answer>, output exactly one line:")
    lines.append("  canonical_id: <one of the canonical_ids below>")
    lines.append("")
    lines.append(f"QUERY: {query_text!r}")
    lines.append("")
    lines.append("CANDIDATES:")
    for c in candidates:
        cid = c.get("canonical_id", "?")
        lemma = c.get("lemma", "?")
        pos = c.get("pos_ud", "?")
        microgloss = c.get("microgloss") or ""
        meta_pairs = []
        for axis in _METADATA_AXES_FOR_PROMPT:
            val = c.get(axis)
            if val:
                meta_pairs.append(f"{axis}={val}")
        meta_str = (" [" + "; ".join(meta_pairs) + "]") if meta_pairs else ""
        lines.append(f"  - {cid}")
        lines.append(f"      lemma: {lemma} ({pos}){meta_str}")
        if microgloss:
            lines.append(f"      microgloss: {microgloss}")
    lines.append("")
    lines.append(
        "Pick the single best canonical_id. Wrap it in <answer> "
        "tags as shown. Brief reasoning in <comments> tags is "
        "welcome but optional."
    )
    return "\n".join(lines)


def _parse_choice(raw):
    """Extract the chosen canonical_id from the LLM response envelope."""
    inner = kv.extract_answer(raw)
    if not inner:
        return None
    blocks = kv.parse_kv_blocks(inner)
    for b in blocks:
        cid = b.get("canonical_id")
        if cid:
            return cid.strip()
    for line in inner.splitlines():
        if ":" in line:
            head, _, tail = line.partition(":")
            if head.strip().lower() == "canonical_id":
                return tail.strip()
    return None


def _call_llm(llm_wrapper, prompt, tier="flash", temp=0.0, timeout_seconds=60):
    """Shell out to the user's LLM wrapper, return the response text."""
    tmp = Path(tempfile.gettempdir())
    tag = f"{os.getpid()}_{secrets.token_hex(4)}"
    in_file = tmp / f"tiebreak_in_{tag}.txt"
    out_file = tmp / f"tiebreak_out_{tag}.txt"
    try:
        in_file.write_text(prompt, encoding="utf-8")
        cmd = [
            sys.executable, str(llm_wrapper),
            "--in-file", str(in_file),
            "--out-file", str(out_file),
            "--tier", tier,
            "--temp", str(temp),
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_seconds,
        )
        if result.returncode != 0:
            return None
        if not out_file.exists():
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