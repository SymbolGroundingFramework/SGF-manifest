"""candidate_strategies.py -- deterministic microgloss candidate generators.

Eight pure-function strategies. Each takes a `sense_context` dict and
returns a list of candidate microgloss strings (lowercase, snake_case,
short). The tournament tries each in order; the first whose candidate
passes the two-test audit wins. If all eight fail, the LLM improver
runs as the fallback.

Why deterministic candidates first:
    Microglosses for the long tail (1.7M senses in full Wiktionary)
    cannot afford one LLM call per sense. Most senses are structurally
    simple: pick the head noun, drop function words, optionally
    qualify with a domain tag. Eight cheap shots cover the bulk; the
    LLM only sees senses where structure fails.

sense_context dict shape:
    lemma                : str
    pos_simple           : str ('n', 'v', 'adj', 'adv', ...)
    gloss                : str (the original Wiktionary gloss)
    examples             : list[str] (example sentences, may be empty)
    tags                 : list[str] (lowercased semantic tags)
    register             : str | None
    temporal_status      : str | None
    social_status        : str | None
    specificity          : str | None
    lemma_mates          : list[dict] (other senses of same lemma)
                           each with: wsid, gloss, microgloss (prior),
                           tags, register
    cousins              : list[dict] (cross-lemma close cousins)
                           each with: wsid, lemma, gloss, microgloss
    synonyms             : list[str]
    antonyms             : list[str]
    hypernyms            : list[str]
    hyponyms             : list[str]
    coordinate_terms     : list[str]
    related              : list[str]

All strategies return between 0 and 3 candidates. Zero is fine -- it
means the strategy could not produce a defensible candidate for this
sense (e.g. example_distilled with no examples). The tournament moves
on to the next strategy.
"""

# Conservative stopword list. We do not import NLTK / spaCy here; those
# add install weight and license complexity. This list is small but
# covers what bites you in lexicon definitions.
_STOPWORDS = frozenset({
    "a", "an", "the", "of", "to", "in", "on", "at", "by", "for",
    "with", "from", "as", "into", "onto", "over", "under", "out",
    "is", "are", "was", "were", "be", "being", "been", "am",
    "do", "does", "did", "doing", "done",
    "have", "has", "had", "having",
    "or", "and", "but", "so", "yet", "if", "than", "then", "that",
    "this", "these", "those", "which", "who", "whom", "whose",
    "it", "its", "he", "she", "him", "her", "his", "hers", "they",
    "them", "their", "theirs", "we", "us", "our", "ours", "you",
    "your", "yours", "i", "me", "my", "mine",
    "not", "no", "nor", "any", "all", "some", "such", "very",
    "more", "most", "less", "least", "much", "many", "few",
    "one", "two", "ones", "thing", "things", "way", "ways",
    "person", "people",  # too generic to anchor a microgloss
    "used", "use", "uses", "using",
    "etc",
})


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------

def _tokenize(text):
    """Whitespace + punctuation tokenizer. No regex (per project rule)."""
    if not text:
        return []
    buf = []
    out = []
    for ch in text.lower():
        if ch.isalpha() or ch == "'":
            buf.append(ch)
        else:
            if buf:
                out.append("".join(buf))
                buf = []
    if buf:
        out.append("".join(buf))
    return out


def _content_words(text, skip_lemma=None):
    """Return content words from text, in original order, deduped.

    skip_lemma : str, the sense's own lemma -- skipped to avoid
                 microglosses that just echo the lemma.
    """
    skip = (skip_lemma or "").lower().strip()
    seen = set()
    out = []
    for tok in _tokenize(text):
        if len(tok) < 2:
            continue
        if tok in _STOPWORDS:
            continue
        if tok == skip:
            continue
        if tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    return out


def _to_snake(words, max_tokens=5):
    """Join words with underscores, capped at max_tokens. Returns "" if
    nothing usable."""
    if not words:
        return ""
    kept = [w for w in words[:max_tokens] if w]
    return "_".join(kept) if kept else ""


def _candidates_unique(candidates):
    """Drop duplicates and empty strings, preserving order."""
    seen = set()
    out = []
    for c in candidates:
        if not c:
            continue
        c = c.strip().strip("_")
        if not c or c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


# ---------------------------------------------------------------------------
# Strategy 1: compositional (gloss head)
# ---------------------------------------------------------------------------

def strategy_compositional(ctx):
    """Take the first 2-4 content words of the gloss, joined by underscores.

    Works for ~60% of simple senses where the gloss is already a tight
    descriptive phrase: "An animal of the bovine family" -> "animal_bovine_family".
    """
    gloss = (ctx.get("gloss") or "").strip()
    if not gloss:
        return []
    # Drop a leading "A "/"An "/"The " for cleanliness
    lower = gloss.lower()
    for art in ("a ", "an ", "the "):
        if lower.startswith(art):
            gloss = gloss[len(art):]
            break
    words = _content_words(gloss, skip_lemma=ctx.get("lemma"))
    out = []
    # Two variants: 3-word and 4-word. The audit picks whichever wins.
    out.append(_to_snake(words, max_tokens=3))
    out.append(_to_snake(words, max_tokens=4))
    return _candidates_unique(out)


# ---------------------------------------------------------------------------
# Strategy 2: lemma-mate disambig (contrast against sibling senses)
# ---------------------------------------------------------------------------

def strategy_lemma_mate_disambig(ctx):
    """Pick content words from THIS sense's gloss that do NOT appear in
    sibling lemma-mates' glosses or microglosses. The first such word
    is the most distinguishing.

    Combine the first distinguishing content word with the second-best
    one. If no distinguishing words exist, return [].
    """
    gloss = ctx.get("gloss") or ""
    mates = ctx.get("lemma_mates") or []
    if not gloss or not mates:
        return []

    # Pool of words used by sibling senses
    sibling_pool = set()
    for m in mates:
        sibling_pool.update(_content_words(m.get("gloss") or "",
                                           skip_lemma=ctx.get("lemma")))
        sibling_pool.update(_content_words(m.get("microgloss") or "",
                                           skip_lemma=ctx.get("lemma")))

    own_words = _content_words(gloss, skip_lemma=ctx.get("lemma"))
    distinguishing = [w for w in own_words if w not in sibling_pool]
    if not distinguishing:
        return []

    # Two candidates: just the top distinguisher, and top-2 combined.
    out = [distinguishing[0]]
    if len(distinguishing) >= 2:
        out.append(_to_snake(distinguishing[:2]))
    if len(distinguishing) >= 1 and own_words:
        # Distinguisher + first own content word (anchors the topic)
        anchor = next((w for w in own_words if w != distinguishing[0]), None)
        if anchor:
            out.append(_to_snake([distinguishing[0], anchor]))
    return _candidates_unique(out)


# ---------------------------------------------------------------------------
# Strategy 3: cluster anchor (pin to a hypernym or coordinate term)
# ---------------------------------------------------------------------------

def strategy_cluster_anchor(ctx):
    """Take the first content word of the gloss and qualify it with the
    first hypernym (semantic category) or coordinate term (peer category).

    "robin" with gloss "small brown bird" and hypernym "bird" ->
        "small_bird" (hypernym variant), "small_brown_bird" (full),
        "robin_bird" -- skipped because echoes the lemma.
    """
    gloss = ctx.get("gloss") or ""
    own_words = _content_words(gloss, skip_lemma=ctx.get("lemma"))
    if not own_words:
        return []
    hypernyms = ctx.get("hypernyms") or []
    coords = ctx.get("coordinate_terms") or []

    out = []
    for anchor in (hypernyms[:2] + coords[:1]):
        anchor_clean = _to_snake(_content_words(anchor,
                                                skip_lemma=ctx.get("lemma")))
        if not anchor_clean:
            continue
        out.append(_to_snake([own_words[0], anchor_clean]))
        if len(own_words) >= 2:
            out.append(_to_snake([own_words[0], own_words[1], anchor_clean]))
    return _candidates_unique(out)


# ---------------------------------------------------------------------------
# Strategy 4: tag qualified (domain prefix)
# ---------------------------------------------------------------------------

def strategy_tag_qualified(ctx):
    """If the sense has a semantic tag (medicine, law, music, ...),
    qualify the head content word with it.

    "negligence" with tag "law" and gloss "failure to exercise care" ->
        "law_failure_care", "law_negligence_failure".
    """
    tags = ctx.get("tags") or []
    if not tags:
        return []
    gloss = ctx.get("gloss") or ""
    words = _content_words(gloss, skip_lemma=ctx.get("lemma"))
    if not words:
        return []
    tag = tags[0]
    out = []
    out.append(_to_snake([tag] + words[:2]))
    out.append(_to_snake([tag] + words[:3]))
    return _candidates_unique(out)


# ---------------------------------------------------------------------------
# Strategy 5: example distilled (pull content words from example)
# ---------------------------------------------------------------------------

def strategy_example_distilled(ctx):
    """When the gloss is thin, the example sentence often tells the
    fuller story. Pull content words from the first example, skip the
    lemma itself, take the first 2-3 distinguishing words.
    """
    examples = ctx.get("examples") or []
    if not examples:
        return []
    out = []
    for ex in examples[:2]:
        words = _content_words(ex, skip_lemma=ctx.get("lemma"))
        # Skip examples where every word was a stopword
        if len(words) < 2:
            continue
        out.append(_to_snake(words, max_tokens=3))
        out.append(_to_snake(words, max_tokens=4))
    return _candidates_unique(out)


# ---------------------------------------------------------------------------
# Strategy 6: antonym contrast
# ---------------------------------------------------------------------------

def strategy_antonym_contrast(ctx):
    """If the sense has a clean antonym, use it as a not_X disambiguator.

    "warm" sense_2 with antonym "cool" -> "not_cool_warm". Catches the
    cases where the sense is structurally defined by contrast.
    """
    antonyms = ctx.get("antonyms") or []
    if not antonyms:
        return []
    gloss = ctx.get("gloss") or ""
    own_words = _content_words(gloss, skip_lemma=ctx.get("lemma"))
    out = []
    for ant in antonyms[:2]:
        ant_clean = _to_snake(_content_words(ant, skip_lemma=ctx.get("lemma")))
        if not ant_clean:
            continue
        if own_words:
            out.append(_to_snake(["not", ant_clean, own_words[0]]))
        out.append(_to_snake(["opposite_of", ant_clean]))
    return _candidates_unique(out)


# ---------------------------------------------------------------------------
# Strategy 7: hypernym specialized (hypernym + modifier)
# ---------------------------------------------------------------------------

def strategy_hypernym_specialized(ctx):
    """Take the hypernym as the category, modify it with the most
    distinguishing adjective/noun from the gloss.

    Similar to cluster_anchor but inverts the order (hypernym first,
    modifier second), which can land differently in cosine space.
    """
    hypernyms = ctx.get("hypernyms") or []
    if not hypernyms:
        return []
    gloss = ctx.get("gloss") or ""
    own_words = _content_words(gloss, skip_lemma=ctx.get("lemma"))
    if not own_words:
        return []
    out = []
    for hyp in hypernyms[:2]:
        hyp_clean = _to_snake(_content_words(hyp, skip_lemma=ctx.get("lemma")))
        if not hyp_clean:
            continue
        out.append(_to_snake([hyp_clean, own_words[0]]))
        if len(own_words) >= 2:
            out.append(_to_snake([hyp_clean, own_words[0], own_words[1]]))
    return _candidates_unique(out)


# ---------------------------------------------------------------------------
# Strategy 8: definitional fallback (full gloss content, longer cap)
# ---------------------------------------------------------------------------

def strategy_definitional_fallback(ctx):
    """When all else fails, take more of the gloss. This trades brevity
    for completeness; the tournament's token-count penalty makes sure
    it only wins when shorter candidates failed.
    """
    gloss = (ctx.get("gloss") or "").strip()
    if not gloss:
        return []
    lower = gloss.lower()
    for art in ("a ", "an ", "the "):
        if lower.startswith(art):
            gloss = gloss[len(art):]
            break
    words = _content_words(gloss, skip_lemma=ctx.get("lemma"))
    if not words:
        return []
    out = []
    out.append(_to_snake(words, max_tokens=5))
    out.append(_to_snake(words, max_tokens=7))
    return _candidates_unique(out)


# ---------------------------------------------------------------------------
# Strategy registry (order matters: tried in sequence by the tournament)
# ---------------------------------------------------------------------------

STRATEGIES = (
    ("compositional",          strategy_compositional),
    ("lemma_mate_disambig",    strategy_lemma_mate_disambig),
    ("cluster_anchor",         strategy_cluster_anchor),
    ("tag_qualified",          strategy_tag_qualified),
    ("example_distilled",      strategy_example_distilled),
    ("antonym_contrast",       strategy_antonym_contrast),
    ("hypernym_specialized",   strategy_hypernym_specialized),
    ("definitional_fallback",  strategy_definitional_fallback),
)


def all_candidates(ctx):
    """Run every strategy and return [(strategy_name, [candidate, ...]), ...]
    in registry order. Strategies with no output are still represented
    (empty list) so the caller sees the full strategy sequence.
    """
    return [(name, fn(ctx)) for (name, fn) in STRATEGIES]
