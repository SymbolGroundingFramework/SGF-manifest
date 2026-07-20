#!/usr/bin/env python3
"""
synapse_grouper.py — Stage 11 of the GLEAN pipeline (v3.2)

Cluster compiled synapses into groups by three cohesion signals:
  - shared_entity      Synapses that share at least one entity participant
  - shared_predicate   Synapses with the same verb
  - discourse          Synapses from the same paragraph

Each group gets:
  - group_label: human-readable name (e.g., "Beethoven" for shared_entity)
  - group_type: composition pattern (STAR, CHAIN, LATTICE, NEST, TREE)
  - parent_group_id: for nesting (set to None for now)

After grouping, PRECEDES links are computed between consecutive synapses
in the same sentence and written to the output.

A synapse may belong to multiple groups. Groups are emitted as a JSON
file.

Usage:
    python synapse_grouper.py --synapses synapses_framed.json \\
                              --output groups.json \\
                              [--persist --doc-id doc_001]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sgflib import load_config


# =============================================================================
# Constants
# =============================================================================

# Valid link types (from the 29 primitives)
VALID_LINK_TYPES = frozenset({
    "PRECEDES", "CAUSES", "ENABLES", "SUPPORTS", "CONTRADICTS",
    "ELABORATES", "SUPERSEDES", "DEPENDS_ON",
})

# Map cohesion signal to group type
SIGNAL_TO_TYPE = {
    "shared_entity": "STAR",
    "shared_predicate": "STAR",
    "discourse": "CHAIN",
}


# =============================================================================
# Helpers
# =============================================================================

def hash_id(*parts) -> str:
    """Deterministic short group_id from cohesion parts."""
    h = hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()
    return f"grp_{h[:12]}"


def _resolve_entity_label(synapses: List[dict], ent_id: str) -> str:
    """Find the preferred_canonical for an entity ID from the synapses."""
    for syn in synapses:
        for spoke in syn.get("spokes", []):
            if spoke.get("target_ent_id") == ent_id:
                cid = spoke.get("target_canonical_id")
                if cid:
                    # Extract last meaningful part of canonical ID
                    parts = cid.split(".")
                    if len(parts) >= 2:
                        return parts[1].replace("_", " ").title()
                return spoke.get("target_surface", ent_id)
    return ent_id


# =============================================================================
# Grouping functions
# =============================================================================

def group_by_shared_entity(synapses: List[dict]) -> List[dict]:
    """Each entity that appears in 2+ synapses defines a group."""
    ent_to_syns: dict[str, List[str]] = defaultdict(list)
    for syn in synapses:
        seen_in_this_syn = set()
        for spoke in syn.get("spokes", []):
            ent_id = spoke.get("target_ent_id")
            if ent_id and ent_id not in seen_in_this_syn:
                ent_to_syns[ent_id].append(syn["synapse_id"])
                seen_in_this_syn.add(ent_id)

    out = []
    for ent_id, sids in ent_to_syns.items():
        if len(sids) < 2:
            continue
        label = _resolve_entity_label(synapses, ent_id)
        out.append({
            "group_id": hash_id("shared_entity", ent_id),
            "cohesion_signal": "shared_entity",
            "cohesion_value": ent_id,
            "group_label": label,
            "group_type": "STAR",
            "parent_group_id": None,
            "synapse_ids": sids,
        })
    return out


def group_by_shared_predicate(synapses: List[dict]) -> List[dict]:
    """Each verb that appears in 2+ synapses defines a group."""
    pred_to_syns: dict[str, List[str]] = defaultdict(list)
    for syn in synapses:
        pred = syn.get("predicate_canonical_id") or syn.get("predicate_lemma")
        if not pred:
            continue
        pred_to_syns[pred].append(syn["synapse_id"])

    out = []
    for pred, sids in pred_to_syns.items():
        if len(sids) < 2:
            continue
        # Extract label from canonical ID or lemma
        label = pred.split(".")[1] if "." in pred else pred
        label = label.replace("_", " ").title()
        out.append({
            "group_id": hash_id("shared_predicate", pred),
            "cohesion_signal": "shared_predicate",
            "cohesion_value": pred,
            "group_label": label,
            "group_type": "STAR",
            "parent_group_id": None,
            "synapse_ids": sids,
        })
    return out


def group_by_discourse(synapses: List[dict]) -> List[dict]:
    """Group by source paragraph. v3.2: uses sentence_id // 3 for paragraph
    buckets, with a label indicating the paragraph number."""
    sent_to_syns: dict[int, List[str]] = defaultdict(list)
    for syn in synapses:
        sent_id = syn.get("source_sentence_id", 0)
        bucket = sent_id // 3
        sent_to_syns[bucket].append(syn["synapse_id"])

    out = []
    for bucket, sids in sent_to_syns.items():
        if len(sids) < 2:
            continue
        para_start = bucket * 3 + 1
        para_end = (bucket + 1) * 3
        out.append({
            "group_id": hash_id("discourse", bucket),
            "cohesion_signal": "discourse",
            "cohesion_value": f"para_{bucket:03d}",
            "group_label": f"Paragraph {para_start}-{para_end}",
            "group_type": "CHAIN",
            "parent_group_id": None,
            "synapse_ids": sids,
        })
    return out


# =============================================================================
# Link computation
# =============================================================================

def compute_links(synapses: List[dict]) -> List[dict]:
    """Generate PRECEDES links between consecutive synapses in the same sentence.

    Returns a list of link dicts with keys:
      source_id, link_type, target_id, confidence
    """
    sent_groups: Dict[int, List[tuple]] = defaultdict(list)
    for syn in synapses:
        sent_id = syn.get("source_sentence_id", 0)
        clause_id = syn.get("source_clause_id", 0)
        syn_id = syn.get("synapse_id")
        if not syn_id:
            continue
        sent_groups[sent_id].append((clause_id, syn_id))

    links = []
    for sent_id, clauses in sent_groups.items():
        clauses.sort(key=lambda x: x[0])
        for i in range(len(clauses) - 1):
            links.append({
                "source_id": clauses[i][1],
                "link_type": "PRECEDES",
                "target_id": clauses[i + 1][1],
                "confidence": 1.0,
            })
    return links


# =============================================================================
# Main grouping function
# =============================================================================

def build_groups(synapses: List[dict]) -> dict:
    """Build groups and links from a list of synapses.

    Returns a dict with two keys:
      groups: list of group dicts
      links: list of link dicts
    """
    groups: List[dict] = []
    groups.extend(group_by_shared_entity(synapses))
    groups.extend(group_by_shared_predicate(synapses))
    groups.extend(group_by_discourse(synapses))

    links = compute_links(synapses)

    return {
        "groups": groups,
        "links": links,
    }


# =============================================================================
# CLI
# =============================================================================

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--synapses", required=True,
                   help="Path to synapses_framed.json")
    p.add_argument("--output", required=True,
                   help="Path for groups.json")
    p.add_argument("--persist", action="store_true",
                   help="Also write the groups into the synapse store DB")
    p.add_argument("--doc-id", help="Required if --persist")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    syn_path = Path(args.synapses)
    if not syn_path.exists():
        print(f"Synapses file not found: {syn_path}", file=sys.stderr)
        return 1

    data = json.loads(syn_path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "synapses" in data:
        synapses = data["synapses"]
    else:
        synapses = data

    result = build_groups(synapses)
    groups = result["groups"]
    links = result["links"]

    # Write output
    output = {
        "groups": groups,
        "links": links,
        "n_groups": len(groups),
        "n_links": len(links),
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    print()
    print(f"Built {len(groups)} groups, {len(links)} links; wrote to {out_path}")
    by_signal = defaultdict(int)
    for g in groups:
        by_signal[g["cohesion_signal"]] += 1
    for sig, n in by_signal.items():
        print(f"  {sig:<20} {n:,}")

    if args.verbose:
        print(f"\n  Links:")
        for l in links[:10]:
            print(f"    {l['source_id'][-8:]} --[{l['link_type']}]--> {l['target_id'][-8:]}")

    # Optional persist
    if args.persist:
        if not args.doc_id:
            print("--persist requires --doc-id", file=sys.stderr)
            return 1
        from synapse_store_persist import persist_all
        # Note: this is a simplified persist call; the full pipeline
        # uses compile_document.py which calls persist_all directly.
        print("  (persist is handled by compile_document.py)")
    return 0


if __name__ == "__main__":
    sys.exit(main())