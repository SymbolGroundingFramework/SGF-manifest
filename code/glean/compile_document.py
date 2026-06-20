#!/usr/bin/env python3
"""
compile_document.py — The top-level GLEAN orchestrator

Compile a prose document end-to-end into the synapse store.

The orchestrator runs every GLEAN stage in order, threading intermediate
artifacts between them as JSON files in a working directory. Each
intermediate is preserved so you can inspect what happened at each step.

Pipeline:
  1. entity_census       prose -> entity_map.json
  2. clause_to_synapse   prose + entity_map -> synapses.json
  3. framing             synapses + prose -> synapses_framed.json
  4. synapse_grouper     synapses_framed -> groups.json
  5. persist             everything -> synapse store DB

Usage:
    python compile_document.py --input beethoven.txt --doc-id beethoven_001
    python compile_document.py --input beethoven.txt --doc-id beethoven_001 \\
                               --workdir D:/test1/work \\
                               --framing-mode deterministic
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sgflib import load_config


def run_step(name: str, fn, *args, **kwargs):
    print()
    print(f"=== Stage: {name} ===")
    t0 = time.time()
    result = fn(*args, **kwargs)
    elapsed = time.time() - t0
    print(f"    [{elapsed:.1f}s]")
    return result


def stage_entity_census(cfg, source_path: Path, doc_id: str,
                        out_path: Path, no_lookup: bool, verbose: bool):
    from entity_census import EntityCensus
    text = source_path.read_text(encoding="utf-8")
    census = EntityCensus(cfg, run_lookup=not no_lookup, verbose=verbose)
    try:
        emap = census.process(text, doc_id=doc_id)
    finally:
        census.close()
    out_path.write_text(json.dumps(emap, indent=2), encoding="utf-8")
    print(f"    {emap['entity_count']} entities -> {out_path.name}")
    return emap


def stage_clause_to_synapse(cfg, source_path: Path, entity_map: dict,
                            doc_id: str, out_path: Path, verbose: bool):
    from clause_to_synapse import SynapseBuilder
    text = source_path.read_text(encoding="utf-8")
    builder = SynapseBuilder(cfg, entity_map, verbose=verbose)
    synapses = builder.build(text, doc_id=doc_id)
    out_path.write_text(json.dumps(synapses, indent=2), encoding="utf-8")
    print(f"    {len(synapses)} synapses -> {out_path.name}")
    return synapses


def stage_framing(cfg, source_path: Path, synapses: list[dict],
                  mode: str, out_path: Path):
    from framing import frame_synapses
    source_text = source_path.read_text(encoding="utf-8")
    framed = frame_synapses(synapses, source_text, mode, cfg)
    out_path.write_text(json.dumps(framed, indent=2), encoding="utf-8")
    print(f"    framed {len(framed)} synapses (mode={mode}) -> {out_path.name}")
    return framed


def stage_groups(framed: list[dict], out_path: Path):
    from synapse_grouper import build_groups
    groups = build_groups(framed)
    out_path.write_text(json.dumps(groups, indent=2), encoding="utf-8")
    print(f"    {len(groups)} groups -> {out_path.name}")
    return groups


def stage_persist(cfg, doc_id: str, source_path: Path,
                  entity_map: dict, framed: list[dict],
                  groups: list[dict]):
    from synapse_store import SynapseStore
    store = SynapseStore(cfg.synapse_store_path)
    try:
        text = source_path.read_text(encoding="utf-8")
        store.clear_document(doc_id)
        store.upsert_document(doc_id=doc_id, source_path=str(source_path),
                              char_length=len(text))
        for ent in entity_map.get("entities", []):
            store.upsert_entity(doc_id, ent)
        store.commit()
        for syn in framed:
            store.insert_synapse(syn)
            store.insert_frame(syn["synapse_id"], syn.get("frame", {}),
                               syn.get("framing_method", "deterministic"))
        store.commit()
        for g in groups:
            store.insert_group(g["group_id"], doc_id, g["cohesion_signal"],
                               g["cohesion_value"], g["synapse_ids"])
        store.commit()
        s = store.status()
        print(f"    store totals: {s}")
    finally:
        store.close()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--input", required=True, help="Prose file to compile")
    p.add_argument("--doc-id", required=True, help="Stable id for this document")
    p.add_argument("--workdir", default=None,
                   help="Where to write intermediate JSON files. Default: <input>_glean/")
    p.add_argument("--framing-mode", choices=["deterministic", "llm"],
                   default="deterministic",
                   help="How to compute synapse frames")
    p.add_argument("--no-lookup", action="store_true",
                   help="Skip lexicon grounding (faster, lower quality)")
    p.add_argument("--no-persist", action="store_true",
                   help="Skip the final write to the synapse store DB")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"Input not found: {in_path}", file=sys.stderr)
        return 1

    workdir = Path(args.workdir) if args.workdir else in_path.with_suffix(".glean")
    workdir.mkdir(parents=True, exist_ok=True)

    em_path = workdir / f"{args.doc_id}.entity_map.json"
    syn_path = workdir / f"{args.doc_id}.synapses.json"
    framed_path = workdir / f"{args.doc_id}.synapses_framed.json"
    groups_path = workdir / f"{args.doc_id}.groups.json"

    cfg = load_config()

    print(f"GLEAN compile_document")
    print(f"  input:    {in_path}")
    print(f"  doc_id:   {args.doc_id}")
    print(f"  workdir:  {workdir}")
    print(f"  framing:  {args.framing_mode}")
    print(f"  persist:  {not args.no_persist}")

    emap = run_step("entity_census", stage_entity_census,
                    cfg, in_path, args.doc_id, em_path,
                    args.no_lookup, args.verbose)

    synapses = run_step("clause_to_synapse", stage_clause_to_synapse,
                        cfg, in_path, emap, args.doc_id, syn_path,
                        args.verbose)

    framed = run_step("framing", stage_framing,
                      cfg, in_path, synapses, args.framing_mode,
                      framed_path)

    groups = run_step("synapse_grouper", stage_groups,
                      framed, groups_path)

    if not args.no_persist:
        run_step("persist", stage_persist,
                 cfg, args.doc_id, in_path, emap, framed, groups)

    print()
    print("=" * 60)
    print("DONE")
    print("=" * 60)
    print(f"  entities:   {len(emap['entities'])}")
    print(f"  synapses:   {len(framed)}")
    print(f"  groups:     {len(groups)}")
    print(f"  workdir:    {workdir}")
    if not args.no_persist:
        print(f"  store:      {cfg.synapse_store_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
