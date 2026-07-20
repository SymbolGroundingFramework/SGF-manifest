#!/usr/bin/env python3
"""
llm_kv_parser.py -- tolerant key-value parser for LLM outputs

TWO-LAYER PARSING CONTRACT
--------------------------
LLM responses to lexicon-pipeline prompts come in TWO LAYERS:

  Layer 1 (envelope):  the LLM wraps its structured answer in
                       <answer>...</answer> tags. Anything outside
                       those tags is conversational noise (preamble,
                       commentary, apologies, "I hope this helps!")
                       and is discarded by extract_answer().

  Layer 2 (content):   inside the <answer> envelope, the LLM emits
                       one or more BLOCKS. Each block begins with a
                       marker line (an all-caps identifier like
                       RELATION_1) and contains "key: value" pairs.
                       parse_kv_blocks() returns these as dicts.

WHY TWO LAYERS
--------------
LLMs are conversational by nature. They want to wrap structured
output in prose ("Here are the relations I found: ... I hope this
helps!"). A strict inline format gets contaminated by that prose.

Tags survive contamination because they are recognized boundaries,
not strict syntax. The model can chatter freely before, after, or
even beside the answer; we just slice between the tags and parse
what is inside.

WHY NOT JSON
------------
Over thousands of calls, an LLM will sometimes produce trailing
commas, missing braces, smart quotes, escaped newlines that break
json.loads, or partially-truncated output. Any one turns a "10 good
relations" response into ZERO parseable relations. The KV format
degrades gracefully: a single bad block loses one relation; the rest
are recovered.

EXAMPLE LLM RESPONSE
--------------------

  Sure, here are the relations I extracted.

  <answer>
  RELATION_1
  relation_type: IS_A
  target_lemma: cancer
  target_pos: noun
  target_description: a disease in which body cells divide uncontrollably
  confidence: 0.95
  rationale: leukemia is a subtype of cancer

  RELATION_2
  relation_type: HAS_LOCATION
  target_lemma: bone marrow
  target_pos: noun
  target_description: the soft tissue inside bones where blood cells form
  confidence: 0.85
  rationale: leukemia originates in bone marrow
  </answer>

  <comments>I am not certain about HAS_LOCATION but it seems likely.</comments>

The envelope extractor returns only the lines inside <answer>...</answer>.
The block parser then sees clean input.

NO REGEX. NO JSON. NO CLASSES.
"""

from __future__ import annotations


ANSWER_OPEN = "<answer>"
ANSWER_CLOSE = "</answer>"


def extract_answer(text):
    """Layer 1: pull the <answer>...</answer> envelope out of an LLM
    response. Returns the content between the tags as a stripped
    string. Returns None if the envelope is missing or malformed.

    NO REGEX. Just string find/slice.

    The lexicon's LLM prompts instruct the model to:
        Wrap your structured answer inside <answer>...</answer> tags.
        Put any commentary, reasoning, or asides inside <comments>...</comments>.
    This function honors the first half of that contract.
    """
    if not text:
        return None
    open_pos = text.find(ANSWER_OPEN)
    if open_pos < 0:
        return None
    start = open_pos + len(ANSWER_OPEN)
    close_pos = text.find(ANSWER_CLOSE, start)
    if close_pos < 0:
        return None
    return text[start:close_pos].strip() or None


def parse_llm_response(text):
    """The full two-layer parse: extract the answer envelope, then
    parse the KV blocks inside it. Returns a list of dicts (possibly
    empty) and never raises.

    Use this when you want the complete parse in one call.
    """
    inner = extract_answer(text)
    if inner is None:
        return []
    return parse_kv_blocks(inner)


def parse_kv_blocks(text):
    """Parse a key-value block-formatted LLM response.

    Arguments:
        text : the raw LLM response string

    Returns: list of dicts, one per block. Each dict has the lowercased
    keys parsed from that block. The block's marker (e.g. "RELATION_1")
    is stored under the "_marker" key.

    The parser operates in TWO MODES:

      - If the input contains at least one marker line (e.g. RELATION_1),
        it ignores everything before the first marker (preamble prose),
        and only treats blocks that start with a marker as real blocks.
        Any content that appears between blocks without a marker is
        ignored. This is the robust mode for noisy LLM responses.

      - If the input has NO marker lines anywhere, the entire input is
        treated as one implicit block (so callers that only need one
        block can omit the marker entirely).
    """
    if not text:
        return []

    lines = text.splitlines()

    # Detect mode by scanning for any marker line.
    has_any_marker = any(
        ":" not in ln.strip() and _looks_like_marker(ln.strip())
        for ln in lines
    )

    out = []
    current = None
    current_marker = None
    current_last_key = None

    for raw_line in lines:
        line = raw_line.strip()
        is_marker = (":" not in line and _looks_like_marker(line))

        if is_marker:
            # Close previous block
            if current is not None:
                out.append(_finalize_block(current, current_marker))
            current = {}
            current_marker = line
            current_last_key = None
            continue

        if not line:
            # Blank line ends the current block.
            if current is not None:
                out.append(_finalize_block(current, current_marker))
                current = None
                current_marker = None
                current_last_key = None
            continue

        # Non-marker, non-blank content.
        # In marker mode: ignore content that isn't inside a block.
        if has_any_marker and current is None:
            continue

        # In no-marker mode: start an implicit block on first content.
        if current is None:
            current = {}
            current_marker = "BLOCK"

        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip()
            if key:
                current[key] = value
                current_last_key = key
        else:
            # Continuation of the most recent value
            if current_last_key is not None:
                current[current_last_key] = (
                    current[current_last_key] + " " + line
                ).strip()

    if current is not None:
        out.append(_finalize_block(current, current_marker))

    # Drop empty blocks (only contain _marker)
    out = [b for b in out if len([k for k in b if k != "_marker"]) > 0]
    return out


def _finalize_block(block, marker):
    """Attach the marker label and return the block."""
    block["_marker"] = marker or "BLOCK"
    return block


def _looks_like_marker(s):
    """True if s looks like an ALL-CAPS identifier line (a block marker).

    Examples that return True:  RELATION, RELATION_1, ENTRY-3, ITEM2,
                                STANDARD_FORM, RESULT
    Examples that return False: "the cat sat", "relation_type", "X",
                                "cancer (disease)", "1. First item"
    """
    if not s or len(s) < 2:
        return False
    # Must start with an uppercase letter
    if not s[0].isalpha() or not s[0].isupper():
        return False
    # Must contain only uppercase letters, digits, underscores, hyphens
    for ch in s:
        if ch.isupper() and ch.isalpha():
            continue
        if ch.isdigit():
            continue
        if ch in "_-":
            continue
        return False
    return True


# ---------------------------------------------------------------------------
# Type coercion helpers
# ---------------------------------------------------------------------------

def as_float(value, default=None):
    """Best-effort float conversion. Returns default if not parseable."""
    if value is None:
        return default
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return default


def as_int(value, default=None):
    """Best-effort int conversion."""
    if value is None:
        return default
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return default


def as_bool(value, default=False):
    """Tolerant bool conversion. Accepts true/yes/1/y/on (case-insensitive)."""
    if value is None:
        return default
    s = str(value).strip().lower()
    if s in ("true", "yes", "1", "y", "on", "t"):
        return True
    if s in ("false", "no", "0", "n", "off", "f"):
        return False
    return default


def as_list(value, sep=","):
    """Split a value into a list by separator. Strips each element."""
    if value is None:
        return []
    return [s.strip() for s in str(value).split(sep) if s.strip()]


# ---------------------------------------------------------------------------
# Self-test (run this file directly to verify)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Well-formed input
    sample_ok = """
RELATION_1
relation_type: IS_A
target_lemma: cancer
target_pos: noun
target_microgloss_hint: a disease characterized by abnormal cell proliferation
confidence: 0.95
rationale: leukemia is a subtype of cancer

RELATION_2
relation_type: HAS_LOCATION
target_lemma: bone marrow
confidence: 0.85
rationale: leukemia originates in bone marrow
"""
    blocks = parse_kv_blocks(sample_ok)
    assert len(blocks) == 2, f"expected 2, got {len(blocks)}"
    assert blocks[0]["relation_type"] == "IS_A"
    assert blocks[0]["target_lemma"] == "cancer"
    assert as_float(blocks[0]["confidence"]) == 0.95
    assert blocks[1]["target_lemma"] == "bone marrow"
    print("OK: well-formed parse works.")

    # Malformed: one block missing fields, another with prose preamble,
    # smart quotes, trailing junk, multi-line rationale
    sample_messy = """
Here are the relations I found:

RELATION_1
relation_type: IS_A
target_lemma: cancer
target_microgloss_hint: a disease where cells divide uncontrollably
and can spread to other parts of the body
confidence: 0.9
rationale: textbook definition

RELATION_2
this line has no colon and no marker
relation_type: HAS_PART
target_lemma:
target_microgloss_hint: white blood cells produced in marrow
confidence: not_a_number

I hope this helps!
"""
    blocks = parse_kv_blocks(sample_messy)
    # We expect 2 blocks (the prose preamble is ignored; the "I hope" is
    # not a marker so it gets appended as a continuation of the last
    # value of the last block before the blank line closes block 2).
    print(f"Messy parse produced {len(blocks)} blocks:")
    for b in blocks:
        print(f"  {b}")
    assert len(blocks) == 2, f"expected 2, got {len(blocks)}"
    # First block has multi-line microgloss_hint joined cleanly
    mh = blocks[0]["target_microgloss_hint"]
    assert "cells divide uncontrollably and can spread" in mh, mh
    # Second block: bad confidence falls back to None
    assert as_float(blocks[1].get("confidence")) is None
    # target_lemma was empty after the colon
    assert blocks[1].get("target_lemma", "") == ""
    print("OK: messy parse degrades gracefully.")

    # Empty / null inputs
    assert parse_kv_blocks("") == []
    assert parse_kv_blocks(None) == []
    print("OK: empty/None inputs return [].")

    # No markers at all (just kv pairs) -- should form one implicit block
    sample_implicit = """
relation_type: IS_A
target_lemma: cancer
"""
    blocks = parse_kv_blocks(sample_implicit)
    assert len(blocks) == 1
    assert blocks[0]["relation_type"] == "IS_A"
    assert blocks[0]["_marker"] == "BLOCK"
    print("OK: marker-less input becomes one implicit block.")

    # --- ENVELOPE TESTS ---

    sample_with_envelope = """
Sure thing. Here are the relations I extracted.

<answer>
RELATION_1
relation_type: IS_A
target_lemma: cancer
target_pos: noun
target_description: a disease in which body cells divide uncontrollably
confidence: 0.95
rationale: leukemia is a kind of cancer

RELATION_2
relation_type: HAS_LOCATION
target_lemma: bone marrow
target_pos: noun
target_description: the soft tissue inside bones where blood cells form
confidence: 0.85
</answer>

<comments>
I am not entirely sure about the HAS_LOCATION confidence; it could be lower.
</comments>

I hope this helps!
"""
    inner = extract_answer(sample_with_envelope)
    assert inner is not None, "envelope extraction returned None"
    assert "RELATION_1" in inner
    assert "I hope this helps" not in inner
    assert "<comments>" not in inner
    print("OK: envelope extraction strips prose and comments.")

    blocks = parse_llm_response(sample_with_envelope)
    assert len(blocks) == 2
    assert blocks[0]["target_lemma"] == "cancer"
    assert blocks[1]["relation_type"] == "HAS_LOCATION"
    print("OK: parse_llm_response (envelope + KV) round-trip works.")

    # Missing envelope returns []
    assert parse_llm_response("no tags here at all") == []
    assert parse_llm_response("") == []
    assert parse_llm_response(None) == []
    print("OK: missing envelope returns empty list.")

    # Mismatched envelope (open but no close): returns []
    assert parse_llm_response("<answer>\nRELATION_1\nrelation_type: IS_A\n") == []
    print("OK: open tag without close returns empty list.")

    print()
    print("ALL TESTS PASS")
