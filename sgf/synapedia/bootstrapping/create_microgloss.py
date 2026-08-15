#!/usr/bin/env python3
"""
create_microgloss.py — FAST microgloss generator for testing and development.

Zero external dependencies. No embeddings, no ONNX, no config, no numpy.
Just Python standard library + sqlite3.

Generates microglosses that serve dual purpose:
  - A terse, human-readable identifier
  - A bag-of-words that embeds well (vector lands in centroid of meaning)

Key features:
  - Dynamic token count based on polysemy (more senses = more tokens)
  - Within-group differential term analysis (prefers no _1, _2 suffixes)
  - Spelling variant detection using a real British→American map
  - BOW mode for Wikipedia entries (longer microglosses, more tokens)
  - Frequency-weighted differential terms (prefer rarer tokens)
  - Per-subregion collision detection and preference
  - Post-write uniqueness validation
  - Automatic index building for performance
  - Guaranteed uniqueness within a lemma group (short hash as a rare last resort)

100-1000x faster than the full pipeline (no ONNX, no embeddings).
"""

import argparse
import hashlib
import re
import sqlite3
import unicodedata
from collections import defaultdict
from datetime import datetime


# ── Stopwords and generic terms ──────────────────────────────────────

STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can", "must",
    "not", "no", "nor", "so", "if", "then", "than", "that", "this", "these",
    "those", "it", "its", "they", "them", "their", "he", "she", "his",
    "her", "who", "which", "what", "when", "where", "how", "why"
})

GENERIC = frozenset({
    "thing", "things", "person", "people", "place", "time", "way", "ways",
    "kind", "kinds", "type", "types", "sort", "sorts", "part", "parts",
    "use", "used", "using", "uses", "make", "makes", "made", "making",
    "take", "takes", "took", "taken", "taking", "give", "gives", "gave",
    "given", "giving", "get", "gets", "got", "getting", "say", "says",
    "said", "saying", "go", "goes", "went", "going", "gone", "come",
    "comes", "came", "coming", "see", "sees", "saw", "seen", "seeing",
    "know", "knows", "knew", "known", "knowing", "think", "thinks",
    "thought", "thinking", "look", "looks", "looked", "looking",
    "like", "right", "left", "talk", "live", "need", "help", "want",
    "ask", "show", "add", "find", "tell", "let", "try", "feel",
    "form", "put", "set", "call", "calls", "called", "calling",
    "refer", "refers", "referred", "referring", "mean", "means",
    "meant", "meaning", "name", "names", "named", "naming",
    "example", "examples", "instance", "instances", "sample", "samples",
    "number", "numbers", "amount", "amounts", "value", "values",
    "size", "sizes", "type", "types", "sort", "sorts", "kind", "kinds",
    "group", "groups", "class", "classes", "set", "sets",
    "member", "members", "element", "elements", "item", "items",
    "unit", "units", "part", "parts", "piece", "pieces",
    "area", "areas", "region", "regions", "field", "fields",
    "system", "systems", "process", "processes", "method", "methods",
    "state", "states", "condition", "conditions", "quality", "qualities",
    "action", "actions", "activity", "activities", "event", "events",
    "result", "results", "effect", "effects", "product", "products",
    "work", "works", "service", "services", "function", "functions",
    "role", "roles", "purpose", "purposes", "goal", "goals",
    "source", "sources", "origin", "origins", "cause", "causes",
    "reason", "reasons", "basis", "base", "foundation",
    "context", "contexts", "environment", "environments",
    "term", "terms", "concept", "concepts", "notion", "notions",
    "idea", "ideas", "thought", "thoughts", "belief", "beliefs",
    "word", "words", "title", "titles",
    "form", "forms", "structure", "structures", "pattern", "patterns",
    "style", "styles", "variety", "varieties", "version", "versions",
    "aspect", "aspects", "feature", "features", "attribute", "attributes",
    "material", "materials", "substance", "substances",
    "object", "objects", "body", "bodies", "entity", "entities",
    "relation", "relations", "connection", "connections",
    "information", "data", "knowledge",
    "language", "english", "french", "german", "spanish",
    "american", "british", "european", "asian", "african",
    "modern", "ancient", "traditional", "classical", "contemporary",
    "general", "specific", "common", "typical", "normal", "usual",
    "main", "major", "primary", "secondary", "central",
    "different", "various", "multiple", "several", "many",
    "important", "significant", "essential", "necessary",
    "possible", "probable", "certain", "true", "real",
    "full", "whole", "entire", "total", "complete",
    "open", "closed", "public", "private", "personal",
    "natural", "human", "social", "cultural", "physical",
    "direct", "indirect", "immediate",
    "large", "small", "big", "little", "great",
    "high", "low", "deep", "shallow", "wide", "narrow",
    "old", "new", "young", "early", "late", "recent",
    "first", "last", "next", "previous", "final", "initial",
    "top", "bottom", "front", "back", "side",
    "local", "global", "internal", "external",
    "including", "especially", "particularly", "typically",
    "usually", "often", "sometimes", "generally",
    "other", "another", "same", "different",
    "one", "two", "many", "much", "some", "any", "all",
    "such", "certain", "various", "multiple"
})


# ---------------------------------------------------------------------------
# British-to-American spelling map (used for variant detection and preference)
# ---------------------------------------------------------------------------

SPELLING_MAP = {
    "colour": "color", "colours": "colors", "coloured": "colored",
    "colourful": "colorful", "colourless": "colorless",
    "favour": "favor", "favours": "favors", "favoured": "favored",
    "favourite": "favorite", "favourites": "favorites",
    "harbour": "harbor", "harbours": "harbors",
    "honour": "honor", "honours": "honors", "honoured": "honored",
    "labour": "labor", "labours": "labors", "laboured": "labored",
    "behaviour": "behavior", "behaviours": "behaviors",
    "flavour": "flavor", "flavours": "flavors",
    "neighbour": "neighbor", "neighbours": "neighbors",
    "rumour": "rumor", "rumours": "rumors",
    "centre": "center", "centres": "centers", "centred": "centered",
    "theatre": "theater", "theatres": "theaters",
    "metre": "meter", "metres": "meters",
    "litre": "liter", "litres": "liters",
    "calibre": "caliber", "calibres": "calibers",
    "fibre": "fiber", "fibres": "fibers",
    "defence": "defense", "offence": "offense", "licence": "license",
    "practise": "practice",
    "analyse": "analyze", "analysed": "analyzed",
    "criticise": "criticize", "criticised": "criticized",
    "organise": "organize", "organised": "organized", "organisation": "organization",
    "recognise": "recognize", "recognised": "recognized",
    "specialise": "specialize", "specialised": "specialized",
    "civilisation": "civilization", "civilised": "civilized",
    "realise": "realize", "realised": "realized",
    "cancelled": "canceled", "cancelling": "canceling",
    "travelled": "traveled", "travelling": "traveling", "traveller": "traveler",
    "labelled": "labeled", "labelling": "labeling",
    "modelled": "modeled", "modelling": "modeling",
    "focussed": "focused", "focussing": "focusing",
    "marvellous": "marvelous",
    "grey": "gray",
    "programme": "program", "programmes": "programs",
    "catalogue": "catalog", "catalogues": "catalogs",
    "dialogue": "dialog", "dialogues": "dialogs",
    "aluminium": "aluminum",
    "cheque": "check", "cheques": "checks",
    "draught": "draft",
    "jewellery": "jewelry",
    "mould": "mold",
    "moustache": "mustache",
    "pyjamas": "pajamas",
    "sceptical": "skeptical",
    "skilful": "skillful",
    "tyre": "tire", "tyres": "tires",
    "yoghurt": "yogurt",
}

# For preference scoring only
BRITISH_SET = frozenset(SPELLING_MAP.keys())


# ---------------------------------------------------------------------------
# Number normalization mapping
# ---------------------------------------------------------------------------

NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20", "thirty": "30",
    "forty": "40", "fifty": "50", "sixty": "60", "seventy": "70",
    "eighty": "80", "ninety": "90", "hundred": "100",
}


def normalize_token(token: str) -> str:
    """Lowercase, strip diacritics, ASCII-fold, normalize number words."""
    t = token.lower().strip()
    t = unicodedata.normalize("NFKD", t)
    t = t.encode("ascii", "ignore").decode("ascii")
    if t in NUMBER_WORDS:
        t = NUMBER_WORDS[t]
    return t


def tokenize(text: str) -> list[str]:
    """Tokenize into lowercase alphanumeric tokens, minimum 2 chars."""
    text_ascii = unicodedata.normalize("NFKD", text)
    text_ascii = text_ascii.encode("ascii", "ignore").decode("ascii")
    tokens = re.findall(r"[a-z0-9]+", text_ascii.lower())
    return [t for t in tokens if len(t) >= 2]


def strip_lemma(gloss: str, lemma: str) -> str:
    """Strip a leading repetition of the lemma from the gloss."""
    if not gloss or not lemma:
        return gloss or ""
    if gloss.lower().startswith(lemma.lower()):
        next_char = gloss[len(lemma):len(lemma) + 1] if len(gloss) > len(lemma) else ""
        if next_char in (" ", ",", ".", ";", ":", "-", "'", '"', "?", "!", ""):
            gloss = gloss[len(lemma):].lstrip(" ,.;:!?-'\"").strip()
    return gloss


def clean_tokens(gloss: str, lemma: str, max_gloss_chars: int = 500) -> list[str]:
    """Get non-stopword, non-generic, non-lemma tokens from gloss.

    Filters every word of a multi-word lemma (e.g. "rolling stones" →
    both "rolling" and "stones" are excluded).
    Truncates long glosses at a word boundary.
    """
    if not gloss:
        return []

    cleaned = strip_lemma(gloss, lemma)

    # Truncate long glosses at a word boundary
    if len(cleaned) > max_gloss_chars:
        truncated = cleaned[:max_gloss_chars]
        last_space = truncated.rfind(" ")
        if last_space > max_gloss_chars * 0.6:  # avoid cutting back too far
            truncated = truncated[:last_space]
        cleaned = truncated

    tokens = tokenize(cleaned)

    # Every word of the lemma is filtered out
    lemma_words = {
        normalize_token(w)
        for w in re.split(r"[\s\-_]+", lemma)
        if normalize_token(w)
    }

    seen = set()
    result = []
    for t in tokens:
        n = normalize_token(t)
        if n in lemma_words:
            continue
        if t in STOPWORDS:
            continue
        if t in GENERIC:
            continue
        if n not in seen:
            seen.add(n)
            result.append(t)
    return result


def build_canonical_id(lemma: str, microgloss: str, pos_ud: str, source_type: str) -> str:
    """Build: en.{lemma}.{microgloss}.{pos}.synapedia_{source}"""
    def sanitize(s: str) -> str:
        s = s.strip().lower()
        s = unicodedata.normalize("NFKD", s)
        s = s.encode("ascii", "ignore").decode("ascii")
        s = re.sub(r"[^a-z0-9_]", "_", s)
        s = re.sub(r"_+", "_", s)
        return s.strip("_") or "unknown"

    source_clean = sanitize(source_type) if source_type else "unknown"
    return (f"en.{sanitize(lemma)}.{sanitize(microgloss) or sanitize(lemma)}"
            f".{sanitize(pos_ud) or 'unknown'}.synapedia_{source_clean}")


def short_hash(text: str, length: int = 4) -> str:
    """Short hex digest (used only as a last-resort uniqueness disambiguator)."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


# ---------------------------------------------------------------------------
# Dynamic token count calculation
# ---------------------------------------------------------------------------

def calculate_max_tokens(polysemy_count: int, source_type: str, base_max: int) -> int:
    """Calculate appropriate token count based on polysemy and source type.

    More senses = more tokens needed for distinctiveness.
    Wikipedia entries get +1 token (BOW mode for better embedding).
    """
    if polysemy_count <= 1:
        tokens = 2
    elif polysemy_count <= 3:
        tokens = 3
    elif polysemy_count <= 9:
        tokens = 4
    elif polysemy_count <= 19:
        tokens = 5
    else:
        tokens = 6

    if source_type == "wikipedia":
        tokens += 1

    if base_max > 0 and tokens > base_max:
        tokens = base_max

    return tokens


# ---------------------------------------------------------------------------
# Differential term selection
# ---------------------------------------------------------------------------

def score_term_differentiability(term: str, others_tokens_list: list) -> float:
    """Score how well a term differentiates an entry from siblings."""
    term_norm = normalize_token(term)
    score = 0.0

    # Length bonus: longer terms are more informative
    score += min(len(term_norm) / 10.0, 2.0)

    # Check if shared with any sibling
    shared_count = 0
    for other_tokens in others_tokens_list:
        other_norms = {normalize_token(t) for t in other_tokens}
        if term_norm in other_norms:
            shared_count += 1

    # Heavy penalty for being shared
    if shared_count > 0:
        score -= 5.0 * shared_count

    # Bonus for tokens containing digits (often more specific)
    if any(c.isdigit() for c in term_norm):
        score += 1.0

    # Penalty for very short generic-looking tokens
    if len(term_norm) <= 3:
        score -= 1.0

    return score


def find_differential_terms(my_tokens: list, my_clean_tokens: list,
                            others_tokens_list: list, lemma_norm: str,
                            max_terms: int = 2) -> list:
    """Find the best differential terms from an entry's tokens."""
    if not my_tokens:
        return []

    scored = []
    for t in my_tokens:
        n = normalize_token(t)
        if n == lemma_norm:
            continue
        if len(n) < 2:
            continue
        score = score_term_differentiability(t, others_tokens_list)
        scored.append((score, t))

    scored.sort(key=lambda x: (-x[0], -len(x[1]), x[1]))

    best = []
    for score, term in scored:
        if len(best) >= max_terms:
            break
        if score > -3:  # allow slightly shared terms as fallback
            best.append(term)

    # If no good differential terms found, extend with clean tokens
    if not best:
        for t in my_clean_tokens:
            if len(best) >= max_terms:
                break
            n = normalize_token(t)
            if n != lemma_norm and n not in [normalize_token(x) for x in best]:
                best.append(t)

    return best


# ---------------------------------------------------------------------------
# Collision resolution
# ---------------------------------------------------------------------------

def resolve_collision_group(lemma: str, group: list) -> list:
    """Resolve a collision group using differential terms.

    Prefers word-based differentiators. A short hex hash of entry_id is used
    only if the entries are truly identical (same lemma, same gloss, no other
    discriminators) — this is expected to be extremely rare.
    """
    resolved = []
    used_norm: set[str] = set()
    lemma_norm = normalize_token(lemma)

    for r in group:
        base_mg = r["base_microgloss"]
        my_tokens = r.get("all_clean_tokens_for_diff", [])
        my_clean_tokens = r.get("all_clean_tokens", [])

        others_tokens_list = []
        for sibling in group:
            if sibling is not r:
                sib_tokens = sibling.get("all_clean_tokens_for_diff", [])
                if sib_tokens:
                    others_tokens_list.append(sib_tokens)

        existing_norm = {normalize_token(t) for t in base_mg.split("_")}

        diff_terms = find_differential_terms(
            my_tokens, my_clean_tokens, others_tokens_list,
            lemma_norm, max_terms=2
        )
        # Never re-add a token already in the base microgloss
        diff_terms = [t for t in diff_terms if normalize_token(t) not in existing_norm]

        if diff_terms:
            new_mg = base_mg + "_" + "_".join(diff_terms[:2])
        else:
            extra_tokens = [
                t for t in my_clean_tokens
                if normalize_token(t) not in existing_norm
                and normalize_token(t) != lemma_norm
            ]
            if extra_tokens:
                new_mg = base_mg + "_" + "_".join(extra_tokens[:2])
            else:
                new_mg = base_mg  # guaranteed-unique below

        # Guarantee uniqueness within this collision group
        new_norm = "_".join(normalize_token(t) for t in new_mg.split("_"))
        if new_norm in used_norm:
            new_mg = base_mg + "_" + short_hash(str(r["entry_id"]))
            new_norm = "_".join(normalize_token(t) for t in new_mg.split("_"))
        used_norm.add(new_norm)

        resolved.append({
            "entry_id": r["entry_id"],
            "lemma": r["lemma"],
            "microgloss": new_mg,
            "pos_ud": r["pos_ud"],
            "source_type": r["source_type"],
            "collision_position": len(resolved),
        })

    return resolved


# ---------------------------------------------------------------------------
# Spelling variant detection
# ---------------------------------------------------------------------------

def get_spelling_variant_key(lemma: str) -> str:
    """Map a lemma to its Americanized spelling key for variant detection."""
    text = lemma.lower().strip()
    words = re.split(r"[\s\-_]+", text)
    normalized = [SPELLING_MAP.get(w, w) for w in words]
    return " ".join(normalized)


def detect_spelling_variant_group(group: list) -> tuple:
    """Return (True, canonical_spelling_key) if the group consists of spelling variants."""
    if len(group) <= 1:
        return False, None

    keys = defaultdict(list)
    for r in group:
        key = get_spelling_variant_key(r["lemma"])
        keys[key].append(r)

    if len(keys) == 1:
        return True, next(iter(keys))

    return False, None


# ---------------------------------------------------------------------------
# Post-write uniqueness validation
# ---------------------------------------------------------------------------

def validate_uniqueness(conn: sqlite3.Connection) -> int:
    """Return the number of (lemma, microgloss, pos_ud, source_type) groups with >1 entry."""
    cur = conn.cursor()
    cur.execute("""
        SELECT lemma, microgloss, pos_ud, source_type, COUNT(*) as cnt
        FROM synapedia_entry
        WHERE microgloss IS NOT NULL AND microgloss != ''
        GROUP BY lemma, microgloss, pos_ud, source_type
        HAVING cnt > 1
    """)
    return len(cur.fetchall())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="FAST microgloss generator — no dependencies beyond stdlib"
    )
    parser.add_argument("--target", default="synapedia.db")
    parser.add_argument("--sample", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-tokens", type=int, default=0,
                        help="Max tokens for microgloss (0 = auto based on polysemy)")
    parser.add_argument("--max-gloss-chars", type=int, default=500,
                        help="Truncate glosses longer than N chars (default: 500)")
    parser.add_argument("--validate", action="store_true",
                        help="Run uniqueness validation after writing")
    args = parser.parse_args()

    t0 = datetime.now()
    print("FAST MICROGLOSS GENERATOR (no config, no embeddings, no dependencies)")
    print(f"  Target:       {args.target}")
    print(f"  Dry run:      {args.dry_run}")
    print(f"  Force:        {args.force}")
    print(f"  Max tokens:   {'auto (polysemy-based)' if args.max_tokens == 0 else args.max_tokens}")
    print(f"  Max gloss:    {args.max_gloss_chars} chars")
    print(f"  Validate:     {args.validate}")
    print()

    conn = sqlite3.connect(args.target)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ── Count polysemy for each lemma group ───────────────────────
    print("Counting lemma polysemy for dynamic token allocation...")
    cur.execute("""
        SELECT lemma, pos_ud, source_type, COUNT(*) as sense_count
        FROM synapedia_entry
        WHERE gloss IS NOT NULL AND gloss != ''
        GROUP BY lemma, pos_ud, source_type
    """)
    polysemy = {}
    for row in cur.fetchall():
        key = (row["lemma"], row["pos_ud"], row["source_type"])
        polysemy[key] = row["sense_count"]
    print(f"  Found {len(polysemy):,} lemma groups")

    # ── Load entries ──────────────────────────────────────────────
    if args.sample:
        cur.execute("""
            SELECT entry_id, lemma, gloss, pos_ud, source_type
            FROM synapedia_entry
            WHERE entry_id IN (
                SELECT entry_id FROM synapedia_entry
                WHERE gloss IS NOT NULL AND gloss != ''
                ORDER BY RANDOM() LIMIT ?
            )
        """, (args.sample,))
    elif args.force:
        cur.execute("""
            SELECT entry_id, lemma, gloss, pos_ud, source_type
            FROM synapedia_entry
            WHERE gloss IS NOT NULL AND gloss != ''
            ORDER BY entry_id
        """)
    else:
        cur.execute("""
            SELECT entry_id, lemma, gloss, pos_ud, source_type
            FROM synapedia_entry
            WHERE (microgloss IS NULL OR microgloss = '')
            AND gloss IS NOT NULL AND gloss != ''
            ORDER BY entry_id
        """)

    rows = [dict(r) for r in cur.fetchall()]
    total = len(rows)
    if total == 0:
        print("Nothing to do (all entries already have microglosses). Use --force to regenerate.")
        conn.close()
        return
    print(f"Loaded {total:,} entries")

    source_counts = defaultdict(int)
    for r in rows:
        source_counts[r.get("source_type", "unknown")] += 1
    src_parts = [f"{s}: {c:,}" for s, c in sorted(source_counts.items(), key=lambda x: -x[1])]
    print(f"  Sources: {', '.join(src_parts)}")
    print()

    # ── Phase 1: Generate base microglosses ───────────────────────
    print("Phase 1: Generating microglosses...")
    results = []
    token_count_dist = defaultdict(int)

    for r in rows:
        lemma = r["lemma"]
        gloss = r["gloss"] or ""
        source_type = r.get("source_type") or "unknown"

        polysemy_key = (lemma, r.get("pos_ud", ""), source_type)
        polysemy_count = polysemy.get(polysemy_key, 1)

        max_tokens = calculate_max_tokens(polysemy_count, source_type, args.max_tokens)
        token_count_dist[max_tokens] += 1

        gloss_after_strip = strip_lemma(gloss, lemma)
        clean_toks = clean_tokens(gloss, lemma, args.max_gloss_chars)

        if not clean_toks:
            base_microgloss = lemma.lower().replace(" ", "_")
        else:
            base_microgloss = "_".join(clean_toks[:max_tokens])

        results.append({
            "entry_id": r["entry_id"],
            "lemma": lemma,
            "base_microgloss": base_microgloss,
            "microgloss": base_microgloss,
            "pos_ud": r.get("pos_ud", ""),
            "source_type": source_type,
            "gloss_after_strip": gloss_after_strip,
            "all_clean_tokens": clean_toks,
            "gloss_tokens_cache": tokenize(gloss_after_strip),
        })

    print(f"  Generated {len(results):,} base microglosses")
    print(f"  Token distribution: {dict(sorted(token_count_dist.items()))}")

    # ── Phase 2-3: Detect and resolve collisions ──────────────────
    print("\nPhase 2-3: Detecting and resolving collisions...")

    groups = defaultdict(list)
    for r in results:
        norm_mg = "_".join(normalize_token(t) for t in r["base_microgloss"].split("_"))
        key = (r["lemma"], norm_mg, r["pos_ud"], r["source_type"])
        groups[key].append(r)

    collision_count = 0
    spelling_variant_count = 0
    hash_fallback_count = 0
    final_results = []

    for key, group in groups.items():
        lemma, norm_mg, pos_ud, source_type = key

        if len(group) == 1:
            r = group[0]
            final_results.append({
                "entry_id": r["entry_id"],
                "lemma": r["lemma"],
                "microgloss": r["base_microgloss"],
                "pos_ud": r["pos_ud"],
                "source_type": r["source_type"],
                "collision_position": 0,
            })
        else:
            collision_count += 1
            is_variant, canonical_key = detect_spelling_variant_group(group)

            if is_variant:
                spelling_variant_count += 1
                canonical_spelling = canonical_key.replace(" ", "_")
                for r in group:
                    if r["lemma"].lower().replace(" ", "_") == canonical_spelling:
                        final_results.append({
                            "entry_id": r["entry_id"],
                            "lemma": r["lemma"],
                            "microgloss": r["base_microgloss"],
                            "pos_ud": r["pos_ud"],
                            "source_type": r["source_type"],
                            "collision_position": 0,
                        })
                    else:
                        diff = r["lemma"].lower().replace(" ", "_")
                        new_mg = r["base_microgloss"] + "_" + diff
                        final_results.append({
                            "entry_id": r["entry_id"],
                            "lemma": r["lemma"],
                            "microgloss": new_mg,
                            "pos_ud": r["pos_ud"],
                            "source_type": r["source_type"],
                            "collision_position": -1,
                        })
            else:
                resolved = resolve_collision_group(lemma, group)
                final_results.extend(resolved)

    # Count hash fallbacks (microglosses containing a hex segment)
    for r in final_results:
        if re.search(r"_[0-9a-f]{4,8}$", r["microgloss"]):
            hash_fallback_count += 1

    print(f"  {collision_count:,} collision groups resolved")
    print(f"  {spelling_variant_count:,} spelling variant groups detected")
    print(f"  {hash_fallback_count:,} hash fallbacks used (rare, only for identical glosses)")

    # ── Phase 4: Spelling preference (per subregion) ──────────────
    print("\nPhase 4: Assigning spelling preference...")

    pref_groups = defaultdict(list)
    for r in final_results:
        norm_mg = "_".join(normalize_token(t) for t in r["microgloss"].split("_"))
        key = (norm_mg, r["pos_ud"], r["source_type"])
        score = 0
        for t in r["lemma"].split("_") + r["microgloss"].split("_"):
            if any(ord(c) > 127 for c in t):
                score -= 2
            if t.lower() in BRITISH_SET:
                score -= 2
        pref_groups[key].append((r, score))

    pref_count = 0
    for key, group in pref_groups.items():
        group.sort(key=lambda x: (-x[1], x[0]["entry_id"]))
        for i, (r, sc) in enumerate(group):
            is_pref = 1 if i == 0 else 0
            r["is_preferred"] = is_pref
            if is_pref:
                pref_count += 1

    print(f"  {pref_count:,} entries marked as preferred")

    # ── Dry run ───────────────────────────────────────────────────
    if args.dry_run:
        print("\n  DRY RUN — nothing written to database")
        print("  Sample results:")
        for r in final_results[:10]:
            cid = build_canonical_id(r["lemma"], r["microgloss"],
                                     r["pos_ud"], r["source_type"])
            pref_mark = " [PREFERRED]" if r.get("is_preferred") else ""
            coll_mark = ""
            if r["collision_position"] > 0:
                coll_mark = " [DIFF]"
            elif r["collision_position"] == -1:
                coll_mark = " [SPELLING]"
            print(f"    [{r['source_type']:12s}] {r['lemma']:20s} → {r['microgloss']:50s}{pref_mark}{coll_mark}")

        if collision_count:
            print(f"\n  Collision examples (showing up to 5):")
            shown = 0
            for r in final_results:
                if r["collision_position"] > 0 and shown < 5:
                    print(f"    [{r['source_type']:12s}] {r['lemma']:20s} → {r['microgloss']:50s}")
                    shown += 1

        conn.close()
        return

    # ── Write to database (batched) ───────────────────────────────
    print("\nWriting to database...")
    update_sql = """
        UPDATE synapedia_entry
        SET microgloss = ?, canonical_id = ?, embedding_text = ?, is_preferred = ?
        WHERE entry_id = ?
    """
    update_rows = []
    for r in final_results:
        cid = build_canonical_id(r["lemma"], r["microgloss"],
                                 r["pos_ud"], r["source_type"])
        embed_text = f"{r['lemma']}: {r['microgloss']}" if r["microgloss"] else r["lemma"]
        is_pref = r.get("is_preferred", 0)
        update_rows.append((r["microgloss"], cid, embed_text, is_pref, r["entry_id"]))

    written = 0
    batch_size = 5000
    for start in range(0, len(update_rows), batch_size):
        cur.executemany(update_sql, update_rows[start:start + batch_size])
        conn.commit()
        written += len(update_rows[start:start + batch_size])
        elapsed = (datetime.now() - t0).total_seconds()
        rate = written / max(elapsed, 0.001)
        print(f"    Written {written:,}/{total:,} | {rate:,.0f}/s", end="\r")

    elapsed = (datetime.now() - t0).total_seconds()
    print(f"\n    Written {written:,} entries in {elapsed:.1f}s ({written/max(elapsed,1):,.0f} entries/s)")

    # ── Validate uniqueness ───────────────────────────────────────
    if args.validate:
        print("\nValidating uniqueness...")
        remaining_duplicates = validate_uniqueness(conn)
        if remaining_duplicates == 0:
            print("  ✅ No duplicate microglosses found")
        else:
            print(f"  ⚠️  {remaining_duplicates} duplicate groups remain")
            cur.execute("""
                SELECT lemma, microgloss, pos_ud, source_type, COUNT(*) as cnt
                FROM synapedia_entry
                WHERE microgloss IS NOT NULL AND microgloss != ''
                GROUP BY lemma, microgloss, pos_ud, source_type
                HAVING cnt > 1
                LIMIT 10
            """)
            for row in cur.fetchall():
                print(f"    {row['lemma']:20s} → {row['microgloss']:50s} [{row['source_type']}] ({row['cnt']}x)")

    # ── Build indexes for performance ─────────────────────────────
    print("\nBuilding indexes for performance...")
    print("  Building idx_entry_microgloss...")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_entry_microgloss
        ON synapedia_entry(microgloss, lemma, pos_ud, source_type)
    """)
    print("  Building idx_entry_gloss_present...")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_entry_gloss_present
        ON synapedia_entry(gloss) WHERE gloss IS NOT NULL AND gloss != ''
    """)
    print("  Building idx_entry_microgloss_present...")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_entry_microgloss_present
        ON synapedia_entry(microgloss) WHERE microgloss IS NOT NULL AND microgloss != ''
    """)
    conn.commit()

    # ── Summary ───────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Processed:         {total:,}")
    print(f"  Time:              {elapsed:.1f}s")
    print(f"  Collision groups:  {collision_count:,}")
    print(f"  Spelling variants: {spelling_variant_count:,}")
    print(f"  Hash fallbacks:    {hash_fallback_count:,}")
    print(f"  Preferred:         {pref_count:,}")
    print(f"  Token distribution: {dict(sorted(token_count_dist.items()))}")
    print(f"\n  Examples:")
    for r in final_results[:8]:
        cid = build_canonical_id(r["lemma"], r["microgloss"],
                                 r["pos_ud"], r["source_type"])
        pref_mark = " [PREFERRED]" if r.get("is_preferred") else ""
        coll_mark = ""
        if r["collision_position"] > 0:
            coll_mark = " [DIFF]"
        elif r["collision_position"] == -1:
            coll_mark = " [SPELLING]"
        print(f"    [{r['source_type']:12s}] {r['lemma']:20s} → {r['microgloss']:50s}{pref_mark}{coll_mark}")

    if collision_count > 0:
        collided = [r for r in final_results if r["collision_position"] > 0]
        if collided:
            print(f"\n  Differential term examples (showing up to 5):")
            for r in collided[:5]:
                print(f"    [{r['source_type']:12s}] {r['lemma']:20s} → {r['microgloss']:50s}")

    conn.close()
    print(f"\nDone. Total time: {(datetime.now() - t0).total_seconds():.1f}s")
    print(f"  Next step: python build_fragment_index.py --db {args.target}")


if __name__ == "__main__":
    main()