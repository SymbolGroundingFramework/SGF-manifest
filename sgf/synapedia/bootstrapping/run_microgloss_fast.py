#!/usr/bin/env python3
"""
run_microgloss_fast.py — FAST microgloss generator for testing and development.

Zero external dependencies. No embeddings, no ONNX, no config, no numpy.
Just Python standard library + sqlite3.

Takes the first 2-4 non-stopword tokens from the gloss, joins with underscores.
For multi-sense lemmas, appends a numeric suffix to avoid collisions.

100-1000x faster than the full pipeline. Use this for testing, UI development,
and integration work. Switch to run_microgloss_pipeline.py for production.
"""

import argparse
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


def normalize_token(token: str) -> str:
    """Lowercase, strip diacritics, ASCII-fold."""
    t = token.lower().strip()
    t = unicodedata.normalize('NFKD', t)
    t = t.encode('ascii', 'ignore').decode('ascii')
    return t


def tokenize(text: str) -> list[str]:
    """Tokenize into lowercase alpha tokens, minimum 3 chars."""
    text_ascii = unicodedata.normalize('NFKD', text)
    text_ascii = text_ascii.encode('ascii', 'ignore').decode('ascii')
    tokens = re.findall(r"[a-z]+[a-z0-9]*", text_ascii.lower())
    return [t for t in tokens if len(t) >= 3]


def strip_lemma(gloss: str, lemma: str) -> str:
    """Strip leading repetition of lemma from gloss (e.g. 'jazz is a...' -> 'is a...')."""
    if not gloss or not lemma:
        return gloss or ""
    if gloss.lower().startswith(lemma.lower()):
        next_char = gloss[len(lemma):len(lemma) + 1] if len(gloss) > len(lemma) else ''
        if next_char in (' ', ',', '.', ';', ':', '-', "'", '"', '?', '!', ''):
            gloss = gloss[len(lemma):].lstrip(" ,.;:!?-'\"").strip()
    return gloss


def clean_tokens(gloss: str, lemma: str) -> list[str]:
    """Get non-stopword, non-generic, non-lemma tokens from gloss."""
    if not gloss:
        return []
    cleaned = strip_lemma(gloss, lemma)
    tokens = tokenize(cleaned)
    seen = set()
    result = []
    lemma_norm = normalize_token(lemma)
    for t in tokens:
        n = normalize_token(t)
        if n == lemma_norm:
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
        s = unicodedata.normalize('NFKD', s)
        s = s.encode('ascii', 'ignore').decode('ascii')
        s = re.sub(r"[^a-z0-9_]", "_", s)
        s = re.sub(r"_+", "_", s)
        return s.strip("_") or "unknown"
    
    return (f"en.{sanitize(lemma)}.{sanitize(microgloss) or sanitize(lemma)}"
            f".{sanitize(pos_ud) or 'unknown'}.synapedia_{sanitize(source_type) or 'unknown'}")


def main():
    parser = argparse.ArgumentParser(
        description="FAST microgloss generator — no dependencies beyond stdlib"
    )
    parser.add_argument("--target", default="synapedia.db")
    parser.add_argument("--sample", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-tokens", type=int, default=4)
    args = parser.parse_args()

    t0 = datetime.now()
    print("FAST MICROGLOSS GENERATOR (no config, no embeddings, no dependencies)")
    print(f"  Target:  {args.target}")
    print(f"  Dry run: {args.dry_run}")
    print(f"  Force:   {args.force}")
    print()

    conn = sqlite3.connect(args.target)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Load entries
    if args.sample:
        cur.execute("""
            SELECT entry_id, lemma, gloss, pos_ud, source_type
            FROM synapedia_entry
            WHERE gloss IS NOT NULL AND gloss != ''
            ORDER BY RANDOM() LIMIT ?
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

    # Phase 1: Generate microglosses
    print("\nPhase 1: Generating microglosses...")
    results = []
    for r in rows:
        lemma = r['lemma']
        gloss = r['gloss'] or ''
        tokens = clean_tokens(gloss, lemma)
        if not tokens:
            microgloss = lemma.lower().replace(' ', '_')
        else:
            microgloss = '_'.join(tokens[:args.max_tokens])
        results.append((r['entry_id'], lemma, microgloss, r.get('pos_ud', ''), r.get('source_type', '')))
    print(f"  Generated {len(results):,} microglosses")

    # Phase 2-3: Detect and resolve collisions via numeric suffix
    print("\nPhase 2-3: Detecting and resolving collisions...")
    groups = defaultdict(list)
    for entry_id, lemma, microgloss, pos_ud, source_type in results:
        norm_mg = '_'.join(normalize_token(t) for t in microgloss.split('_'))
        groups[(lemma, norm_mg, pos_ud)].append((entry_id, microgloss, source_type))

    resolved = []
    collision_count = 0
    for key, group in groups.items():
        if len(group) == 1:
            eid, mg, st = group[0]
            resolved.append((eid, key[0], mg, key[2], st, 0))
        else:
            collision_count += 1
            for i, (eid, mg, st) in enumerate(group):
                suffix = '' if i == 0 else f'_{i + 1}'
                resolved.append((eid, key[0], mg + suffix, key[2], st, i))
    print(f"  {collision_count:,} collision groups resolved (numeric suffixes)")

    # Phase 4: Spelling preference
    print("\nPhase 4: Assigning spelling preference...")
    british_set = {
        'colour', 'favour', 'centre', 'theatre', 'metre', 'defence',
        'offence', 'licence', 'practise', 'analyse', 'organise',
        'recognise', 'realise', 'travelled', 'cancelled', 'labelled',
        'modelled', 'focussed', 'grey', 'programme', 'catalogue',
        'dialogue', 'aluminium', 'cheque', 'draught', 'jewellery',
        'mould', 'moustache', 'pyjamas', 'sceptical', 'skilful',
        'tyre', 'yoghurt', 'favourite',
    }
    pref_groups = defaultdict(list)
    for entry_id, lemma, microgloss, pos_ud, source_type, _ in resolved:
        norm_mg = '_'.join(normalize_token(t) for t in microgloss.split('_'))
        key = (norm_mg, pos_ud)
        score = 0
        for t in lemma.split('_') + microgloss.split('_'):
            if any(ord(c) > 127 for c in t):
                score -= 2
            if t.lower() in british_set:
                score -= 2
        pref_groups[key].append((entry_id, lemma, microgloss, pos_ud, source_type, score))

    final_results = []
    pref_count = 0
    for key, group in pref_groups.items():
        group.sort(key=lambda x: (-x[5], x[0]))
        for i, (eid, lemma, mg, pos, st, sc) in enumerate(group):
            is_pref = 1 if i == 0 else 0
            final_results.append((eid, lemma, mg, pos, st, is_pref))
            if is_pref:
                pref_count += 1

    print(f"  {pref_count:,} entries marked as preferred")

    # Write or dry-run
    if args.dry_run:
        print("\n  DRY RUN — nothing written to database")
        print("  Sample results:")
        for eid, lemma, mg, pos, st, pref in final_results[:10]:
            cid = build_canonical_id(lemma, mg, pos, st)
            tag = " [PREFERRED]" if pref else ""
            print(f"    {lemma:15s} → {mg:40s}  {cid}{tag}")
        conn.close()
        return

    print("\nWriting to database...")
    written = 0
    update_sql = """
        UPDATE synapedia_entry
        SET microgloss = ?, canonical_id = ?, embedding_text = ?, is_preferred = ?
        WHERE entry_id = ?
    """
    for eid, lemma, mg, pos, st, pref in final_results:
        cid = build_canonical_id(lemma, mg, pos, st)
        embed_text = f"{lemma}: {mg}" if mg else lemma
        cur.execute(update_sql, (mg, cid, embed_text, pref, eid))
        written += 1
        if written % 5000 == 0:
            conn.commit()

    conn.commit()
    elapsed = (datetime.now() - t0).total_seconds()
    print(f"  Written {written:,} entries in {elapsed:.1f}s ({written/max(elapsed,1):,.0f} entries/s)")

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Processed:   {total:,}")
    print(f"  Time:        {elapsed:.1f}s")
    print(f"  Collisions:  {collision_count:,}")
    print(f"  Preferred:   {pref_count:,}")
    print(f"\n  Examples:")
    for eid, lemma, mg, pos, st, pref in final_results[:5]:
        cid = build_canonical_id(lemma, mg, pos, st)
        tag = " [PREFERRED]" if pref else ""
        print(f"    {lemma:15s} → {mg:40s}{tag}")

    conn.close()
    print("\nDone. For production quality, run run_microgloss_pipeline.py")


if __name__ == "__main__":
    main()