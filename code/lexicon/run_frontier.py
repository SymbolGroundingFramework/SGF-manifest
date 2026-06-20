#!/usr/bin/env python3
"""
run_frontier.py -- orchestrator

Reads a TOML frontier config and runs every pipeline stage with the
right scope and tier filters. Resumable: senses already at or above
the target tier are skipped per stage.

CONFIG SHAPE
------------
A frontier config is a TOML file. See bootstrap_top_5k.toml for the
example shipped with the bundle. Keys:

    name                       # arbitrary identifier
    target_tier                # how far in-scope senses should go
    [scope]                    # which senses are in scope
      top_lemmas               #   include all senses for the top-N
                               #   most-frequent lemmas
      include_polysemous_below_rank  # include polysemous lemmas below rank
      include_proper_nouns_below_rank
      include_sparse_below_rank
    [embeddings]
      diagnostic               # embedder used in Stage 5
      production               # embedder used in Stage 8
    [quality_gate]
      relaxed_pass_rate_min    # production-audit threshold (0.99 default)
    [stages]                   # optional; if omitted, all stages run
      include = ["3","5","5.5","6","8","8.5","9","10","11"]

USAGE
-----
    python run_frontier.py --config bootstrap_top_5k.toml \\
        --llm-wrapper /path/to/llm.py

    python run_frontier.py --config bootstrap_top_5k.toml --dry-run

    python run_frontier.py --config bootstrap_top_5k.toml \\
        --skip-stages 11   # skip semantic-relation harvest this run

WHAT IT DOES NOT DO
-------------------
- Run Stages 1 and 2 (Wiktionary ingest). Those are one-time
  prerequisites and stay outside the frontier abstraction.
- Apply schema migrations. Run schema.sql once before the first frontier run.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib
    except ImportError:
        print(
            "ERROR: tomllib (3.11+) or tomli is required to parse TOML configs.\n"
            "Install: pip install tomli",
            file=sys.stderr,
        )
        sys.exit(2)


HERE = Path(__file__).resolve().parent


# Tier ordering. Used to decide which stages are needed to reach the
# requested target_tier.
TIER_ORDER = [
    "raw", "provisional", "embedded_v1", "improved",
    "embedded_v2", "clustered", "related",
]

# Each stage advances a sense from a source tier to a destination tier
# (or it's a tier-neutral audit). Stages can be filtered out via
# config or CLI.
STAGE_DEFS = [
    # stage_id, description, target_tier_after, audit_only
    ("3",   "Stage 3: deterministic microgloss + metadata",       "provisional", False),
    ("5",   "Stage 5: first-pass embeddings (diagnostic)",        "embedded_v1", False),
    ("5.5", "Stage 5.5: first-pass quality audit",                None,           True),
    ("6",   "Stage 6: LLM improver",                              "improved",    False),
    ("8",   "Stage 8: production embeddings",                     "embedded_v2", False),
    ("8.5", "Stage 8.5: production quality audit",                None,           True),
    ("9",   "Stage 9: cluster discovery",                         "clustered",   False),
    ("10",  "Stage 10: standard-form selection",                  "clustered",   False),
    ("11",  "Stage 11: semantic-relation harvest",                "related",     False),
]


def load_config(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def python_script(name):
    return [sys.executable, str(HERE / name)]


def now_int():
    return int(time.time())


def run_subprocess(cmd, dry_run, log_file=None):
    """Run a stage subprocess, STREAMING its output live to the parent's
    stdout. Also tees to log_file if provided. Returns
    (returncode, stdout, stderr).

    Streaming matters: a stage that takes 5 minutes (like
    compute_embeddings.py over 72K senses) prints progress lines every
    few seconds. If we buffered with capture_output=True, the user sees
    a blank screen for the whole 5 minutes and cannot tell whether the
    script is making progress, stuck, or dead.
    """
    pretty = " ".join(str(c) for c in cmd)
    print(f"  $ {pretty}", flush=True)
    if dry_run:
        return 0, "", ""
    t0 = time.time()

    # Stream stdout line-by-line; merge stderr into stdout so the user
    # sees everything interleaved as it happens. Each line is prefixed
    # with four spaces to stay visually grouped under the '  $ ...' line.
    #
    # PYTHONUNBUFFERED forces the child to flush print() immediately
    # instead of buffering. Without this, the child's progress lines
    # would only appear when the child exits -- defeating the whole
    # point of streaming.
    child_env = os.environ.copy()
    child_env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,           # line-buffered
        env=child_env,
    )

    captured = []
    try:
        for line in proc.stdout:
            sys.stdout.write("    " + line)
            sys.stdout.flush()
            captured.append(line)
    finally:
        proc.stdout.close()
        proc.wait()

    dt = time.time() - t0
    full_output = "".join(captured)

    if log_file:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n## {pretty}  ({dt:.1f}s)  exit={proc.returncode}\n")
            f.write("--- OUTPUT ---\n")
            f.write(full_output)

    if proc.returncode != 0:
        print(f"    FAIL ({dt:.1f}s, exit={proc.returncode})")
        tail = full_output.strip()[-500:]
        if tail:
            print(f"    tail: {tail}")
    else:
        print(f"    ok ({dt:.1f}s)")
    return proc.returncode, full_output, ""


def stages_required_for(target_tier):
    """Return the ordered list of stage_ids needed to reach target_tier."""
    if target_tier not in TIER_ORDER:
        raise ValueError(f"unknown target_tier {target_tier!r}")
    target_idx = TIER_ORDER.index(target_tier)
    out = []
    for stage_id, _desc, after_tier, audit in STAGE_DEFS:
        if audit:
            # Audits run after the preceding production stage. Include
            # 5.5 only if we're going through embedded_v1 (Stage 5);
            # include 8.5 only if we're going through embedded_v2.
            if stage_id == "5.5" and target_idx >= TIER_ORDER.index("embedded_v1"):
                out.append(stage_id)
            elif stage_id == "8.5" and target_idx >= TIER_ORDER.index("embedded_v2"):
                out.append(stage_id)
            continue
        # Production stage: include if its destination tier is needed.
        if after_tier and TIER_ORDER.index(after_tier) <= target_idx:
            out.append(stage_id)
    return out


def write_frontier_run(conn, run_id, cfg, target_tier, scope_summary,
                       stages_ran, status, n_promoted, error=None):
    config_toml = json.dumps(cfg, indent=2)  # JSON copy for the audit row
    conn.execute(
        """
        INSERT OR REPLACE INTO frontier_run (
            run_id, config_name, config_toml, started_at, completed_at,
            target_tier, scope_summary, stages_ran, status,
            n_promoted, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id, cfg.get("name", "anonymous"), config_toml,
            now_int(), now_int() if status != "running" else None,
            target_tier, scope_summary,
            ",".join(stages_ran), status, n_promoted, error,
        ),
    )
    conn.commit()


def count_promoted_to_or_above(conn, target_tier):
    target_idx = TIER_ORDER.index(target_tier)
    valid = TIER_ORDER[target_idx:]
    placeholders = ",".join("?" * len(valid))
    cur = conn.execute(
        f"SELECT COUNT(*) FROM sgf_lexicon WHERE maturity_tier IN ({placeholders})",
        valid,
    )
    return cur.fetchone()[0]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True, help="Path to a frontier TOML config")
    p.add_argument("--target", default="sgf_lexicon.db")
    p.add_argument("--llm-wrapper", help="Path to LLM wrapper (required for stages 6/10/11)")
    p.add_argument("--dry-run", action="store_true",
                   help="Show the stage commands without running them")
    p.add_argument("--skip-stages", default="",
                   help="Comma-separated stage ids to skip (e.g., '11,8.5')")
    p.add_argument("--only-stages", default="",
                   help="Comma-separated stage ids to RUN (overrides target_tier)")
    p.add_argument("--log-dir", default=None,
                   help="If set, write per-run stdout/stderr to this directory")
    args = p.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"Config not found: {cfg_path}", file=sys.stderr)
        return 1

    cfg = load_config(cfg_path)
    cfg_name = cfg.get("name") or cfg_path.stem
    target_tier = cfg.get("target_tier", "related")
    scope = cfg.get("scope", {})
    embeddings = cfg.get("embeddings", {})
    quality_gate = cfg.get("quality_gate", {})

    top_lemmas = int(scope.get("top_lemmas", 5000))
    polysemy_cutoff = int(scope.get("include_polysemous_below_rank", top_lemmas * 5))
    propnoun_cutoff = int(scope.get("include_proper_nouns_below_rank", top_lemmas * 2))
    sparse_cutoff   = int(scope.get("include_sparse_below_rank", top_lemmas * 2))

    diagnostic_embedder = embeddings.get("diagnostic", "bge-small-en-v1")
    production_embedder = embeddings.get("production", "bge-large-en-v1")
    relaxed_min = float(quality_gate.get("relaxed_pass_rate_min", 0.99))

    # Stage selection
    skip = {s.strip() for s in args.skip_stages.split(",") if s.strip()}
    only = {s.strip() for s in args.only_stages.split(",") if s.strip()}
    if only:
        stages = [s for s in only]
    else:
        stages = stages_required_for(target_tier)
    stages = [s for s in stages if s not in skip]

    db = Path(args.target)
    if not db.exists():
        print(f"DB not found: {db}", file=sys.stderr)
        return 1

    print("=" * 70)
    print(f"  FRONTIER RUN: {cfg_name}")
    print("=" * 70)
    print(f"  config:               {cfg_path}")
    print(f"  target_tier:          {target_tier}")
    print(f"  scope.top_lemmas:     {top_lemmas:,}")
    print(f"  diagnostic_embedder:  {diagnostic_embedder}")
    print(f"  production_embedder:  {production_embedder}")
    print(f"  relaxed_pass_min:     {relaxed_min:.3f}")
    print(f"  stages to run:        {stages}")
    print(f"  dry_run:              {args.dry_run}")
    print()

    run_id = f"frontier_{cfg_name}_{now_int()}_{secrets.token_hex(3)}"
    log_file = None
    if args.log_dir:
        Path(args.log_dir).mkdir(parents=True, exist_ok=True)
        log_file = Path(args.log_dir) / f"{run_id}.log"

    conn = sqlite3.connect(db)
    conn.execute("PRAGMA busy_timeout = 60000")

    scope_summary = (
        f"top_lemmas={top_lemmas} polysemy={polysemy_cutoff} "
        f"propnoun={propnoun_cutoff} sparse={sparse_cutoff}"
    )
    n_before = count_promoted_to_or_above(conn, target_tier)
    write_frontier_run(conn, run_id, cfg, target_tier, scope_summary,
                       stages, "running", 0)

    stage_status = {}
    for stage_id in stages:
        desc = next((d for sid, d, _, _ in STAGE_DEFS if sid == stage_id), stage_id)
        print()
        print(f"--- {desc} ---")
        ok = run_stage(
            stage_id, db, top_lemmas, polysemy_cutoff, propnoun_cutoff, sparse_cutoff,
            diagnostic_embedder, production_embedder, args.llm_wrapper,
            args.dry_run, log_file, run_id,
        )
        stage_status[stage_id] = ok
        if not ok:
            print(f"\nStage {stage_id} failed; aborting frontier run.")
            n_after = count_promoted_to_or_above(conn, target_tier)
            write_frontier_run(
                conn, run_id, cfg, target_tier, scope_summary,
                stages, "failed", max(0, n_after - n_before),
                error=f"stage {stage_id} failed",
            )
            return 1

    n_after = count_promoted_to_or_above(conn, target_tier)
    write_frontier_run(conn, run_id, cfg, target_tier, scope_summary,
                       stages, "complete" if not args.dry_run else "dry_run",
                       max(0, n_after - n_before))

    print()
    print("=" * 70)
    print(f"  FRONTIER RUN COMPLETE")
    print("=" * 70)
    print(f"  run_id:               {run_id}")
    print(f"  senses promoted:      {max(0, n_after - n_before):,}")
    print(f"  senses at >= {target_tier}: {n_after:,}")
    if log_file:
        print(f"  log:                  {log_file}")
    print("=" * 70)
    return 0


def run_stage(stage_id, db, top_lemmas, polysemy_cutoff, propnoun_cutoff,
              sparse_cutoff, diagnostic_embedder, production_embedder,
              llm_wrapper, dry_run, log_file, run_id):
    """Dispatch one stage to its underlying script."""
    if stage_id == "3":
        cmd = python_script("generate_microglosses.py") + ["--target", str(db)]
    elif stage_id == "5":
        # First build the embedding text v1, then embed.
        rc, _, _ = run_subprocess(
            python_script("build_embedding_texts.py")
            + ["--target", str(db), "--pass", "v1"],
            dry_run, log_file,
        )
        if rc != 0:
            return False
        cmd = python_script("compute_embeddings.py") + [
            "--target", str(db),
            "--embedding-method", diagnostic_embedder,
            "--device", "cpu",
        ]
    elif stage_id == "5.5":
        cmd = python_script("quality_audit.py") + [
            "--target", str(db),
            "--embedding-method", diagnostic_embedder,
            "--audit-phase", "first_pass",
            "--audit-run-id", f"{run_id}_first",
        ]
    elif stage_id == "6":
        if not llm_wrapper:
            if dry_run:
                print("    [dry-run] Stage 6 would need --llm-wrapper; skipping plan")
                return True
            print("    ERROR: Stage 6 requires --llm-wrapper")
            return False
        cmd = python_script("improve_microgloss.py") + [
            "--target", str(db),
            "--llm-wrapper", llm_wrapper,
            "--top-lemmas", str(top_lemmas),
            "--polysemy-cutoff", str(polysemy_cutoff),
            "--propnoun-cutoff", str(propnoun_cutoff),
            "--sparse-cutoff", str(sparse_cutoff),
        ]
    elif stage_id == "8":
        rc, _, _ = run_subprocess(
            python_script("build_embedding_texts.py")
            + ["--target", str(db), "--pass", "v2"],
            dry_run, log_file,
        )
        if rc != 0:
            return False
        cmd = python_script("compute_embeddings.py") + [
            "--target", str(db),
            "--embedding-method", production_embedder,
            "--device", "cpu",
        ]
    elif stage_id == "8.5":
        cmd = python_script("quality_audit.py") + [
            "--target", str(db),
            "--embedding-method", production_embedder,
            "--audit-phase", "production",
            "--audit-run-id", f"{run_id}_prod",
        ]
    elif stage_id == "9":
        cmd = python_script("discover_clusters.py") + [
            "--target", str(db),
            "--embedding-method", production_embedder,
            "--discovery-run-id", f"{run_id}_clusters",
        ]
    elif stage_id == "10":
        cmd = python_script("select_standard_forms.py") + [
            "--target", str(db),
            "--embedding-method", production_embedder,
        ]
        if llm_wrapper:
            cmd += ["--llm-wrapper", llm_wrapper]
    elif stage_id == "11":
        cmd = python_script("harvest_semantic_relations.py") + [
            "--target", str(db),
            "--top-lemmas", str(max(top_lemmas, propnoun_cutoff)),
        ]
        if llm_wrapper:
            cmd += ["--llm-wrapper", llm_wrapper]
        else:
            cmd.append("--patterns-only")
    else:
        print(f"    ERROR: unknown stage_id {stage_id!r}")
        return False

    rc, _, _ = run_subprocess(cmd, dry_run, log_file)
    return rc == 0


if __name__ == "__main__":
    sys.exit(main())
