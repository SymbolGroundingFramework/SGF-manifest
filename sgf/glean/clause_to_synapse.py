#!/usr/bin/env python3
"""
clause_to_synapse.py — Stage 7 of the GLEAN pipeline (v3.2)

Read a document plus its entity_map, walk each clause, emit a list of
synapses (predicate + spokes with closed-grammar roles).

For each clause:
  1. Identify the root verb (the predicate).
  2. Walk its dependency children, mapping each to one of the 15 closed
     semantic roles using a deterministic role-mapper based on spaCy
     dependency labels and preposition heads.
  3. Resolve each argument's entity reference using the entity_map.
  4. Emit one synapse per root verb.

OUTPUT SCHEMA (v3.2 — synapedia-compatible):
  Each synapse dict contains:
    synapse_id, doc_id, source_sentence_id, source_clause_id,
    source_span_start, source_span_end,
    verb_lemma, verb_canonical_id, predicate_surface (legacy),
    polarity, spokes,
    plane='claim', epistemic_status='SOURCED', derivation_tag='EXPRESSED',
    pov=None, source_span (JSON string)

  Each spoke dict contains:
    role, target_ent_id, target_canonical_id, target_surface,
    target_id, target_type, target_lemma, literal_value

v3.2 improvements:
  - Verb canonical ID lookup cache (avoids redundant HTTP calls)
  - --no-verb-lookup flag to skip search server entirely
  - Graceful fallback when search server is unreachable
  - Deterministic synapse IDs from content hash

Usage:
    python clause_to_synapse.py --input doc.txt --entity-map entity_map.json \\
                                --output synapses.json --doc-id doc_001
    python clause_to_synapse.py --input doc.txt --entity-map entity_map.json \\
                                --output synapses.json --doc-id doc_001 --no-verb-lookup
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sgflib import load_config, ROLES


# =============================================================================
# Verb canonical ID cache (avoids redundant HTTP calls)
# =============================================================================
_VERB_CACHE: dict = {}


# =============================================================================
# Deterministic dep -> role mapping (loaded from JSON, edit without code change)
# =============================================================================

_DEP_TO_ROLE_CACHE: dict[str, str] | None = None


def _load_dep_to_role() -> dict[str, str]:
    global _DEP_TO_ROLE_CACHE
    if _DEP_TO_ROLE_CACHE is not None:
        return _DEP_TO_ROLE_CACHE
    path = Path(__file__).resolve().parent / "dep_to_role.json"
    if not path.exists():
        raise FileNotFoundError(
            f"dep_to_role.json not found at {path}. "
            "This file is required and ships with the GLEAN bundle."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    for k, v in data.items():
        if k.startswith("_") or v is None:
            continue
        if v not in ROLES:
            raise ValueError(
                f"dep_to_role.json maps {k!r} to {v!r}, which is not one "
                f"of the 15 closed-grammar roles. Valid roles: {ROLES}"
            )
        mapping[k] = v
    _DEP_TO_ROLE_CACHE = mapping
    return mapping


def _dep_role(dep: str) -> str | None:
    return _load_dep_to_role().get(dep)

# Preposition -> role mapping for pobj children of prep heads.
PREP_TO_ROLE = {
    "in": "HAS_LOCATION",
    "on": "HAS_LOCATION",
    "at": "HAS_LOCATION",
    "near": "HAS_LOCATION",
    "inside": "HAS_LOCATION",
    "outside": "HAS_LOCATION",

    "from": "HAS_SOURCE",
    "out_of": "HAS_SOURCE",

    "to": "HAS_DESTINATION",
    "toward": "HAS_DESTINATION",
    "towards": "HAS_DESTINATION",
    "into": "HAS_DESTINATION",
    "onto": "HAS_DESTINATION",

    "with": "HAS_INSTRUMENT",
    "via": "HAS_INSTRUMENT",
    "by": "HAS_INSTRUMENT",
    "using": "HAS_INSTRUMENT",

    "for": "HAS_BENEFICIARY",
    "on_behalf_of": "HAS_BENEFICIARY",

    "because_of": "HAS_CAUSE",
    "due_to": "HAS_CAUSE",
    "owing_to": "HAS_CAUSE",

    "in_order_to": "HAS_REASON",

    "about": "HAS_THEME",
    "regarding": "HAS_THEME",
    "concerning": "HAS_THEME",
    "of": "HAS_THEME",
}

# Temporal preposition / phrase markers
TEMPORAL_PREPS = {"in", "on", "at", "during", "before", "after", "since",
                  "until", "by"}


# =============================================================================
# Helpers
# =============================================================================

def _deterministic_synapse_id(verb: str, doc_id: str, clause_idx: int) -> str:
    """Generate a deterministic synapse_id from content."""
    raw = f"{doc_id}:{verb}:{clause_idx}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"syn.{h}"


def load_spacy(model_name: str):
    import spacy
    try:
        return spacy.load(model_name)
    except OSError:
        raise RuntimeError(
            f"spaCy model {model_name!r} is not installed. "
            f"Install: python -m spacy download {model_name}"
        )


def find_entity_for_span(entity_map: dict, span_start: int,
                        span_end: int, surface: str) -> str | None:
    """Find the ent_id whose mentions include this span (or matching surface)."""
    surface_low = surface.lower()
    for ent in entity_map.get("entities", []):
        for m in ent.get("mentions", []):
            if m["span_start"] == span_start and m["span_end"] == span_end:
                return ent["ent_id"]
            if m["surface"].lower() == surface_low:
                return ent["ent_id"]
        if ent["preferred_canonical"].lower() == surface_low:
            return ent["ent_id"]
        for alias in ent.get("aliases", []):
            if alias.lower() == surface_low:
                return ent["ent_id"]
    return None


def find_canonical_id_for_ent(entity_map: dict, ent_id: str) -> str | None:
    for ent in entity_map.get("entities", []):
        if ent["ent_id"] == ent_id:
            return ent.get("lexicon_canonical_id")
    return None


def _lookup_verb_canonical_id(verb_lemma: str, search_server_url: str) -> str | None:
    """Resolve a verb lemma to its canonical ID via the search server.

    Results are cached in _VERB_CACHE to avoid redundant HTTP calls.
    Returns None if the search server is unreachable or the verb is not found.
    """
    cache_key = (verb_lemma.lower(), "verb")
    cached = _VERB_CACHE.get(cache_key)
    if cached is not None:
        return cached

    try:
        import urllib.request
        import json as _json
        payload = _json.dumps({"lemma": verb_lemma, "pos": "verb"}).encode()
        req = urllib.request.Request(
            f"{search_server_url}/lookup/lemma",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            data = _json.loads(r.read().decode())
        results = data.get("results", [])
        if results:
            cid = results[0].get("canonical_id")
            _VERB_CACHE[cache_key] = cid
            return cid
    except Exception:
        pass

    _VERB_CACHE[cache_key] = None
    return None


# =============================================================================
# The clause-to-synapse builder
# =============================================================================

def is_clause_root(token) -> bool:
    if token.pos_ not in ("VERB", "AUX"):
        return False
    return token.dep_ in ("ROOT", "conj", "ccomp", "xcomp", "relcl",
                          "advcl", "acl")


def build_synapses(cfg, entity_map, text, doc_id, verbose=False,
                   search_server_url: str | None = None,
                   no_verb_lookup: bool = False):
    """Public entry: extract synapses from a prose text.

    Args:
        cfg: Config dict (from sgflib.load_config())
        entity_map: Dict from entity_census.process_document()
        text: Raw prose text
        doc_id: Stable document identifier
        verbose: Print debug output
        search_server_url: URL for verb canonical ID resolution, or None to skip
        no_verb_lookup: If True, skip verb canonical ID resolution entirely

    Returns:
        List of synapse dicts (synapedia-compatible output schema)
    """
    nlp = load_spacy(cfg.get("spacy", {}).get("model", "en_core_web_sm"))
    doc = nlp(text)
    synapses = []

    resolve_verbs = (not no_verb_lookup) and search_server_url is not None

    for sent_idx, sent in enumerate(doc.sents):
        roots = [t for t in sent if is_clause_root(t)]
        for clause_idx, root in enumerate(roots):
            syn = build_one_synapse(
                entity_map, doc_id, root, sent_idx, clause_idx,
                verbose, search_server_url if resolve_verbs else None,
            )
            if syn is not None:
                synapses.append(syn)

    return synapses


def build_one_synapse(entity_map, doc_id, root, sent_idx, clause_idx,
                      verbose=False, search_server_url: str | None = None):
    """Build one synapse from a clause root verb."""
    # Polarity
    polarity = "positive"
    for child in root.children:
        if child.dep_ == "neg":
            polarity = "negative"
            break

    predicate_surface = root.text
    verb_lemma = root.lemma_

    # Resolve verb canonical ID (optional, cached)
    verb_canonical_id = None
    if search_server_url is not None:
        verb_canonical_id = _lookup_verb_canonical_id(verb_lemma, search_server_url)
        if verbose:
            print(f"  verb '{verb_lemma}' -> cid={verb_canonical_id}")

    # Build spokes
    spokes = []
    for child in root.children:
        if child.dep_ == "neg":
            continue
        spoke = child_to_spoke(entity_map, child)
        if spoke is not None:
            spokes.append(spoke)

    if not spokes:
        return None

    # Source span
    subtree = list(root.subtree)
    span_start = min(t.idx for t in subtree)
    span_end = max(t.idx + len(t.text) for t in subtree)

    # Deterministic synapse ID
    synapse_id = _deterministic_synapse_id(verb_lemma, doc_id, clause_idx)

    # Source span JSON
    source_span_json = json.dumps({
        "start": span_start,
        "end": span_end,
        "sentence": sent_idx,
        "clause": clause_idx,
        "doc_id": doc_id,
    })

    return {
        # Synapedia v3.2 fields
        "synapse_id": synapse_id,
        "verb_lemma": verb_lemma,
        "verb_canonical_id": verb_canonical_id,
        "plane": "claim",
        "epistemic_status": "SOURCED",
        "derivation_tag": "EXPRESSED",
        "pov": None,
        "source_span": source_span_json,

        # Legacy / GLEAN v1.2 fields (for backward compat)
        "doc_id": doc_id,
        "source_clause_id": clause_idx,
        "source_sentence_id": sent_idx,
        "source_span_start": span_start,
        "source_span_end": span_end,
        "predicate_surface": predicate_surface,
        "predicate_lemma": verb_lemma,
        "predicate_pos": root.pos_,
        "predicate_canonical_id": verb_canonical_id,
        "polarity": polarity,
        "spokes": spokes,
        "statement_type": "factual",
    }


def child_to_spoke(entity_map, child) -> dict | None:
    """Map one direct child of the clause root to a role + target."""
    skip = {"punct", "mark", "cc", "aux", "auxpass", "expl", "complm",
            "discourse"}
    if child.dep_ in skip:
        return None

    if child.dep_ == "prep":
        return handle_prep(entity_map, child)

    role = _dep_role(child.dep_)
    if not role:
        if child.pos_ in ("NOUN", "PROPN", "PRON"):
            role = "HAS_THEME"
        else:
            return None

    return build_spoke(entity_map, role, child)


def handle_prep(entity_map, prep_token) -> dict | None:
    """Handle prepositional phrases."""
    prep_text = prep_token.text.lower()
    pobj = next((c for c in prep_token.children if c.dep_ == "pobj"), None)
    if pobj is None:
        return None

    role = PREP_TO_ROLE.get(prep_text)

    if prep_text in TEMPORAL_PREPS:
        if pobj.ent_type_ in ("DATE", "TIME"):
            role = "HAS_TIME"

    if not role:
        role = "HAS_THEME"
    return build_spoke(entity_map, role, pobj)


def build_spoke(entity_map, role, token) -> dict:
    """Build a spoke dict from a dependency token."""
    if role not in ROLES:
        role = "HAS_THEME"

    # Determine span
    np_start = token.idx
    np_end = token.idx + len(token.text)
    try:
        for tok in token.subtree:
            np_start = min(np_start, tok.idx)
            np_end = max(np_end, tok.idx + len(tok.text))
    except Exception:
        pass

    target_surface = token.text
    ent_id = find_entity_for_span(entity_map, np_start, np_end, target_surface)
    if not ent_id:
        ent_id = find_entity_for_span(entity_map, token.idx,
                                      token.idx + len(token.text),
                                      target_surface)

    canonical_id = (find_canonical_id_for_ent(entity_map, ent_id)
                    if ent_id else None)

    # Determine target_type
    target_type = "concept"
    literal_value = None
    if canonical_id:
        if canonical_id.startswith("lit."):
            target_type = "TYPED_LITERAL"
            literal_value = canonical_id.split(".", 2)[-1]
        elif canonical_id.startswith("en."):
            target_type = "LEXICON_ENTRY"
        elif canonical_id.startswith("doc.") or canonical_id.startswith("dyn."):
            target_type = "INSTANCE"
    elif ent_id:
        target_type = "DOCUMENT_ENTITY"
    else:
        target_type = "GHOST"

    return {
        # Synapedia v3.2 fields
        "role": role,
        "target_id": canonical_id or ent_id,
        "target_type": target_type,
        "target_lemma": target_surface,
        "literal_value": literal_value,

        # Legacy fields
        "target_ent_id": ent_id,
        "target_canonical_id": canonical_id,
        "target_surface": target_surface,
    }


# =============================================================================
# CLI
# =============================================================================

def main() -> int:
    p = argparse.ArgumentParser(
        description="Extract synapses from a prose document (v3.2)"
    )
    p.add_argument("--input", required=True, help="Path to the prose document")
    p.add_argument("--entity-map", required=True,
                   help="Path to the entity_map.json produced by entity_census.py")
    p.add_argument("--output", required=True, help="Path for synapses.json")
    p.add_argument("--doc-id", default="doc_001")
    p.add_argument("--search-server", default="http://localhost:8400",
                   help="URL of the search server for verb canonical ID resolution")
    p.add_argument("--no-verb-lookup", action="store_true",
                   help="Skip verb canonical ID resolution (faster, no search server needed)")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    in_path = Path(args.input)
    em_path = Path(args.entity_map)
    if not in_path.exists():
        print(f"Input not found: {in_path}", file=sys.stderr)
        return 1
    if not em_path.exists():
        print(f"Entity map not found: {em_path}", file=sys.stderr)
        return 1

    text = in_path.read_text(encoding="utf-8")
    entity_map = json.loads(em_path.read_text(encoding="utf-8"))

    cfg = load_config()

    # If --no-verb-lookup, don't pass search server URL
    search_server_url = None if args.no_verb_lookup else args.search_server

    synapses = build_synapses(
        cfg, entity_map, text, doc_id=args.doc_id,
        verbose=args.verbose,
        search_server_url=search_server_url,
        no_verb_lookup=args.no_verb_lookup,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(synapses, indent=2), encoding="utf-8")

    print()
    print(f"Wrote {len(synapses)} synapses to {out_path}")
    if args.verbose:
        for s in synapses[:20]:
            cid = s.get('verb_canonical_id') or '(unresolved)'
            print(f"  syn {s['synapse_id'][-8:]}  verb={s['verb_lemma']!r}  "
                  f"cid={cid}  spokes={len(s['spokes'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())