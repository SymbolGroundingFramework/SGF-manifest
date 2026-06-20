#!/usr/bin/env python3
"""
improve_lexicon.py -- Phase 2A friendly runner: improve a top-N slice

WHAT THIS IS
------------
Phase 2A of the lexicon pipeline is "make the microglosses and metadata
better for the most important senses." This runner is the friendly
single-command wrapper that drives the underlying stages in the right
order on a frequency-bounded scope:

  1. improve_microgloss.py  -- LLM rewrites microglosses + metadata,
                               using contrast sets (lemma-mates +
                               cousins) to sharpen disambiguation.
  2. build_embedding_texts.py --pass v2  -- rebuild embedding text from
                               the new microglosses.
  3. compute_embeddings.py    -- compute bge-large production embeddings
                               for the improved senses.
  4. quality_audit.py         -- production-quality self-retrieval audit
                               (bge-large). This is the ship gate.

After this runs, the in-scope senses are at tier 'embedded_v2' (or
higher if they were already past it), with sharper microglosses, full
metadata, and production embeddings.

WHEN TO USE
-----------
Anytime you want to expand the scope of "high-quality, improved" senses.
First run might do top-100 to validate the LLM is producing sane output.
Then top-1000. Then top-5000. Or you can re-run on a frontier you
already processed with --revisit, which lets the LLM refine its prior
work.

This is INCREMENTAL and IDEMPOTENT:
  - Already-improved senses are skipped by default.
  - --revisit re-processes them.
  - You can stop and restart at any time.

USAGE
-----
    # First run: improve the top 100 senses, validate output
    python improve_lexicon.py --target sgf_lexicon.db \\
        --llm-wrapper llm_wrapper.py --top-lemmas 100

    # Expand to top 1000
    python improve_lexicon.py --target sgf_lexicon.db \\
        --llm-wrapper llm_wrapper.py --top-lemmas 1000

    # Revisit and refine work already done
    python improve_lexicon.py --target sgf_lexicon.db \\
        --llm-wrapper llm_wrapper.py --top-lemmas 1000 --revisit

    # Dry run: show what would happen
    python improve_lexicon.py --target sgf_lexicon.db \\
        --llm-wrapper llm_wrapper.py --top-lemmas 1000 --dry-run

WHAT THIS DOESN'T DO
--------------------
It does NOT build the semantic-relation graph (IS_A, HAS_PART, the 15
SGF semantic roles). For that, use build_relations.py (Phase 2B).
The two runners are independent; you can run either without the other,
in any order, on any frontier.
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
                   help="Re-process already-improved senses, refining prior output")
    p.add_argument("--diagnostic-embedder", default="bge-small-en-v1",
                   help="Embedder used for cousin discovery (default: bge-small-en-v1)")
    p.add_argument("--production-embedder", default="bge-large-en-v1",
                   help="Embedder used for production embeddings (default: bge-large-en-v1)")
    p.add_argument("--tier", default="flash",
                   help="LLM tier hint passed to the wrapper")
    p.add_argument("--temp", type=float, default=0.0,
                   help="LLM temperature")
    p.add_argument("--workers", type=int, default=1,
                   help="LLM workers for the improver (default: 1)")
    p.add_argument("--device", default="cpu",
                   help="ONNX device for embeddings (cpu, dml, cuda)")
    p.add_argument("--skip-improve", action="store_true",
                   help="Skip the LLM improver stage")
    p.add_argument("--skip-embed", action="store_true",
                   help="Skip the embedding rebuild stage")
    p.add_argument("--skip-audit", action="store_true",
                   help="Skip the final production audit")
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
    print("  Phase 2A: Improve a top-N lexicon frontier")
    print("=" * 70)
    print(f"  target:               {db.resolve()}")
    print(f"  llm-wrapper:          {wrapper}")
    print(f"  top-lemmas:           {args.top_lemmas:,}")
    print(f"  revisit mode:         {args.revisit}")
    print(f"  diagnostic embedder:  {args.diagnostic_embedder}")
    print(f"  production embedder:  {args.production_embedder}")
    print(f"  device:               {args.device}")

    py = sys.executable
    stages_run = 0

    # ---- 1. LLM improver pass ----
    if not args.skip_improve:
        cmd = [py, str(HERE / "improve_microgloss.py"),
               "--target", str(db),
               "--llm-wrapper", str(wrapper),
               "--top-lemmas", str(args.top_lemmas),
               "--embedding-method", args.diagnostic_embedder,
               "--tier", args.tier,
               "--temp", str(args.temp),
               "--workers", str(args.workers)]
        if args.revisit:
            cmd.append("--revisit")
        rc = run_stage("Stage 1/4: LLM microgloss + metadata improvement",
                       cmd, args.dry_run)
        stages_run += 1
        if rc != 0 and not args.dry_run:
            return rc

    # ---- 2. Rebuild embedding text ----
    if not args.skip_embed:
        cmd = [py, str(HERE / "build_embedding_texts.py"),
               "--target", str(db), "--pass", "v2"]
        rc = run_stage("Stage 2/4: Rebuild embedding text (v2)",
                       cmd, args.dry_run)
        stages_run += 1
        if rc != 0 and not args.dry_run:
            return rc

    # ---- 3. Production embeddings (bge-large) ----
    if not args.skip_embed:
        cmd = [py, str(HERE / "compute_embeddings.py"),
               "--target", str(db),
               "--embedding-method", args.production_embedder,
               "--device", args.device]
        rc = run_stage("Stage 3/4: Compute production embeddings",
                       cmd, args.dry_run)
        stages_run += 1
        if rc != 0 and not args.dry_run:
            return rc

    # ---- 4. Production audit (ship gate) ----
    if not args.skip_audit:
        cmd = [py, str(HERE / "quality_audit.py"),
               "--target", str(db),
               "--embedding-method", args.production_embedder,
               "--audit-phase", "production"]
        rc = run_stage("Stage 4/4: Production self-retrieval audit",
                       cmd, args.dry_run)
        stages_run += 1
        if rc != 0 and not args.dry_run:
            return rc

    print()
    print("=" * 70)
    print(f"  PHASE 2A COMPLETE -- ran {stages_run} stage(s)")
    print("=" * 70)
    print("  Next options:")
    print("    - Expand the frontier: re-run with --top-lemmas 5000 (or higher)")
    print("    - Refine: re-run with --revisit to improve already-improved senses")
    print("    - Build the relation graph: python build_relations.py ...")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
