#!/usr/bin/env python3
"""
llm_tiebreaker.py -- LLM-of-last-resort tie-breaker for ambiguous queries

WHEN IT FIRES
-------------
The client-side search pipeline runs three layers:

  1. bi-encoder cosine retrieval (cheap, fast, lexicon-wide)
  2. cross-encoder reranker (precise, but slower, on top-N only)
  3. LLM tiebreaker (THIS module; slow, expensive, last resort)

Each layer is gated by the margin between the top-1 and top-2 scores.
If the cosine path already separates candidates cleanly, the reranker
does not fire. If the reranker already separates them cleanly, the
LLM tiebreaker does not fire. The LLM only sees cases the prior two
layers could not confidently resolve.

PROMPT CONTRACT
---------------
Every LLM call routes through the user's `llm_wrapper.py` adapter
(the same adapter the lexicon pipeline uses). The prompt asks the
LLM to wrap its answer in `<answer>...</answer>` tags and any
reasoning or asides in `<comments>...</comments>` tags. Reasoning:
this two-layer envelope contract lets downstream parsers extract
the structured answer cleanly without regex acrobatics, no matter
what the LLM puts around it.

The LLM is told which candidate it picked (by canonical_id) and
which it rejected. It is NOT asked to rank or score. Picking one
out of N is a smaller, more reliable LLM task than scoring or
ranking, and the upstream layers already provided the ranking; we
only need the LLM to confirm or override the top-1 pick.
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
                # LLM agreed with the top pick; no reordering needed but
                # we still annotate.
                candidates[0]["llm_tiebreak_picked"] = True
                return candidates
            picked = candidates.pop(i)
            picked["llm_tiebreak_picked"] = True
            return [picked] + candidates

    # LLM picked something not in the list (hallucination). Leave order.
    return candidates


# Metadata axes shown to the LLM for every candidate. These mirror
# the divergent_axes the cascade uses to decide when to fire the LLM,
# so the LLM sees the structured signals that triggered its call.
_METADATA_AXES_FOR_PROMPT = (
    "register",
    "social_status",
    "temporal_status",
    "specificity",
    "audience_tier",
)


def _build_prompt(query_text, candidates):
    """Build the LLM tiebreak prompt. Generic, single-prompt, all-purpose.

    The same prompt handles every kind of disambiguation the cascade
    might escalate, across every kind of source text: medical, legal,
    technical, financial, logistics, scientific, narrative fiction,
    journalism, conversational transcripts, historical documents,
    fantasy worldbuilding, or anything else. We do NOT assume the
    query is conversational or that there is a speaker and an
    addressee. We do NOT pre-select what kind of question this is.
    The query's own text tells the LLM what kind of context it is in,
    and the LLM applies whatever knowledge fits. We hand it the query
    and the candidates and trust its training corpus to do the rest.

    Output uses the two-layer envelope contract: machine-parseable
    canonical_id in <answer>...</answer>, free-form reasoning in
    <comments>...</comments>.
    """
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
        "(register, social_status, temporal_status, specificity, "
        "audience_tier). The metadata is descriptive, not "
        "prescriptive: it tells you what a sense IS, not which "
        "contexts it FITS. That second judgment is yours to make."
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
        pos = c.get("pos_simple", "?")
        microgloss = c.get("microgloss") or ""
        gloss = c.get("gloss") or ""
        meta_pairs = []
        for axis in _METADATA_AXES_FOR_PROMPT:
            val = c.get(axis)
            if val:
                if isinstance(val, (list, tuple)):
                    val = ", ".join(str(x) for x in val)
                meta_pairs.append(f"{axis}={val}")
        meta_str = (" [" + "; ".join(meta_pairs) + "]") if meta_pairs else ""
        lines.append(f"  - {cid}")
        lines.append(f"      lemma: {lemma} ({pos}){meta_str}")
        if microgloss:
            lines.append(f"      microgloss: {microgloss}")
        if gloss and gloss != microgloss:
            lines.append(f"      gloss: {gloss}")
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
    # Two acceptable shapes: a single block with canonical_id, or a flat
    # canonical_id line (which parse_kv_blocks returns as a one-entry list).
    for b in blocks:
        cid = b.get("canonical_id")
        if cid:
            return cid.strip()
    # Fallback: a bare "canonical_id: X" line outside any block.
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
