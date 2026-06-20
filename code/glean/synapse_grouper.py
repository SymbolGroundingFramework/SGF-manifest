#!/usr/bin/env python3
"""
synapse_grouper.py — Stage 11 of the GLEAN pipeline

Cluster compiled synapses into groups by three cohesion signals:
  - shared_entity      Synapses that share at least one entity participant
  - shared_predicate   Synapses with the same predicate_canonical_id
  - discourse          Synapses extracted from the same paragraph

A synapse may belong to multiple groups. Groups are emitted as a JSON
file and (when --persist) written into the synapse_store DB.

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

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sgflib import load_config


def hash_id(*parts) -> str:
    """Deterministic short group_id from cohesion parts."""
    h = hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()
    return f"grp_{h[:12]}"


def group_by_shared_entity(synapses: list[dict]) -> list[dict]:
    """Each entity that appears in 2+ synapses defines a group."""
    ent_to_syns: dict[str, list[str]] = defaultdict(list)
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
        out.append({
            "group_id": hash_id("shared_entity", ent_id),
            "cohesion_signal": "shared_entity",
            "cohesion_value": ent_id,
            "synapse_ids": sids,
        })
    return out


def group_by_shared_predicate(synapses: list[dict]) -> list[dict]:
    pred_to_syns: dict[str, list[str]] = defaultdict(list)
    for syn in synapses:
        pred = syn.get("predicate_canonical_id") or syn.get("predicate_lemma")
        if not pred:
            continue
        pred_to_syns[pred].append(syn["synapse_id"])

    out = []
    for pred, sids in pred_to_syns.items():
        if len(sids) < 2:
            continue
        out.append({
            "group_id": hash_id("shared_predicate", pred),
            "cohesion_signal": "shared_predicate",
            "cohesion_value": pred,
            "synapse_ids": sids,
        })
    return out


def group_by_discourse(synapses: list[dict]) -> list[dict]:
    """Group by source paragraph. v1 approximation: contiguous runs of
    sentences that share a sentence_id bucket. We bucket every 3 sentences
    as one 'paragraph' since prose doesn't tell us paragraph boundaries
    after sentence split."""
    sent_to_syns: dict[int, list[str]] = defaultdict(list)
    for syn in synapses:
        sent_id = syn.get("source_sentence_id", 0)
        bucket = sent_id // 3
        sent_to_syns[bucket].append(syn["synapse_id"])

    out = []
    for bucket, sids in sent_to_syns.items():
        if len(sids) < 2:
            continue
        out.append({
            "group_id": hash_id("discourse", bucket),
            "cohesion_signal": "discourse",
            "cohesion_value": f"para_{bucket:03d}",
            "synapse_ids": sids,
        })
    return out


def build_groups(synapses: list[dict]) -> list[dict]:
    groups: list[dict] = []
    groups.extend(group_by_shared_entity(synapses))
    groups.extend(group_by_shared_predicate(synapses))
    groups.extend(group_by_discourse(synapses))
    return groups


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--synapses", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--persist", action="store_true",
                   help="Also write the groups into the synapse store DB")
    p.add_argument("--doc-id", help="Required if --persist")
    args = p.parse_args()

    syn_path = Path(args.synapses)
    if not syn_path.exists():
        print(f"Synapses file not found: {syn_path}", file=sys.stderr)
        return 1

    synapses = json.loads(syn_path.read_text(encoding="utf-8"))
    groups = build_groups(synapses)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(groups, indent=2), encoding="utf-8")

    print()
    print(f"Built {len(groups)} groups; wrote to {out_path}")
    by_signal = defaultdict(int)
    for g in groups:
        by_signal[g["cohesion_signal"]] += 1
    for sig, n in by_signal.items():
        print(f"  {sig:<20} {n:,}")

    if args.persist:
        if not args.doc_id:
            print("--persist requires --doc-id", file=sys.stderr)
            return 1
        from synapse_store import SynapseStore
        cfg = load_config()
        store = SynapseStore(cfg.synapse_store_path)
        try:
            for g in groups:
                store.insert_group(g["group_id"], args.doc_id,
                                   g["cohesion_signal"], g["cohesion_value"],
                                   g["synapse_ids"])
            store.commit()
            print(f"Persisted to {store.db_path}")
        finally:
            store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
