#!/usr/bin/env python3
"""
build_relations.py -- Phase 2B friendly runner: build the relation graph

WHAT THIS IS
------------
Phase 2B of the lexicon pipeline is "build the navigation graph on top of
the senses." This runner is the friendly single-command wrapper that
drives the three underlying stages in the right order on a
frequency-bounded scope:

  1. discover_clusters.py        -- find cosine-similar sense clusters
                                    (the candidates for "these mean the
                                    same thing" merging).
  2. select_standard_forms.py    -- LLM picks the canonical lemma for
                                    each cluster (so IS_A / HAS_PART
                                    targets land on a single standard
                                    sense, not on N near-duplicates).
  3. harvest_semantic_relations.py
                                 -- LLM proposes IS_A, HAS_PART, and the
                                    15 SGF semantic roles for each
                                    in-scope sense. Targets are resolved
                                    by embed-and-filter (LLM gives
                                    target_lemma + target_description;
                                    the resolver embeds the description,
                                    filters by lemma, picks top-1).

After this runs, the in-scope senses have a relation graph: each sense
has 0..N typed edges to other senses, drawn ONLY from the 17 canonical
relation names. GLEAN can traverse this graph.

WHEN TO USE
-----------
Run AFTER Phase 1 bootstrap is done. Optionally run Phase 2A first to
get sharper microglosses (better cousins, better disambiguation, better
relation targets). The two phases are independent; either order works.

This is INCREMENTAL and IDEMPOTENT:
  - Already-harvested senses are skipped by default.
  - --revisit re-processes them.
  - You can stop and restart at any time.
  - Clusters and standard forms are also incremental; re-running on a
    larger frontier extends prior work.

USAGE
-----
    # First run: build relations for the top 100 senses
    python build_relations.py --target sgf_lexicon.db ^
        --llm-wrapper llm_wrapper.py --top-lemmas 100

    # Expand to top 1000
    python build_relations.py --target sgf_lexicon.db ^
        --llm-wrapper llm_wrapper.py --top-lemmas 1000

    # Revisit and refine relation work already done
    python build_relations.py --target sgf_lexicon.db ^
        --llm-wrapper llm_wrapper.py --top-lemmas 1000 --revisit

    # Dry run: show what would happen
    python build_relations.py --target sgf_lexicon.db ^
        --llm-wrapper llm_wrapper.py --top-lemmas 1000 --dry-run

    # Skip clusters/forms if you've already built them on a larger scope
    python build_relations.py --target sgf_lexicon.db ^
        --llm-wrapper llm_wrapper.py --top-lemmas 1000 ^
        --skip-clusters --skip-forms

WHAT THIS DOESN'T DO
--------------------
It does NOT improve microglosses or metadata. For that, use
improve_lexicon.py (Phase 2A). The two runners are independent; you can
run either without the other, in any order, on any frontier.

TODO V2 (lexicon as encyclopedia):
A future Phase 2C runner (working name `extract_encyclopedic.py`)
would sit alongside this one. It would run each sense's gloss +
example sentences through a shared synapse_extractor (factored out
of GLEAN's prose pipeline) and attach descriptive synapses --
possibly conceptual SynapseGroups -- to the lexicon entry. Same 17
relations, same closed grammar, just more *content per concept*. The
lexicon becomes encyclopedic. See V2_VISION.md.

NOTE ON EMBEDDER
----------------
Cluster discovery and standard-form selection use the PRODUCTION embedder
(default bge-large-en-v1) because cluster quality depends on embedding
quality. If you have not yet run compute_embeddings.py with the
production embedder on this frontier, do that first (Phase 2A's stage 3
takes care of it; alternatively run compute_embeddings.py directly).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent


def run_stage(name, cmd, dry_run=False):
    """Run one stage as a subprocess, streaming output live."""
    pretty = " ".join(str(c) for c in cmd)
    print()
    print("=" * 70)
    print(f"  {name}")
    print("=" * 70)
    print(f"  $ {pretty}", flush=True)
    if dry_run:
        print("  (dry-run; would run the above)")
        return 0
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    t0 = time.time()
    try:
        for line in proc.stdout:
            sys.stdout.write("    " + line)
            sys.stdout.flush()
    finally:
        proc.stdout.close()
        proc.wait()
    dt = time.time() - t0
    if proc.returncode != 0:
        print(f"    FAIL ({dt:.1f}s, exit={proc.returncode})")
    else:
        print(f"    ok ({dt:.1f}s)")
    return proc.returncode


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    p.add_argument("--target", default="sgf_lexicon.db")
    p.add_argument("--llm-wrapper", required=True,
                   help="Path to your LLM wrapper script")
    p.add_argument("--top-lemmas", type=int, default=1000,
                   help="Process the top N most-frequent lemmas (default: 1000)")
    p.add_argument("--revisit", action="store_true",
                   help="Re-process already-harvested senses, refining prior relations")
    p.add_argument("--production-embedder", default="bge-large-en-v1",
                   help="Embedder used for clusters, standard forms, and "
                        "relation-target resolution (default: bge-large-en-v1)")
    p.add_argument("--tier", default="flash",
                   help="LLM tier hint passed to the wrapper")
    p.add_argument("--temp", type=float, default=0.0,
                   help="LLM temperature")
    p.add_argument("--workers", type=int, default=1,
                   help="LLM workers for the harvester (default: 1)")
    p.add_argument("--cluster-top-k", type=int, default=20,
                   help="Top-K neighbors per seed for cluster discovery (default: 20)")
    p.add_argument("--strong-threshold", type=float, default=None,
                   help="Cosine threshold for strong cluster edges "
                        "(default: discover_clusters.py's built-in)")
    p.add_argument("--patterns-only", action="store_true",
                   help="Harvester: use deterministic patterns only, no LLM")
    p.add_argument("--llm-only", action="store_true",
                   help="Harvester: use LLM only, skip deterministic patterns")
    p.add_argument("--skip-clusters", action="store_true",
                   help="Skip cluster discovery (use existing clusters)")
    p.add_argument("--skip-forms", action="store_true",
                   help="Skip standard-form selection (use existing standard forms)")
    p.add_argument("--skip-harvest", action="store_true",
                   help="Skip semantic-relation harvest")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the plan; don't run anything")
    args = p.parse_args()

    db = Path(args.target)
    if not db.exists():
        print(f"DB not found: {db}", file=sys.stderr)
        return 1
    wrapper = Path(args.llm_wrapper).resolve()

    print()
    print("=" * 70)
    print("  Phase 2B: Build the relation graph on a top-N frontier")
    print("=" * 70)
    print(f"  target:               {db.resolve()}")
    print(f"  llm-wrapper:          {wrapper}")
    print(f"  top-lemmas:           {args.top_lemmas:,}")
    print(f"  revisit mode:         {args.revisit}")
    print(f"  production embedder:  {args.production_embedder}")
    print(f"  cluster top-k:        {args.cluster_top_k}")

    py = sys.executable
    stages_run = 0

    # ---- 1. Cluster discovery ----
    if not args.skip_clusters:
        cmd = [py, str(HERE / "discover_clusters.py"),
               "--target", str(db),
               "--embedding-method", args.production_embedder,
               "--top-k", str(args.cluster_top_k)]
        if args.strong_threshold is not None:
            cmd += ["--strong-threshold", str(args.strong_threshold)]
        rc = run_stage("Stage 1/3: Discover near-duplicate sense clusters",
                       cmd, args.dry_run)
        stages_run += 1
        if rc != 0 and not args.dry_run:
            return rc

    # ---- 2. Standard-form selection ----
    if not args.skip_forms:
        cmd = [py, str(HERE / "select_standard_forms.py"),
               "--target", str(db),
               "--embedding-method", args.production_embedder,
               "--llm-wrapper", str(wrapper),
               "--tier", args.tier,
               "--temp", str(args.temp)]
        rc = run_stage("Stage 2/3: Select canonical (standard) form per cluster",
                       cmd, args.dry_run)
        stages_run += 1
        if rc != 0 and not args.dry_run:
            return rc

    # ---- 3. Semantic-relation harvest ----
    if not args.skip_harvest:
        cmd = [py, str(HERE / "harvest_semantic_relations.py"),
               "--target", str(db),
               "--llm-wrapper", str(wrapper),
               "--top-lemmas", str(args.top_lemmas),
               "--embedding-method", args.production_embedder,
               "--tier", args.tier,
               "--temp", str(args.temp)]
        if args.patterns_only:
            cmd.append("--patterns-only")
        if args.llm_only:
            cmd.append("--llm-only")
        if args.revisit:
            cmd.append("--revisit")
        rc = run_stage("Stage 3/3: Harvest IS_A, HAS_PART, and 15 SGF roles",
                       cmd, args.dry_run)
        stages_run += 1
        if rc != 0 and not args.dry_run:
            return rc

    print()
    print("=" * 70)
    print(f"  PHASE 2B COMPLETE -- ran {stages_run} stage(s)")
    print("=" * 70)
    print("  What you have now:")
    print("    - sense_cluster:           groups of cosine-similar senses")
    print("    - sense_standard_form:     canonical lemma per cluster")
    print("    - sense_semantic_relation: typed edges from the 17 canonical")
    print("                               relation names (IS_A, HAS_PART,")
    print("                               6 core roles, 9 context roles)")
    print()
    print("  Next options:")
    print("    - Expand the frontier: re-run with --top-lemmas 5000 (or higher)")
    print("    - Refine: re-run with --revisit to redo work for senses you've")
    print("      since improved via Phase 2A")
    print("    - Improve microglosses first: python improve_lexicon.py ...")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
