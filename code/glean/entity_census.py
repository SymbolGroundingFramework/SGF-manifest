#!/usr/bin/env python3
"""
entity_census.py — Stage 4 of the GLEAN pipeline

Identify every entity in a document, cluster aliases, resolve pronouns,
detect possessive chains, classify literals, and emit an Entity Map JSON.

CHANGES IN v1.1
---------------
- Add possessive stripping (Beethoven's -> Beethoven), including curly
  apostrophes.
- Add canonical_text_normalizer for clustering.
- Add looks_like_noise() filter to drop abbreviation junk and bare numbers.
- Rewrite alias merging to use SequenceMatcher similarity and word-boundary
  containment, not just suffix-token-match.
- Classify DATE/CARDINAL/ORDINAL/MONEY/PERCENT/QUANTITY entities. Years and
  small integers (0-1000) become 'literal' entities with lit.<type>.<value>
  canonical_ids; the rest are dropped from the entity table and stay only
  as target_surface on synapse spokes (handled by clause_to_synapse.py).
- spaCy model fallback: try config, then en_core_web_lg, then md, then sm.

Output is a single JSON file that downstream stages (clause_to_synapse,
framing) read to ground every reference to a canonical_id.

Usage:
    python entity_census.py --input INPUT.txt --output entity_map.json
    python entity_census.py --input INPUT.txt --output entity_map.json --no-lookup
    python entity_census.py --input INPUT.txt --output entity_map.json --verbose
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sgflib import LexiconClient, LITERAL_NER_LABELS, load_config


# =============================================================================
# Data structures
# =============================================================================

@dataclass
class Mention:
    clause_id: int
    sentence_id: int
    surface: str
    span_start: int
    span_end: int
    pos: str
    resolved_by: str = "direct"


@dataclass
class Entity:
    ent_id: str
    preferred_canonical: str
    type_hint: str
    pos: str
    aliases: list[str] = field(default_factory=list)
    mentions: list[Mention] = field(default_factory=list)
    anonymous: bool = False
    chain: list[dict] = field(default_factory=list)
    # Adjacent-text harvest — sentence(s) around the FIRST occurrence of
    # the longest surface form. Used as embedding context at lookup time.
    context_text: str = ""
    # Lexicon lookup
    lexicon_canonical_id: str | None = None
    lookup_decision_level: int = 0
    lookup_confidence: float = 0.0
    minted: bool = False
    # Literal info (when this is a year/number, not a real entity)
    is_literal: bool = False
    literal_type: str | None = None        # 'year', 'int_small'
    literal_value: str | None = None       # normalized value as string


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
    "their":("third",   "plur"),
    "theirs":("third",  "plur"),
}

KEEP_NER_TYPES = {
    "PERSON", "ORG", "GPE", "LOC", "NORP", "WORK_OF_ART",
    "EVENT", "FAC", "PRODUCT", "LANGUAGE",
}

# These produce literals (some kept as nodes, some dropped) — see classify
LITERAL_HINT_LABELS = LITERAL_NER_LABELS

DROP_NER_TYPES = {
    "LAW",      # often noisy in v1
}


# =============================================================================
# Helpers
# =============================================================================

def short_uuid() -> str:
    return uuid.uuid4().hex[:8]


def strip_possessive(text: str) -> str:
    if not text:
        return text
    t = text.replace("\u2019", "'")
    if re.search(r"'s$", t, flags=re.IGNORECASE):
        t = re.sub(r"'s$", "", t, flags=re.IGNORECASE)
    elif re.search(r"s'$", t, flags=re.IGNORECASE):
        t = re.sub(r"s'$", "", t, flags=re.IGNORECASE)
    return t.strip()


def strip_outer_quotes(text: str) -> str:
    if not text:
        return text
    t = text.strip()
    if len(t) >= 2 and t[0] in "\"'\u201C\u2018" and t[-1] in "\"'\u201D\u2019":
        t = t[1:-1]
    return t.strip()


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_leading_the(text: str) -> str:
    if not text:
        return text
    if text.lower().startswith("the "):
        return text[4:].strip()
    return text


def canonical_normalizer(text: str) -> str:
    """Lowercase + strip quotes + strip possessive + collapse whitespace.
    Used for clustering and alias-key matching."""
    t = normalize_whitespace(text)
    t = strip_outer_quotes(t)
    t = strip_possessive(t)
    t = normalize_leading_the(t)
    t = normalize_whitespace(t)
    return t.lower()


def sequence_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def looks_like_noise(canonical: str, ent_type: str) -> bool:
    """Filter for entities that are more trouble than they're worth."""
    if not canonical:
        return True
    t = normalize_whitespace(canonical).strip("#").strip()
    if not t:
        return True

    # Very short non-DATE tokens
    if ent_type != "DATE" and len(t) <= 2 and not re.search(r"[A-Za-z]", t):
        return True

    # Bare punctuation
    if re.fullmatch(r"[\.\,\;\:\-\"'`]+", t):
        return True

    # Common-noun phrases that aren't entities
    junk_phrases = {
        "the middle of the", "his first decade", "two centuries ago",
        "a few", "some time", "a moment",
    }
    if t.lower() in junk_phrases:
        return True

    # Abbreviation soup ("t. m. o.")
    if re.search(r"\b[a-z]\.\s*[a-z]\.\s*[a-z]\b", t.lower()):
        return True

    return False


# -----------------------------------------------------------------------------
# Literal classification
# -----------------------------------------------------------------------------

YEAR_RE = re.compile(r"^\s*(\d{3,4})\s*$")
SMALL_INT_RE = re.compile(r"^\s*(\d{1,4})\s*$")

# Spelled-out small integers (handle a useful subset; full English number
# parsing is out of v1 scope)
SPELLED_INTS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}


def classify_literal(surface: str, ner_label: str) -> tuple[str | None, str | None]:
    """Decide if a surface form is a node-worthy literal.

    Returns (literal_type, normalized_value) or (None, None) if it's
    not node-worthy. Node-worthy literals get lit.<type>.<value>
    canonical_ids. Non-node-worthy literals stay as target_surface only.

    Rules:
      - Year (4-digit number in 1000-2099 range, or year inside a DATE) -> node
      - Small integer 0-1000 (digit or spelled) -> node
      - Specific calendar dates ("December 17, 1770") -> NOT a node
      - Large numbers -> NOT a node
      - Money, percent -> NOT a node
    """
    if not surface:
        return None, None
    s = normalize_whitespace(surface).rstrip(".,;:")

    # 4-digit year
    m = YEAR_RE.match(s)
    if m:
        n = int(m.group(1))
        if 1000 <= n <= 2099:
            return "year", str(n)
        if 0 <= n <= 1000:
            return "int_small", str(n)
        return None, None

    # DATE label: try to extract the year from inside
    if ner_label == "DATE":
        years = re.findall(r"\b(1\d{3}|20\d{2})\b", s)
        if years and len(set(years)) == 1:
            return "year", years[0]
        # Otherwise the date is too specific to be a node
        return None, None

    # Bare small integer
    if SMALL_INT_RE.match(s):
        n = int(s)
        if 0 <= n <= 1000:
            return "int_small", str(n)
        return None, None

    # Spelled small integer (single word)
    if s.lower() in SPELLED_INTS:
        return "int_small", str(SPELLED_INTS[s.lower()])

    # Compound spelled like "twenty-one"
    if "-" in s:
        parts = s.lower().split("-")
        if len(parts) == 2 and parts[0] in SPELLED_INTS and parts[1] in SPELLED_INTS:
            n = SPELLED_INTS[parts[0]] + SPELLED_INTS[parts[1]]
            if 0 <= n <= 1000:
                return "int_small", str(n)

    return None, None


def literal_canonical_id(literal_type: str, value: str) -> str:
    return f"lit.{literal_type}.{value}"


# -----------------------------------------------------------------------------
# Type hint mapping
# -----------------------------------------------------------------------------

def type_hint_for_spacy_label(label: str) -> str:
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

def load_spacy_with_fallback(preferred: str):
    """Try preferred first, then a fallback chain of large -> medium -> small."""
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
        f"No usable spaCy English model found. Tried: {chain}. "
        f"Install one with: python -m spacy download en_core_web_sm. "
        f"Last error: {last_err}"
    )


# =============================================================================
# The census
# =============================================================================

class EntityCensus:

    _NAMED_TYPES = {"person", "org", "gpe", "loc", "facility", "work",
                    "norp", "product", "event", "thing"}

    def __init__(self, cfg, *, run_lookup: bool = True, verbose: bool = False):
        self.cfg = cfg
        self.run_lookup = run_lookup
        self.verbose = verbose
        self.entities: list[Entity] = []
        self._by_surface_lower: dict[str, str] = {}
        self._lex = LexiconClient(cfg) if run_lookup else None
        self._spacy_model = cfg.raw["spacy"]["model"]
        self._nlp = None

    def _load_spacy(self):
        if self._nlp is None:
            self._nlp = load_spacy_with_fallback(self._spacy_model)

    def process(self, text: str, doc_id: str = "doc_001") -> dict:
        self._load_spacy()
        doc = self._nlp(text)

        self._pass1_collect(doc)
        self._pass2_filter_noise()
        # Multi-pass alias clustering: run until no more merges happen.
        # Capped at 5 iterations to avoid pathological loops.
        for iteration in range(5):
            before = len(self.entities)
            self._pass3_cluster()
            if len(self.entities) == before:
                if self.verbose and iteration > 0:
                    print(f"[entity_census] alias clustering converged after "
                          f"{iteration + 1} passes", file=sys.stderr)
                break
        self._pass4_resolve_pronouns(doc)
        self._pass5_possessive_chains(doc)
        self._pass5b_harvest_context(doc, text)
        if self.run_lookup:
            self._pass6_lookup()

        return self._emit(doc_id, text)

    # ---- Pass 1: collect ----

    def _pass1_collect(self, doc):
        # 1a. Named entities
        for ent in doc.ents:
            if ent.label_ in DROP_NER_TYPES:
                continue
            type_hint = type_hint_for_spacy_label(ent.label_)
            # Check for literal classification
            lit_type, lit_value = classify_literal(ent.text, ent.label_)
            is_literal = lit_type is not None
            # If this is a literal NER label but didn't classify as a node,
            # skip it entirely (it'll appear as target_surface on a spoke)
            if ent.label_ in LITERAL_HINT_LABELS and not is_literal:
                continue
            if not is_literal and ent.label_ not in KEEP_NER_TYPES:
                # Unrecognized non-literal NER label: skip
                continue

            pos = "name" if ent.label_ in ("PERSON", "ORG", "GPE", "LOC") else "noun"
            self._add_or_extend_entity(
                surface=ent.text,
                pos=pos,
                type_hint=type_hint,
                sentence_id=self._sent_index(doc, ent.sent),
                clause_id=0,
                span_start=ent.start_char,
                span_end=ent.end_char,
                resolved_by="direct",
                is_literal=is_literal,
                literal_type=lit_type,
                literal_value=lit_value,
            )

        # 1b. Role-noun heads not covered by NER (open vocabulary, no literals here)
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
            self._add_or_extend_entity(
                surface=token.text,
                pos="noun" if token.pos_ == "NOUN" else "name",
                type_hint="thing",
                sentence_id=self._sent_index(doc, token.sent),
                clause_id=0,
                span_start=start,
                span_end=end,
                resolved_by="direct",
            )

    def _sent_index(self, doc, sent) -> int:
        for i, s in enumerate(doc.sents):
            if s.start == sent.start:
                return i
        return -1

    def _add_or_extend_entity(self, *, surface, pos, type_hint, sentence_id,
                              clause_id, span_start, span_end, resolved_by,
                              is_literal=False, literal_type=None,
                              literal_value=None):
        # Normalize for de-duplication keying
        norm_key = canonical_normalizer(surface)
        if is_literal:
            # Literals dedupe on their value, not surface
            norm_key = f"_lit_{literal_type}_{literal_value}"

        existing_id = self._by_surface_lower.get(norm_key)
        if existing_id is not None:
            ent = self._find_by_id(existing_id)
        else:
            ent_id = f"ent_{len(self.entities) + 1:03d}_{short_uuid()}"
            ent = Entity(
                ent_id=ent_id,
                preferred_canonical=surface,
                type_hint=type_hint,
                pos=pos,
                aliases=[surface],
                is_literal=is_literal,
                literal_type=literal_type,
                literal_value=literal_value,
            )
            self.entities.append(ent)
            self._by_surface_lower[norm_key] = ent_id

        ent.mentions.append(Mention(
            clause_id=clause_id,
            sentence_id=sentence_id,
            surface=surface,
            span_start=span_start,
            span_end=span_end,
            pos=pos,
            resolved_by=resolved_by,
        ))

    def _find_by_id(self, ent_id: str) -> Entity:
        for e in self.entities:
            if e.ent_id == ent_id:
                return e
        raise KeyError(ent_id)

    # ---- Pass 2: drop noise ----

    def _pass2_filter_noise(self):
        kept = []
        for e in self.entities:
            if e.is_literal:
                kept.append(e)
                continue
            if looks_like_noise(e.preferred_canonical, e.type_hint):
                continue
            kept.append(e)
        self.entities = kept
        # Rebuild surface index
        self._by_surface_lower = {}
        for e in self.entities:
            if e.is_literal:
                self._by_surface_lower[f"_lit_{e.literal_type}_{e.literal_value}"] = e.ent_id
            else:
                self._by_surface_lower[canonical_normalizer(e.preferred_canonical)] = e.ent_id

    # ---- Pass 3: alias cluster (Hoplogic-inspired heuristic) ----

    def _pass3_cluster(self):
        """Merge entities whose surface forms are aliases of one another."""
        # Anchors: every non-literal entity that looks named
        anchors = [e for e in self.entities
                   if not e.is_literal and self._looks_named(e)]
        anchors.sort(key=lambda e: -len(e.preferred_canonical.split()))

        merged: set[str] = set()
        for ent in list(self.entities):
            if ent.ent_id in merged or ent.is_literal:
                continue
            if not self._looks_named(ent):
                continue
            for anchor in anchors:
                if anchor.ent_id == ent.ent_id or anchor.ent_id in merged:
                    continue
                if not self._types_compatible(ent.type_hint, anchor.type_hint):
                    continue
                if self._should_merge(ent, anchor):
                    self._merge_into(ent, anchor)
                    merged.add(ent.ent_id)
                    break

        if merged:
            self.entities = [e for e in self.entities if e.ent_id not in merged]

    def _looks_named(self, ent: Entity) -> bool:
        if ent.pos == "name":
            return True
        if ent.type_hint in self._NAMED_TYPES:
            return True
        if (ent.preferred_canonical and ent.preferred_canonical[0].isupper()
                and not ent.preferred_canonical.isupper()):
            return True
        return False

    @classmethod
    def _types_compatible(cls, t1: str, t2: str) -> bool:
        return t1 == t2 or (t1 in cls._NAMED_TYPES and t2 in cls._NAMED_TYPES)

    def _should_merge(self, short_ent: Entity, long_ent: Entity) -> bool:
        s = canonical_normalizer(short_ent.preferred_canonical)
        l = canonical_normalizer(long_ent.preferred_canonical)
        if not s or not l:
            return False
        if s == l:
            return True
        if sequence_similarity(s, l) > 0.94:
            return True
        # Single-token-in-multi-token (Beethoven in Ludwig van Beethoven)
        s_tokens = s.split()
        l_tokens = l.split()
        if len(s_tokens) >= len(l_tokens):
            return False
        # Word-boundary substring match
        if re.search(r"\b" + re.escape(s) + r"\b", l):
            return True
        # Subset of tokens
        if set(s_tokens).issubset(set(l_tokens)):
            return True
        return False

    def _merge_into(self, ent: Entity, anchor: Entity):
        if ent.preferred_canonical not in anchor.aliases:
            anchor.aliases.append(ent.preferred_canonical)
        for a in ent.aliases:
            if a not in anchor.aliases:
                anchor.aliases.append(a)
        anchor.mentions.extend(ent.mentions)
        norm_key = canonical_normalizer(ent.preferred_canonical)
        self._by_surface_lower[norm_key] = anchor.ent_id

    # ---- Pass 4: pronoun resolution ----

    def _pass4_resolve_pronouns(self, doc):
        ent_track: list[tuple[int, str, str | None, str]] = []
        for ent in self.entities:
            if ent.is_literal:
                continue
            for m in ent.mentions:
                gender = None
                if ent.type_hint == "person":
                    gender = "third"
                elif ent.type_hint in ("org", "gpe", "loc", "facility"):
                    gender = "third-n"
                ent_track.append((m.sentence_id, ent.ent_id, gender, "sing"))

        sentences = list(doc.sents)
        for sent_idx, sent in enumerate(sentences):
            for token in sent:
                if token.pos_ != "PRON":
                    continue
                key = token.text.lower()
                if key not in PRONOUNS:
                    continue
                pron_person, pron_num = PRONOUNS[key]
                if not pron_person.startswith("third"):
                    continue
                cand = self._nearest_preceding(ent_track, sent_idx, pron_person)
                if cand is None:
                    continue
                ent = self._find_by_id(cand)
                ent.mentions.append(Mention(
                    clause_id=0,
                    sentence_id=sent_idx,
                    surface=token.text,
                    span_start=token.idx,
                    span_end=token.idx + len(token.text),
                    pos="pronoun",
                    resolved_by="proximity",
                ))
                ent_track.append((sent_idx, ent.ent_id, pron_person,
                                  pron_num or "sing"))

    @staticmethod
    def _nearest_preceding(track, sent_idx, pron_person) -> str | None:
        best = None
        best_dist = 1000
        for (s_idx, ent_id, gender, _num) in track:
            if s_idx > sent_idx:
                continue
            dist = sent_idx - s_idx
            if dist >= best_dist:
                continue
            if pron_person == "third" and gender in ("third", "third-m",
                                                     "third-f", "third-n"):
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

    # ---- Pass 5: possessive chains ----

    def _get_or_create_anonymous_entity(self, doc, head_tok):
        """Find existing entity for head_tok or create an anonymous one.

        Returns (ent_id, ent). The returned entity is marked anonymous.
        Lexicon-agnostic: works for any noun, no hard-coded words.
        """
        head_key = canonical_normalizer(head_tok.text)
        head_id = self._by_surface_lower.get(head_key)
        if head_id:
            head_ent = self._find_by_id(head_id)
            head_ent.anonymous = True
            return head_id, head_ent

        head_id = f"ent_{len(self.entities) + 1:03d}_{short_uuid()}"
        head_ent = Entity(
            ent_id=head_id,
            preferred_canonical=head_tok.text,
            type_hint="thing",
            pos="noun",
            aliases=[head_tok.text],
            anonymous=True,
        )
        head_ent.mentions.append(Mention(
            clause_id=0,
            sentence_id=self._sent_index(doc, head_tok.sent),
            surface=head_tok.text,
            span_start=head_tok.idx,
            span_end=head_tok.idx + len(head_tok.text),
            pos="noun",
            resolved_by="possessive",
        ))
        self.entities.append(head_ent)
        self._by_surface_lower[head_key] = head_id
        return head_id, head_ent

    def _pass5_possessive_chains(self, doc):
        """Build possessive chains. Walks every 'poss' dep in the doc, so
        deeper chains (e.g., "Beethoven's father's house") emerge naturally
        because spaCy already represents them via stacked poss edges.
        """
        for token in doc:
            if token.dep_ != "poss":
                continue
            possessor_tok = token
            head_tok = token.head
            if head_tok.pos_ not in ("NOUN", "PROPN"):
                continue

            possessor_id = self._by_surface_lower.get(
                canonical_normalizer(possessor_tok.text))
            if not possessor_id:
                continue

            _, head_ent = self._get_or_create_anonymous_entity(doc, head_tok)

            head_ent.chain.append({
                "role": "HAS_POSSESSOR",
                "target_ent_id": possessor_id,
            })

    # ---- Pass 5b: adjacent-text harvest ----

    def _pass5b_harvest_context(self, doc, source_text: str):
        """For each entity, harvest the sentence(s) around the FIRST
        occurrence of its LONGEST surface form.

        Why: the entity's local context is a stronger embedding signal than
        the bare surface form alone. This also lets ad-hoc minted senses be
        useful, since the context becomes the gloss.

        Window: the mention sentence plus one neighbor on each side. The
        rule is lexicon-agnostic; no domain tokens are hard-coded.
        """
        sents = list(doc.sents)
        if not sents:
            return

        for ent in self.entities:
            if ent.is_literal:
                continue
            if not ent.mentions:
                continue

            longest = max(ent.mentions, key=lambda m: len(m.surface or ""))
            sent_idx = None
            for i, sent in enumerate(sents):
                if sent.start_char <= longest.span_start < sent.end_char:
                    sent_idx = i
                    break
            if sent_idx is None:
                if 0 <= longest.sentence_id < len(sents):
                    sent_idx = longest.sentence_id
                else:
                    continue

            lo = max(0, sent_idx - 1)
            hi = min(len(sents), sent_idx + 2)
            window_sents = sents[lo:hi]
            ent.context_text = " ".join(
                normalize_whitespace(s.text) for s in window_sents
            ).strip()

    # ---- Pass 6: lexicon lookup ----

    def _pass6_lookup(self):
        """Look up each entity in the lexicon.

        Strategy: try the FULL canonical (longest known surface form)
        first; if it doesn't resolve well, fall back to shorter aliases.
        This means "Ludwig van Beethoven" gets tried before "Beethoven",
        making the resulting canonical_id more specific where possible.
        """
        for ent in self.entities:
            if ent.is_literal:
                ent.lexicon_canonical_id = literal_canonical_id(
                    ent.literal_type, ent.literal_value)
                ent.lookup_decision_level = 0      # literal, no cascade
                ent.lookup_confidence = 1.0
                ent.minted = False
                continue
            pos_hint = "name" if ent.pos == "name" else "noun"

            # Try the full canonical first; if minted (no good match),
            # fall back through shorter aliases looking for a real hit.
            candidates = [ent.preferred_canonical]
            for alias in ent.aliases:
                if alias not in candidates:
                    candidates.append(alias)

            best_result = None
            for target in candidates:
                try:
                    result = self._lex.lookup(
                        target=target,
                        context=ent.preferred_canonical,
                        pos_hint=pos_hint,
                        enable_llm=False,
                        enable_mint=False,         # don't mint yet
                    )
                except Exception as e:
                    if self.verbose:
                        print(f"[!] lookup failed for {target}: {e}",
                              file=sys.stderr)
                    continue
                if result.canonical_id and result.decision_level in (1, 2):
                    best_result = result
                    break
                if best_result is None:
                    best_result = result

            if best_result is None or not best_result.canonical_id:
                # Mint a doc-scoped entry using the FULL canonical form
                try:
                    mint_result = self._lex.lookup(
                        target=ent.preferred_canonical,
                        context=ent.preferred_canonical,
                        pos_hint=pos_hint,
                        enable_llm=False,
                        enable_mint=True,
                    )
                    best_result = mint_result
                except Exception:
                    continue

            ent.lexicon_canonical_id = best_result.canonical_id
            ent.lookup_decision_level = best_result.decision_level
            ent.lookup_confidence = best_result.confidence
            ent.minted = best_result.minted

    # ---- Pass 7: emit ----

    def _emit(self, doc_id: str, source_text: str) -> dict:
        return {
            "doc_id": doc_id,
            "source_length_chars": len(source_text),
            "entity_count": len(self.entities),
            "entities": [asdict(e) for e in self.entities],
        }

    def close(self):
        if self._lex:
            self._lex.close()


# =============================================================================
# CLI
# =============================================================================

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--doc-id", default="doc_001")
    p.add_argument("--no-lookup", action="store_true")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"Input file not found: {in_path}", file=sys.stderr)
        return 1
    text = in_path.read_text(encoding="utf-8")

    cfg = load_config()
    census = EntityCensus(cfg, run_lookup=not args.no_lookup, verbose=args.verbose)
    try:
        emap = census.process(text, doc_id=args.doc_id)
    finally:
        census.close()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(emap, indent=2), encoding="utf-8")

    print()
    print(f"Wrote {emap['entity_count']:,} entities to {out_path}")
    if args.verbose:
        for e in emap["entities"][:40]:
            cid = e.get("lexicon_canonical_id") or "(unmapped)"
            lvl = e.get("lookup_decision_level", 0)
            tag = " [LITERAL]" if e.get("is_literal") else ""
            print(f"  {e['preferred_canonical']:<35} -> {cid}  (level {lvl}){tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
