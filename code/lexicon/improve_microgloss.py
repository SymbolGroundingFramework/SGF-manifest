#!/usr/bin/env python3
"""
improve_microgloss.py -- Stage 6 -- LLM improver

Stage 6 of the SGF lexicon pipeline. For senses in scope, calls an LLM
to refine the microgloss, refine the definition, populate richer
metadata, classify cousins, declare content-identical pairs (with
audience_tier), and (for proper nouns) populate biographical metadata.

Notes:
  - canonical_id format is en.<lemma>.<microgloss>.<pos>.<namespace>
    (namespace replaces register as 5th field)
  - Output schema adds 'content_identical_with' list with audience_tier
  - System-prompt framing emphasizes lexicographic-research role to
    suppress reflexive refusals on documented vocabulary
  - On parse failure, retry-with-acknowledgment is supported by the
    wrapper contract

SCOPE
-----
A sense is in scope if ANY of:
  (a) lemma_frequency_rank <= --top-lemmas (default 10000)
  (b) the lemma has multiple senses AND rank <= --polysemy-cutoff (default 100000)
  (c) pos_simple == 'name' AND rank <= --propnoun-cutoff (default 50000)
  (d) sparse_data_flag == 1 AND rank <= --sparse-cutoff (default 50000)

WHAT IT WRITES
--------------
sense_enrichment row with enrichment_version='v4' containing:
  improved_microgloss, improved_definition,
  register, temporal_status, social_status,
  social_notes, domain, biographical_metadata_json, rationale

sense_relation rows for each cousin classification

Also propagates improved values to sgf_lexicon:
  microgloss, canonical_id (rebuilt from improved values),
  register, temporal_status, social_status
And sets embedding_text_needs_rebuild = 1 so Stage 7 picks it up.

LLM WRAPPER CONTRACT
--------------------
The --llm-wrapper script must accept:
    --in-file <path>     a file containing the full prompt
    --out-file <path>    a file the wrapper writes the LLM response to

The wrapper script is invoked as a subprocess for each sense.
Optional standard flags: --tier, --temp, --policy, --system-file.

USAGE
-----
    python improve_microgloss.py --target sgf_lexicon.db \
        --llm-wrapper /path/to/llm_wrapper.py \
        --top-lemmas 10000 \
        --workers 8

    python improve_microgloss.py --target sgf_lexicon.db --dry-run
    python improve_microgloss.py --target sgf_lexicon.db --self-test-prompt

STATUS
------
Skeleton implementation. Prompt template, validation, output parsing,
and parallel-worker contract are all complete. LLM wrapper invocation
follows the established enrich_lexicon.py pattern but has NOT been
end-to-end tested with a real LLM wrapper in this delivery. Test on
your own wrapper before running at scale.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lexicon_metadata import (  # noqa: E402
    VALID_REGISTERS, VALID_TEMPORAL, VALID_SOCIAL, VALID_COUSIN_RELATIONS,
    REGISTER_DEFAULT, TEMPORAL_DEFAULT, SOCIAL_DEFAULT,
)
from microgloss import _norm, _norm_for_id  # noqa: E402

IMPROVER_VERSION = "v4"  # enrichment_version key (unchanged from v2)
IMPROVER_METHOD = "improver_v4_2026_06"
PROMPT_VERSION = "v3_2026_06"  # for audit trail in rationale


# ===========================================================================
# THE PROMPT
# ===========================================================================

SYSTEM_FRAMING = """\
You are a lexicographer working on a research-grade multilingual
lexicon. Your role is identical to an editor at the OED or
Merriam-Webster: you DESCRIBE how words are used, including informal,
slang, vulgar, flagged, offensive, dated, and archaic usage. This is
descriptive lexicography, not endorsement. Retrieval policy decides
what to surface; your job is to catalog honestly so that downstream
policy has accurate data to act on.

THE FOUR JOBS OF A MICROGLOSS
-----------------------------
Each microgloss simultaneously serves four purposes:

  1. Disambiguate this sense from OTHER SENSES OF THE SAME LEMMA
     (intra-language grounding case: the query knows the lemma, the
     search filters to lemma-mates, the microgloss is what picks
     among them).

  2. Disambiguate this sense from CLOSE COUSINS in embedding space
     (cross-language case: the query is a foreign-language token with
     no lemma overlap; the microgloss content alone has to land on
     the right meaning region).

  3. Read naturally to a human scanning the canonical_id.

  4. Give an LLM enough content for rerank without reading the full
     definition.

Length is a CONSEQUENCE of disambiguation need, not a target. Two
tokens are right when two tokens suffice; six tokens are right when
six are needed.

THE FOUR METADATA AXES (all required)
-------------------------------------
You must tag every sense on four controlled-vocabulary axes:

  register (9 values):
    formal, neutral, informal, slang, vulgar,
    affectionate, poetic, clinical, archaic

  temporal_status (5 values):
    live, dated, archaic, obsolete, revived

  social_status (6 values):
    unmarked, informal_only, dated, flagged, offensive, slur

  specificity (3 values):
    general    -- everyday vocabulary used by ordinary speakers
    specialist -- domain vocabulary (medicine, law, science,
                  finance, engineering) that makes a precision
                  distinction the general term elides; examples:
                  leukemia, negligence, derivative (financial)
    technical  -- subspecialty vocabulary within a specialist
                  field; examples: acute_lymphoblastic_leukemia,
                  credit_default_swap

Specialist and technical senses are NEVER snapped to general terms at
retrieval time. \"leukemia\" stays \"leukemia\", not \"cancer\". Tag
specificity honestly.

CONTRAST SETS YOU WILL BE SHOWN
-------------------------------
With each sense, you will see:

  LEMMA-MATES -- other senses of the same lemma. Your microgloss must
                 distinguish from these.

  COUSINS     -- close embedding-space neighbors (different lemmas,
                 similar meaning). Your microgloss must distinguish
                 from these too, because cross-language retrieval has
                 no lemma to filter on.

Use them. A microgloss for \"bank (river edge)\" that ignores both
\"shore\" and \"riverside\" cousins is doing only half its job. A
microgloss for \"jubilant\" that fails to encode an intensity-distinct
content marker from \"happy\" and \"glad\" is similarly weak.

WRAP YOUR ANSWER IN TAGS
------------------------
Put the structured reply inside <answer>...</answer>. Put any thinking,
caveats, or commentary inside <comments>...</comments>. The parser only
reads what is inside <answer>. NO JSON. NO CODE FENCES.

THE ANSWER BLOCK FORMAT
-----------------------
<answer>
IMPROVEMENT
improved_microgloss: <2-7 lowercase tokens joined by underscores; must NOT contain the lemma itself>
improved_definition: <a natural-language sentence or two, content-only>
register: <one of the 9 register values above>
temporal_status: <one of the 5 temporal_status values above>
social_status: <one of the 6 social_status values above>
specificity: <one of the 3 specificity values above>
social_notes: <optional 1-line note on social marking>
domain: <one-word domain tag like 'medicine', 'finance', 'general'>
rationale: <one sentence on why this microgloss is sharp>
</answer>

<comments>
optional reasoning, caveats, anything you want to think aloud about
</comments>

If you want to suggest cousin classifications or content-identical
declarations as supplemental blocks, add additional blocks AFTER the
IMPROVEMENT block, separated by blank lines:

  COUSIN_1
  lemma: <cousin lemma>
  relation_type: <TRUE_SYNONYM | SHADED_SYNONYM | COHYPONYM | HYPONYM | HYPERNYM | PART_OF | AGENT_OF | LOCATION_OF | EMBEDDER_NOISE | UNCLEAR>
  interchangeable_intra_language: <true | false>
  interchangeable_cross_language_standard: <true | false>
  interchangeable_cross_language_preserve: <true | false>
  note: <optional>

  CONTENT_IDENTICAL_1
  lemma: <other lemma that is content-identical at general tier>
  audience_tier: general
  confidence: <0.0 to 1.0>

These are optional. Omit them when not applicable.
"""

WORKED_EXAMPLE = """\
======= WORKED EXAMPLE =======

INPUT:
  LEMMA: dad
  POS: noun
  GLOSS: One's father.
  WIKTIONARY TAGS: [informal]
  PROVISIONAL MICROGLOSS: ones_father
  LEMMA-MATES: (none -- \"dad\" has only this sense as a noun)
  COUSINS:
    - father (en.father.male_parent.noun.core) cos=0.91 register=neutral
    - papa (en.papa.male_parent.noun.core) cos=0.88 register=affectionate
    - daddy (en.daddy.male_parent.noun.core) cos=0.86 register=affectionate
    - pater (en.pater.male_parent.noun.core) cos=0.79 register=archaic

EXAMPLE OUTPUT:

<comments>
This is informal but not slang; standard term in everyday speech.
Sharing meaning with father, papa, daddy, pater -- the microgloss
must encode the content (male parent) cleanly so the register field
carries the marking.
</comments>

<answer>
IMPROVEMENT
improved_microgloss: male_parent
improved_definition: A human male parent; the everyday informal-register term used in most American and British English.
register: informal
temporal_status: live
social_status: unmarked
specificity: general
domain: general
rationale: Content-only microgloss matches the cousin cluster's shared meaning; register field carries the informal marking.
</answer>
"""


def build_prompt(sense_context: dict) -> str:
    """Compose the improvement prompt for one sense.

    sense_context must contain at minimum:
        lemma, pos_simple, gloss, provisional_microgloss, namespace,
        register, temporal_status, social_status,
        lemma_mates  -- list of dicts (sid, microgloss, gloss)
        cousins      -- list of dicts (sid, lemma, canonical_id, register, gloss[, cosine])
        tags         -- list of Wiktionary tag strings
    """
    parts = [SYSTEM_FRAMING, "", WORKED_EXAMPLE, "",
             "======= NOW PROCESS THIS SENSE =======", ""]

    parts.append(f"LEMMA: {sense_context['lemma']}")
    parts.append(f"POS: {sense_context['pos_simple']}")
    parts.append(f"GLOSS: {sense_context['gloss']}")
    parts.append(f"WIKTIONARY TAGS: {sense_context.get('tags', [])}")
    parts.append(f"PROVISIONAL MICROGLOSS: {sense_context.get('provisional_microgloss', '')}")
    parts.append(f"PROVISIONAL CANONICAL_ID: {sense_context.get('canonical_id', '')}")
    parts.append(f"HARVESTED REGISTER: {sense_context.get('register', 'neutral')}")
    parts.append(f"HARVESTED TEMPORAL_STATUS: {sense_context.get('temporal_status', 'live')}")
    parts.append(f"HARVESTED SOCIAL_STATUS: {sense_context.get('social_status', 'unmarked')}")

    lemma_mates = sense_context.get("lemma_mates", [])
    parts.append("")
    if lemma_mates:
        parts.append("LEMMA-MATES (you must disambiguate from these):")
        for lm in lemma_mates:
            parts.append(
                f"  - sense_id={lm.get('sid')}: "
                f"microgloss={lm.get('microgloss', '')!r}, "
                f"gloss={(lm.get('gloss') or '')[:120]!r}"
            )
    else:
        parts.append("LEMMA-MATES: (none; this is the only sense for this lemma+pos)")

    cousins = sense_context.get("cousins", [])
    parts.append("")
    if cousins:
        parts.append("COUSINS (embedding-space neighbors with different lemmas; your microgloss must disambiguate from these for cross-language retrieval):")
        for c in cousins:
            cos = c.get("cosine")
            cos_str = f"cos={cos:.2f} " if cos is not None else ""
            parts.append(
                f"  - sense_id={c.get('sid')}: lemma={c.get('lemma','')!r}, "
                f"canonical_id={c.get('canonical_id','')!r}, "
                f"{cos_str}register={c.get('register','neutral')}, "
                f"gloss={(c.get('gloss') or '')[:120]!r}"
            )
    else:
        parts.append("COUSINS: (no embedding-space neighbors at the configured cosine threshold)")

    # If this is a revisit, show what we already wrote
    prior = sense_context.get("prior_improvement")
    if prior:
        parts.append("")
        parts.append("PRIOR IMPROVEMENT (this sense was improved before -- propose refinements only if you can do strictly better):")
        for k in ("improved_microgloss", "improved_definition", "register",
                  "temporal_status", "social_status", "specificity"):
            v = prior.get(k)
            if v:
                parts.append(f"  {k}: {v}")

    # If this came from an audit failure, surface the verdict
    audit = sense_context.get("audit_collision")
    if audit:
        parts.append("")
        parts.append(f"AUDIT FAILURE -- self-retrieval collided with: {audit}")
        parts.append("Make the microgloss sharp enough to win against that competitor at top-1.")

    parts.append("")
    parts.append("Emit your reply now. Wrap the IMPROVEMENT block in <answer>...</answer>.")
    return "\n".join(parts)


# ===========================================================================
# Response parsing (envelope + KV blocks; NO JSON, NO REGEX)
# ===========================================================================

import llm_kv_parser as kv  # noqa: E402

def parse_llm_response(raw):
    """Parse the LLM response (envelope + KV blocks). Returns dict or None.

    The dict has the IMPROVEMENT block keys flattened, plus
    'cousin_classifications' and 'content_identical_with' built from
    any COUSIN_* or CONTENT_IDENTICAL_* blocks the LLM included.
    """
    if not raw or not raw.strip():
        return None
    blocks = kv.parse_llm_response(raw)
    if not blocks:
        return None

    out = {}
    cousins = []
    content_identical = []
    for b in blocks:
        marker = (b.get("_marker") or "").upper()
        if marker.startswith("IMPROVEMENT") or "improved_microgloss" in b:
            # Flatten IMPROVEMENT block fields into out
            for k, v in b.items():
                if k == "_marker":
                    continue
                out[k] = v
        elif marker.startswith("COUSIN"):
            cousins.append({
                "lemma": b.get("lemma"),
                "relation_type": (b.get("relation_type") or "").upper(),
                "interchangeable_intra_language":
                    kv.as_bool(b.get("interchangeable_intra_language"), False),
                "interchangeable_cross_language_standard":
                    kv.as_bool(b.get("interchangeable_cross_language_standard"), False),
                "interchangeable_cross_language_preserve":
                    kv.as_bool(b.get("interchangeable_cross_language_preserve"), False),
                "note": (b.get("note") or "").strip(),
            })
        elif marker.startswith("CONTENT_IDENTICAL"):
            content_identical.append({
                "lemma": b.get("lemma"),
                "audience_tier": (b.get("audience_tier") or "general").strip(),
                "confidence": kv.as_float(b.get("confidence"), 0.9),
            })

    if not out:
        return None  # No IMPROVEMENT block found

    if cousins:
        out["cousin_classifications"] = cousins
    if content_identical:
        out["content_identical_with"] = content_identical
    return out



def validate_response(resp: dict, lemma_mate_microglosses: set, lemma: str,
                      pos_simple: str) -> tuple[bool, str]:
    """Validate the LLM response against the rules in the spec.

    Returns (ok, error_message). ok=True if valid.
    """
    if not isinstance(resp, dict):
        return False, "response is not a dict (envelope+KV parse failed)"

    # V1: improved_microgloss
    mg = resp.get("improved_microgloss")
    if not mg or not isinstance(mg, str):
        return False, "missing or non-string improved_microgloss"
    if not re.fullmatch(r"[a-z][a-z0-9_]+", mg):
        return False, f"improved_microgloss {mg!r} contains invalid characters"
    tokens = mg.split("_")
    if not (2 <= len(tokens) <= 7):
        return False, f"improved_microgloss has {len(tokens)} tokens; must be 2-7"

    # V2: lemma-mate uniqueness
    if mg in lemma_mate_microglosses:
        return False, f"improved_microgloss {mg!r} collides with a lemma-mate"

    # V3: doesn't contain the lemma itself
    lemma_norm = _norm(lemma).replace(" ", "_")
    if lemma_norm and lemma_norm in tokens:
        return False, f"improved_microgloss {mg!r} contains the lemma {lemma_norm!r}"

    # V4, V5, V6, V7: controlled vocabularies (registers/temporal/social/specificity)
    from lexicon_metadata import VALID_SPECIFICITY  # local import to avoid circular noise
    reg = (resp.get("register") or "").strip()
    if reg not in VALID_REGISTERS:
        return False, f"register {reg!r} not in controlled vocabulary"

    temp = (resp.get("temporal_status") or "").strip()
    if temp not in VALID_TEMPORAL:
        return False, f"temporal_status {temp!r} not in controlled vocabulary"

    soc = (resp.get("social_status") or "").strip()
    if soc not in VALID_SOCIAL:
        return False, f"social_status {soc!r} not in controlled vocabulary"

    spec = (resp.get("specificity") or "").strip()
    if spec and spec not in VALID_SPECIFICITY:
        return False, f"specificity {spec!r} not in controlled vocabulary"

    # V7: cousin relation types
    cousins = resp.get("cousin_classifications", [])
    if not isinstance(cousins, list):
        return False, "cousin_classifications must be a list"
    for i, c in enumerate(cousins):
        if not isinstance(c, dict):
            return False, f"cousin_classifications[{i}] is not a dict"
        rt = c.get("relation_type")
        if rt not in VALID_COUSIN_RELATIONS:
            return False, f"cousin_classifications[{i}].relation_type {rt!r} invalid"

    # V8: proper nouns get biographical_metadata
    if pos_simple == "name":
        bm = resp.get("biographical_metadata")
        if bm is None:
            return False, "biographical_metadata required for proper-noun sense"

    # V9: rationale present
    if not resp.get("rationale"):
        return False, "rationale is empty"

    # V9.5 : specificity is optional but if present must be valid.
    spec = resp.get("specificity")
    if spec is not None and spec not in ("general", "specialist", "technical"):
        return False, f"specificity {spec!r} not in {{general, specialist, technical}}"

    # V10 : content_identical_with, if present, must be a well-formed list.
    # It is OPTIONAL: a sense may have no content-identical relatives.
    ci = resp.get("content_identical_with")
    if ci is not None:
        if not isinstance(ci, list):
            return False, "content_identical_with must be a list (or omitted)"
        for i, entry in enumerate(ci):
            if not isinstance(entry, dict):
                return False, f"content_identical_with[{i}] is not a dict"
            if not entry.get("lemma"):
                return False, f"content_identical_with[{i}] missing lemma"
            tier = entry.get("audience_tier", "general")
            if not isinstance(tier, str):
                return False, f"content_identical_with[{i}].audience_tier must be a string"
            # accept any string that starts with 'general' or 'expert_'
            if not (tier == "general" or tier.startswith("expert_")):
                return False, (
                    f"content_identical_with[{i}].audience_tier {tier!r} must be "
                    "'general' or 'expert_<domain>'"
                )
            conf = entry.get("confidence")
            if conf is not None:
                try:
                    cf = float(conf)
                    if not (0.0 <= cf <= 1.0):
                        return False, (
                            f"content_identical_with[{i}].confidence {cf} out of [0,1]"
                        )
                except (TypeError, ValueError):
                    return False, (
                        f"content_identical_with[{i}].confidence not a number"
                    )

    return True, ""


# ===========================================================================
# LLM wrapper invocation
# ===========================================================================

def call_llm(llm_wrapper, prompt: str, tier: str = "flash", temp: float = 0.0,
             timeout_seconds: int = 120) -> str | None:
    """Invoke the user's LLM wrapper script. Returns the raw response text
    or None on failure.

    Wrapper contract:
        <llm_wrapper> --in-file <prompt> --out-file <response>
                      [--tier <tier>] [--temp <temp>]
    """
    tmp = Path(tempfile.gettempdir())
    tag = f"{os.getpid()}_{secrets.token_hex(4)}"
    in_file = tmp / f"improver_in_{tag}.txt"
    out_file = tmp / f"improver_out_{tag}.txt"
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
            stderr_snippet = (result.stderr or "").strip()[:300]
            if stderr_snippet and not hasattr(call_llm, "_printed_stderr"):
                print(f"  LLM wrapper stderr: {stderr_snippet}", flush=True)
                call_llm._printed_stderr = True
            return None
        if not out_file.exists():
            return None
        return out_file.read_text(encoding="utf-8")
    except (subprocess.TimeoutExpired, OSError, UnicodeDecodeError) as exc:
        if not hasattr(call_llm, "_printed_exc"):
            print(f"  LLM wrapper invocation error: {type(exc).__name__}: {exc}",
                  flush=True)
            call_llm._printed_exc = True
        return None
    finally:
        try:
            in_file.unlink(missing_ok=True)
            out_file.unlink(missing_ok=True)
        except OSError:
            pass


# ===========================================================================
# Scope selection
# ===========================================================================

def select_scope(conn, top_lemmas, polysemy_cutoff, propnoun_cutoff, sparse_cutoff):
    """Return list of wsids whose lemma is in the top-N most-frequent lemmas.

    --top-lemmas is the dominant frontier control. A sense is in scope iff
    its lemma's frequency_rank is <= top_lemmas. The other cutoffs
    (polysemy/propnoun/sparse) are kept as parameters for backward
    compatibility but no longer expand the scope beyond top_lemmas; they
    can only narrow it within that ceiling. This makes --top-lemmas mean
    exactly what its name says.
    """
    cur = conn.execute("""
        SELECT DISTINCT sl.wiktionary_source_id
        FROM sgf_lexicon sl
        JOIN lemma_frequency lf ON lf.lemma = LOWER(sl.lemma)
        WHERE lf.frequency_rank <= ?
        ORDER BY lf.frequency_rank ASC
    """, (top_lemmas,))
    return [row[0] for row in cur.fetchall()]


# ===========================================================================
# Main (skeleton -- pending end-to-end testing with real wrapper)
# ===========================================================================

def self_test_prompt():
    """Print a sample prompt for the 'dame' sense so you can eyeball it."""
    sense_context = {
        "lemma": "dame",
        "pos_simple": "noun",
        "gloss": "A woman.",
        "tags": ["dated", "slang"],
        "provisional_microgloss": "a_woman",
        "canonical_id": "en.dame.a_woman.noun.core",
        "register": "slang",
        "temporal_status": "dated",
        "social_status": "flagged",
        "lemma_mates": [
            {"sid": 99, "microgloss": "woman_of_rank",
             "gloss": "A woman of rank or honor (British title)."},
        ],
        "cousins": [
            {"sid": 1001, "lemma": "woman", "canonical_id": "en.woman.adult_female_human.noun.core",
             "register": "neutral", "gloss": "An adult female human."},
            {"sid": 1002, "lemma": "gal", "canonical_id": "en.gal.adult_female_human.noun.core",
             "register": "slang", "gloss": "An attractive young woman."},
            {"sid": 1003, "lemma": "lass", "canonical_id": "en.lass.young_woman.noun.core",
             "register": "poetic", "gloss": "A young woman."},
        ],
    }
    prompt = build_prompt(sense_context)
    print(prompt)
    print()
    print("=" * 60)
    print(f"Prompt length: {len(prompt)} chars (~{len(prompt)//4} tokens)")
    print("=" * 60)
    return 0


def _get_audit_failed_wsids(conn, embedding_method, audit_phase):
    """Pull wsids that failed the most recent quality_audit run for the
    given embedder and phase. Matches repair_audit_failures.get_failed_wsids
    so the two paths agree on what counts as a failure.
    """
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(quality_audit)")
    cols = {row[1] for row in cur.fetchall()}
    if "intralemma_pass" not in cols:
        print("ERROR: quality_audit.intralemma_pass column missing. "
              "Run quality_audit.py first.", file=sys.stderr)
        return []
    cur.execute(
        """
        SELECT wsid FROM quality_audit
         WHERE intralemma_pass = 0
           AND audit_phase = ?
           AND embedding_method = ?
           AND audit_run_id = (
               SELECT audit_run_id FROM quality_audit
                WHERE audit_phase = ? AND embedding_method = ?
                ORDER BY audited_at DESC LIMIT 1
           )
        """,
        (audit_phase, embedding_method, audit_phase, embedding_method),
    )
    return [row[0] for row in cur.fetchall()]


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    p.add_argument("--target", default="sgf_lexicon.db")
    p.add_argument("--llm-wrapper", help="Path to your LLM wrapper script")
    p.add_argument("--top-lemmas", type=int, default=10000)
    p.add_argument("--polysemy-cutoff", type=int, default=100000)
    p.add_argument("--propnoun-cutoff", type=int, default=50000)
    p.add_argument("--sparse-cutoff", type=int, default=50000)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--tier", default="flash")
    p.add_argument("--temp", type=float, default=0.0)
    p.add_argument("--dry-run", action="store_true",
                   help="Show scope and a sample prompt, don't call LLM")
    p.add_argument("--self-test-prompt", action="store_true",
                   help="Print a sample prompt for 'dame' and exit")
    p.add_argument("--limit", type=int, default=None,
                   help="Process at most N senses (for testing)")
    p.add_argument("--revisit", action="store_true",
                   help="Re-improve senses already at the 'improved' tier; "
                        "the LLM is shown its prior output and asked to refine")
    p.add_argument("--embedding-method", default="bge-small-en-v1",
                   help="Which embedder to use for cousin discovery "
                        "(default: bge-small-en-v1)")
    p.add_argument("--k-cousins", type=int, default=5,
                   help="Max cousins to show the LLM (default: 5)")
    p.add_argument("--cousin-min-cosine", type=float, default=0.70,
                   help="Cousin minimum cosine threshold (default: 0.70)")
    p.add_argument("--wsids", default=None,
                   help="Comma-separated wsids to improve. Overrides all "
                        "scope filters. Used by repair_audit_failures.py "
                        "to target specific audit-failed senses.")
    p.add_argument("--target-audit-failures", action="store_true",
                   help="Select only senses that failed the most recent "
                        "quality_audit run (intralemma_pass = 0). Pulls the "
                        "failed wsids from the quality_audit table and uses "
                        "them as the work scope. Overridden by --wsids and "
                        "--wsids-file if those are also passed.")
    p.add_argument("--audit-phase", default="production",
                   choices=["first_pass", "production", "rebuild"],
                   help="Which audit phase to source failures from when "
                        "--target-audit-failures is set. Default: production.")
    p.add_argument("--wsids-file", default=None,
                   help="Path to a file containing wsids, one per line. "
                        "Convenient for piping GLEAN-flagged miss lists. "
                        "Bypasses the OS command-line length limit.")
    args = p.parse_args()

    if args.self_test_prompt:
        return self_test_prompt()

    db_path = Path(args.target)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA busy_timeout = 60000")

    print(f"Target: {db_path.resolve()}")
    print(f"Scope criteria:")
    print(f"  top-lemmas:       <= {args.top_lemmas:,}")
    print(f"  polysemy-cutoff:  <= {args.polysemy_cutoff:,}")
    print(f"  propnoun-cutoff:  <= {args.propnoun_cutoff:,}")
    print(f"  sparse-cutoff:    <= {args.sparse_cutoff:,}")
    print()

    if args.wsids_file:
        wsids_path = Path(args.wsids_file)
        if not wsids_path.exists():
            print(f"--wsids-file not found: {wsids_path}", file=sys.stderr)
            return 1
        in_scope = [
            int(line.strip())
            for line in wsids_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        print(f"--wsids-file override: {len(in_scope)} senses from {wsids_path}")
    elif args.wsids:
        in_scope = [int(x) for x in args.wsids.split(",") if x.strip()]
        print(f"--wsids override: {len(in_scope)} senses")
    elif args.target_audit_failures:
        in_scope = _get_audit_failed_wsids(
            conn, args.embedding_method, args.audit_phase)
        if not in_scope:
            print("--target-audit-failures: no failed senses found in "
                  "the most recent quality_audit run.")
            print("Nothing to do. Run quality_audit.py first if you expected "
                  "failures.")
            return 0
        print(f"--target-audit-failures: {len(in_scope):,} senses failed "
              f"intralemma audit (phase={args.audit_phase}, "
              f"embedder={args.embedding_method})")
    else:
        in_scope = select_scope(conn, args.top_lemmas, args.polysemy_cutoff,
                            args.propnoun_cutoff, args.sparse_cutoff)
    print(f"Senses in scope: {len(in_scope):,}")

    if args.dry_run:
        print()
        print("DRY RUN. To actually run, omit --dry-run and provide --llm-wrapper.")
        print()
        print("Sample prompt for the first in-scope sense:")
        print("-" * 60)
        if in_scope:
            wsid = in_scope[0]
            row = conn.execute("""
                SELECT lemma, pos_simple, gloss, microgloss, canonical_id,
                       register, temporal_status, social_status
                FROM sgf_lexicon WHERE wiktionary_source_id = ?
            """, (wsid,)).fetchone()
            if row:
                ctx = {
                    "lemma": row[0], "pos_simple": row[1], "gloss": row[2],
                    "provisional_microgloss": row[3], "canonical_id": row[4],
                    "register": row[5], "temporal_status": row[6],
                    "social_status": row[7],
                    "tags": [], "lemma_mates": [], "cousins": [],
                }
                print(build_prompt(ctx)[:2000])
                print("[... truncated ...]")
        return 0

    if not args.llm_wrapper:
        print("ERROR: --llm-wrapper is required unless --dry-run", file=sys.stderr)
        return 1


    if args.limit is not None:
        in_scope = in_scope[: args.limit]
        print(f"Limited to first {len(in_scope):,} senses (--limit).")

    # Load the lexicon context for in-process contrast-set lookup.
    # This is the same lexicon_search module the production search
    # server uses; using it here ensures the contrast-aware improver
    # and the production retrieval see the same neighborhood.
    print()
    print("Loading lexicon for in-process contrast-set lookup ...")
    try:
        import lexicon_search
        lexicon_ctx = lexicon_search.load_lexicon(db_path, verbose=True)
    except Exception as e:
        print(f"  WARNING: could not load lexicon ({e}); cousins will fall "
              "back to sense_relation table", file=sys.stderr)
        lexicon_ctx = None

    print()
    print("Running improver pass ...")
    print(f"  revisit mode:         {args.revisit}")
    print(f"  embedding method:     {args.embedding_method}")
    print(f"  k cousins:            {args.k_cousins}")
    print(f"  cousin min cosine:    {args.cousin_min_cosine}")
    print()
    t0 = time.time()
    n_ok, n_fail, n_skip = 0, 0, 0
    for i, wsid in enumerate(in_scope, 1):
        ctx = load_sense_context(
            conn, wsid,
            lexicon_ctx=lexicon_ctx,
            embedding_method=args.embedding_method,
            k_cousins=args.k_cousins,
            cousin_min_cosine=args.cousin_min_cosine,
        )
        if ctx is None:
            n_skip += 1
            continue

        # In revisit mode, also pull the prior improvement so the LLM
        # can refine rather than start from scratch.
        if args.revisit:
            prior = conn.execute(
                """
                SELECT improved_microgloss, improved_definition,
                       register, temporal_status, social_status
                  FROM sense_enrichment
                 WHERE source_sense_id = ?
                 ORDER BY created_at DESC
                 LIMIT 1
                """,
                (wsid,),
            ).fetchone()
            if prior:
                ctx["prior_improvement"] = {
                    "improved_microgloss": prior[0],
                    "improved_definition": prior[1],
                    "register": prior[2],
                    "temporal_status": prior[3],
                    "social_status": prior[4],
                }

        # If this sense failed Stage 5.5 audit, surface the competitor
        # that beat it so the LLM can sharpen the microgloss against
        # that specific collision.
        try:
            qa = conn.execute(
                """
                SELECT top_k_canonical_ids_json
                  FROM quality_audit
                 WHERE wsid = ? AND strict_pass = 0
                 ORDER BY audited_at DESC
                 LIMIT 1
                """,
                (wsid,),
            ).fetchone()
            if qa and qa[0]:
                topk_list = json.loads(qa[0])
                # Surface the first non-self entry as the collision target.
                if topk_list and topk_list[0] != ctx.get("canonical_id"):
                    ctx["audit_collision"] = topk_list[0]
        except (sqlite3.OperationalError, json.JSONDecodeError, TypeError):
            pass
        prompt = build_prompt(ctx)
        raw = call_llm(args.llm_wrapper, prompt, tier=args.tier, temp=args.temp)
        if raw is None:
            n_fail += 1
            if n_fail <= 3:
                print(f"  LLM call failed wsid={wsid} lemma={ctx['lemma']!r} "
                      f"(returned None; check wrapper path and run "
                      f"`python llm_wrapper.py --self-test`)", flush=True)
            continue
        if not raw.strip():
            n_fail += 1
            if n_fail <= 3:
                print(f"  LLM returned empty text wsid={wsid} lemma={ctx['lemma']!r}",
                      flush=True)
            continue
        resp = parse_llm_response(raw)
        if resp is None:
            n_fail += 1
            if n_fail <= 3:
                snippet = raw[:200].replace("\n", " ")
                print(f"  parse fail wsid={wsid} lemma={ctx['lemma']!r}: {snippet!r}",
                      flush=True)
            continue
        ok, err = validate_response(
            resp, set(lm["microgloss"] for lm in ctx["lemma_mates"]),
            ctx["lemma"], ctx["pos_simple"],
        )
        if not ok:
            n_fail += 1
            if n_fail <= 5:
                print(f"  validation fail wsid={wsid} lemma={ctx['lemma']!r}: {err}")
            continue
        try:
            persist_improvement(conn, ctx, resp)
            n_ok += 1
        except sqlite3.Error as e:
            n_fail += 1
            print(f"  DB write fail wsid={wsid}: {e}", file=sys.stderr)
        # Stream progress: first 5 so the user sees immediate signal,
        # then every 25.
        if i <= 5 or i % 25 == 0:
            elapsed = time.time() - t0
            rate = i / max(elapsed, 0.001)
            remain = (len(in_scope) - i) / max(rate, 0.001)
            print(
                f"  [{i}/{len(in_scope)}] ok={n_ok} fail={n_fail} "
                f"skip={n_skip}  {rate:.1f}/s  eta={remain/60:.1f}m",
                flush=True,
            )

    print()
    print("=" * 60)
    print("IMPROVER PASS COMPLETE")
    print("=" * 60)
    print(f"  processed: {len(in_scope):,}")
    print(f"  ok      :  {n_ok:,}")
    print(f"  failed  :  {n_fail:,}")
    print(f"  skipped :  {n_skip:,}")
    print(f"  elapsed :  {(time.time() - t0)/60:.1f} min")
    return 0


# ===========================================================================
# DB helpers used by main
# ===========================================================================

def load_sense_context(conn, wsid, lexicon_ctx=None,
                       embedding_method=None, k_cousins=5,
                       cousin_min_cosine=0.70):
    """Load full sense context including lemma_mates and cousins.

    If lexicon_ctx is provided, cousins are pulled from embedding-space
    using lexicon_search.find_contrast_set() -- this is the contrast-
    aware path used by Phase 2A improvement. If lexicon_ctx is None,
    cousins fall back to the older sense_relation lookup (used by
    legacy callers).
    """
    row = conn.execute(
        """
        SELECT lemma, pos_simple, gloss, microgloss, canonical_id,
               register, temporal_status, social_status, namespace
          FROM sgf_lexicon
         WHERE wiktionary_source_id = ?
        """,
        (wsid,),
    ).fetchone()
    if not row:
        return None
    lemma, pos, gloss, mg, cid, reg, temp, soc, ns = row
    lemma_mates = []
    for r in conn.execute(
        """
        SELECT wiktionary_source_id, microgloss, gloss
          FROM sgf_lexicon
         WHERE lemma = ? AND pos_simple = ? AND wiktionary_source_id != ?
        """,
        (lemma, pos, wsid),
    ):
        lemma_mates.append(
            {"sid": r[0], "microgloss": r[1] or "", "gloss": r[2] or ""}
        )
    cousins = []
    # Preferred: pull cousins from embedding-space using the shared
    # lexicon_search module (the same one the production search server
    # uses). This works at the very first improver run because it
    # only needs the existing bge-small embeddings, not prior
    # improvement output.
    if lexicon_ctx is not None and embedding_method is not None:
        try:
            import lexicon_search
            contrast = lexicon_search.find_contrast_set(
                lexicon_ctx, wsid, embedding_method,
                k_cousins=k_cousins,
                cousin_min_cosine=cousin_min_cosine,
            )
            if contrast:
                for cand, cos in contrast["cousins"]:
                    cousins.append({
                        "sid": cand["wsid"],
                        "lemma": cand["lemma"],
                        "canonical_id": cand["canonical_id"],
                        "register": cand.get("register") or "neutral",
                        "gloss": cand.get("microgloss") or "",
                        "cosine": cos,
                    })
        except Exception:
            cousins = []
    # Fallback: legacy sense_relation lookup (only useful AFTER a prior
    # improver run has populated that table)
    if not cousins:
        try:
            for r in conn.execute(
                """
                SELECT sl.wiktionary_source_id, sl.lemma, sl.canonical_id,
                       sl.register, sl.gloss
                  FROM sense_relation sr
                  JOIN sgf_lexicon sl ON sl.wiktionary_source_id = sr.target_wsid
                 WHERE sr.source_wsid = ?
                 LIMIT 8
                """,
                (wsid,),
            ):
                cousins.append({
                    "sid": r[0], "lemma": r[1], "canonical_id": r[2],
                    "register": r[3] or "neutral", "gloss": r[4] or "",
                })
        except sqlite3.OperationalError:
            pass
    tags = []
    try:
        tr = conn.execute(
            "SELECT tags_json FROM wiktionary_source WHERE source_sense_id = ?",
            (wsid,),
        ).fetchone()
        if tr and tr[0]:
            tags = json.loads(tr[0]) if isinstance(tr[0], str) else tr[0]
    except (sqlite3.OperationalError, json.JSONDecodeError):
        pass
    return {
        "wsid": wsid, "lemma": lemma, "pos_simple": pos, "gloss": gloss,
        "provisional_microgloss": mg, "canonical_id": cid,
        "namespace": ns or "core",
        "register": reg or "neutral",
        "temporal_status": temp or "live",
        "social_status": soc or "unmarked",
        "tags": tags, "lemma_mates": lemma_mates, "cousins": cousins,
    }


def build_canonical_id_v3(lemma, microgloss, pos_simple, namespace):
    """Local copy of generate_microglosses.build_canonical_id."""
    def _norm_low(s):
        return _norm(s).strip("_")
    return (
        f"en.{_norm_for_id(lemma)}."
        f"{microgloss}."
        f"{_norm_low(pos_simple)}."
        f"{_norm_low(namespace or 'core')}"
    )


def persist_improvement(conn, ctx, resp):
    """Atomic write of improver outputs to the database."""
    wsid = ctx["wsid"]
    lemma = ctx["lemma"]
    pos = ctx["pos_simple"]
    ns = ctx["namespace"] or "core"
    now = int(time.time())
    improved_mg = resp["improved_microgloss"]
    improved_def = resp.get("improved_definition", "")
    new_cid = build_canonical_id_v3(lemma, improved_mg, pos, ns)
    bm = resp.get("biographical_metadata")
    bm_json = json.dumps(bm) if bm is not None else None
    conn.execute("BEGIN")
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO sense_enrichment (
                source_sense_id, enrichment_version, model, prompt_version,
                improved_microgloss, improved_definition,
                register, temporal_status, social_status,
                social_notes, domain, biographical_metadata_json,
                rationale, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                wsid, IMPROVER_VERSION, IMPROVER_METHOD, PROMPT_VERSION,
                improved_mg, improved_def,
                resp.get("register", "neutral"),
                resp.get("temporal_status", "live"),
                resp.get("social_status", "unmarked"),
                resp.get("social_notes", ""),
                resp.get("domain", "general"),
                bm_json,
                resp.get("rationale", ""),
                now,
            ),
        )
        # also advance maturity_tier to 'improved' and persist
        # the specificity field (general / specialist / technical).
        # Specificity defaults to 'general' when the improver did not
        # set it explicitly.
        spec = resp.get("specificity", "general")
        if spec not in ("general", "specialist", "technical"):
            spec = "general"
        conn.execute(
            """
            UPDATE sgf_lexicon SET
                microgloss = ?, canonical_id = ?,
                register = ?, temporal_status = ?, social_status = ?,
                specificity = ?,
                embedding_text_needs_rebuild = 1,
                maturity_tier = CASE
                    WHEN maturity_tier IN ('raw', 'provisional', 'embedded_v1')
                        THEN 'improved'
                    ELSE maturity_tier
                END
             WHERE wiktionary_source_id = ?
            """,
            (
                improved_mg, new_cid,
                resp.get("register", "neutral"),
                resp.get("temporal_status", "live"),
                resp.get("social_status", "unmarked"),
                spec,
                wsid,
            ),
        )
        for c in resp.get("cousin_classifications", []):
            target_lemma = c.get("lemma")
            if not target_lemma:
                continue
            tr = conn.execute(
                "SELECT wiktionary_source_id FROM sgf_lexicon WHERE lemma = ? LIMIT 1",
                (target_lemma,),
            ).fetchone()
            if not tr:
                continue
            target_wsid = tr[0]
            conn.execute(
                """
                INSERT OR REPLACE INTO sense_relation (
                    source_wsid, target_wsid, relation_type,
                    interchangeable_intra_language,
                    interchangeable_cross_language_standard,
                    interchangeable_cross_language_preserve,
                    relation_note, source_method, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    wsid, target_wsid, c.get("relation_type", "COHYPONYM"),
                    1 if c.get("interchangeable_intra_language") else 0,
                    1 if c.get("interchangeable_cross_language_standard") else 0,
                    1 if c.get("interchangeable_cross_language_preserve") else 0,
                    c.get("note", ""),
                    IMPROVER_METHOD,
                    now,
                ),
            )
        for ci in resp.get("content_identical_with") or []:
            target_lemma = ci.get("lemma")
            if not target_lemma:
                continue
            tier = ci.get("audience_tier", "general")
            conf = float(ci.get("confidence") or 0.9)
            tr = conn.execute(
                "SELECT wiktionary_source_id FROM sgf_lexicon WHERE lemma = ? LIMIT 1",
                (target_lemma,),
            ).fetchone()
            if not tr:
                continue
            target_wsid = tr[0]
            existing = conn.execute(
                """
                SELECT cig.group_id
                  FROM content_identical_group cig
                  JOIN content_identical_member cim
                    ON cim.group_id = cig.group_id
                 WHERE cig.audience_tier = ?
                   AND cim.wsid IN (?, ?)
                 LIMIT 1
                """,
                (tier, wsid, target_wsid),
            ).fetchone()
            if existing:
                gid = existing[0]
            else:
                cur = conn.execute(
                    """
                    INSERT INTO content_identical_group (
                        audience_tier, selection_method, rationale, discovered_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (tier, "improver_v3", ci.get("note", ""), now),
                )
                gid = cur.lastrowid
            for member_wsid in (wsid, target_wsid):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO content_identical_member (
                        group_id, wsid, added_at, add_method, confidence
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (gid, member_wsid, now, "improver_v3", conf),
                )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


if __name__ == "__main__":
    sys.exit(main())
