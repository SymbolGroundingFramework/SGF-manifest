#!/usr/bin/env python3
"""
pos_converter.py

Maps Wiktionary's raw POS strings to a small SGF-internal vocabulary.

Two columns matter in the SGF lexicon:
    pos_wiktionary  - the raw string from Wiktionary, preserved verbatim
    pos_simple      - the 5-value bucket used in canonical IDs

The 5 simple buckets:
    noun, verb, adj, adv, name, other

If you need richer POS tagging later (Universal Dependencies, 27-value SGF
detailed, etc.), add it as a separate column without disturbing canonical IDs.
"""

from typing import Optional, Dict

# Map every Wiktionary POS string we've ever observed to spaCy's Universal
# Dependencies POS tag. This matters because GLEAN tags tokens with spaCy
# (so JOIN-by-pos is the natural query pattern).
# Keys are lowercase, leading/trailing whitespace stripped.
WIKTIONARY_TO_SPACY: Dict[str, str] = {
    # Direct hits
    "noun":               "NOUN",
    "verb":               "VERB",
    "adj":                "ADJ",
    "adjective":          "ADJ",
    "adv":                "ADV",
    "adverb":             "ADV",
    "adverbial phrase":   "ADV",

    # Proper nouns - spaCy uses PROPN
    "proper noun":        "PROPN",
    "proper name":        "PROPN",
    "name":               "PROPN",

    # Closed-class function words
    "pronoun":            "PRON",
    "preposition":        "ADP",
    "postposition":       "ADP",
    "prepositional phrase": "ADP",
    "conjunction":        "CCONJ",
    "determiner":         "DET",
    "article":            "DET",
    "particle":           "PART",
    "numeral":            "NUM",
    "interjection":       "INTJ",

    # Multi-word and phrase types - phrases tend to be nominal unless tagged
    "phrase":             "NOUN",
    "proverb":            "NOUN",
    "noun phrase":        "NOUN",
    "verb phrase":        "VERB",

    # Morphological pieces - spaCy uses X for foreign/unknown/sub-word
    "prefix":             "X",
    "suffix":             "X",
    "infix":              "X",
    "circumfix":          "X",
    "interfix":           "X",
    "affix":              "X",
    "combining form":     "X",

    # Special
    "contraction":        "X",
    "symbol":             "SYM",
    "character":          "X",
    "punctuation":        "PUNCT",
    "letter":             "X",
    "abbreviation":       "X",
    "initialism":         "X",
    "acronym":            "X",
    "syllable":           "X",
    "han character":      "X",
    "ideogram":           "X",
}


# Map every Wiktionary POS string to one of the 5 simple buckets.
WIKTIONARY_TO_SIMPLE: Dict[str, str] = {
    # Direct hits
    "noun":               "noun",
    "verb":               "verb",
    "adj":                "adj",
    "adjective":          "adj",
    "adv":                "adv",
    "adverb":             "adv",
    "adverbial phrase":   "adv",

    # Proper nouns - distinct bucket because canonical IDs need to distinguish
    # entities from concepts.
    "proper noun":        "name",
    "proper name":        "name",
    "name":               "name",

    # Function / closed-class words bucket to 'other'.
    "pronoun":            "other",
    "preposition":        "other",
    "postposition":       "other",
    "prepositional phrase": "other",
    "conjunction":        "other",
    "determiner":         "other",
    "article":            "other",
    "particle":           "other",
    "numeral":            "other",
    "interjection":       "other",

    # Multi-word and phrase types - bucket to 'noun' if nominal in nature,
    # 'other' otherwise. Phrases tend to behave as noun phrases unless tagged.
    "phrase":             "noun",
    "proverb":            "noun",
    "noun phrase":        "noun",
    "verb phrase":        "verb",

    # Morphological pieces - 'other' since they are not standalone lexemes.
    "prefix":             "other",
    "suffix":             "other",
    "infix":              "other",
    "circumfix":          "other",
    "interfix":           "other",
    "affix":              "other",
    "combining form":     "other",

    # Special
    "contraction":        "other",
    "symbol":             "other",
    "character":          "other",
    "punctuation":        "other",
    "letter":             "other",
    "abbreviation":       "other",
    "initialism":         "other",
    "acronym":            "other",
    "syllable":           "other",
    "han character":      "other",
    "ideogram":           "other",
}


SIMPLE_VALUES = frozenset({"noun", "verb", "adj", "adv", "name", "other"})
SPACY_VALUES = frozenset({
    "NOUN", "VERB", "PROPN", "ADJ", "ADV", "DET", "ADP",
    "CONJ", "CCONJ", "SCONJ", "NUM", "PART", "PRON", "INTJ",
    "PUNCT", "SYM", "AUX", "X", "SPACE",
})


def to_simple(pos_wiktionary: Optional[str]) -> str:
    """
    Convert a Wiktionary POS string to one of the 5 simple buckets.
    Unknown or empty inputs return 'other'.
    """
    if not pos_wiktionary:
        return "other"
    key = pos_wiktionary.strip().lower()
    return WIKTIONARY_TO_SIMPLE.get(key, "other")


def to_spacy(pos_wiktionary: Optional[str]) -> str:
    """
    Convert a Wiktionary POS string to spaCy's Universal Dependencies tag.
    Unknown or empty inputs return 'X' (spaCy's catch-all).
    """
    if not pos_wiktionary:
        return "X"
    key = pos_wiktionary.strip().lower()
    return WIKTIONARY_TO_SPACY.get(key, "X")


def validate_simple(pos: str) -> bool:
    """Return True if `pos` is one of the 5 valid simple buckets."""
    return pos in SIMPLE_VALUES


def validate_spacy(pos: str) -> bool:
    """Return True if `pos` is a valid spaCy Universal Dependencies tag."""
    return pos in SPACY_VALUES


if __name__ == "__main__":
    test_inputs = [
        "noun", "Noun", "NOUN",
        "verb", "adj", "adverb", "proper noun", "proper name",
        "phrase", "proverb", "prefix", "symbol",
        "pronoun", "preposition", "interjection",
        "unknown_type", None, "",
    ]
    print(f"{'Wiktionary POS':<25} -> {'Simple':<10} {'spaCy':<10}")
    print("-" * 50)
    for p in test_inputs:
        print(f"{str(p):<25} -> {to_simple(p):<10} {to_spacy(p):<10}")
