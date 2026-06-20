#!/usr/bin/env python3
"""
framing.py — Stage 9 of the GLEAN pipeline

For each synapse, attach a frame: rhetorical mode, hedging level, point
of view, statement type, temporal anchor, and verb features.

CHANGES IN v1.1
---------------
- Attribution-first POV: the subject of a clause is NEVER the POV unless
  there is an explicit reporting verb (said, claimed, alleged, ...). The
  document author is the default POV. This fixes the naive v1.0 default
  that called Beethoven the POV of "Beethoven moved to Vienna."
- Three-class epistemic_status: proven_fact, reported_claim, speculative.
- Quote-type detection: looks for surrounding quotation marks in the
  source text. Direct quotes get quote_type='direct'.
- pov_layer field for nested-reality support. v1.1 only writes one layer
  per synapse (the discourse layer), but the schema supports stacking.

Two modes:
  --mode deterministic   spaCy + heuristics only. Fast. No LLM.
  --mode llm             Adds LLM call for rhetorical_mode, full verb features.

Usage:
    python framing.py --synapses synapses.json --source doc.txt \\
                      --output synapses_framed.json --mode deterministic
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sgflib import LLMClient, get_reporting_verbs, load_config, parse_mdkv


# =============================================================================
# Heuristic lists
# =============================================================================

HEDGE_WORDS = {
    "may", "might", "could", "would", "should", "perhaps", "possibly",
    "probably", "presumably", "supposedly", "apparently", "seemingly",
    "potentially", "arguably", "reportedly", "allegedly", "purportedly",
    "evidently", "ostensibly", "believe", "believes", "believed",
    "rumor", "rumored", "estimated", "estimates", "approximately",
    "around", "about", "some", "many", "few", "several",
}

# Words that indicate negation by determiner/quantifier rather than dep=neg.
# Used to flip polarity when the verb's argument is "no X", "no surviving X"
DET_NEGATION_WORDS = {"no", "none", "neither", "nothing", "nobody", "never"}


# =============================================================================
# Deterministic frame
# =============================================================================

def detect_pov(synapse: dict, source_text: str,
               reporting_verbs: set[str]) -> dict:
    """Attribution-first POV detection.

    Returns a dict with keys:
        point_of_view, pov_speaker_surface, pov_layer, statement_type_hint

    The rule (from Hoplogic pov_extractors.py, attribution-first):
      - If the clause's predicate lemma is a reporting verb, the subject
        of that verb is the POV speaker. statement_type = reported_claim.
      - If the predicate is governed by a reporting verb (clause is a
        ccomp/xcomp of a reporting verb), same rule applies.
      - Otherwise the POV is the document author.
    """
    pred_lemma = (synapse.get("predicate_lemma") or
                  synapse.get("predicate_surface", "")).lower()

    # Direct reporting verb at the hub
    if pred_lemma in reporting_verbs:
        # Subject of the clause = the speaker
        speaker = None
        for sp in synapse.get("spokes", []):
            if sp.get("role") == "HAS_AGENT":
                speaker = sp.get("target_surface") or sp.get("target_ent_id")
                break
        return {
            "point_of_view": "character" if speaker else "author",
            "pov_speaker_surface": speaker,
            "pov_layer": "character" if speaker else "discourse",
            "statement_type_hint": "reported_claim",
        }

    # Reporting hedge by phrase ("some scholars believe...")
    span_text = source_text[synapse.get("source_span_start", 0):
                            synapse.get("source_span_end", 0)].lower()
    if any(rv in span_text for rv in ("believe", "claim", "alleged",
                                     "reportedly", "rumored", "according to")):
        return {
            "point_of_view": "citation",
            "pov_speaker_surface": None,
            "pov_layer": "discourse",
            "statement_type_hint": "reported_claim",
        }

    return {
        "point_of_view": "author",
        "pov_speaker_surface": None,
        "pov_layer": "discourse",
        "statement_type_hint": "proven_fact",
    }


def detect_quote_type(synapse: dict, source_text: str) -> str:
    """Detect quote type from the source text around the clause span."""
    start = max(0, synapse.get("source_span_start", 0) - 5)
    end = min(len(source_text), synapse.get("source_span_end", 0) + 5)
    span = source_text[start:end]
    if any(q in span for q in ('"', "\u201C", "\u201D")):
        return "direct"
    # indirect: reporting verb + "that"
    span_low = source_text[
        synapse.get("source_span_start", 0):synapse.get("source_span_end", 0)
    ].lower()
    if " that " in span_low:
        for rv in ("said", "claimed", "argued", "reported", "wrote",
                   "stated", "noted", "observed"):
            if rv in span_low:
                return "indirect"
    return "none"


def detect_determiner_negation(synapse: dict, source_text: str) -> bool:
    """Catch determiner-scope negation that spaCy's neg dep misses.

    Example: 'no surviving letter confirms the claim' — 'no' is det of
    'letter', not neg of 'confirms'. We flip polarity if a HAS_AGENT or
    HAS_PATIENT spoke's target_surface starts with a negation determiner.
    """
    for sp in synapse.get("spokes", []):
        if sp.get("role") not in ("HAS_AGENT", "HAS_PATIENT"):
            continue
        surf = (sp.get("target_surface") or "").lower()
        if not surf:
            continue
        first_word = surf.split()[0] if surf.split() else ""
        if first_word in DET_NEGATION_WORDS:
            return True
    # Also check the source span directly for "no" or "never" before predicate
    pred_start = synapse.get("source_span_start", 0)
    window = source_text[max(0, pred_start - 30):pred_start].lower()
    if re.search(r"\b(no|never|none|neither)\s+\w+\s*$", window):
        return True
    return False


def deterministic_frame(synapse: dict, source_text: str,
                        reporting_verbs: set[str]) -> dict:
    span_text = source_text[synapse["source_span_start"]:synapse["source_span_end"]]
    span_low = span_text.lower()
    words = set(re.findall(r"[a-z']+", span_low))

    # Hedging
    hedge_hits = sorted(words & HEDGE_WORDS)
    if not hedge_hits:
        hedging = "none"
    elif len(hedge_hits) == 1:
        hedging = "light"
    elif len(hedge_hits) <= 3:
        hedging = "moderate"
    else:
        hedging = "heavy"

    # POV (attribution-first)
    pov = detect_pov(synapse, source_text, reporting_verbs)

    # Statement type: start with POV hint, refine
    statement_type = pov["statement_type_hint"]
    if hedging in ("moderate", "heavy") and any(w in words for w in (
            "believe", "claim", "rumor", "alleged", "reportedly")):
        statement_type = "reported_claim"
    if hedging in ("moderate", "heavy") and statement_type == "proven_fact":
        statement_type = "speculative"

    # Polarity (combine spaCy neg with determiner-scope check)
    polarity = synapse.get("polarity", "positive")
    if polarity == "positive" and detect_determiner_negation(synapse, source_text):
        polarity = "negative"

    # Verb modality
    verb_modality = "indicative"
    if "might" in words or "may" in words or "could" in words:
        verb_modality = "epistemic"
    if "must" in words or "should" in words:
        verb_modality = "deontic"

    # Verb tense (crude)
    pred = synapse.get("predicate_surface", "").lower()
    verb_tense = "present"
    if pred.endswith("ed") or pred in ("was", "were", "had", "did", "went",
                                       "saw", "took", "gave", "made"):
        verb_tense = "past"
    if pred.endswith("ing"):
        verb_tense = "present_progressive"

    # Quote type
    quote_type = detect_quote_type(synapse, source_text)

    return {
        "rhetorical_mode": "straight",
        "hedging_level": hedging,
        "hedging_words": ", ".join(hedge_hits) if hedge_hits else None,
        "point_of_view": pov["point_of_view"],
        "pov_speaker_surface": pov["pov_speaker_surface"],
        "pov_layer": pov["pov_layer"],
        "pov_entity_id": None,
        "statement_type": statement_type,
        "quote_type": quote_type,
        "temporal_anchor": None,
        "verb_tense": verb_tense,
        "verb_aspect": "simple",
        "verb_mood": "indicative",
        "verb_voice": "active",
        "verb_polarity": polarity,
        "verb_modality": verb_modality,
        "verb_features": {},
    }


# =============================================================================
# LLM frame (unchanged from v1.0 except adds pov_layer and quote_type)
# =============================================================================

FRAMING_SYSTEM = (
    "You are a linguistic analyzer. For a given clause from a document, "
    "produce a frame describing its rhetorical mode, hedging, point of "
    "view, statement type, quote type, temporal anchor, and verb features. "
    "Respond ONLY with the requested MDKV block."
)

FRAMING_USER_TEMPLATE = (
    "Source paragraph:\n{paragraph}\n\n"
    "Specific clause (verb at center):\n{clause}\n\n"
    "Synapse predicate: {predicate}\n"
    "Polarity (already detected): {polarity}\n"
    "Provisional POV: {pov}\n\n"
    "Produce the frame in this exact format:\n"
    ":::frame\n"
    "rhetorical_mode: straight | irony | sarcasm | hyperbole | humor | metaphor | rhetorical_question\n"
    "hedging_level: none | light | moderate | heavy\n"
    "hedging_words: <comma-separated, or blank>\n"
    "point_of_view: author | character | witness | citation | hypothesis | reported\n"
    "pov_layer: discourse | character | witness | citation\n"
    "pov_speaker_surface: <name of POV entity, or blank if author>\n"
    "statement_type: proven_fact | reported_claim | speculative | hypothetical | counterfactual | rumor | definition | opinion\n"
    "quote_type: none | direct | indirect | mixed\n"
    "temporal_anchor: <ISO date, year, relative duration, or blank>\n"
    "verb_tense: past | present | future | past_perfect | present_perfect | future_perfect\n"
    "verb_aspect: simple | progressive | perfect | perfect_progressive\n"
    "verb_mood: indicative | imperative | subjunctive | conditional\n"
    "verb_voice: active | passive\n"
    "verb_polarity: positive | negative\n"
    "verb_modality: indicative | epistemic | deontic | dynamic\n"
    ":::"
)


def llm_frame(synapse: dict, source_text: str, llm: LLMClient,
              reporting_verbs: set[str]) -> dict:
    sp_start = max(0, synapse["source_span_start"] - 200)
    sp_end = min(len(source_text), synapse["source_span_end"] + 200)
    paragraph = source_text[sp_start:sp_end]
    clause = source_text[synapse["source_span_start"]:synapse["source_span_end"]]

    det = deterministic_frame(synapse, source_text, reporting_verbs)

    user = FRAMING_USER_TEMPLATE.format(
        paragraph=paragraph.strip(),
        clause=clause.strip(),
        predicate=synapse.get("predicate_surface", ""),
        polarity=synapse.get("polarity", "positive"),
        pov=det["point_of_view"],
    )

    try:
        blocks = llm.complete_mdkv(FRAMING_SYSTEM, user, expected_kind="frame")
    except Exception as e:
        print(f"[framing] LLM call failed: {e}; using deterministic",
              file=sys.stderr)
        return det
    if not blocks:
        return det

    b = blocks[0]
    def pick(key, default=None):
        v = b.get(key)
        if not v:
            return default
        if isinstance(v, str):
            v = v.strip()
        return v or default

    return {
        "rhetorical_mode": pick("rhetorical_mode", det["rhetorical_mode"]),
        "hedging_level": pick("hedging_level", det["hedging_level"]),
        "hedging_words": pick("hedging_words", det["hedging_words"]),
        "point_of_view": pick("point_of_view", det["point_of_view"]),
        "pov_layer": pick("pov_layer", det["pov_layer"]),
        "pov_speaker_surface": pick("pov_speaker_surface", det["pov_speaker_surface"]),
        "pov_entity_id": None,
        "statement_type": pick("statement_type", det["statement_type"]),
        "quote_type": pick("quote_type", det["quote_type"]),
        "temporal_anchor": pick("temporal_anchor", det["temporal_anchor"]),
        "verb_tense": pick("verb_tense", det["verb_tense"]),
        "verb_aspect": pick("verb_aspect", det["verb_aspect"]),
        "verb_mood": pick("verb_mood", det["verb_mood"]),
        "verb_voice": pick("verb_voice", det["verb_voice"]),
        "verb_polarity": pick("verb_polarity", det["verb_polarity"]),
        "verb_modality": pick("verb_modality", det["verb_modality"]),
        "verb_features": {},
    }


# =============================================================================
# Pipeline
# =============================================================================

def frame_synapses(synapses, source_text, mode, cfg):
    reporting_verbs = get_reporting_verbs()
    out = []
    llm = LLMClient(cfg) if mode == "llm" else None
    for syn in synapses:
        if mode == "deterministic":
            frame = deterministic_frame(syn, source_text, reporting_verbs)
            method = "deterministic"
        else:
            frame = llm_frame(syn, source_text, llm, reporting_verbs)
            method = f"llm:{cfg.raw['llm']['model']}"
        syn["frame"] = frame
        syn["framing_method"] = method
        # also propagate polarity refinement back to the synapse top-level
        if frame.get("verb_polarity") and syn.get("polarity") != frame["verb_polarity"]:
            syn["polarity"] = frame["verb_polarity"]
        out.append(syn)
    return out


# =============================================================================
# CLI
# =============================================================================

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--synapses", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--mode", choices=["deterministic", "llm"],
                   default="deterministic")
    args = p.parse_args()

    syn_path = Path(args.synapses)
    src_path = Path(args.source)
    if not syn_path.exists():
        print(f"Synapses file not found: {syn_path}", file=sys.stderr)
        return 1
    if not src_path.exists():
        print(f"Source file not found: {src_path}", file=sys.stderr)
        return 1

    synapses = json.loads(syn_path.read_text(encoding="utf-8"))
    source_text = src_path.read_text(encoding="utf-8")

    cfg = load_config()
    framed = frame_synapses(synapses, source_text, args.mode, cfg)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(framed, indent=2), encoding="utf-8")
    print()
    print(f"Wrote {len(framed)} framed synapses to {out_path}")
    print(f"Mode: {args.mode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
