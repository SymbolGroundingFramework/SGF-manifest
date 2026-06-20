#!/usr/bin/env python3
"""
repair_audit_failures.py -- per-sense closed-loop repair

WHAT THIS IS
------------
Targeted repair for senses that failed Stage 5.5 (diagnostic) or
Stage 8.5 (production) self-retrieval audit. Operates in small batches
with immediate feedback: improve a batch, re-embed those rows,
re-audit those rows, report which got fixed. Optionally retry stubborn
failures with a stronger LLM tier.

This is the Phase 2A workflow when you do NOT want to improve
"the top N most frequent lemmas." You want to improve "every sense
that is broken right now." Audit-failure-driven, not frequency-driven.

WORKFLOW
--------
1. Read quality_audit; pick senses where intralemma_pass = 0 (the
   dominant intra-language production criterion).
2. Process in batches of --batch (default 25):
   2a. Improve each sense via improve_microgloss.py --wsids ...
   2b. Rebuild embedding_text for those wsids
       (build_embedding_texts.py --pass v2)
   2c. Recompute embeddings for those wsids
       (compute_embeddings.py --wsids ... -- forces overwrite)
   2d. Re-audit those wsids (quality_audit.py --wsids ...)
   2e. Report: before -> after pass/fail per wsid
3. Stubborn cases (still failing after retry) get logged as
   `repair_unresolved.txt` so you can inspect them by hand.

USAGE
-----
    python repair_audit_failures.py \\
        --target sgf_lexicon.db \\
        --llm-wrapper llm_wrapper.py \\
        [--audit-phase first_pass|production] \\
        [--embedding-method bge-small-en-v1|bge-large-en-v1] \\
        [--batch 25] \\
        [--max-attempts 100] \\
        [--retry-tier strong] \\
        [--dry-run]

Defaults:
  --audit-phase first_pass    (the bge-small Stage 5.5 audit)
  --embedding-method bge-small-en-v1
  --batch 25
  --max-attempts (none; process all failures)
  --retry-tier strong (re-try failed-after-improvement with stronger LLM)

DESIGN CHOICES
--------------
- Ship gate is intralemma_pass only. A sense that passes intralemma
  is queryable in grounding mode (the dominant production case).
  Strict/topk failures are kept but not gated on.
- Retry-with-stronger-tier on still-failing senses (one retry).
  Keeps whichever of the two attempts has the better verdict.
- Per-batch feedback. You see fix rates within minutes, not hours.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sqlite3
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent


def run_subprocess(name, cmd, stream=True, capture=False):
    """Run a subprocess. Returns (returncode, stdout_if_captured)."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    if capture:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        return result.returncode, result.stdout
    if stream:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=env,
        )
        try:
            for line in proc.stdout:
                sys.stdout.write("    " + line)
                sys.stdout.flush()
        finally:
            proc.stdout.close()
            proc.wait()
        return proc.returncode, None
    rc = subprocess.call(cmd, env=env)
    return rc, None


def get_failed_wsids(db_path, embedding_method, audit_phase):
    """Pull the most recent audit run's failed-intralemma wsids."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(quality_audit)")
    cols = {row[1] for row in cur.fetchall()}
    if "intralemma_pass" not in cols:
        print("ERROR: quality_audit.intralemma_pass column missing. "
              "Run quality_audit.py first.", file=sys.stderr)
        return []
    cur.execute(
        """
        SELECT wsid FROM quality_audit
         WHERE intralemma_pass = 0
           AND audit_phase = ?
           AND embedding_method = ?
           AND audit_run_id = (
               SELECT audit_run_id FROM quality_audit
                WHERE audit_phase = ? AND embedding_method = ?
                ORDER BY audited_at DESC LIMIT 1
           )
        """,
        (audit_phase, embedding_method, audit_phase, embedding_method),
    )
    out = [row[0] for row in cur.fetchall()]
    conn.close()
    return out


def get_intralemma_pass_for_wsids(db_path, embedding_method, audit_phase, wsids):
    """Return dict {wsid: 1|0|None} from the most recent audit for these wsids."""
    if not wsids:
        return {}
    conn = sqlite3.connect(db_path)
    placeholders = ",".join("?" * len(wsids))
    sql = f"""
        SELECT wsid, intralemma_pass, audited_at
          FROM quality_audit
         WHERE wsid IN ({placeholders})
           AND audit_phase = ?
           AND embedding_method = ?
         ORDER BY wsid, audited_at DESC
    """
    cur = conn.execute(sql, wsids + [audit_phase, embedding_method])
    seen = {}
    for w, ip, _ in cur:
        if w not in seen:  # ORDER BY audited_at DESC gives newest first
            seen[w] = ip
    conn.close()
    return seen


def process_batch(args, batch_wsids, tier_for_this_attempt):
    """One repair attempt against a batch of wsids. Returns dict of new verdicts."""
    wsids_csv = ",".join(str(w) for w in batch_wsids)
    py = sys.executable

    print()
    print(f"  --- improving {len(batch_wsids)} wsids with tier={tier_for_this_attempt} ---")
    cmd = [py, str(HERE / "improve_microgloss.py"),
           "--target", args.target,
           "--llm-wrapper", args.llm_wrapper,
           "--embedding-method", args.embedding_method,
           "--tier", tier_for_this_attempt,
           "--temp", "0.0",
           "--wsids", wsids_csv,
           "--revisit"]
    rc, _ = run_subprocess("improver", cmd)
    if rc != 0:
        print(f"  WARN: improver returned {rc}; continuing")

    print()
    print(f"  --- rebuilding embedding_text for {len(batch_wsids)} wsids ---")
    cmd = [py, str(HERE / "build_embedding_texts.py"),
           "--target", args.target,
           "--pass", "v2"]
    rc, _ = run_subprocess("text", cmd)
    if rc != 0:
        print(f"  WARN: build_embedding_texts returned {rc}")

    print()
    print(f"  --- recomputing embeddings for {len(batch_wsids)} wsids ---")
    cmd = [py, str(HERE / "compute_embeddings.py"),
           "--target", args.target,
           "--embedding-method", args.embedding_method,
           "--device", args.device,
           "--wsids", wsids_csv]
    rc, _ = run_subprocess("embed", cmd)
    if rc != 0:
        print(f"  WARN: compute_embeddings returned {rc}")

    print()
    print(f"  --- re-auditing {len(batch_wsids)} wsids ---")
    audit_run_id = f"repair_{int(time.time())}"
    cmd = [py, str(HERE / "quality_audit.py"),
           "--target", args.target,
           "--embedding-method", args.embedding_method,
           "--audit-phase", args.audit_phase,
           "--audit-run-id", audit_run_id,
           "--wsids", wsids_csv]
    rc, _ = run_subprocess("audit", cmd)
    if rc != 0:
        print(f"  WARN: quality_audit returned {rc}")

    return get_intralemma_pass_for_wsids(
        args.target, args.embedding_method, args.audit_phase, batch_wsids,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    p.add_argument("--target", default="sgf_lexicon.db")
    p.add_argument("--llm-wrapper", required=True)
    p.add_argument("--audit-phase", default="first_pass",
                   choices=["first_pass", "production"],
                   help="Which audit phase to repair (default: first_pass)")
    p.add_argument("--embedding-method", default="bge-small-en-v1")
    p.add_argument("--device", default="cpu", choices=["cpu", "dml", "cuda"])
    p.add_argument("--batch", type=int, default=25,
                   help="Senses per repair iteration (default: 25)")
    p.add_argument("--max-attempts", type=int, default=None,
                   help="Stop after attempting this many senses (default: all)")
    p.add_argument("--retry-tier", default="strong",
                   help="LLM tier for the retry pass on stubborn failures "
                        "(default: strong)")
    p.add_argument("--initial-tier", default="flash",
                   help="LLM tier for the first attempt (default: flash)")
    p.add_argument("--no-retry", action="store_true",
                   help="Skip the retry-with-stronger-tier pass")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would be done; do not call LLM or write")
    args = p.parse_args()

    db = Path(args.target)
    if not db.exists():
        print(f"DB not found: {db}", file=sys.stderr)
        return 1

    print()
    print("=" * 70)
    print("  Audit-failure-driven lexicon repair")
    print("=" * 70)
    print(f"  target:          {db.resolve()}")
    print(f"  audit phase:     {args.audit_phase}")
    print(f"  embedder:        {args.embedding_method}")
    print(f"  batch size:      {args.batch}")
    print(f"  initial tier:    {args.initial_tier}")
    print(f"  retry tier:      {args.retry_tier} (disabled: {args.no_retry})")
    print()

    failed = get_failed_wsids(db, args.embedding_method, args.audit_phase)
    if not failed:
        print("No audit failures to repair. Lexicon is clean for this audit phase.")
        return 0
    if args.max_attempts:
        failed = failed[: args.max_attempts]
    print(f"Audit-failed senses to repair: {len(failed):,}")

    if args.dry_run:
        print("\nDRY RUN -- first 10 failed wsids:")
        for w in failed[:10]:
            print(f"  {w}")
        return 0

    # Track stubborn cases for second pass
    fixed_total = 0
    still_failing = []
    t0 = time.time()

    for i in range(0, len(failed), args.batch):
        batch = failed[i: i + args.batch]
        print()
        print("=" * 70)
        print(f"  Batch {i // args.batch + 1}: senses {i+1}-{i+len(batch)} of {len(failed)}")
        print("=" * 70)

        verdicts = process_batch(args, batch, args.initial_tier)
        fixed = [w for w in batch if verdicts.get(w) == 1]
        still = [w for w in batch if verdicts.get(w) != 1]
        fixed_total += len(fixed)
        still_failing.extend(still)

        elapsed = time.time() - t0
        rate = (i + len(batch)) / max(elapsed, 0.001)
        eta_min = (len(failed) - i - len(batch)) / max(rate, 0.001) / 60.0
        print()
        print(f"  BATCH RESULT: fixed {len(fixed)}/{len(batch)}  "
              f"running total fixed: {fixed_total}/{i + len(batch)}  "
              f"eta: {eta_min:.1f}m")

    # Retry pass with stronger tier, if requested
    if still_failing and not args.no_retry:
        print()
        print("=" * 70)
        print(f"  RETRY PASS with tier={args.retry_tier}: "
              f"{len(still_failing)} stubborn senses")
        print("=" * 70)
        retry_fixed_total = 0
        unresolved = []
        for i in range(0, len(still_failing), args.batch):
            batch = still_failing[i: i + args.batch]
            verdicts = process_batch(args, batch, args.retry_tier)
            fixed = [w for w in batch if verdicts.get(w) == 1]
            still = [w for w in batch if verdicts.get(w) != 1]
            retry_fixed_total += len(fixed)
            unresolved.extend(still)
            print(f"  retry batch fixed {len(fixed)}/{len(batch)}  "
                  f"running: {retry_fixed_total}/{i + len(batch)}")
        fixed_total += retry_fixed_total
    else:
        unresolved = still_failing

    # Final summary + unresolved list
    print()
    print("=" * 70)
    print("  REPAIR COMPLETE")
    print("=" * 70)
    print(f"  audit failures at start:    {len(failed):,}")
    print(f"  fixed:                       {fixed_total:,}")
    print(f"  unresolved:                  {len(unresolved):,}")
    print(f"  elapsed:                     {(time.time() - t0)/60:.1f} min")

    if unresolved:
        log_path = Path("repair_unresolved.txt")
        log_path.write_text(
            "\n".join(str(w) for w in unresolved) + "\n", encoding="utf-8"
        )
        print(f"\n  Unresolved wsids written to: {log_path.resolve()}")
        print("  Inspect them by hand. The retry tier could not repair these.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
