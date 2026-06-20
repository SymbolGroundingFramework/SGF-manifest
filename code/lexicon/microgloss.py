#!/usr/bin/env python3
"""
micro_gloss_v4.py

Lexicon-agnostic microgloss generator. Designed to work without
hardcoded knowledge of any particular source vocabulary (Wiktionary,
WordNet, OmegaWiki, hand-curated domain lexicons, etc.).

THE CORE INSIGHT
----------------
The microgloss for a single sense should encode what DISTINGUISHES that
sense from its sibling senses (other senses of the same lemma in the
same lexicon). Tokens that appear in many siblings are filler. Tokens
that appear in only one or a few siblings are discriminators.

This collapses many problems into one mechanism:

  * Lemma echo: the lemma itself appears in all siblings -- IDF weight 0
    -- so it is naturally never chosen as a discriminator.
  * Register tag noise: "transitive", "countable", "informal" each appear
    in many sibling glosses -- low IDF weight -- so they lose to content.
  * Placename head nouns: "city", "town", "village" appear in most place
    senses of a name like Washington -- low IDF weight -- so the county
    and state names automatically win without the algorithm "knowing"
    they are states.
  * Cross-domain content: "money", "vehicle", "color" -- if they appear
    in only one sibling, they win; if they appear in all (rare), they
    lose. Either outcome is the right one.

TWO-PHASE API
-------------
The algorithm needs to see all siblings of a lemma before it can score
any of them. Use it in two phases per lemma:

    gen = MicroglossGenerator()

    # Phase 1: ingest every sense for the lemma.
    for sense in lemma_senses:
        gen.add_sibling(lemma, pos_simple, gloss)

    # Phase 2: generate microglosses in deterministic order.
    for sense in lemma_senses:
        mg = gen.generate(lemma, pos_simple, gloss)

If you generate without ingesting first, the algorithm degrades to a
content-token-frequency heuristic and still produces reasonable output,
but the sibling-IDF benefit is lost. The generator detects this case and
emits a warning the first time it happens.

A convenience method is provided for batch processing:

    rows = [(lemma, pos, gloss, row_id), ...]
    results = gen.generate_batch(rows)   # returns {row_id: microgloss}

The batch method handles ingestion and generation automatically and
processes one lemma at a time.

LEXICON-AGNOSTIC GUARANTEES
---------------------------
The algorithm uses ONLY:

  1. A universal English function-word stopword list (a, the, of, and,
     in, on, etc.). These are properties of the English language itself,
     not of any particular lexicon.

  2. A universal grammatical/register tag list (transitive, countable,
     slang, archaic, etc.). Same justification: these are English
     metalinguistic terms.

  3. Position-in-gloss heuristics (first-clause boost, position-decay).
     Lexicon-neutral; depends only on glosses being prose with
     left-to-right defining-first conventions.

  4. Sibling IDF, computed at runtime from the lexicon being processed.

NO hardcoded geography, biology, chemistry, politics, or domain-specific
vocabulary. The algorithm has never heard of Indiana, BGE-M3, or
piglets. When fed senses for "Indiana" in a hypothetical lexicon, it
would discriminate them the same way it discriminates "Washington" --
purely from the sibling text.

CLI:
    python micro_gloss_v4.py --self-test
    python micro_gloss_v4.py --demo-lemma washington
"""

from __future__ import annotations

import math
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Optional


# ===========================================================================
# UNIVERSAL English-language vocabulary (justified above)
# ===========================================================================

# Function words: articles, prepositions, pronouns, auxiliaries, conjunctions.
# These are properties of English grammar, not of any specific lexicon.
STOPWORDS = frozenset({
    "a", "an", "the",
    "and", "or", "but", "nor", "so", "yet",
    "of", "in", "on", "at", "by", "for", "with", "from", "to", "into",
    "onto", "upon", "over", "under", "above", "below", "between",
    "during", "before", "after", "since", "until", "while",
    "as", "than", "then", "though", "although", "because",
    "is", "am", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "done", "doing",
    "has", "have", "had", "having",
    "this", "that", "these", "those", "such",
    "it", "its", "they", "them", "their", "theirs", "we", "us", "our",
    "i", "me", "my", "you", "your", "he", "him", "his", "she", "her",
    "who", "whom", "whose", "which", "what", "where", "when", "why", "how",
    "not", "no", "if", "else", "whether",
    "would", "could", "should", "shall", "will", "may", "might", "must",
    "can", "ought",
    # Generic quantifiers/determiners that carry zero sense distinction
    "all", "any", "some", "each", "every", "both", "either", "neither",
    "one", "two",  # bare numerals
    "very", "quite", "rather", "more", "most", "less", "least",
    "much", "many", "few",
    "also", "too", "still", "just", "even", "only",
})

# English grammatical and register meta-vocabulary. These describe
# how a word is used, not what it means.
GRAMMATICAL_REGISTER_TAGS = frozenset({
    # Argument structure
    "transitive", "intransitive", "ambitransitive",
    "ditransitive", "monotransitive",
    "ergative", "reflexive", "reciprocal",
    "passive", "active", "pronominal", "impersonal",
    "attributive", "predicative", "postpositive",
    "auxiliary", "modal", "copular",
    # Number / countability
    "countable", "uncountable", "pluralonly", "singularonly",
    "plural", "singular",
    # Inflection
    "comparative", "superlative",
    # Register
    "informal", "formal", "colloquial", "slang", "vulgar", "offensive",
    "derogatory", "pejorative", "euphemistic", "humorous", "ironic",
    "figurative", "figuratively", "literally", "literal", "metonymic",
    "metaphorical", "metaphorically",
    # Temporal
    "archaic", "obsolete", "dated", "historical", "rare",
    # Style
    "poetic", "literary", "dialectal", "regional",
    "childish", "babytalk", "endearing",
    # Hedges
    "chiefly", "mainly", "mostly", "sometimes", "often",
    "specifically", "broadly", "narrowly", "loosely", "strictly",
    # Provenance tags
    "abbreviation", "alt", "altof", "ellipsis", "acronym", "initialism",
    "in_compounds", "in_combination",
})

# Universal English discourse glue (especially, etc., e.g., i.e.).
# These never carry sense distinction.
DISCOURSE_GLUE = frozenset({
    "especially", "particularly", "specifically", "generally", "typically",
    "usually", "normally", "often", "sometimes", "occasionally",
    "always", "never", "rarely", "seldom",
    "various", "several", "numerous", "certain",
    "etc", "ie", "eg",
    "e", "g", "i",
    "now", "today", "yesterday", "tomorrow",
    "see",  # "See also X" pointer marker
})

# Combined set used as a hard skip during scoring. Anything here is
# either grammatical noise or English-language overhead, not lexicon
# content.
UNIVERSAL_SKIP = STOPWORDS | GRAMMATICAL_REGISTER_TAGS | DISCOURSE_GLUE


# ===========================================================================
# Normalization
# ===========================================================================

def _strip_diacritics(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    )


def _norm(s: str) -> str:
    """Aggressive normalization for TOKEN comparison (IDF scoring, exclusion).
    Lowercases, strips diacritics, drops all punctuation except internal
    hyphens, collapses whitespace.
    """
    s = _strip_diacritics(s.lower())
    s = re.sub(r"[^a-z0-9 _\-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _norm_for_id(s: str) -> str:
    """Light normalization for the LEMMA component of a canonical_id.

    Lemma identity is a structural property of the lexicon, not a content
    scoring decision. We preserve distinguishing detail that _norm() throws
    away:

      * apostrophes  ('a'a vs a'a vs aa are distinct surface lemmas)
      * diacritics   (Béjaïa vs Bejaia are distinct surface lemmas)
      * trailing punctuation that disambiguates (Bd vs Bd. are distinct)

    What we still do:
      * lowercase                       ("Bank" == "bank" for namespace)
      * replace whitespace with '_'    ("New York" -> "new_york")
      * replace '.' with '_'           (avoids breaking the canonical_id's
                                        dot-delimited structure)
      * replace ',' with '_'           (same)
      * collapse runs of underscores   (cleanup)

    For lemmas with NO ASCII letters or digits (pure-unicode lemmas like
    Braille \u2825 or Shavian \U00010465), we use a deterministic hex
    fallback so two distinct unicode lemmas produce distinct canonical_ids.
    """
    if not s:
        return ""
    low = s.lower().strip()
    if any(c.isascii() and c.isalnum() for c in low):
        # Characters that would break the canonical_id's dot-delimited
        # structure must be escaped, NOT dropped (otherwise "Bd" and "Bd."
        # collapse to the same namespace and collide).
        #   space  ->  _
        #   .      ->  -dot-      (preserves disambiguation)
        #   ,      ->  -com-      (preserves disambiguation)
        out = low
        out = re.sub(r"\s+", "_", out)
        out = out.replace(".", "-dot-")
        out = out.replace(",", "-com-")
        out = re.sub(r"_+", "_", out).strip("_")
        return out
    # Pure unicode lemma (Braille, Shavian, ideographs, etc.). Use a hex
    # representation of the original codepoints so distinct lemmas stay
    # distinct in the canonical_id namespace.
    return "u" + "_".join(f"{ord(c):x}" for c in s if not c.isspace())


def _lemma_inflections(lemma: str) -> set[str]:
    """Surface inflections of the lemma to exclude from microgloss."""
    base = _norm(lemma)
    forms = {base}
    if not base:
        return forms
    for suf in ("s", "es", "ed", "ing", "er", "ers", "ly"):
        forms.add(base + suf)
    if base.endswith("e"):
        forms.add(base[:-1] + "ing")
        forms.add(base[:-1] + "ed")
    if base.endswith("y"):
        forms.add(base[:-1] + "ies")
        forms.add(base[:-1] + "ied")
    return forms


def _singularize(tok: str) -> str:
    """Plural -> singular for IDF bucketing. Output uses surface form."""
    if len(tok) <= 3:
        return tok
    if tok.endswith("ies"):
        return tok[:-3] + "y"
    if tok.endswith("ses") or tok.endswith("xes") or tok.endswith("zes"):
        return tok[:-2]
    if tok.endswith("ches") or tok.endswith("shes"):
        return tok[:-2]
    if tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


# ===========================================================================
# Parenthetical-tag parsing
# Many lexicons use "(register) body" convention. Where they do not, the
# tag list is simply empty and the body is the full gloss -- no harm done.
# ===========================================================================

_LEADING_PAREN_RE = re.compile(r"^\s*\(([^)]+)\)\s*")


def parse_leading_tags(gloss: str) -> tuple[list[str], str]:
    tags: list[str] = []
    body = gloss
    while True:
        m = _LEADING_PAREN_RE.match(body)
        if not m:
            break
        chunk = m.group(1)
        body = body[m.end():]
        for raw in chunk.split(","):
            for piece in re.split(r"\s+(?:and|or)\s+", raw.strip()):
                t = _norm(piece)
                if t:
                    tags.append(t.replace(" ", "_"))
    return tags, body.strip()


def is_content_tag(tag: str) -> bool:
    """True if the tag carries sense distinction (not pure metadata)."""
    if tag in GRAMMATICAL_REGISTER_TAGS:
        return False
    if tag.startswith("of_"):
        head = tag[3:].split("_")[-1]
        return head not in {
            "person", "people", "thing", "things", "one",
            "someone", "something", "anyone", "anything",
        }
    return True


def strip_of_prefix(tag: str) -> str:
    if not tag.startswith("of_"):
        return tag
    parts = tag[3:].split("_")
    drop = {"a", "an", "the", "or", "and"}
    kept = [p for p in parts if p and p not in drop]
    return "_".join(kept) if kept else tag


# ===========================================================================
# Cross-reference detection (DEFAULT = universal lexicon-agnostic patterns)
#
# A SMALL number of English dictionary conventions are nearly universal:
# almost every traditional English lexicon emits "Synonym of X" or
# "Abbreviation of X" senses, regardless of source (Wiktionary, OED,
# Merriam-Webster, etc.). We default to detecting only those.
#
# WHY NOT MORE PATTERNS BY DEFAULT?
#
# It would be tempting to also detect "Plural of X", "Past tense of X",
# "Diminutive of X", "Misspelling of X" -- Wiktionary has hundreds of
# thousands of such senses. But these phrasings are SPECIFIC to
# Wiktionary's editorial conventions. WordNet does not emit standalone
# inflection senses at all. OmegaWiki uses different conventions.
# A hand-curated philosophy lexicon may use none of these phrasings.
#
# Hard-coding Wiktionary-specific patterns would silently degrade
# performance on other lexicons. We therefore keep the default minimal
# and offer an OPT-IN extension list for callers that know their source
# uses richer conventions.
#
# WHAT HAPPENS TO INFLECTION POINTERS WITHOUT THE EXTENSIONS?
#
# They fall through to the regular IDF-scored body tokenizer. The lemma
# inflection set excludes the lemma's surface form but NOT its backward
# singularization, so a gloss like "plural of Arabologist" for the
# lemma "Arabologists" still produces a meaningful microgloss whose top
# token is "arabologist" -- the actual discriminator, even without any
# inflection-pattern detection. Less pretty than "plural_of_arabologist",
# equally functional for embedding-based federation.
#
# HOW TO OPT IN TO WIKTIONARY-FLAVORED PATTERNS
#
#     from micro_gloss_v4 import (
#         MicroglossGenerator,
#         WIKTIONARY_XREF_EXTENSIONS,
#     )
#     gen = MicroglossGenerator(xref_patterns_extra=WIKTIONARY_XREF_EXTENSIONS)
#
# Or define your own list of (compiled_regex, prefix) tuples for any
# source-specific conventions you want pretty-printed.
# ===========================================================================

# Reusable target capture: a word or short phrase, ending before
# punctuation or end of string.
_XREF_TARGET = r"([A-Za-z][\w\s\-\']+?)(?:\s*[\.;\(,]|$)"

# Universal patterns (default).
_SYNONYM_OF_RE = re.compile(rf"^\s*synonym\s+of\s+{_XREF_TARGET}", re.IGNORECASE)
_ABBR_OF_RE = re.compile(
    rf"^\s*(?:abbreviation|ellipsis|acronym|initialism|short\s+form)\s+of\s+{_XREF_TARGET}",
    re.IGNORECASE,
)

UNIVERSAL_XREF_PATTERNS = [
    (_SYNONYM_OF_RE, "synonym_of"),
    (_ABBR_OF_RE,    "abbreviation_of"),
]


# Optional Wiktionary-flavored extensions. Opt in at MicroglossGenerator
# construction time via xref_patterns_extra=WIKTIONARY_XREF_EXTENSIONS.
# These add pretty-printed microglosses for the inflection-pointer senses
# that Wiktionary emits in vast quantity (plurals, past tenses, etc.).
# Pass an empty list (or do not pass) for other lexicons.

_ALT_OF_RE = re.compile(
    rf"^\s*alternat(?:ive|e)\s+(?:form|spelling|name)\s+of\s+{_XREF_TARGET}",
    re.IGNORECASE,
)
_MISSPELL_RE = re.compile(
    rf"^\s*(?:common\s+)?misspelling\s+of\s+{_XREF_TARGET}", re.IGNORECASE,
)
_OBSOLETE_SPELL_RE = re.compile(
    rf"^\s*(?:obsolete|archaic|dated|rare|nonstandard|eye\s+dialect)\s+"
    rf"(?:spelling|form)\s+of\s+{_XREF_TARGET}",
    re.IGNORECASE,
)
_PLURAL_OF_RE = re.compile(rf"^\s*plural\s+of\s+{_XREF_TARGET}", re.IGNORECASE)
_SINGULAR_OF_RE = re.compile(rf"^\s*singular\s+of\s+{_XREF_TARGET}", re.IGNORECASE)
_PAST_PART_RE = re.compile(
    rf"^\s*past\s+participle\s+of\s+{_XREF_TARGET}", re.IGNORECASE,
)
_PRESENT_PART_RE = re.compile(
    rf"^\s*present\s+participle\s+of\s+{_XREF_TARGET}", re.IGNORECASE,
)
_SIMPLE_PAST_RE = re.compile(
    rf"^\s*simple\s+past\s+(?:tense\s+)?(?:and\s+past\s+participle\s+)?of\s+{_XREF_TARGET}",
    re.IGNORECASE,
)
_PAST_TENSE_RE = re.compile(
    rf"^\s*past\s+tense\s+of\s+{_XREF_TARGET}", re.IGNORECASE,
)
_GERUND_RE = re.compile(rf"^\s*gerund\s+of\s+{_XREF_TARGET}", re.IGNORECASE)
_THIRD_PERSON_RE = re.compile(
    rf"^\s*third[\-\s]person\s+singular\s+"
    rf"(?:simple\s+present|present(?:\s+indicative)?|present\s+tense)?"
    rf"\s*(?:indicative\s+)?of\s+{_XREF_TARGET}",
    re.IGNORECASE,
)
_COMPARATIVE_RE = re.compile(
    rf"^\s*comparative\s+(?:form\s+)?of\s+{_XREF_TARGET}", re.IGNORECASE,
)
_SUPERLATIVE_RE = re.compile(
    rf"^\s*superlative\s+(?:form\s+)?of\s+{_XREF_TARGET}", re.IGNORECASE,
)
_DIMINUTIVE_RE = re.compile(
    rf"^\s*diminutive\s+of\s+{_XREF_TARGET}", re.IGNORECASE,
)
_AUGMENTATIVE_RE = re.compile(
    rf"^\s*augmentative\s+of\s+{_XREF_TARGET}", re.IGNORECASE,
)
_FEMININE_RE = re.compile(
    rf"^\s*feminine\s+(?:form\s+|equivalent\s+)?of\s+{_XREF_TARGET}", re.IGNORECASE,
)
_MASCULINE_RE = re.compile(
    rf"^\s*masculine\s+(?:form\s+|equivalent\s+)?of\s+{_XREF_TARGET}", re.IGNORECASE,
)
_INFLECTION_RE = re.compile(
    rf"^\s*inflection\s+of\s+{_XREF_TARGET}", re.IGNORECASE,
)
_GENERIC_FORM_RE = re.compile(
    rf"^\s*(?:a\s+)?form\s+of\s+{_XREF_TARGET}", re.IGNORECASE,
)

# Ordered: most-specific first.
WIKTIONARY_XREF_EXTENSIONS = [
    (_ALT_OF_RE,          "alt_of"),
    (_MISSPELL_RE,        "misspelling_of"),
    (_OBSOLETE_SPELL_RE,  "obsolete_spelling_of"),
    (_THIRD_PERSON_RE,    "third_person_singular_of"),
    (_PAST_PART_RE,       "past_participle_of"),
    (_PRESENT_PART_RE,    "present_participle_of"),
    (_SIMPLE_PAST_RE,     "simple_past_of"),
    (_PAST_TENSE_RE,      "past_tense_of"),
    (_GERUND_RE,          "gerund_of"),
    (_COMPARATIVE_RE,     "comparative_of"),
    (_SUPERLATIVE_RE,     "superlative_of"),
    (_DIMINUTIVE_RE,      "diminutive_of"),
    (_AUGMENTATIVE_RE,    "augmentative_of"),
    (_FEMININE_RE,        "feminine_of"),
    (_MASCULINE_RE,       "masculine_of"),
    (_PLURAL_OF_RE,       "plural_of"),
    (_SINGULAR_OF_RE,     "singular_of"),
    (_INFLECTION_RE,      "inflection_of"),
    (_GENERIC_FORM_RE,    "form_of"),
]


def detect_cross_reference(body: str, patterns: list | None = None) -> str | None:
    """
    Detect short pointer-style senses ("Synonym of X", optionally
    "Plural of X" etc.) and produce a microgloss of the form
    <relation>_of_<target>.

    Args:
        body: the gloss body (after leading-parens stripping).
        patterns: list of (compiled_regex, prefix) tuples. Defaults to
            UNIVERSAL_XREF_PATTERNS if None.

    Returns None if no pattern matches.
    """
    if patterns is None:
        patterns = UNIVERSAL_XREF_PATTERNS
    for pat, prefix in patterns:
        m = pat.match(body)
        if m:
            target = _norm(m.group(1)).replace(" ", "_").replace("-", "_")
            target = re.sub(r"_+", "_", target).strip("_")
            if target:
                return f"{prefix}_{target}"
    return None


# ===========================================================================
# Tokenization (keeps hyphenated tokens whole)
# ===========================================================================

_BODY_PAREN_RE = re.compile(r"\(([^)]*)\)")
_TAIL_SEE_RE = re.compile(r"[;,.]\s*see\s+\w+.*$", re.IGNORECASE)
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[\-][a-z0-9]+)*")


def tokenize_body(body: str) -> tuple[list[str], list[str]]:
    body = _TAIL_SEE_RE.sub("", body)
    body = _BODY_PAREN_RE.sub(r" \1 ", body)
    body_n = _strip_diacritics(body.lower())
    head_split = re.split(r"[.;]", body_n, maxsplit=1)
    first_clause = head_split[0] if head_split else body_n
    first_tokens = _TOKEN_RE.findall(first_clause)
    all_tokens = _TOKEN_RE.findall(body_n)
    return first_tokens, all_tokens


def gloss_tokens(gloss: str) -> set[str]:
    """All distinct content tokens that appear in a gloss, after stripping
    parens and stopwords. Used to build the sibling-IDF table."""
    _, body = parse_leading_tags(gloss)
    _, toks = tokenize_body(body)
    out: set[str] = set()
    for t in toks:
        s = _singularize(t)
        if t in UNIVERSAL_SKIP or s in UNIVERSAL_SKIP:
            continue
        if len(t) <= 1:
            continue
        out.add(s)  # bucket by singular form
    return out


# ===========================================================================
# Scoring
# ===========================================================================

@dataclass
class TokenScore:
    token: str            # surface form for output
    bucket: str           # singularized form for IDF lookup
    score: float


def score_tokens(
    first_tokens: list[str],
    all_tokens: list[str],
    excluded: set[str],
    idf: dict[str, float],
    n_siblings: int,
) -> list[TokenScore]:
    """Score every distinct surface token. IDF weight is the primary signal."""
    counts: dict[str, int] = defaultdict(int)
    first_set = set(first_tokens)
    for t in all_tokens:
        counts[t] += 1
    first_position: dict[str, int] = {}
    for i, t in enumerate(all_tokens):
        if t not in first_position:
            first_position[t] = i

    # Maximum possible IDF for this sibling set (used to normalize boosts)
    max_idf = math.log(max(2, n_siblings))

    scored: list[TokenScore] = []
    for tok, n in counts.items():
        if tok in excluded:
            continue
        if len(tok) <= 1:
            continue
        bucket = _singularize(tok)
        if tok in UNIVERSAL_SKIP or bucket in UNIVERSAL_SKIP:
            continue
        # Pure short numerals -> drop
        if tok.isdigit() and len(tok) <= 2:
            continue
        # Hyphenated tokens that CONTAIN a lemma inflection (e.g. "dark-blue"
        # for lemma "blue") are still lemma echoes. Drop them.
        if "-" in tok or "_" in tok:
            sub_parts = re.split(r"[-_]", tok)
            if any(sp in excluded or _singularize(sp) in excluded for sp in sub_parts if sp):
                continue

        # ===== PRIMARY SIGNAL: sibling-IDF =====
        # Tokens absent from the IDF table appear in zero siblings (the
        # IDF table tracks tokens that appear AT LEAST ONCE in the sibling
        # set, so any token here must be present somewhere). Tokens with
        # df=N appear in every sibling -> IDF = 0 -> filler.
        w = idf.get(bucket, max_idf)
        # Strong primary weighting
        s = 3.0 * w

        # ===== SECONDARY: structural position =====
        # First-clause boost (gloss conventions are head-first)
        if tok in first_set:
            s += 1.5
        pos = first_position.get(tok, 99)
        s += max(0.0, 1.0 - 0.1 * pos)

        # ===== TERTIARY: token shape =====
        # Frequency within the gloss itself
        if n > 1:
            s += min(0.5, 0.15 * (n - 1))
        # Digit-containing tokens are usually models, dates, codes -- high signal
        if any(c.isdigit() for c in tok):
            s += 1.5
        # Long technical-looking tokens
        elif len(tok) >= 9 and not tok.endswith(
            ("ing", "ed", "ly", "tion", "sion", "ment", "ness", "ship")
        ):
            s += 0.8

        scored.append(TokenScore(token=tok, bucket=bucket, score=s))
    scored.sort(key=lambda x: (-x.score, x.token))
    return scored


# ===========================================================================
# Candidate construction
# ===========================================================================

SOFT_TARGET_TOKENS = 3
HARD_MAX_TOKENS = 8


def build_candidates(
    body_scored: list[TokenScore],
    content_tags: list[str],
) -> list[str]:
    body = [t.token for t in body_scored if t.score > 0]
    if not body and not content_tags:
        return []

    candidates: list[str] = []

    def add(c: str) -> None:
        if c and c not in candidates:
            candidates.append(c)

    if body:
        # Try the sweet spot lengths first, then progressively longer for
        # collision recovery.
        length_order = [3, 2, 4, 1, 5, 6, 7, HARD_MAX_TOKENS]
        for ntoks in length_order:
            if ntoks > len(body):
                continue
            picked = body[:ntoks]
            base = "_".join(picked)
            # Variant with content tag prepended
            for ctag in content_tags[:1]:
                add(f"{ctag}_{base}")
            # Bare body
            add(base)
            # Swap top-2 for collision recovery
            if ntoks >= 2:
                swapped = "_".join([picked[1], picked[0]] + picked[2:])
                for ctag in content_tags[:1]:
                    add(f"{ctag}_{swapped}")
                add(swapped)

    if not body and content_tags:
        add(content_tags[0])
        if len(content_tags) > 1:
            add(f"{content_tags[0]}_{content_tags[1]}")
            add("_".join(content_tags[:3]))

    return candidates


# ===========================================================================
# Public generator
# ===========================================================================

@dataclass
class _SiblingStats:
    n_senses: int = 0
    df: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    idf: dict[str, float] = field(default_factory=dict)
    finalized: bool = False


class MicroglossGenerator:
    """Stateful, lexicon-agnostic microgloss generator.

    Two-phase usage:
        gen.add_sibling(lemma, pos, gloss)   # phase 1, repeat per sense
        gen.generate(lemma, pos, gloss)      # phase 2, repeat per sense

    Or batch:
        gen.generate_batch([(lemma, pos, gloss, row_id), ...])
    """

    def __init__(self, xref_patterns_extra: list | None = None) -> None:
        """
        Args:
            xref_patterns_extra: optional list of (compiled_regex, prefix)
                tuples to ADD to the universal cross-reference patterns.
                Pass WIKTIONARY_XREF_EXTENSIONS for Wiktionary-style
                inflection-pointer detection. Default None = use only
                the universal patterns ("Synonym of X", "Abbreviation of X").
        """
        # (lemma_norm, pos_norm) -> sibling-IDF stats
        self._stats: dict[tuple[str, str], _SiblingStats] = defaultdict(_SiblingStats)
        # (lemma_norm, pos_norm) -> emitted microglosses (collision dedup)
        self._emitted: dict[tuple[str, str], set[str]] = defaultdict(set)
        # (lemma_norm, pos_norm) -> fallback counter
        self._fallback_counter: dict[tuple[str, str], int] = defaultdict(int)
        self._warned_no_siblings = False
        # Cross-reference patterns: universal defaults + any extensions.
        self._xref_patterns = list(UNIVERSAL_XREF_PATTERNS)
        if xref_patterns_extra:
            self._xref_patterns.extend(xref_patterns_extra)

    # ----------------------------------------------------------------- ingest
    def add_sibling(self, lemma: str, pos_simple: str, gloss: str) -> None:
        """Phase 1: register one sense for sibling-IDF computation."""
        key = (_norm(lemma), _norm(pos_simple))
        stats = self._stats[key]
        if stats.finalized:
            # New sibling arrived after we already started generating;
            # reset finalized state so we recompute IDF when needed.
            stats.finalized = False
        stats.n_senses += 1
        for tok in gloss_tokens(gloss or ""):
            stats.df[tok] += 1

    def _finalize(self, key) -> None:
        stats = self._stats[key]
        if stats.finalized:
            return
        n = max(1, stats.n_senses)
        # Standard smoothed IDF: log(N / df), with df=0 meaning "absent
        # from siblings" which produces log(N) (high weight).
        # Tokens present in every sibling get log(1) = 0 (filler).
        for tok, df in stats.df.items():
            stats.idf[tok] = math.log(n / df) if df > 0 else math.log(n)
        stats.finalized = True

    # --------------------------------------------------------------- generate
    def generate(self, lemma: str, pos_simple: str, gloss: str) -> str:
        lemma_norm = _norm(lemma)
        pos_norm = _norm(pos_simple)
        key = (lemma_norm, pos_norm)

        if not gloss or not gloss.strip():
            return self._fallback(key, content_tag=None)

        stats = self._stats[key]
        if stats.n_senses == 0 and not self._warned_no_siblings:
            sys.stderr.write(
                "micro_gloss_v4: WARNING: generate() called for "
                f"({lemma_norm!r}, {pos_norm!r}) before any add_sibling(). "
                "Falling back to no-IDF mode. Call add_sibling() for every "
                "sense BEFORE calling generate() for best results.\n"
            )
            self._warned_no_siblings = True
        self._finalize(key)

        # Step 1: tags
        raw_tags, body = parse_leading_tags(gloss)
        content_tags: list[str] = []
        for tg in raw_tags:
            if is_content_tag(tg):
                content_tags.append(strip_of_prefix(tg))

        # Step 2: cross-reference short-circuit (universal patterns + any
        # opt-in extensions configured at __init__).
        xref = detect_cross_reference(body, patterns=self._xref_patterns)
        if xref:
            cand = self._sanitize(xref)
            cand = self._ensure_unique(key, cand)
            self._emitted[key].add(cand)
            return cand

        # Step 3: tokenize
        first_tokens, all_tokens = tokenize_body(body)

        # Step 4: score with sibling-IDF.
        # Exclusion set: the lemma's surface form and its FORWARD
        # inflections (lemma+s, lemma+ed, etc.). We deliberately do NOT
        # exclude the BACKWARD-singularization of the lemma. Rationale:
        # for a plural lemma like "Arabologists" whose gloss is
        # "plural of Arabologist", the singular "Arabologist" is the
        # token that carries the actual discrimination signal. Excluding
        # it would leave no content tokens at all and force a useless
        # sense_N fallback.
        #
        # The risk we accept: a gloss that happens to use the lemma's
        # own singular as a self-reference (rare). The benefit: every
        # plural/past-tense/comparative pointer row gets a meaningful
        # microgloss out of the box, regardless of how the source
        # lexicon phrases the pointer.
        excluded = _lemma_inflections(lemma_norm)
        scored = score_tokens(
            first_tokens, all_tokens, excluded,
            stats.idf, max(1, stats.n_senses),
        )

        # Step 5: candidates
        candidates = build_candidates(scored, content_tags)

        # Step 6: first non-colliding candidate
        for cand in candidates:
            cand = self._sanitize(cand)
            if not cand:
                continue
            if cand not in self._emitted[key]:
                self._emitted[key].add(cand)
                return cand

        # Step 7: tagged-fallback
        if candidates:
            base = self._sanitize(candidates[0])
            self._fallback_counter[key] += 1
            tagged = f"{base}_{self._fallback_counter[key] + 1}"
            self._emitted[key].add(tagged)
            return tagged

        return self._fallback(
            key, content_tag=content_tags[0] if content_tags else None
        )

    # --------------------------------------------------------------- batch
    def generate_batch(
        self,
        rows: Iterable[tuple],
    ) -> dict:
        """Convenience: ingest all siblings, then generate. Expects rows
        of (lemma, pos_simple, gloss, row_id). Returns {row_id: microgloss}.
        Order within each (lemma, pos_simple) group is preserved by the
        caller's input order, which matters for collision resolution
        determinism."""
        rows = list(rows)
        # Phase 1: ingest
        for lemma, pos, gloss, _row_id in rows:
            self.add_sibling(lemma, pos, gloss or "")
        # Phase 2: generate
        out: dict = {}
        for lemma, pos, gloss, row_id in rows:
            out[row_id] = self.generate(lemma, pos, gloss or "")
        return out

    # ----------------------------------------------------------------- utils
    def _sanitize(self, s: str) -> str:
        s = _norm(s).replace(" ", "_")
        s = s.replace("-", "_")
        s = re.sub(r"_+", "_", s).strip("_")
        parts = s.split("_")
        if len(parts) > HARD_MAX_TOKENS:
            parts = parts[:HARD_MAX_TOKENS]
        return "_".join(parts)

    def _ensure_unique(self, key, cand: str) -> str:
        if cand not in self._emitted[key]:
            return cand
        i = 2
        while f"{cand}_{i}" in self._emitted[key]:
            i += 1
        return f"{cand}_{i}"

    def _fallback(self, key, content_tag: Optional[str]) -> str:
        self._fallback_counter[key] += 1
        n = self._fallback_counter[key]
        if content_tag:
            cand = f"{self._sanitize(content_tag)}_sense_{n}"
        else:
            cand = f"sense_{n}"
        while cand in self._emitted[key]:
            self._fallback_counter[key] += 1
            n = self._fallback_counter[key]
            cand = (
                f"{self._sanitize(content_tag)}_sense_{n}"
                if content_tag else f"sense_{n}"
            )
        self._emitted[key].add(cand)
        return cand


# ===========================================================================
# Self-test / regression corpus
# ===========================================================================

# Each entry: (lemma, pos, gloss, expected)
# expected:
#   * a set of strings: at least one token-match OR substring-match required
#   * "_NOT_LEMMA_": only require no lemma echo
REGRESSION_GROUPS: list[tuple[str, str, list[tuple[str, object]]]] = [
    # ===== bank/noun =====
    ("bank", "noun", [
        ("(countable) An institution where one can place and borrow money and take care of financial affairs.",
         {"institution", "financial", "money"}),
        ("(countable) A branch office of such an institution.",
         {"branch", "office"}),
        ("(countable) An underwriter or controller of a card game.",
         {"underwriter", "card", "game", "controller"}),
        ("(slang, uncountable) Money; profit.",
         {"money", "profit"}),
        ("(hydrology) An edge of river, lake, or other watercourse.",
         {"hydrology", "edge", "river", "lake"}),
        ("(nautical, hydrology) An elevation under the sea; a shallow area of shifting sand, gravel, mud, and so forth",
         {"elevation", "sea", "shallow", "sand"}),
        ("(geography) A slope of earth, sand, etc.; an embankment.",
         {"slope", "embankment", "geography"}),
        ("(aviation) The incline of an aircraft, especially during a turn.",
         {"aviation", "incline", "aircraft"}),
        ("A mass of clouds.", {"mass", "cloud"}),
        ("(mining) The face of the coal at which miners are working.",
         {"mining", "coal", "face"}),
        ("(computing) A contiguous block of memory that is of fixed, hardware-dependent size.",
         {"computing", "block", "memory"}),
    ]),

    # ===== bank/verb =====
    ("bank", "verb", [
        ("(transitive) To put into a bank.", "_NOT_LEMMA_"),
        ("(transitive, slang) To conceal in the rectum for use in prison.",
         {"conceal", "rectum", "prison"}),
        ("(transitive, finance) To provide banking services to.",
         {"finance", "services"}),
        ("(intransitive, aviation) To roll or incline laterally in order to turn.",
         {"aviation", "roll", "incline", "laterally"}),
    ]),

    # ===== pig/noun =====
    ("pig", "noun", [
        ("(countable) Any of several mammalian species of the family Suidae, having cloven hooves, bristles and a snout adapted for digging; especially the domesticated animal Sus domesticus.",
         {"mammalian", "suidae", "snout", "hooves"}),
        ("(uncountable) The edible meat of such an animal; pork.",
         {"edible", "meat", "pork"}),
        ("(figuratively, derogatory) Someone who overeats or eats rapidly and noisily.",
         {"overeats", "rapidly", "noisily"}),
        ("(figuratively, derogatory) A lecherous or sexist man.",
         {"lecherous", "sexist", "man"}),
        ("(figuratively, derogatory) A dirty or slovenly person.",
         {"dirty", "slovenly"}),
        ("(figuratively, derogatory) An obese person.", {"obese"}),
        ("(derogatory, slang) A police officer.", {"police", "officer"}),
        ("(US, military, slang) The general-purpose M60 machine gun, considered to be heavy and bulky.",
         {"m60", "machine", "gun", "military"}),
        ("A lead container used for radioactive waste.",
         {"lead", "container", "radioactive"}),
    ]),

    # ===== blue/noun =====
    ("blue", "noun", [
        ("(countable and uncountable) The colour of the clear sky or the deep sea; the colour midway between green and violet in the visible spectrum and one of the primary additive colours.",
         {"colour", "sky", "spectrum", "green", "violet", "primary", "additive", "midway", "clear"}),
        ("A blue dye or pigment.", {"dye", "pigment"}),
        ("(uncountable) Blue clothing.", {"clothing"}),
        ("(in the plural) A blue uniform. See blues.", {"uniform", "plural"}),
        ("A member of a sports team that wears blue colours; (in the plural) a nickname for the team as a whole.",
         {"sports", "team"}),
        ("(baseball, slang) An umpire, in reference to the typical dark-blue colour of the umpire's uniform.",
         {"baseball", "umpire"}),
        ("(slang) A member of law enforcement.",
         {"law", "enforcement"}),
        ("(now historical) A bluestocking.", {"bluestocking"}),
        ("The sky, literally or figuratively.", {"sky"}),
        ("The ocean; deep waters.", {"ocean", "waters"}),
        ("(snooker) One of the colour balls used in snooker, with a value of five points.",
         {"snooker", "ball"}),
        ("A bluefish.", {"bluefish"}),
        ("(Australia, colloquial) An argument or brawl.",
         {"argument", "brawl", "australia"}),
        ("A blue cheese.", {"cheese"}),
    ]),

    # ===== blue/adj =====
    ("blue", "adj", [
        ("(informal) Depressed, melancholic, sad.",
         {"depressed", "melancholic", "sad"}),
        ("Having a bluish or purplish shade to the skin due to a lack of oxygen to the normally deep-red red blood cells; cyanotic.",
         {"cyanotic", "skin", "oxygen", "bluish", "purplish"}),
        ("(of a flame) Pale, without redness or glare.",
         {"flame", "pale"}),
        ("(US politics) Supportive of or related to the Democratic Party.",
         {"democratic", "party"}),
        ("(Australian politics) Supportive of or related to the Liberal Party.",
         {"liberal", "party", "australian"}),
        ("(UK politics) Supportive of or related to the Conservative Party.",
         {"conservative", "party", "uk"}),
        ("(astronomy) Of, dominated by, or shifted toward the higher-frequency, or \"bluer\", end of the electromagnetic spectrum.",
         {"astronomy", "frequency", "electromagnetic", "spectrum"}),
        ("(of steak) Extra rare; left very raw and cold.", {"steak", "raw"}),
        ("(of a dog or cat) Having a coat of fur of a slaty gray shade.",
         {"slaty", "gray", "coat", "fur"}),
    ]),

    # ===== washington/name — placename cluster =====
    # 10 siblings; state/county names should dominate.
    ("washington", "name", [
        ("A state in the Pacific Northwest region of the United States. Capital: Olympia. Largest city: Seattle.",
         {"pacific", "northwest", "olympia", "seattle"}),
        ("Washington, D.C. (the capital city of the United States).",
         "_NOT_LEMMA_"),
        ("An English habitational surname from Old English.",
         {"habitational", "surname"}),
        ("(figuratively, metonymic) The federal government or administrative authority of the United States.",
         {"federal", "government", "administrative"}),
        ("A small city, the county seat of Daviess County, Indiana.",
         {"daviess", "indiana"}),
        ("A town in Knox County, Maine.", {"knox", "maine"}),
        ("A small town in Berkshire County, Massachusetts.",
         {"berkshire", "massachusetts"}),
        ("An unincorporated community in Macomb County, Michigan.",
         {"macomb", "michigan"}),
        ("A city in Tazewell County, Illinois.", {"tazewell", "illinois"}),
        ("A neighborhood of the city of Maysville, Mason County, Kentucky.",
         {"maysville", "mason", "kentucky"}),
        ("A small city, the county seat of Wilkes County, Georgia.",
         {"wilkes", "georgia"}),
        ("A small city, the county seat of Washington County, Iowa.",
         {"iowa"}),
    ]),

    # ===== louisiana/name historical territories =====
    ("louisiana", "name", [
        ("A state in the Deep South and South Central regions of the United States. Capital: Baton Rouge. Largest city: New Orleans.",
         {"baton", "rouge", "orleans", "south"}),
        ("An administrative district of New France. (1682-1769; 1801-1803)",
         {"administrative", "france", "1682", "1801"}),
        ("A governorate of New Spain. (1769-1801)",
         {"governorate", "spain", "1769"}),
        ("A former territory of the United States. (1805-1812)",
         {"former", "territory", "1805"}),
        ("A city in Pike County, Missouri, named for the founder's daughter, Louisiana Bayse.",
         {"pike", "missouri", "bayse", "founder"}),
        ("A ghost town in Douglas County, Kansas.",
         {"ghost", "douglas", "kansas"}),
        ("The University of Louisiana at Lafayette, and especially its athletic program, the Louisiana Ragin' Cajuns.",
         {"university", "lafayette", "athletic", "cajuns"}),
        ("A female given name.", {"female", "given"}),
    ]),

    # ===== cross-reference patterns =====
    ("washington", "noun", [
        ("Synonym of agawan base (a team game)", {"synonym_of_agawan", "agawan"}),
    ]),
]


def _flatten_corpus() -> list[tuple[str, str, str, object]]:
    out: list[tuple[str, str, str, object]] = []
    for lemma, pos, items in REGRESSION_GROUPS:
        for gloss, expected in items:
            out.append((lemma, pos, gloss, expected))
    return out


def run_self_test(verbose: bool = True) -> int:
    gen = MicroglossGenerator()

    # Phase 1: ingest every sibling
    for lemma, pos, items in REGRESSION_GROUPS:
        for gloss, _exp in items:
            gen.add_sibling(lemma, pos, gloss)

    # Phase 2: generate and check
    corpus = _flatten_corpus()
    n_total = 0
    n_pass = 0
    failures: list[tuple] = []

    print(f"Running micro_gloss_v4 regression corpus: {len(corpus)} cases")
    print()

    for lemma, pos, gloss, expected in corpus:
        n_total += 1
        mg = gen.generate(lemma, pos, gloss)
        parts = set(mg.split("_"))
        lemma_forms = _lemma_inflections(lemma)

        if parts & lemma_forms:
            failures.append((lemma, pos, gloss[:70], mg, "LEMMA_ECHO"))
            continue
        if parts.issubset(UNIVERSAL_SKIP):
            failures.append((lemma, pos, gloss[:70], mg, "SKIP_ONLY"))
            continue

        if expected == "_NOT_LEMMA_":
            n_pass += 1
            if verbose:
                print(f"  PASS  {lemma}/{pos:5s}  {mg}")
            continue

        if isinstance(expected, set):
            hit = False
            for want in expected:
                if want in parts:
                    hit = True
                    break
                if "_" in want and want in mg:
                    hit = True
                    break
                # Allow singularized match
                if _singularize(want) in parts:
                    hit = True
                    break
            if hit:
                n_pass += 1
                if verbose:
                    print(f"  PASS  {lemma}/{pos:5s}  {mg}")
                continue
            failures.append(
                (lemma, pos, gloss[:70], mg, f"NO_SIGNAL want any of {sorted(expected)}")
            )

    print()
    print("=" * 70)
    print(f"Results: {n_pass}/{n_total} pass ({100.0 * n_pass / n_total:.1f}%)")
    print("=" * 70)
    if failures:
        print("\nFAILURES:")
        for lemma, pos, gloss_head, mg, reason in failures:
            print(f"  {lemma}/{pos}  mg={mg!r}")
            print(f"      gloss: {gloss_head}...")
            print(f"      reason: {reason}")
    return 0 if n_pass == n_total else 1


def main(argv: list[str]) -> int:
    import argparse
    p = argparse.ArgumentParser(description="lexicon-agnostic microgloss v4")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--lemma")
    p.add_argument("--pos", default="noun")
    p.add_argument("--gloss")
    args = p.parse_args(argv)

    if args.self_test:
        return run_self_test(verbose=True)
    if args.lemma and args.gloss:
        gen = MicroglossGenerator()
        gen.add_sibling(args.lemma, args.pos, args.gloss)
        print(gen.generate(args.lemma, args.pos, args.gloss))
        return 0
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
