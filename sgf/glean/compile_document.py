#!/usr/bin/env python3
"""
compile_document.py — The top-level GLEAN orchestrator (v3.2)

Compile a prose document end-to-end into the synapse store, custom lexicon,
and ghost registry.

Pipeline:
  1. entity_census       prose -> entity_map.json
  2. clause_to_synapse   prose + entity_map -> synapses.json
  3. framing             synapses + prose -> synapses_framed.json
  4. synapse_grouper     synapses_framed -> groups.json + links.json
  5. persist             everything -> synapse_store.db + custom_lexicon.db + ghost_registry.db

v3.2 changes:
  - New CLI parameters: --custom-lexicon, --synapse-store, --accuracy-mode
  - Persist stage writes to synapedia v3.0 compatible tables
  - Supports accuracy modes: casual, standard, rigorous

Usage:
    python compile_document.py --input beethoven.txt --doc-id beethoven_001
    python compile_document.py --input beethoven.txt --doc-id beethoven_001 \\
                               --workdir D:/test1/work \\
                               --framing-mode deterministic \\
                               --accuracy-mode standard \\
                               --custom-lexicon D:/glean/custom_lexicon_corp_001.db \\
                               --synapse-store D:/glean/synapse_store_corp_001.db
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sgflib import load_config

try:
    import call_llm
    _HAVE_CALL_LLM = True
except Exception:
    _HAVE_CALL_LLM = False


def run_step(name: str, fn, *args, **kwargs):
    print()
    print(f"=== Stage: {name} ===")
    t0 = time.time()
    result = fn(*args, **kwargs)
    elapsed = time.time() - t0
    print(f"    [{elapsed:.1f}s]")
    return result


def stage_entity_census(cfg, source_path, doc_id, out_path,
                        no_lookup, verbose, llm_cfg,
                        accuracy_mode="standard"):
    from entity_census import process_document
    text = source_path.read_text(encoding="utf-8")
    emap = process_document(
        text,
        cfg=cfg,
        doc_id=doc_id,
        run_lookup=not no_lookup,
        verbose=verbose,
        llm_cfg=llm_cfg,
        # New v3.2 params — entity_census will accept them via **kwargs
        accuracy_mode=accuracy_mode,
    )
    out_path.write_text(json.dumps(emap, indent=2), encoding="utf-8")
    print(f"    {emap['entity_count']} entities -> {out_path.name}")
    return emap


def stage_clause_to_synapse(cfg, source_path, entity_map, doc_id, out_path,
                            verbose, search_server_url="http://localhost:8400"):
    from clause_to_synapse import build_synapses
    text = source_path.read_text(encoding="utf-8")
    synapses = build_synapses(
        cfg, entity_map, text, doc_id=doc_id,
        verbose=verbose,
        search_server_url=search_server_url,
    )
    out_path.write_text(json.dumps(synapses, indent=2), encoding="utf-8")
    print(f"    {len(synapses)} synapses -> {out_path.name}")
    return synapses


def stage_framing(cfg, source_path, synapses, mode, out_path, llm_cfg):
    from framing import frame_synapses
    source_text = source_path.read_text(encoding="utf-8")
    framed = frame_synapses(synapses, source_text, mode, cfg, llm_cfg=llm_cfg)
    out_path.write_text(json.dumps(framed, indent=2), encoding="utf-8")
    print(f"    framed {len(framed)} synapses (mode={mode}) -> {out_path.name}")
    return framed


def stage_groups(synapses_framed, out_path, verbose=False):
    from synapse_grouper import build_groups
    result = build_groups(synapses_framed)
    groups = result["groups"]
    links = result["links"]
    output = {
        "groups": groups,
        "links": links,
        "n_groups": len(groups),
        "n_links": len(links),
    }
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"    {len(groups)} groups, {len(links)} links -> {out_path.name}")
    if verbose:
        for l in links[:10]:
            print(f"      {l['source_id'][-8:]} --[{l['link_type']}]--> {l['target_id'][-8:]}")
    return output


def stage_persist(cfg, doc_id, source_path, entity_map, framed, groups_result,
                  custom_lexicon_path=None, synapse_store_path=None,
                  ghost_registry_path=None, accuracy_mode="standard"):
    from synapse_store_persist import persist_all

    text = source_path.read_text(encoding="utf-8")
    syn_path = synapse_store_path or cfg.get("synapse_store", {}).get("path")
    if not syn_path:
        raise RuntimeError("synapse_store.path missing from sgf.toml and no --synapse-store provided")

    # Extract groups and links from the groups result
    groups = groups_result.get("groups", [])
    links = groups_result.get("links", [])

    counts = persist_all(
        syn_db_path=syn_path,
        custom_db_path=custom_lexicon_path,
        ghost_db_path=ghost_registry_path,
        doc_id=doc_id,
        entity_map=entity_map,
        synapses_framed=framed,
        groups=groups,
        links=links,
        source_path=str(source_path),
        source_text=text,
        accuracy_mode=accuracy_mode,
    )
    print(f"    persist counts: {counts}")
    return counts


def main():
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

    # New v3.2 parameters
    p.add_argument("--custom-lexicon", default=None,
                   help="Path to custom lexicon DB for this corpus")
    p.add_argument("--synapse-store", default=None,
                   help="Path to synapse store DB (overrides config)")
    p.add_argument("--ghost-registry", default=None,
                   help="Path to ghost registry DB (default: <custom-lexicon-dir>/ghost_registry.db)")
    p.add_argument("--accuracy-mode", default="standard",
                   choices=["casual", "standard", "rigorous"],
                   help="Entity resolution accuracy mode")
    p.add_argument("--search-server", default="http://localhost:8400",
                   help="Search server URL for verb canonical ID resolution")
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

    llm_cfg = None
    if _HAVE_CALL_LLM:
        try:
            llm_cfg = call_llm.load_llm_config(cfg.get("_config_path"))
        except Exception:
            llm_cfg = None

    # Derive ghost registry path if not provided
    ghost_registry_path = args.ghost_registry
    if not ghost_registry_path and args.custom_lexicon:
        cl_dir = Path(args.custom_lexicon).parent
        ghost_registry_path = str(cl_dir / "ghost_registry.db")

    print(f"GLEAN compile_document (v3.2)")
    print(f"  input:       {in_path}")
    print(f"  doc_id:      {args.doc_id}")
    print(f"  workdir:     {workdir}")
    print(f"  framing:     {args.framing_mode}")
    print(f"  accuracy:    {args.accuracy_mode}")
    print(f"  persist:     {not args.no_persist}")
    print(f"  custom-lex:  {args.custom_lexicon or '(not set)'}")
    print(f"  syn-store:   {args.synapse_store or '(from config)'}")
    print(f"  ghost-reg:   {ghost_registry_path or '(not set)'}")
    if llm_cfg and _HAVE_CALL_LLM:
        is_cfg = call_llm.is_wrapper_configured(llm_cfg)
        print(f"  llm:         configured={is_cfg}  "
              f"path={llm_cfg.get('wrapper_path', '')!r}")

    # Stage 1: Entity Census
    emap = run_step("entity_census", stage_entity_census,
                    cfg, in_path, args.doc_id, em_path,
                    args.no_lookup, args.verbose, llm_cfg,
                    accuracy_mode=args.accuracy_mode)

    # Stage 2: Clause to Synapse
    synapses = run_step("clause_to_synapse", stage_clause_to_synapse,
                        cfg, in_path, emap, args.doc_id, syn_path,
                        args.verbose, args.search_server)

    # Stage 3: Framing
    framed = run_step("framing", stage_framing,
                      cfg, in_path, synapses, args.framing_mode,
                      framed_path, llm_cfg)

    # Stage 4: Grouping
    groups_result = run_step("synapse_grouper", stage_groups,
                             framed, groups_path, args.verbose)

    # Stage 5: Persist
    if not args.no_persist:
        run_step("persist", stage_persist,
                 cfg, args.doc_id, in_path, emap, framed, groups_result,
                 custom_lexicon_path=args.custom_lexicon,
                 synapse_store_path=args.synapse_store,
                 ghost_registry_path=ghost_registry_path,
                 accuracy_mode=args.accuracy_mode)

    print()
    print("=" * 60)
    print("DONE")
    print("=" * 60)
    print(f"  entities:   {len(emap['entities'])}")
    print(f"  synapses:   {len(framed)}")
    print(f"  groups:     {len(groups_result.get('groups', []))}")
    print(f"  links:      {len(groups_result.get('links', []))}")
    print(f"  workdir:    {workdir}")
    if not args.no_persist:
        store_path = args.synapse_store or cfg.get("synapse_store", {}).get("path", "(unset)")
        print(f"  store:      {store_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())