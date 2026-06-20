#!/usr/bin/env python3
"""
clause_to_synapse.py — Stage 7 of the GLEAN pipeline

Read a document plus its entity_map, walk each clause, emit a list of
synapses (predicate + spokes with closed-grammar roles).

For each clause:
  1. Identify the root verb (the predicate).
  2. Walk its dependency children, mapping each to one of the 15 closed
     semantic roles using a deterministic role-mapper based on spaCy
     dependency labels and preposition heads.
  3. Resolve each argument's entity reference using the entity_map.
  4. Emit one synapse per root verb.

For copular constructions ("X is Y"), the predicate is the copula and
the spokes are HAS_AGENT (X) and HAS_ATTRIBUTE (Y) or HAS_AGENT (X) and
HAS_THEME (Y) depending on whether Y is an adjective or a noun.

Output is a JSON file: list of synapse dicts, each with:
  synapse_id, source_clause_id, source_sentence_id, source_span,
  predicate_surface, predicate_lemma, predicate_pos,
  polarity, spokes: [{role, target_ent_id, target_surface}, ...]

Usage:
    python clause_to_synapse.py --input doc.txt --entity-map entity_map.json \\
                                --output synapses.json --doc-id doc_001
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sgflib import load_config, ROLES


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

def short_uuid() -> str:
    return uuid.uuid4().hex[:8]


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
        # Last-resort match on preferred_canonical
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


# =============================================================================
# The clause-to-synapse builder
# =============================================================================

class SynapseBuilder:

    def __init__(self, cfg, entity_map: dict, *, verbose: bool = False):
        self.cfg = cfg
        self.entity_map = entity_map
        self.verbose = verbose
        self.nlp = load_spacy(cfg.raw["spacy"]["model"])

    def build(self, text: str, doc_id: str) -> list[dict]:
        doc = self.nlp(text)
        synapses: list[dict] = []

        for sent_idx, sent in enumerate(doc.sents):
            # Each sentence has one or more clauses. For v1 we treat
            # each finite verb as a clause root. spaCy's dep parse
            # identifies these as VERB with dep in (ROOT, conj, ccomp,
            # xcomp, relcl, advcl).
            roots = [t for t in sent if self._is_clause_root(t)]
            for clause_idx, root in enumerate(roots):
                syn = self._build_one(doc_id, root, sent_idx, clause_idx)
                if syn is not None:
                    synapses.append(syn)

        return synapses

    def _is_clause_root(self, token) -> bool:
        if token.pos_ not in ("VERB", "AUX"):
            return False
        return token.dep_ in ("ROOT", "conj", "ccomp", "xcomp", "relcl",
                              "advcl", "acl")

    def _build_one(self, doc_id: str, root, sent_idx: int, clause_idx: int) -> dict | None:
        # Polarity: look for negation child
        polarity = "positive"
        for child in root.children:
            if child.dep_ == "neg":
                polarity = "negative"
                break

        # Predicate
        predicate_surface = root.text
        predicate_lemma = root.lemma_

        # Walk children to map spokes
        spokes: list[dict] = []
        for child in root.children:
            if child.dep_ == "neg":
                continue
            spoke = self._child_to_spoke(child)
            if spoke is not None:
                spokes.append(spoke)

        # If no spokes at all, skip (e.g. "He went." with no objects/preps
        # at all still has nsubj, so this should be rare).
        if not spokes:
            return None

        # span of the clause in source text: span the subtree
        subtree = list(root.subtree)
        span_start = min(t.idx for t in subtree)
        span_end = max(t.idx + len(t.text) for t in subtree)

        return {
            "synapse_id": f"syn_{short_uuid()}",
            "doc_id": doc_id,
            "source_sentence_id": sent_idx,
            "source_clause_id": clause_idx,
            "source_span_start": span_start,
            "source_span_end": span_end,
            "predicate_surface": predicate_surface,
            "predicate_lemma": predicate_lemma,
            "predicate_pos": root.pos_,
            "polarity": polarity,
            "spokes": spokes,
            "statement_type": "factual",       # default; framing may override
        }

    def _child_to_spoke(self, child) -> dict | None:
        """Map one direct child of the clause root to a role + target."""
        # Skip dependency types that don't carry argument content
        skip = {"punct", "mark", "cc", "aux", "auxpass", "expl", "complm",
                "discourse"}
        if child.dep_ in skip:
            return None

        # Preposition with a pobj child carries the actual filler
        if child.dep_ == "prep":
            return self._handle_prep(child)

        role = _dep_role(child.dep_)
        if not role:
            # Default: if it's a noun/pronoun/named entity, call it theme
            if child.pos_ in ("NOUN", "PROPN", "PRON"):
                role = "HAS_THEME"
            else:
                return None

        return self._build_spoke(role, child)

    def _handle_prep(self, prep_token) -> dict | None:
        # The prep's pobj is the filler. The preposition text gives us the role.
        prep_text = prep_token.text.lower()
        pobj = next((c for c in prep_token.children if c.dep_ == "pobj"), None)
        if pobj is None:
            return None

        # Multi-word prepositions: re-check using head + lemma
        role = PREP_TO_ROLE.get(prep_text)

        # Disambiguate temporal vs locative for in/on/at: if pobj is a
        # DATE or TIME named entity, prefer HAS_TIME.
        if prep_text in TEMPORAL_PREPS:
            if pobj.ent_type_ in ("DATE", "TIME"):
                role = "HAS_TIME"

        if not role:
            role = "HAS_THEME"
        return self._build_spoke(role, pobj)

    def _build_spoke(self, role: str, token) -> dict:
        if role not in ROLES:
            # Defensive: anything that escapes the closed grammar gets
            # mapped to HAS_THEME as the safest catch-all.
            role = "HAS_THEME"

        # Build the full NP span for the spoke target
        np_start = token.idx
        np_end = token.idx + len(token.text)
        try:
            for tok in token.subtree:
                np_start = min(np_start, tok.idx)
                np_end = max(np_end, tok.idx + len(tok.text))
        except Exception:
            pass

        # Take the head token's text as surface; we'll let entity_map
        # resolve the full alias-set.
        target_surface = token.text
        ent_id = find_entity_for_span(self.entity_map, np_start, np_end,
                                      target_surface)
        if not ent_id:
            ent_id = find_entity_for_span(self.entity_map, token.idx,
                                          token.idx + len(token.text),
                                          target_surface)
        canonical_id = (find_canonical_id_for_ent(self.entity_map, ent_id)
                        if ent_id else None)

        return {
            "role": role,
            "target_ent_id": ent_id,
            "target_canonical_id": canonical_id,
            "target_surface": target_surface,
        }


# =============================================================================
# CLI
# =============================================================================

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--input", required=True, help="Path to the prose document")
    p.add_argument("--entity-map", required=True,
                   help="Path to the entity_map.json produced by entity_census.py")
    p.add_argument("--output", required=True, help="Path for synapses.json")
    p.add_argument("--doc-id", default="doc_001")
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
    builder = SynapseBuilder(cfg, entity_map, verbose=args.verbose)
    synapses = builder.build(text, doc_id=args.doc_id)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(synapses, indent=2), encoding="utf-8")

    print()
    print(f"Wrote {len(synapses)} synapses to {out_path}")
    if args.verbose:
        for s in synapses[:20]:
            print(f"  syn {s['synapse_id'][-8:]}  pred={s['predicate_surface']!r}  "
                  f"spokes={len(s['spokes'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
