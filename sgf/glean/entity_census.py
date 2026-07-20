#!/usr/bin/env python3
"""
entity_census.py — Stage 4 of the GLEAN pipeline (v3.2)

Identify every entity in a document, cluster aliases, resolve pronouns,
detect possessive chains, classify literals, and emit an Entity Map JSON.

v3.2 changes:
  - Added accuracy_mode parameter (casual | standard | rigorous)
  - Added nexus_namespace field to each entity (synapedia | custom | literal | ghost)
  - Added custom_lexicon_id field for minted entities
  - Added in-memory lookup cache for duplicate lemmas (no quality loss)
  - Added progress print statements for debugging hangs
  - Added LLM enrichment for minted entities (hybrid: deterministic + LLM)

Usage:
    python entity_census.py --input INPUT.txt --output entity_map.json
    python entity_census.py --input INPUT.txt --output entity_map.json --no-lookup
    python entity_census.py --input INPUT.txt --output entity_map.json --accuracy-mode rigorous
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import uuid
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sgflib import (
    LITERAL_NER_LABELS,
    load_config,
    lookup_in_lexicon,
    parse_mdkv,
)

try:
    import call_llm
    _HAVE_CALL_LLM = True
except Exception:
    _HAVE_CALL_LLM = False


# =============================================================================
# In-memory lookup cache (prevents redundant HTTP calls for duplicate lemmas)
# =============================================================================
_LOOKUP_CACHE: dict = {}

# LLM enrichment cache: same lemma + POS → skip re-classification
_LLM_ENRICH_CACHE: dict = {}


# =============================================================================
# Constants
# =============================================================================

PRONOUNS = {
    "he":   ("third-m", "sing"),
    "him":  ("third-m", "sing"),
    "his":  ("third-m", "sing"),
    "she":  ("third-f", "sing"),
    "her":  ("third-f", "sing"),
    "hers": ("third-f", "sing"),
    "it":   ("third-n", "sing"),
    "its":  ("third-n", "sing"),
    "they": ("third",   "plur"),
    "them": ("third",   "plur"),
    "their": ("third",  "plur"),
    "theirs": ("third", "plur"),
}

KEEP_NER_TYPES = {
    "PERSON", "ORG", "GPE", "LOC", "NORP", "WORK_OF_ART",
    "EVENT", "FAC", "PRODUCT", "LANGUAGE",
}

LITERAL_HINT_LABELS = LITERAL_NER_LABELS

DROP_NER_TYPES = {
    "LAW",
}

NAMED_TYPES = frozenset({
    "person", "org", "gpe", "loc", "facility", "work",
    "norp", "product", "event", "thing",
})


# =============================================================================
# Plain-dict factories
# =============================================================================

def new_mention(*, clause_id, sentence_id, surface, span_start, span_end,
                pos, resolved_by="direct"):
    return {
        "clause_id": clause_id,
        "sentence_id": sentence_id,
        "surface": surface,
        "span_start": span_start,
        "span_end": span_end,
        "pos": pos,
        "resolved_by": resolved_by,
    }


def new_entity(*, ent_id, preferred_canonical, type_hint, pos,
               is_literal=False, literal_type=None, literal_value=None):
    return {
        "ent_id": ent_id,
        "preferred_canonical": preferred_canonical,
        "type_hint": type_hint,
        "pos": pos,
        "aliases": [preferred_canonical],
        "mentions": [],
        "anonymous": False,
        "chain": [],
        "context_text": "",
        # Lexicon lookup
        "lexicon_canonical_id": None,
        "lookup_decision_level": 0,
        "lookup_confidence": 0.0,
        "minted": False,
        # v1.2 enrichment fields
        "specificity": None,
        "maturity_tier": None,
        "rewritten_to_standard": False,
        "matched_canonical_id": None,
        # v3.2 new fields
        "nexus_namespace": "synapedia",
        "custom_lexicon_id": None,
        # LLM enrichment (populated for minted entities)
        "llm_type_hint": None,
        "llm_domain": None,
        "llm_gloss": None,
        "llm_is_instance": None,
        "llm_is_compound": None,
        "llm_is_metonymy": None,
        "llm_parent_category": None,
        # Literal info
        "is_literal": is_literal,
        "literal_type": literal_type,
        "literal_value": literal_value,
    }


def new_census_state(cfg, *, run_lookup=True, verbose=False, llm_cfg=None,
                     accuracy_mode="standard"):
    return {
        "cfg": cfg,
        "run_lookup": run_lookup,
        "verbose": verbose,
        "llm_cfg": llm_cfg,
        "accuracy_mode": accuracy_mode,
        "entities": [],
        "by_surface_lower": {},
        "spacy_model": cfg.get("spacy", {}).get("model", "en_core_web_sm"),
        "nlp": None,
    }


# =============================================================================
# Text helpers
# =============================================================================

def short_uuid():
    return uuid.uuid4().hex[:8]


def strip_possessive(text):
    if not text:
        return text
    t = text.replace("\u2019", "'")
    if re.search(r"'s$", t, flags=re.IGNORECASE):
        t = re.sub(r"'s$", "", t, flags=re.IGNORECASE)
    elif re.search(r"s'$", t, flags=re.IGNORECASE):
        t = re.sub(r"s'$", "", t, flags=re.IGNORECASE)
    return t.strip()


def strip_outer_quotes(text):
    if not text:
        return text
    t = text.strip()
    if len(t) >= 2 and t[0] in "\"'\u201C\u2018" and t[-1] in "\"'\u201D\u2019":
        t = t[1:-1]
    return t.strip()


def normalize_whitespace(text):
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_leading_the(text):
    if not text:
        return text
    if text.lower().startswith("the "):
        return text[4:].strip()
    return text


def canonical_normalizer(text):
    t = normalize_whitespace(text)
    t = strip_outer_quotes(t)
    t = strip_possessive(t)
    t = normalize_leading_the(t)
    t = normalize_whitespace(t)
    return t.lower()


def sequence_similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()


def looks_like_noise(canonical, ent_type):
    if not canonical:
        return True
    t = normalize_whitespace(canonical).strip("#").strip()
    if not t:
        return True
    if ent_type != "DATE" and len(t) <= 2 and not re.search(r"[A-Za-z]", t):
        return True
    if re.fullmatch(r"[\.\,\;\:\-\"'`]+", t):
        return True
    junk_phrases = {
        "the middle of the", "his first decade", "two centuries ago",
        "a few", "some time", "a moment",
    }
    if t.lower() in junk_phrases:
        return True
    if re.search(r"\b[a-z]\.\s*[a-z]\.\s*[a-z]\b", t.lower()):
        return True
    return False


# -----------------------------------------------------------------------------
# Literal classification
# -----------------------------------------------------------------------------

YEAR_RE = re.compile(r"^\s*(\d{3,4})\s*$")
SMALL_INT_RE = re.compile(r"^\s*(\d{1,4})\s*$")

SPELLED_INTS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}


def classify_literal(surface, ner_label):
    if not surface:
        return None, None
    s = normalize_whitespace(surface).rstrip(".,;:")
    m = YEAR_RE.match(s)
    if m:
        n = int(m.group(1))
        if 1000 <= n <= 2099:
            return "year", str(n)
        if 0 <= n <= 1000:
            return "int_small", str(n)
        return None, None
    if ner_label == "DATE":
        years = re.findall(r"\b(1\d{3}|20\d{2})\b", s)
        if years and len(set(years)) == 1:
            return "year", years[0]
        return None, None
    if SMALL_INT_RE.match(s):
        n = int(s)
        if 0 <= n <= 1000:
            return "int_small", str(n)
        return None, None
    if s.lower() in SPELLED_INTS:
        return "int_small", str(SPELLED_INTS[s.lower()])
    if "-" in s:
        parts = s.lower().split("-")
        if len(parts) == 2 and parts[0] in SPELLED_INTS and parts[1] in SPELLED_INTS:
            n = SPELLED_INTS[parts[0]] + SPELLED_INTS[parts[1]]
            if 0 <= n <= 1000:
                return "int_small", str(n)
    return None, None


def literal_canonical_id(literal_type, value):
    return f"lit.{literal_type}.{value}"


def type_hint_for_spacy_label(label):
    return {
        "PERSON": "person", "ORG": "org", "GPE": "gpe", "LOC": "loc",
        "FAC": "facility", "EVENT": "event", "WORK_OF_ART": "work",
        "LAW": "law", "LANGUAGE": "language",
        "DATE": "date", "TIME": "time",
        "PERCENT": "percent", "MONEY": "money", "QUANTITY": "quantity",
        "ORDINAL": "ordinal", "CARDINAL": "number",
        "NORP": "norp", "PRODUCT": "product",
    }.get(label, label.lower() if label else "thing")


# =============================================================================
# spaCy loader with model fallback
# =============================================================================

def load_spacy_with_fallback(preferred):
    import spacy
    chain = [preferred] + [m for m in
                           ("en_core_web_lg", "en_core_web_md", "en_core_web_sm")
                           if m != preferred]
    last_err = None
    for model in chain:
        try:
            nlp = spacy.load(model)
            print(f"[entity_census] spaCy model: {model}", file=sys.stderr)
            return nlp
        except OSError as e:
            last_err = e
            continue
    raise RuntimeError(
        "No usable spaCy English model found. Tried: " + str(chain)
        + ". Install one with: python -m spacy download en_core_web_sm."
    )


def ensure_spacy(census_state):
    if census_state["nlp"] is None:
        print(f"[entity_census] Loading spaCy model...", file=sys.stderr)
        census_state["nlp"] = load_spacy_with_fallback(census_state["spacy_model"])
        print(f"[entity_census] spaCy model loaded.", file=sys.stderr)
    return census_state["nlp"]


# =============================================================================
# Internal: entity table helpers
# =============================================================================

def find_by_id(census_state, ent_id):
    for e in census_state["entities"]:
        if e["ent_id"] == ent_id:
            return e
    raise KeyError(ent_id)


def looks_named(ent):
    if ent["pos"] == "name":
        return True
    if ent["type_hint"] in NAMED_TYPES:
        return True
    pc = ent["preferred_canonical"]
    if pc and pc[0].isupper() and not pc.isupper():
        return True
    return False


def types_compatible(t1, t2):
    return t1 == t2 or (t1 in NAMED_TYPES and t2 in NAMED_TYPES)


def should_merge(short_ent, long_ent):
    s = canonical_normalizer(short_ent["preferred_canonical"])
    l = canonical_normalizer(long_ent["preferred_canonical"])
    if not s or not l:
        return False
    if s == l:
        return True
    if sequence_similarity(s, l) > 0.94:
        return True
    s_tokens = s.split()
    l_tokens = l.split()
    if len(s_tokens) >= len(l_tokens):
        return False
    if re.search(r"\b" + re.escape(s) + r"\b", l):
        return True
    if set(s_tokens).issubset(set(l_tokens)):
        return True
    return False


def merge_into(census_state, ent, anchor):
    if ent["preferred_canonical"] not in anchor["aliases"]:
        anchor["aliases"].append(ent["preferred_canonical"])
    for a in ent["aliases"]:
        if a not in anchor["aliases"]:
            anchor["aliases"].append(a)
    anchor["mentions"].extend(ent["mentions"])
    norm_key = canonical_normalizer(ent["preferred_canonical"])
    census_state["by_surface_lower"][norm_key] = anchor["ent_id"]


def sent_index(doc, sent):
    for i, s in enumerate(doc.sents):
        if s.start == sent.start:
            return i
    return -1


def add_or_extend_entity(census_state, *, surface, pos, type_hint, sentence_id,
                         clause_id, span_start, span_end, resolved_by,
                         is_literal=False, literal_type=None,
                         literal_value=None):
    norm_key = canonical_normalizer(surface)
    if is_literal:
        norm_key = f"_lit_{literal_type}_{literal_value}"

    existing_id = census_state["by_surface_lower"].get(norm_key)
    if existing_id is not None:
        ent = find_by_id(census_state, existing_id)
    else:
        ent_id = f"ent_{len(census_state['entities']) + 1:03d}_{short_uuid()}"
        ent = new_entity(
            ent_id=ent_id,
            preferred_canonical=surface,
            type_hint=type_hint,
            pos=pos,
            is_literal=is_literal,
            literal_type=literal_type,
            literal_value=literal_value,
        )
        if is_literal:
            ent["nexus_namespace"] = "literal"
        census_state["entities"].append(ent)
        census_state["by_surface_lower"][norm_key] = ent_id

    ent["mentions"].append(new_mention(
        clause_id=clause_id,
        sentence_id=sentence_id,
        surface=surface,
        span_start=span_start,
        span_end=span_end,
        pos=pos,
        resolved_by=resolved_by,
    ))


# =============================================================================
# LLM enrichment for minted entities
# =============================================================================

def _llm_enrich_entity(ent, llm_cfg):
    """Ask the LLM to enrich a novel entity with structured metadata.

    Returns a dict with keys like 'type', 'domain', 'is_instance', 'is_compound',
    'is_metonymy', 'parent_category', 'gloss', or None if LLM unavailable.

    Results are cached by lemma so the same entity is not re-classified.
    """
    if llm_cfg is None or not call_llm.is_wrapper_configured(llm_cfg):
        return None

    lemma_lower = ent["preferred_canonical"].lower()
    cache_key = (lemma_lower, ent.get("pos", "noun"))
    cached = _LLM_ENRICH_CACHE.get(cache_key)
    if cached is not None:
        return cached

    context = ent.get("context_text", "") or ent["preferred_canonical"]
    prompt = f"""
Entity: "{ent['preferred_canonical']}"
Context: "{context[:250]}"

Analyze this entity and return ONE MDKV block of kind 'entity_analysis' with these fields:

type: one of: person, organization, location, medical_condition, drug, 
      chemical_compound, tool, device, software, animal, plant, food, 
      concept, event, law, regulation, financial_instrument, 
      geological_feature, physical_phenomenon, other_noun, other_proper_noun
domain: one of: general, medical, legal, scientific, technical, financial, 
        military, academic, artistic, culinary, natural, other
is_instance: true | false
is_compound: true | false
is_metonymy: true | false
is_acronym: true | false
is_technical_term: true | false
parent_category: the most specific hypernym you can infer (e.g., "tool", 
                 "disease", "musical instrument", "financial instrument")
gloss: a short definition (10-20 words)

Example:
:::entity_analysis
type: tool
domain: technical
is_instance: false
is_compound: true
is_metonymy: false
is_acronym: false
is_technical_term: true
parent_category: hand tool
gloss: a tool for driving screws with controlled torque
:::
"""
    try:
        raw = call_llm.call_llm(prompt, llm_cfg)
        blocks = parse_mdkv(raw)
        for b in blocks:
            if b.get("_kind") == "entity_analysis":
                _LLM_ENRICH_CACHE[cache_key] = b
                return b
        return None
    except Exception:
        return None


# =============================================================================
# Passes — all flat module-level functions
# =============================================================================

def pass1_collect(census_state, doc):
    print(f"  [entity_census] Pass 1: collecting entities...", file=sys.stderr, flush=True)
    for ent in doc.ents:
        if ent.label_ in DROP_NER_TYPES:
            continue
        type_hint = type_hint_for_spacy_label(ent.label_)
        lit_type, lit_value = classify_literal(ent.text, ent.label_)
        is_literal = lit_type is not None
        if ent.label_ in LITERAL_HINT_LABELS and not is_literal:
            continue
        if not is_literal and ent.label_ not in KEEP_NER_TYPES:
            continue
        pos = "name" if ent.label_ in ("PERSON", "ORG", "GPE", "LOC") else "noun"
        add_or_extend_entity(
            census_state,
            surface=ent.text,
            pos=pos,
            type_hint=type_hint,
            sentence_id=sent_index(doc, ent.sent),
            clause_id=0,
            span_start=ent.start_char,
            span_end=ent.end_char,
            resolved_by="direct",
            is_literal=is_literal,
            literal_type=lit_type,
            literal_value=lit_value,
        )

    covered = {(e.start_char, e.end_char) for e in doc.ents}
    for token in doc:
        if token.pos_ not in ("NOUN", "PROPN"):
            continue
        if token.dep_ not in ("nsubj", "nsubjpass", "dobj", "pobj", "attr",
                              "appos", "iobj", "dative", "oprd"):
            continue
        start, end = token.idx, token.idx + len(token.text)
        if (start, end) in covered:
            continue
        add_or_extend_entity(
            census_state,
            surface=token.text,
            pos="noun" if token.pos_ == "NOUN" else "name",
            type_hint="thing",
            sentence_id=sent_index(doc, token.sent),
            clause_id=0,
            span_start=start,
            span_end=end,
            resolved_by="direct",
        )
    print(f"  [entity_census] Pass 1 done: {len(census_state['entities'])} candidate entities", file=sys.stderr, flush=True)


def pass2_filter_noise(census_state):
    print(f"  [entity_census] Pass 2: filtering noise...", file=sys.stderr, flush=True)
    kept = []
    for e in census_state["entities"]:
        if e["is_literal"]:
            kept.append(e)
            continue
        if looks_like_noise(e["preferred_canonical"], e["type_hint"]):
            continue
        kept.append(e)
    census_state["entities"] = kept
    census_state["by_surface_lower"] = {}
    for e in census_state["entities"]:
        if e["is_literal"]:
            census_state["by_surface_lower"][
                f"_lit_{e['literal_type']}_{e['literal_value']}"
            ] = e["ent_id"]
        else:
            census_state["by_surface_lower"][
                canonical_normalizer(e["preferred_canonical"])
            ] = e["ent_id"]
    print(f"  [entity_census] Pass 2 done: {len(census_state['entities'])} entities remain", file=sys.stderr, flush=True)


def pass3_cluster(census_state):
    anchors = [e for e in census_state["entities"]
               if not e["is_literal"] and looks_named(e)]
    anchors.sort(key=lambda e: -len(e["preferred_canonical"].split()))
    merged = set()
    for ent in list(census_state["entities"]):
        if ent["ent_id"] in merged or ent["is_literal"]:
            continue
        if not looks_named(ent):
            continue
        for anchor in anchors:
            if anchor["ent_id"] == ent["ent_id"] or anchor["ent_id"] in merged:
                continue
            if not types_compatible(ent["type_hint"], anchor["type_hint"]):
                continue
            if should_merge(ent, anchor):
                merge_into(census_state, ent, anchor)
                merged.add(ent["ent_id"])
                break
    if merged:
        census_state["entities"] = [
            e for e in census_state["entities"] if e["ent_id"] not in merged
        ]


def nearest_preceding(track, sent_idx, pron_person):
    best = None
    best_dist = 1000
    for (s_idx, ent_id, gender, _num) in track:
        if s_idx > sent_idx:
            continue
        dist = sent_idx - s_idx
        if dist >= best_dist:
            continue
        if pron_person == "third" and gender in ("third", "third-m", "third-f", "third-n"):
            pass
        elif pron_person == "third-m" and gender in ("third-m", "third"):
            pass
        elif pron_person == "third-f" and gender in ("third-f", "third"):
            pass
        elif pron_person == "third-n" and gender in ("third-n", "third"):
            pass
        else:
            continue
        best = ent_id
        best_dist = dist
    return best


def pass4_resolve_pronouns(census_state, doc):
    print(f"  [entity_census] Pass 4: resolving pronouns...", file=sys.stderr, flush=True)
    ent_track = []
    for ent in census_state["entities"]:
        if ent["is_literal"]:
            continue
        for m in ent["mentions"]:
            gender = None
            if ent["type_hint"] == "person":
                gender = "third"
            elif ent["type_hint"] in ("org", "gpe", "loc", "facility"):
                gender = "third-n"
            ent_track.append((m["sentence_id"], ent["ent_id"], gender, "sing"))
    sentences = list(doc.sents)
    for s_idx, sent in enumerate(sentences):
        for token in sent:
            if token.pos_ != "PRON":
                continue
            key = token.text.lower()
            if key not in PRONOUNS:
                continue
            pron_person, pron_num = PRONOUNS[key]
            if not pron_person.startswith("third"):
                continue
            cand = nearest_preceding(ent_track, s_idx, pron_person)
            if cand is None:
                continue
            ent = find_by_id(census_state, cand)
            ent["mentions"].append(new_mention(
                clause_id=0,
                sentence_id=s_idx,
                surface=token.text,
                span_start=token.idx,
                span_end=token.idx + len(token.text),
                pos="pronoun",
                resolved_by="proximity",
            ))
            ent_track.append((s_idx, ent["ent_id"], pron_person, pron_num or "sing"))
    print(f"  [entity_census] Pass 4 done.", file=sys.stderr, flush=True)


def get_or_create_anonymous_entity(census_state, doc, head_tok):
    head_key = canonical_normalizer(head_tok.text)
    head_id = census_state["by_surface_lower"].get(head_key)
    if head_id:
        head_ent = find_by_id(census_state, head_id)
        head_ent["anonymous"] = True
        return head_id, head_ent
    head_id = f"ent_{len(census_state['entities']) + 1:03d}_{short_uuid()}"
    head_ent = new_entity(
        ent_id=head_id,
        preferred_canonical=head_tok.text,
        type_hint="thing",
        pos="noun",
    )
    head_ent["anonymous"] = True
    head_ent["nexus_namespace"] = "ghost"
    head_ent["mentions"].append(new_mention(
        clause_id=0,
        sentence_id=sent_index(doc, head_tok.sent),
        surface=head_tok.text,
        span_start=head_tok.idx,
        span_end=head_tok.idx + len(head_tok.text),
        pos="noun",
        resolved_by="possessive",
    ))
    census_state["entities"].append(head_ent)
    census_state["by_surface_lower"][head_key] = head_id
    return head_id, head_ent


def pass5_possessive_chains(census_state, doc):
    print(f"  [entity_census] Pass 5: possessive chains...", file=sys.stderr, flush=True)
    for token in doc:
        if token.dep_ != "poss":
            continue
        possessor_tok = token
        head_tok = token.head
        if head_tok.pos_ not in ("NOUN", "PROPN"):
            continue
        possessor_id = census_state["by_surface_lower"].get(
            canonical_normalizer(possessor_tok.text))
        if not possessor_id:
            continue
        _, head_ent = get_or_create_anonymous_entity(census_state, doc, head_tok)
        head_ent["chain"].append({
            "role": "HAS_POSSESSOR",
            "target_ent_id": possessor_id,
        })
    print(f"  [entity_census] Pass 5 done.", file=sys.stderr, flush=True)


def pass5b_harvest_context(census_state, doc):
    print(f"  [entity_census] Pass 5b: harvesting context...", file=sys.stderr, flush=True)
    sents = list(doc.sents)
    if not sents:
        return
    for ent in census_state["entities"]:
        if ent["is_literal"]:
            continue
        if not ent["mentions"]:
            continue
        longest = max(ent["mentions"], key=lambda m: len(m["surface"] or ""))
        s_idx = None
        for i, sent in enumerate(sents):
            if sent.start_char <= longest["span_start"] < sent.end_char:
                s_idx = i
                break
        if s_idx is None:
            if 0 <= longest["sentence_id"] < len(sents):
                s_idx = longest["sentence_id"]
            else:
                continue
        lo = max(0, s_idx - 1)
        hi = min(len(sents), s_idx + 2)
        window_sents = sents[lo:hi]
        ent["context_text"] = " ".join(
            normalize_whitespace(s.text) for s in window_sents
        ).strip()
    print(f"  [entity_census] Pass 5b done.", file=sys.stderr, flush=True)


def _apply_lookup_result_to_entity(ent, result):
    ent["lexicon_canonical_id"] = result.get("canonical_id")
    ent["lookup_decision_level"] = result.get("decision_level", 0)
    ent["lookup_confidence"] = float(result.get("confidence", 0.0))
    ent["minted"] = bool(result.get("minted", False))
    ent["specificity"] = result.get("specificity")
    ent["maturity_tier"] = result.get("maturity_tier")
    ent["rewritten_to_standard"] = bool(result.get("rewritten_to_standard", False))
    ent["matched_canonical_id"] = result.get("matched_canonical_id")

    cid = result.get("canonical_id", "")
    if cid.startswith("lit."):
        ent["nexus_namespace"] = "literal"
    elif cid.startswith("doc.") or cid.startswith("dyn.") or cid.startswith("corp."):
        ent["nexus_namespace"] = "custom"
    elif ent.get("is_literal"):
        ent["nexus_namespace"] = "literal"
    elif ent.get("minted"):
        ent["nexus_namespace"] = "custom"
    else:
        ent["nexus_namespace"] = "synapedia"


def pass6_lookup(census_state):
    cfg = census_state["cfg"]
    llm_cfg = census_state.get("llm_cfg")
    verbose = census_state["verbose"]

    total = len(census_state["entities"])
    looked_up = 0
    found_count = 0
    minted_count = 0
    cache_hits = 0
    enriched_count = 0
    last_print = time.time()
    print(f"  [entity_census] Pass 6: lexicon lookup for {total} entities...", file=sys.stderr, flush=True)

    for ent in census_state["entities"]:
        if ent["is_literal"]:
            ent["lexicon_canonical_id"] = literal_canonical_id(
                ent["literal_type"], ent["literal_value"])
            ent["lookup_decision_level"] = 0
            ent["lookup_confidence"] = 1.0
            ent["minted"] = False
            ent["nexus_namespace"] = "literal"
            looked_up += 1
            continue

        pos_hint = "name" if ent["pos"] == "name" else "noun"

        # ── Cache check: same lemma + POS → skip HTTP call ──
        cache_key = (ent["preferred_canonical"].lower(), pos_hint)
        cached = _LOOKUP_CACHE.get(cache_key)
        if cached is not None:
            _apply_lookup_result_to_entity(ent, cached)
            looked_up += 1
            cache_hits += 1
            if cached.get("minted"):
                minted_count += 1
            elif cached.get("canonical_id"):
                found_count += 1
            now = time.time()
            if looked_up % 20 == 0 or now - last_print > 5:
                remaining = total - looked_up
                print(f"  [entity_census] Lookup {looked_up}/{total}: {found_count} found, {minted_count} minted, {enriched_count} enriched, {cache_hits} cached, {remaining} remaining", file=sys.stderr, flush=True)
                last_print = now
            continue
        # ── End cache check ──

        candidates = [ent["preferred_canonical"]]
        for alias in ent["aliases"]:
            if alias not in candidates:
                candidates.append(alias)

        best_result = None
        for target in candidates:
            try:
                result = lookup_in_lexicon(
                    target=target,
                    context=ent["preferred_canonical"],
                    pos_hint=pos_hint,
                    cfg=cfg,
                    enable_mint=False,
                    llm_cfg=llm_cfg,
                )
            except Exception as e:
                if verbose:
                    print(f"[!] lookup failed for {target}: {e}", file=sys.stderr)
                continue
            if result.get("canonical_id") and result.get("decision_level") in (1, 2):
                best_result = result
                break
            if best_result is None:
                best_result = result

        if best_result is None or not best_result.get("canonical_id"):
            try:
                mint_result = lookup_in_lexicon(
                    target=ent["preferred_canonical"],
                    context=ent["preferred_canonical"],
                    pos_hint=pos_hint,
                    cfg=cfg,
                    enable_mint=True,
                    llm_cfg=llm_cfg,
                )
                best_result = mint_result
            except Exception:
                continue

        if best_result is not None:
            _apply_lookup_result_to_entity(ent, best_result)
            _LOOKUP_CACHE[cache_key] = best_result  # Store in cache

            # ── LLM enrichment for minted entities ──
            if ent.get("minted") and llm_cfg is not None:
                enrichment = _llm_enrich_entity(ent, llm_cfg)
                if enrichment:
                    ent["llm_type_hint"] = enrichment.get("type")
                    ent["llm_domain"] = enrichment.get("domain")
                    ent["llm_is_instance"] = enrichment.get("is_instance") == "true"
                    ent["llm_is_compound"] = enrichment.get("is_compound") == "true"
                    ent["llm_is_metonymy"] = enrichment.get("is_metonymy") == "true"
                    ent["llm_is_acronym"] = enrichment.get("is_acronym") == "true"
                    ent["llm_is_technical_term"] = enrichment.get("is_technical_term") == "true"
                    ent["llm_parent_category"] = enrichment.get("parent_category")
                    ent["llm_gloss"] = enrichment.get("gloss")
                    enriched_count += 1
                    if verbose:
                        print(f"    enriched '{ent['preferred_canonical']}' -> type={enrichment.get('type')} domain={enrichment.get('domain')}", file=sys.stderr)

        looked_up += 1
        if ent.get("minted"):
            minted_count += 1
        elif ent.get("lexicon_canonical_id"):
            found_count += 1

        now = time.time()
        if looked_up % 10 == 0 or now - last_print > 5:
            remaining = total - looked_up
            print(f"  [entity_census] Lookup {looked_up}/{total}: {found_count} found, {minted_count} minted, {enriched_count} enriched, {cache_hits} cached, {remaining} remaining", file=sys.stderr, flush=True)
            last_print = now

    print(f"  [entity_census] Pass 6 done: {found_count} found, {minted_count} minted, {enriched_count} enriched, {cache_hits} cache hits", file=sys.stderr, flush=True)


def emit(census_state, doc_id, source_text):
    return {
        "doc_id": doc_id,
        "source_length_chars": len(source_text),
        "entity_count": len(census_state["entities"]),
        "entities": list(census_state["entities"]),
    }


# =============================================================================
# Public driver
# =============================================================================

def process_document(text, *, cfg=None, doc_id="doc_001", run_lookup=True,
                     verbose=False, llm_cfg=None,
                     accuracy_mode="standard"):
    if cfg is None:
        cfg = load_config()

    census_state = new_census_state(
        cfg, run_lookup=run_lookup, verbose=verbose, llm_cfg=llm_cfg,
        accuracy_mode=accuracy_mode,
    )
    nlp = ensure_spacy(census_state)
    doc = nlp(text)

    pass1_collect(census_state, doc)
    pass2_filter_noise(census_state)

    print(f"  [entity_census] Pass 3: clustering aliases...", file=sys.stderr, flush=True)
    for iteration in range(5):
        before = len(census_state["entities"])
        pass3_cluster(census_state)
        if len(census_state["entities"]) == before:
            if verbose and iteration > 0:
                print(f"[entity_census] alias clustering converged after {iteration + 1} passes", file=sys.stderr)
            break

    pass4_resolve_pronouns(census_state, doc)
    pass5_possessive_chains(census_state, doc)
    pass5b_harvest_context(census_state, doc)

    if run_lookup:
        pass6_lookup(census_state)

    return emit(census_state, doc_id, text)


# =============================================================================
# CLI
# =============================================================================

def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--doc-id", default="doc_001")
    p.add_argument("--no-lookup", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--config", default=None)
    p.add_argument("--accuracy-mode", default="standard",
                   choices=["casual", "standard", "rigorous"])
    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"Input file not found: {in_path}", file=sys.stderr)
        return 1
    text = in_path.read_text(encoding="utf-8")

    cfg = load_config(args.config) if args.config else load_config()
    llm_cfg = None
    if _HAVE_CALL_LLM:
        try:
            llm_cfg = call_llm.load_llm_config(cfg.get("_config_path"))
        except Exception:
            llm_cfg = None

    emap = process_document(
        text,
        cfg=cfg,
        doc_id=args.doc_id,
        run_lookup=not args.no_lookup,
        verbose=args.verbose,
        llm_cfg=llm_cfg,
        accuracy_mode=args.accuracy_mode,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(emap, indent=2), encoding="utf-8")

    print()
    print(f"Wrote {emap['entity_count']:,} entities to {out_path}")
    if args.verbose:
        for e in emap["entities"][:40]:
            cid = e.get("lexicon_canonical_id") or "(unmapped)"
            lvl = e.get("lookup_decision_level", 0)
            ns = e.get("nexus_namespace", "?")
            tag = " [LITERAL]" if e.get("is_literal") else ""
            enrich = ""
            if e.get("llm_type_hint"):
                enrich = f" type={e['llm_type_hint']}"
            print(f"  {e['preferred_canonical']:<35} -> {cid}  (level {lvl}){tag}{enrich}  ns={ns}")
    return 0


if __name__ == "__main__":
    sys.exit(main())