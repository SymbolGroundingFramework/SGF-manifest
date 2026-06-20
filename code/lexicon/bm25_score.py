#!/usr/bin/env python3
"""
bm25_score.py -- on-the-fly BM25 lexical scoring + divergence detection.

This module is a stage in the search server's cascade. It does NOT
maintain a precomputed inverted index. Instead, it scores BM25 over
whatever small candidate set the prior stages handed it (typically
3 to 50 senses). That keeps the lexicon storage simple and avoids
index drift when the LLM improver rewrites microglosses.

Public functions:

    tokenize(text, lowercase=True, stemmer="porter") -> list[str]
        Deterministic tokenization. Strips punctuation, splits on
        whitespace, optionally Porter-stems each token.

    bm25_scores(query_terms, docs, k1=1.5, b=0.75) -> list[float]
        Classic BM25 over a small in-memory corpus. `docs` is a list
        of tokenized documents. Returns a list of scores aligned with
        `docs`. No external dependencies.

    normalize_minmax(scores) -> list[float]
        Min-max normalize a list of scores into [0, 1]. Used before
        weighted fusion with prior-stage scores.

    fuse_weighted(prior_norm, bm25_norm, alpha=0.7) -> list[float]
        Linear combination of two normalized score vectors:
        alpha * prior + (1 - alpha) * bm25.

    candidates_diverge_on(candidates, axes) -> bool
        True iff the candidates differ on at least one of the listed
        metadata axes. Used to decide whether the LLM tiebreak should
        fire under "when_tight_divergent" mode.

    cascade_should_fire(stage_cfg, scores) -> bool
        Given a stage config (dict with `mode` and `margin_threshold`)
        and the prior stage's scores, decide whether to run this stage.
        Modes: "always", "never", "when_tight".

No regex. No external models. Deterministic. Fast.
"""

from __future__ import annotations

import math
import string
from typing import Any, Dict, Iterable, List, Sequence


# ---------------------------------------------------------------------------
# Porter stemmer (inline; ~150 lines). Implements the original Porter
# algorithm (Porter, 1980) faithfully enough for BM25 morphology collapse.
# No external dependency.
# ---------------------------------------------------------------------------

_VOWELS = set("aeiou")


def _is_consonant(word, i):
    ch = word[i]
    if ch in _VOWELS:
        return False
    if ch == "y":
        return True if i == 0 else not _is_consonant(word, i - 1)
    return True


def _measure(stem):
    """Compute Porter's `m`: number of VC pairs in the stem."""
    m = 0
    n = len(stem)
    i = 0
    # Skip leading consonants
    while i < n and _is_consonant(stem, i):
        i += 1
    # Each VC pair increases m
    while i < n:
        # Skip vowels
        while i < n and not _is_consonant(stem, i):
            i += 1
        if i >= n:
            break
        # Skip consonants (counts as one VC pair)
        while i < n and _is_consonant(stem, i):
            i += 1
        m += 1
    return m


def _contains_vowel(stem):
    for i in range(len(stem)):
        if not _is_consonant(stem, i):
            return True
    return False


def _ends_double_consonant(word):
    n = len(word)
    if n < 2:
        return False
    if word[-1] != word[-2]:
        return False
    return _is_consonant(word, n - 1)


def _ends_cvc(word):
    """True iff word ends consonant-vowel-consonant, and final isn't W/X/Y."""
    n = len(word)
    if n < 3:
        return False
    if not _is_consonant(word, n - 3):
        return False
    if _is_consonant(word, n - 2):
        return False
    if not _is_consonant(word, n - 1):
        return False
    if word[-1] in ("w", "x", "y"):
        return False
    return True


def porter_stem(word):
    """Apply the Porter stemming algorithm. Lower-case input expected."""
    if len(word) <= 2:
        return word

    # Step 1a
    if word.endswith("sses"):
        word = word[:-2]
    elif word.endswith("ies"):
        word = word[:-2]
    elif word.endswith("ss"):
        pass
    elif word.endswith("s"):
        word = word[:-1]

    # Step 1b
    flag_1b = False
    if word.endswith("eed"):
        stem = word[:-3]
        if _measure(stem) > 0:
            word = word[:-1]
    elif word.endswith("ed"):
        stem = word[:-2]
        if _contains_vowel(stem):
            word = stem
            flag_1b = True
    elif word.endswith("ing"):
        stem = word[:-3]
        if _contains_vowel(stem):
            word = stem
            flag_1b = True

    if flag_1b:
        if word.endswith(("at", "bl", "iz")):
            word = word + "e"
        elif _ends_double_consonant(word) and not word.endswith(("l", "s", "z")):
            word = word[:-1]
        elif _measure(word) == 1 and _ends_cvc(word):
            word = word + "e"

    # Step 1c
    if word.endswith("y"):
        stem = word[:-1]
        if _contains_vowel(stem):
            word = stem + "i"

    # Step 2 -- map double suffixes onto single suffixes when m > 0
    step2_map = [
        ("ational", "ate"), ("tional", "tion"), ("enci", "ence"),
        ("anci", "ance"), ("izer", "ize"), ("abli", "able"),
        ("alli", "al"), ("entli", "ent"), ("eli", "e"),
        ("ousli", "ous"), ("ization", "ize"), ("ation", "ate"),
        ("ator", "ate"), ("alism", "al"), ("iveness", "ive"),
        ("fulness", "ful"), ("ousness", "ous"), ("aliti", "al"),
        ("iviti", "ive"), ("biliti", "ble"),
    ]
    for suffix, replacement in step2_map:
        if word.endswith(suffix):
            stem = word[:-len(suffix)]
            if _measure(stem) > 0:
                word = stem + replacement
            break

    # Step 3
    step3_map = [
        ("icate", "ic"), ("ative", ""), ("alize", "al"),
        ("iciti", "ic"), ("ical", "ic"), ("ful", ""), ("ness", ""),
    ]
    for suffix, replacement in step3_map:
        if word.endswith(suffix):
            stem = word[:-len(suffix)]
            if _measure(stem) > 0:
                word = stem + replacement
            break

    # Step 4 -- drop -al, -ance, -ence, ... when m > 1
    step4_suffixes = [
        "al", "ance", "ence", "er", "ic", "able", "ible", "ant",
        "ement", "ment", "ent", "ion", "ou", "ism", "ate", "iti",
        "ous", "ive", "ize",
    ]
    for suffix in sorted(step4_suffixes, key=len, reverse=True):
        if word.endswith(suffix):
            stem = word[:-len(suffix)]
            if _measure(stem) > 1:
                # Special case for "ion": only drop after s or t
                if suffix == "ion":
                    if stem and stem[-1] in ("s", "t"):
                        word = stem
                else:
                    word = stem
            break

    # Step 5a
    if word.endswith("e"):
        stem = word[:-1]
        m = _measure(stem)
        if m > 1 or (m == 1 and not _ends_cvc(stem)):
            word = stem

    # Step 5b -- drop double-l if m > 1
    if _measure(word) > 1 and _ends_double_consonant(word) and word.endswith("l"):
        word = word[:-1]

    return word


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------

_PUNCT_TO_SPACE = str.maketrans({c: " " for c in string.punctuation})


def tokenize(text, lowercase=True, stemmer="porter"):
    """Deterministic tokenizer used on both query and document side."""
    if text is None:
        return []
    s = str(text)
    if lowercase:
        s = s.lower()
    s = s.translate(_PUNCT_TO_SPACE)
    tokens = [t for t in s.split() if t]
    if stemmer == "porter":
        tokens = [porter_stem(t) for t in tokens]
    elif stemmer in (None, "none", ""):
        pass
    else:
        raise ValueError(f"unknown stemmer: {stemmer!r}")
    return tokens


# ---------------------------------------------------------------------------
# BM25
# ---------------------------------------------------------------------------

def bm25_scores(query_terms, docs, k1=1.5, b=0.75):
    """Classic BM25 over a small in-memory corpus.

    Args:
        query_terms: list of tokenized query terms.
        docs: list of tokenized documents (each a list of tokens).
        k1: term-frequency saturation parameter.
        b: length-normalization parameter.

    Returns:
        list of float scores aligned with `docs`.
    """
    n_docs = len(docs)
    if n_docs == 0:
        return []
    if not query_terms:
        return [0.0] * n_docs

    # Compute document lengths and average
    doc_lens = [len(d) for d in docs]
    avg_dl = sum(doc_lens) / n_docs if n_docs > 0 else 0.0
    if avg_dl == 0:
        return [0.0] * n_docs

    # Document frequencies for each query term
    query_terms_unique = set(query_terms)
    df = {}
    for term in query_terms_unique:
        df[term] = sum(1 for d in docs if term in d)

    # IDF (BM25 variant with +1 to avoid log of 0)
    idf = {}
    for term, df_t in df.items():
        idf[term] = math.log((n_docs - df_t + 0.5) / (df_t + 0.5) + 1.0)

    # Score each doc
    scores = []
    for i, doc in enumerate(docs):
        dl = doc_lens[i]
        # Count term frequencies in this doc once
        tf = {}
        for term in doc:
            if term in query_terms_unique:
                tf[term] = tf.get(term, 0) + 1
        score = 0.0
        for term in query_terms:
            if term not in tf:
                continue
            tf_t = tf[term]
            numerator = tf_t * (k1 + 1)
            denominator = tf_t + k1 * (1 - b + b * dl / avg_dl)
            score += idf[term] * (numerator / denominator)
        scores.append(score)
    return scores


# ---------------------------------------------------------------------------
# Score normalization and fusion
# ---------------------------------------------------------------------------

def normalize_minmax(scores):
    """Min-max normalize into [0, 1]. Returns zeros for an empty or
    flat input."""
    if not scores:
        return []
    lo = min(scores)
    hi = max(scores)
    if hi - lo < 1e-12:
        return [1.0] * len(scores)  # all-equal -> all max
    return [(s - lo) / (hi - lo) for s in scores]


def fuse_weighted(prior_norm, bm25_norm, alpha=0.7):
    """Linear combination of two equal-length normalized score vectors."""
    if len(prior_norm) != len(bm25_norm):
        raise ValueError("score vectors must be equal length")
    return [alpha * p + (1.0 - alpha) * b for p, b in zip(prior_norm, bm25_norm)]


# ---------------------------------------------------------------------------
# Margin and cascade decisions
# ---------------------------------------------------------------------------

def normalized_margin(scores):
    """Top-1 minus top-2 after min-max normalization. Returns 1.0 when
    only one candidate is present, 0.0 when zero candidates."""
    if not scores:
        return 0.0
    if len(scores) == 1:
        return 1.0
    norm = normalize_minmax(scores)
    sorted_norm = sorted(norm, reverse=True)
    return sorted_norm[0] - sorted_norm[1]


def cascade_should_fire(stage_cfg, prior_scores):
    """Decide whether to run a cascade stage given the prior stage's scores.

    `stage_cfg` is a dict with keys `mode` and `margin_threshold`.
    `mode` is one of "always", "never", "when_tight".
    """
    mode = (stage_cfg or {}).get("mode", "never")
    if mode == "always":
        return True
    if mode == "never":
        return False
    if mode == "when_tight":
        threshold = float((stage_cfg or {}).get("margin_threshold", 0.05))
        margin = normalized_margin(prior_scores)
        return margin < threshold
    if mode == "when_tight_divergent":
        # The divergence check is the caller's responsibility (it needs
        # the candidate metadata). We only check the margin here.
        threshold = float((stage_cfg or {}).get("margin_threshold", 0.03))
        margin = normalized_margin(prior_scores)
        return margin < threshold
    raise ValueError(f"unknown cascade mode: {mode!r}")


# ---------------------------------------------------------------------------
# Divergence detection (for LLM tiebreak "when_tight_divergent" mode)
# ---------------------------------------------------------------------------

def candidates_diverge_on(candidates, axes):
    """True iff candidates differ on at least one of the listed axes.

    `candidates` is a list of dicts (each carrying metadata fields).
    `axes` is a list of field names to inspect.

    A candidate that is missing an axis is treated as having value None.
    Divergence is "at least two distinct values, excluding None as a
    single bucket of its own".
    """
    if not candidates or len(candidates) < 2:
        return False
    for axis in axes:
        values = set()
        for c in candidates:
            v = c.get(axis) if isinstance(c, dict) else getattr(c, axis, None)
            # Normalize list/tuple values into a canonical hashable form
            if isinstance(v, (list, tuple)):
                v = tuple(sorted(str(x) for x in v))
            values.add(v)
            if len(values) > 1:
                return True
    return False


# ---------------------------------------------------------------------------
# Convenience: score a small candidate set in one call
# ---------------------------------------------------------------------------

def score_candidates(query_text, candidate_texts, bm25_cfg):
    """Score a small candidate set given a query string and a parallel list
    of candidate text strings.

    Returns a list of raw BM25 scores aligned with `candidate_texts`.
    """
    lowercase = bool(bm25_cfg.get("lowercase", True))
    stemmer = bm25_cfg.get("stemmer", "porter")
    query_terms = tokenize(query_text, lowercase=lowercase, stemmer=stemmer)
    docs = [tokenize(t, lowercase=lowercase, stemmer=stemmer) for t in candidate_texts]
    return bm25_scores(query_terms, docs)
