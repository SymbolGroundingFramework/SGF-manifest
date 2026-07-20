#!/usr/bin/env python3
"""
framing.py — Stage 9 of the GLEAN pipeline (v3.2)

For each synapse, attach a frame describing its rhetorical mode, hedging
level, point of view, statement type, temporal anchor, verb features,
speech act, scope, conditional marker, and rhetorical mood.

v3.2 changes
------------
- Adds `frame_json` to each synapse's output — a JSON-serialized copy of
  the frame dict, for storage in synapedia_synapse.frame_json.
- No changes to the frame dict itself.  All v1.2 detectors are preserved.
- frame_json is a superset of the deterministic frame; it includes
  every frame field so the persist stage can store it as a single blob.

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

from sgflib import get_reporting_verbs, load_config, parse_mdkv
from call_llm import call_llm, is_wrapper_configured, load_llm_config


# ===========================================================================
# Heuristic lists
# ===========================================================================

HEDGE_WORDS = {
    "perhaps", "maybe", "might", "may", "possibly", "probably",
    "likely", "unlikely", "supposedly", "allegedly", "reportedly",
    "apparently", "presumably", "seemingly", "purportedly",
    "approximately", "roughly", "about", "somewhat", "sort", "kind",
    "appear", "appears", "appeared", "seem", "seems", "seemed",
    "believe", "believes", "believed", "claim", "claims", "claimed",
    "thought", "thinks", "think",
}

DETERMINER_NEG_WORDS = {"no", "none", "neither", "nothing", "nobody"}

REQUEST_OPENERS = (
    "can you", "could you", "would you", "will you",
    "would you mind", "could i ask you to",
)

COUNTERFACTUAL_PATTERN = re.compile(
    r"\b(?:if\s+[a-z]+\s+had\b|if\s+[a-z]+\s+were\b|were\s+to\b|"
    r"(?:would|could|might|should)\s+have\b)",
    re.IGNORECASE,
)

HYPERBOLE_PHRASES = (
    "could eat a horse", "moved heaven and earth", "a thousand times",
    "a million times", "forever and ever", "end of the world",
    "die of embarrassment", "hungry enough to eat", "could kill for",
    "ten pizzas",
)
HYPERBOLE_NUMBERS_PATTERN = re.compile(
    r"\b(?:a\s+)?(?:million|billion|trillion|thousand|hundred)\s+"
    r"(?:times|years|hours|miles|pounds|dollars|reasons|pizzas)",
    re.IGNORECASE,
)

IMPERATIVE_VERB_LEMMAS = {
    "open", "close", "pass", "give", "take", "go", "come", "stop",
    "start", "wait", "listen", "look", "see", "hear", "sit", "stand",
    "run", "walk", "speak", "tell", "show", "send", "bring", "put",
    "call", "answer", "do", "don't",
}

DETERMINERS = {
    "the", "a", "an", "this", "that", "these", "those",
    "some", "all", "every", "each", "my", "your", "his", "her",
    "our", "their", "its",
}


# ===========================================================================
# POV detection (attribution-first)
# ===========================================================================

def detect_pov(synapse, source_text, reporting_verbs):
    """Detect point_of_view + statement_type_hint.

    Returns a dict with keys:
      point_of_view, pov_speaker_surface, pov_layer, statement_type_hint
    """
    predicate = (synapse.get("predicate_surface") or "").lower()
    span_start = synapse["source_span_start"]
    span_end = synapse["source_span_end"]
    span_text = source_text[span_start:span_end]

    if predicate in reporting_verbs:
        agent_surface = None
        for spoke in synapse.get("spokes", []):
            if spoke.get("role") == "HAS_AGENT":
                agent_surface = spoke.get("target_surface")
                break
        if agent_surface:
            return {
                "point_of_view": "character",
                "pov_speaker_surface": agent_surface,
                "pov_layer": "character",
                "statement_type_hint": "reported_claim",
            }
        return {
            "point_of_view": "citation",
            "pov_speaker_surface": None,
            "pov_layer": "citation",
            "statement_type_hint": "reported_claim",
        }

    if '"' in span_text or "'" in span_text:
        if span_text.count('"') >= 2 or span_text.count("''") >= 1:
            return {
                "point_of_view": "citation",
                "pov_speaker_surface": None,
                "pov_layer": "citation",
                "statement_type_hint": "reported_claim",
            }

    return {
        "point_of_view": "author",
        "pov_speaker_surface": None,
        "pov_layer": "author",
        "statement_type_hint": "proven_fact",
    }


def detect_quote_type(synapse, source_text):
    span_text = source_text[synapse["source_span_start"]:
                            synapse["source_span_end"]]
    if '"' in span_text and span_text.count('"') >= 2:
        return "direct"
    if any(rv in span_text.lower()
           for rv in ("said that", "stated that", "claimed that",
                      "reported that", "alleged that")):
        return "indirect"
    return "none"


def detect_determiner_negation(synapse, source_text):
    """Catch 'no surviving letter' as a polarity flip.

    spaCy puts the neg dep on the determiner 'no', not on the verb.
    We flag the synapse as negative if a HAS_AGENT or HAS_PATIENT
    surface starts with 'no '/'none '/'neither '.
    """
    for spoke in synapse.get("spokes", []):
        if spoke.get("role") not in ("HAS_AGENT", "HAS_PATIENT"):
            continue
        surface = (spoke.get("target_surface") or "").lower().strip()
        first = surface.split()[0] if surface else ""
        if first in DETERMINER_NEG_WORDS:
            return True
    return False

# ===========================================================================
# v1.2 detectors (unchanged)
# ===========================================================================

def detect_speech_act(span_text, predicate_surface,
                      ends_with_question_mark, ends_with_exclamation):
    low = span_text.lower().strip()
    if any(low.startswith(o) for o in REQUEST_OPENERS):
        return "REQUEST"
    if low.startswith("please ") or " please " in low[:30]:
        return "REQUEST"
    if ends_with_question_mark:
        return "QUESTION"
    if ends_with_exclamation:
        return "EXCLAMATION"
    if re.match(r"^i\s+(?:will|'ll|promise|swear|guarantee)\b", low):
        return "PROMISE"
    if re.match(r"^we\s+(?:will|'ll|promise|swear|guarantee)\b", low):
        return "PROMISE"
    first = low.split()[0] if low else ""
    if first in IMPERATIVE_VERB_LEMMAS:
        return "COMMAND"
    return "INFORM"


def detect_conditional_marker(span_text):
    low = span_text.lower()
    if COUNTERFACTUAL_PATTERN.search(low):
        return "counterfactual"
    if re.match(r"^\s*(?:suppose|imagine|assume)\b", low):
        return "hypothetical"
    words = re.findall(r"[a-z']+", low)
    if words and words[0] in ("if", "unless", "should"):
        return "conditional"
    return None


def detect_rhetorical_mood(span_text):
    low = span_text.lower()
    if any(phrase in low for phrase in HYPERBOLE_PHRASES):
        return "hyperbolic_suspected"
    if HYPERBOLE_NUMBERS_PATTERN.search(low):
        return "hyperbolic_suspected"
    return None


def detect_scope(synapse, span_text):
    subj_surface = ""
    for spoke in synapse.get("spokes", []):
        if spoke.get("role") in ("HAS_AGENT", "HAS_THEME", "HAS_EXPERIENCER"):
            subj_surface = (spoke.get("target_surface") or "").strip().lower()
            break
    if not subj_surface:
        return "specific"
    first = subj_surface.split()[0] if subj_surface else ""
    if first in DETERMINERS:
        return "specific"
    if subj_surface.endswith("s") and not subj_surface.endswith("ss"):
        if " was " not in span_text.lower() and " were " not in span_text.lower():
            pred = (synapse.get("predicate_surface") or "").lower()
            if not pred.endswith("ed") and pred not in (
                "was", "were", "had", "did", "went", "saw", "took",
            ):
                return "generic"
    return "specific"


def detect_verb_features(synapse, span_text, tier):
    pred = (synapse.get("predicate_surface") or "").lower()
    feats = {
        "tense":     "past" if pred.endswith("ed") else "present",
        "aspect":    "progressive" if pred.endswith("ing") else "simple",
        "voice":     "active",
        "person":    "3rd",
        "number":    "singular",
        "mood":      "indicative",
        "polarity":  synapse.get("polarity", "positive"),
        "modality_category": None,
        "is_copula":   pred in ("is", "are", "was", "were", "be", "been", "being"),
        "is_reporting": False,
    }
    low = span_text.lower()
    if "can " in low or "could " in low or "able to" in low:
        feats["modality_category"] = "capability"
    elif "must " in low or "have to" in low or "obliged" in low:
        feats["modality_category"] = "obligation"
    elif "may " in low or "might " in low or "perhaps" in low:
        feats["modality_category"] = "possibility"
    elif "should " in low or "ought" in low or "supposed to" in low:
        feats["modality_category"] = "necessity"

    if tier in ("high_fidelity", "archival"):
        feats.update({
            "evidentiality": None,
            "volition": None,
            "telicity": None,
            "dynamicity": None,
            "causation_type": None,
        })
    if tier == "archival":
        feats.update({
            "clusivity": None,
            "obviation": None,
            "directional": None,
            "associated_motion": None,
            "mirativity": None,
            "verbal_classifier": None,
        })
    return feats


# ===========================================================================
# Deterministic frame
# ===========================================================================

def deterministic_frame(synapse, source_text, reporting_verbs,
                        verb_tier="standard"):
    span_text = source_text[synapse["source_span_start"]:
                            synapse["source_span_end"]]
    span_low = span_text.lower()
    words = set(re.findall(r"[a-z']+", span_low))

    hedge_hits = sorted(words & HEDGE_WORDS)
    if not hedge_hits:
        hedging = "none"
    elif len(hedge_hits) == 1:
        hedging = "light"
    elif len(hedge_hits) <= 3:
        hedging = "moderate"
    else:
        hedging = "heavy"

    pov = detect_pov(synapse, source_text, reporting_verbs)

    statement_type = pov["statement_type_hint"]
    if hedging in ("moderate", "heavy") and any(
        w in words for w in ("believe", "claim", "rumor", "alleged", "reportedly")
    ):
        statement_type = "reported_claim"
    if hedging in ("moderate", "heavy") and statement_type == "proven_fact":
        statement_type = "speculative"

    polarity = synapse.get("polarity", "positive")
    if polarity == "positive" and detect_determiner_negation(synapse, source_text):
        polarity = "negative"

    verb_modality = "indicative"
    if "might" in words or "may" in words or "could" in words:
        verb_modality = "epistemic"
    if "must" in words or "should" in words:
        verb_modality = "deontic"

    quote_type = detect_quote_type(synapse, source_text)

    ends_q = span_text.rstrip().endswith("?")
    ends_ex = span_text.rstrip().endswith("!")
    speech_act = detect_speech_act(
        span_text, synapse.get("predicate_surface", ""), ends_q, ends_ex,
    )
    conditional = detect_conditional_marker(span_text)
    rhetorical_mood = detect_rhetorical_mood(span_text)
    scope = detect_scope(synapse, span_text)
    verb_features = detect_verb_features(synapse, span_text, verb_tier)

    if conditional == "counterfactual":
        statement_type = "counterfactual"
    elif conditional == "hypothetical":
        statement_type = "hypothetical"
    elif conditional == "conditional" and statement_type == "proven_fact":
        statement_type = "conditional"

    temporal_anchor = None
    if re.search(r"\b(?:1[0-9]|20)\d{2}\b", span_text):
        temporal_anchor = "explicit_date"
    elif scope == "generic":
        temporal_anchor = "generic"
    elif any(w in words for w in
             ("later", "yesterday", "tomorrow", "then", "recently")):
        temporal_anchor = "relative"

    return {
        "rhetorical_mode": "straight",
        "rhetorical_mood": rhetorical_mood,
        "hedging_level": hedging,
        "hedging_words": ", ".join(hedge_hits) if hedge_hits else None,
        "point_of_view": pov["point_of_view"],
        "pov_speaker_surface": pov["pov_speaker_surface"],
        "pov_layer": pov["pov_layer"],
        "pov_entity_id": None,
        "statement_type": statement_type,
        "quote_type": quote_type,
        "speech_act": speech_act,
        "scope": scope,
        "conditional_marker": conditional,
        "temporal_anchor": temporal_anchor,
        "verb_tense": verb_features["tense"],
        "verb_aspect": verb_features["aspect"],
        "verb_mood": verb_features["mood"],
        "verb_voice": verb_features["voice"],
        "verb_polarity": polarity,
        "verb_modality": verb_modality,
        "verb_features": verb_features,
    }


# ===========================================================================
# LLM frame (MDKV in, MDKV out via the user's wrapper)
# ===========================================================================

FRAMING_SYSTEM = (
    "You are framing a single proposition extracted from prose. "
    "Reply with ONE MDKV block of kind 'frame'. No prose outside the "
    "block. Fields are listed in the user message."
)

FRAMING_USER_TEMPLATE = (
    "Paragraph: {paragraph}\n\n"
    "Clause: {clause}\n\n"
    "Predicate: {predicate}\n"
    "Polarity from extractor: {polarity}\n"
    "Default POV (deterministic): {pov}\n\n"
    "Return:\n"
    ":::frame\n"
    "rhetorical_mode: straight | metaphor | hyperbole | sarcasm | understatement\n"
    "rhetorical_mood: null | hyperbolic_suspected | sarcasm_suspected\n"
    "hedging_level: none | light | moderate | heavy\n"
    "hedging_words: <comma-separated or empty>\n"
    "point_of_view: author | character | citation\n"
    "pov_layer: author | character | citation\n"
    "pov_speaker_surface: <surface form or empty>\n"
    "statement_type: proven_fact | reported_claim | speculative | "
    "counterfactual | hypothetical | conditional\n"
    "speech_act: INFORM | QUESTION | REQUEST | COMMAND | PROMISE | EXCLAMATION\n"
    "scope: specific | generic\n"
    "quote_type: none | direct | indirect\n"
    "temporal_anchor: explicit_date | inherited | relative | generic | unknown\n"
    "verb_tense: past | present | future | present_progressive | past_perfect\n"
    "verb_aspect: simple | progressive | perfect | perfect_progressive\n"
    "verb_mood: indicative | subjunctive | imperative | conditional\n"
    "verb_voice: active | passive\n"
    "verb_polarity: positive | negative\n"
    "verb_modality: indicative | epistemic | deontic | dynamic\n"
    ":::"
)


def llm_frame(synapse, source_text, llm_cfg, reporting_verbs,
              verb_tier="standard"):
    det = deterministic_frame(synapse, source_text, reporting_verbs, verb_tier)

    if not is_wrapper_configured(llm_cfg):
        return det

    sp_start = max(0, synapse["source_span_start"] - 200)
    sp_end = min(len(source_text), synapse["source_span_end"] + 200)
    paragraph = source_text[sp_start:sp_end]
    clause = source_text[synapse["source_span_start"]:synapse["source_span_end"]]

    user_prompt = FRAMING_USER_TEMPLATE.format(
        paragraph=paragraph.strip(),
        clause=clause.strip(),
        predicate=synapse.get("predicate_surface", ""),
        polarity=synapse.get("polarity", "positive"),
        pov=det["point_of_view"],
    )

    try:
        raw = call_llm(
            prompt_text=user_prompt,
            llm_cfg=llm_cfg,
            system_text=FRAMING_SYSTEM,
        )
    except RuntimeError as e:
        print(f"[framing] LLM call failed: {e}; using deterministic",
              file=sys.stderr)
        return det

    blocks = [b for b in parse_mdkv(raw) if b.get("_kind") == "frame"]
    if not blocks:
        return det

    b = blocks[0]

    def pick(key, default=None):
        v = b.get(key)
        if v is None:
            return default
        if isinstance(v, str):
            v = v.strip()
            if v in ("", "null", "none", "None"):
                return default
        return v

    out = dict(det)
    for key in (
        "rhetorical_mode", "rhetorical_mood", "hedging_level", "hedging_words",
        "point_of_view", "pov_layer", "pov_speaker_surface", "statement_type",
        "quote_type", "speech_act", "scope", "temporal_anchor",
        "verb_tense", "verb_aspect", "verb_mood", "verb_voice",
        "verb_polarity", "verb_modality",
    ):
        out[key] = pick(key, det.get(key))
    return out


# ===========================================================================
# Pipeline driver
# ===========================================================================

def frame_synapses(synapses, source_text, mode, cfg, llm_cfg=None):
    """Frame a list of synapse dicts. Returns a new list with each
    synapse augmented by a 'frame' key and a 'frame_json' key.

    frame_json is a JSON-serialized copy of the frame dict, suitable
    for storage in synapedia_synapse.frame_json.
    """
    reporting_verbs = get_reporting_verbs()
    verb_tier = (cfg.get("verb_features", {}) or {}).get("tier", "standard")

    framed = []
    for syn in synapses:
        if mode == "llm" and llm_cfg is not None:
            frame = llm_frame(syn, source_text, llm_cfg, reporting_verbs, verb_tier)
            framing_method = "llm:wrapper"
        else:
            frame = deterministic_frame(syn, source_text, reporting_verbs, verb_tier)
            framing_method = "deterministic"
        syn_out = dict(syn)
        syn_out["frame"] = frame
        syn_out["frame_json"] = json.dumps(frame)   # NEW v3.2
        syn_out["framing_method"] = framing_method
        framed.append(syn_out)
    return framed


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--synapses", required=True, help="synapses.json input")
    p.add_argument("--source", required=True, help="source text file")
    p.add_argument("--output", required=True, help="output framed JSON")
    p.add_argument("--mode", default="deterministic",
                   choices=["deterministic", "llm"])
    p.add_argument("--config", default=None)
    args = p.parse_args()

    cfg = load_config(args.config)
    llm_cfg = load_llm_config(cfg.get("_config_path"))

    src = Path(args.source).read_text(encoding="utf-8")
    with open(args.synapses, "r", encoding="utf-8") as f:
        syns = json.load(f)
    if isinstance(syns, dict) and "synapses" in syns:
        syns = syns["synapses"]

    framed = frame_synapses(syns, src, args.mode, cfg, llm_cfg)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump({"synapses": framed, "framing_mode": args.mode},
                  f, indent=2)
    print(f"framed {len(framed)} synapses -> {args.output}")


if __name__ == "__main__":
    main()