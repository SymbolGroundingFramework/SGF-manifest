#!/usr/bin/env python3
"""
quality_audit.py -- Stages 5.5 / 8.5 -- self-retrieval audit

For every (or a sampled subset of) senses with an embedding in the
specified embedding_method, runs the self-retrieval test under FOUR
criteria, each of which mirrors a real production retrieval regime:

  1. INTRA-LEMMA: among the senses sharing this lemma, is my own
     embedding at top-1? This mirrors GROUNDING MODE (lemma known) --
     the dominant intra-language production path.

  2. STRICT (full lexicon): across the entire lexicon, is my own
     embedding at top-1? This mirrors CROSS-LANGUAGE MODE where the
     query is a foreign-language token with no lemma overlap; the
     production embedding must find its content match across the whole
     space.

  3. TOPK (full lexicon): across the entire lexicon, am I in top-K?
     This is the cross-language regime relaxed -- "did I land in the
     right neighborhood, even if not exactly self?"

  4. CLUSTER (full lexicon, post-cluster only): across the entire
     lexicon, is top-1 either self OR a member of my content-identical
     group? This mirrors SNAP-TO-STANDARD policy. Only computable after
     Stage 9/10 have built clusters; before that, this column is left
     NULL.

Writes one row to quality_audit per sense per audit_run_id.

WHY FOUR CRITERIA
-----------------
A single "self at top-1 across the full lexicon" criterion is
architecturally wrong for any sense that lives in a synonym cluster.
Asking the embedding for `freezing` to retrieve `freezing` ahead of
`frigid` is asking the embedder to manufacture a distinction the
language itself does not make. The four-criterion audit reports
honestly: each criterion answers a different question, and the right
criterion to ship-gate on depends on the search regime your downstream
will operate in.

The lexicon spec commits to two production retrieval modes (Part 7.4
grounding mode; Part 7.5 cross-language mode) plus the snap-to-
standard policy (Part 7.2). The four-criterion audit gives each mode a
dedicated, falsifiable health metric.

PERFORMANCE
-----------
All criteria are computed via batched NumPy matmul -- one query batch
of B senses times the (N x D) embedding matrix produces a (B x N)
similarity matrix; top-K is extracted with argpartition. Total work is
O(N * B_total) but the inner kernel is BLAS. On a CPU, 72K senses x
384 dims completes in 2-3 minutes; 1.7M senses x 1024 dims completes
in 30-60 minutes. Above ~200K senses, swap in FAISS; the structure of
this script does not change, only the candidate-set step.

The previous version of this script iterated all_vecs in pure Python.
At 72K senses, that was 5 billion Python-level operations per audit
run, effectively never finishing. The fix is implementation, not
algorithm.

USAGE
-----
    python quality_audit.py --target sgf_lexicon.db \\
        --embedding-method bge-small-en-v1 \\
        --audit-phase first_pass \\
        --top-k 10 \\
        [--sample 5000] [--seed 42] [--audit-run-id MY_RUN] \\
        [--batch-size 512]
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import struct
import sys
import time
from pathlib import Path

import numpy as np


# ----------------------------------------------------------------------
# schema migration: add the new criterion columns if missing
# ----------------------------------------------------------------------

def ensure_quality_audit_columns(conn):
    """Add intralemma_pass and topk_pass columns if they are not yet
    present on the quality_audit table. Idempotent -- safe to call on
    every run.
    """
    cur = conn.execute("PRAGMA table_info(quality_audit)")
    existing = {row[1] for row in cur.fetchall()}
    if not existing:
        print(
            "ERROR: quality_audit table missing. Run: python apply_schema.py",
            file=sys.stderr,
        )
        return False
    if "intralemma_pass" not in existing:
        conn.execute("ALTER TABLE quality_audit ADD COLUMN intralemma_pass INTEGER")
    if "topk_pass" not in existing:
        conn.execute("ALTER TABLE quality_audit ADD COLUMN topk_pass INTEGER")
    if "cluster_pass" not in existing:
        # alias of relaxed_pass conceptually, but we leave them separate
        # so old runs keep their relaxed_pass meaning intact. cluster_pass
        # is only populated when content_identical_member is non-empty.
        conn.execute("ALTER TABLE quality_audit ADD COLUMN cluster_pass INTEGER")
    conn.commit()
    return True


# ----------------------------------------------------------------------
# embedding load
# ----------------------------------------------------------------------

def load_embeddings(conn, embedding_method, limit_population=None):
    """Load all embeddings into NumPy arrays. Returns:
        wsids      : np.int64 array (N,)
        cids       : list of N strings (canonical_id, for logging)
        lemmas     : np.array of N strings (for intra-lemma grouping)
        vecs       : np.float32 array (N, D), L2-normalized
        lemma_groups : dict mapping lemma -> np.int64 array of row indices
    """
    print()
    print("Loading embeddings ...")
    t0 = time.time()
    sql = """
        SELECT sl.wiktionary_source_id, sl.canonical_id, sl.lemma, se.embed
          FROM sense_embedding se
          JOIN sgf_lexicon sl
            ON sl.wiktionary_source_id = se.wiktionary_source_id
         WHERE se.embedding_method = ?
           AND sl.canonical_id IS NOT NULL
           AND se.embed IS NOT NULL
    """
    if limit_population:
        sql += f" LIMIT {int(limit_population)}"
    cur = conn.execute(sql, (embedding_method,))

    wsid_list = []
    cid_list = []
    lemma_list = []
    vec_blobs = []
    expected_dim = None
    n_skipped = 0
    for wsid, cid, lemma, vec_blob in cur:
        if vec_blob is None:
            n_skipped += 1
            continue
        n = len(vec_blob) // 4
        if expected_dim is None:
            expected_dim = n
        if n != expected_dim:
            n_skipped += 1
            continue
        wsid_list.append(wsid)
        cid_list.append(cid)
        lemma_list.append(lemma or "")
        vec_blobs.append(vec_blob)

    if not wsid_list:
        return None

    N = len(wsid_list)
    D = expected_dim
    # Materialize the vector matrix from blob bytes. This is a single
    # contiguous allocation of N*D float32s -- 72K * 384 * 4 = ~110 MB,
    # 1.7M * 1024 * 4 = ~7 GB.
    vecs = np.empty((N, D), dtype=np.float32)
    for i, blob in enumerate(vec_blobs):
        vecs[i] = np.frombuffer(blob, dtype="<f4", count=D)

    # Re-normalize defensively -- compute_embeddings.py emits normalized
    # vectors, but if anything was written un-normalized this prevents
    # silent bias.
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    vecs = vecs / norms

    wsids = np.array(wsid_list, dtype=np.int64)
    lemmas = np.array(lemma_list)

    # Build lemma -> row-indices map for the intra-lemma criterion.
    lemma_groups = {}
    for i, lm in enumerate(lemma_list):
        if not lm:
            continue
        lemma_groups.setdefault(lm, []).append(i)
    lemma_groups = {lm: np.array(ix, dtype=np.int64)
                    for lm, ix in lemma_groups.items()}

    dt = time.time() - t0
    n_polysemous = sum(1 for v in lemma_groups.values() if len(v) > 1)
    print(f"  loaded {N:,} senses with embeddings (dim={D})  in {dt:.1f}s")
    if n_skipped:
        print(f"  skipped {n_skipped:,} rows with missing/dim-mismatched blobs")
    print(f"  distinct lemmas: {len(lemma_groups):,} ({n_polysemous:,} polysemous)")
    return wsids, cid_list, lemmas, vecs, lemma_groups


# ----------------------------------------------------------------------
# cluster lookup -- only meaningful after Stage 9/10
# ----------------------------------------------------------------------

def load_cluster_membership(conn, wsids):
    """Return dict wsid -> set of cluster-sibling wsids, considering
    only the 'general' audience_tier. Returns empty dict if cluster
    tables are empty (pre-Stage-9 audit)."""
    cur = conn.execute(
        "SELECT COUNT(*) FROM content_identical_member"
    )
    if cur.fetchone()[0] == 0:
        return {}, False
    sib_map = {}
    wsid_set = set(int(w) for w in wsids)
    cur = conn.execute(
        """
        SELECT cim.group_id, cim.wsid
          FROM content_identical_member cim
          JOIN content_identical_group cig
            ON cig.group_id = cim.group_id
         WHERE cig.audience_tier = 'general'
        """
    )
    group_to_members = {}
    for gid, wsid in cur.fetchall():
        if wsid in wsid_set:
            group_to_members.setdefault(gid, []).append(wsid)
    for gid, members in group_to_members.items():
        ms = set(members)
        for w in members:
            sib_map[w] = ms
    return sib_map, True


# ----------------------------------------------------------------------
# the main audit kernel: batched NumPy matmul
# ----------------------------------------------------------------------

def audit_batched(
    wsids, cids, lemmas, vecs, lemma_groups, sib_map, has_clusters,
    sample_idx, top_k, batch_size, embedding_method, audit_run_id,
    audit_phase, conn, t_start,
):
    """Run the four-criterion audit in batches.

    For each batch of B query rows, computes the (B x N) similarity
    matrix in one BLAS call, extracts top-K per row, and computes the
    four pass criteria.
    """
    N, D = vecs.shape
    sample_arr = np.array(sample_idx, dtype=np.int64)
    n_samples = len(sample_arr)

    n_strict = 0
    n_topk = 0
    n_intralemma_polysemous = 0
    n_intralemma_passing = 0
    n_intralemma_monoseme = 0   # trivially passes (no siblings to compete)
    n_cluster_passing = 0
    rank_hist = {"1": 0, "2-5": 0, "6-10": 0, "11+": 0, "miss": 0}

    print()
    print(f"Auditing {n_samples:,} senses in batches of {batch_size:,} ...")
    if has_clusters:
        print("  cluster_pass criterion: ENABLED "
              "(content_identical_member is populated)")
    else:
        print("  cluster_pass criterion: SKIPPED "
              "(no clusters yet -- run Stage 9/10 first to enable)")

    now = int(time.time())

    # NumPy uses BLAS for matmul -- single-threaded float32 BLAS gets
    # us most of the way. Multi-threading is automatic.
    for batch_start in range(0, n_samples, batch_size):
        batch_end = min(batch_start + batch_size, n_samples)
        idx_batch = sample_arr[batch_start:batch_end]
        Q = vecs[idx_batch]                            # (B, D)
        sims = Q @ vecs.T                              # (B, N)  -- BLAS

        # exclude self from "top across full lexicon" by setting self
        # similarity to -infinity? No -- we WANT to know if top-1 is
        # self. Keep self in the matrix.

        # top-K per row, descending. argpartition is O(N log K), faster
        # than full sort.
        K = max(top_k, 2)
        # argpartition finds K largest, unordered; sort within those K.
        part_idx = np.argpartition(-sims, kth=K-1, axis=1)[:, :K]
        # gather and sort those K per row
        row_arange = np.arange(part_idx.shape[0])[:, None]
        part_sims = sims[row_arange, part_idx]
        order = np.argsort(-part_sims, axis=1)
        topk_idx = part_idx[row_arange, order]         # (B, K) sorted desc
        topk_sims = part_sims[row_arange, order]       # (B, K)

        # Process each row in the batch.
        for b, src_i in enumerate(idx_batch):
            src_wsid = int(wsids[src_i])
            src_lemma = lemmas[src_i]
            tk_indices = topk_idx[b]                   # (K,)
            tk_wsids = wsids[tk_indices]               # (K,)
            tk_cids = [cids[int(j)] for j in tk_indices]
            tk_dists = topk_sims[b]                    # (K,)

            # --- self_rank (within top-K window) ---
            self_rank = None
            for pos, w in enumerate(tk_wsids):
                if int(w) == src_wsid:
                    self_rank = pos + 1
                    break

            strict_pass = 1 if (len(tk_wsids) > 0 and int(tk_wsids[0]) == src_wsid) else 0
            topk_pass = 1 if self_rank is not None else 0

            # --- cluster_pass: top-1 is self or content-identical sibling ---
            cluster_pass = None
            if has_clusters:
                top1 = int(tk_wsids[0]) if len(tk_wsids) > 0 else None
                if top1 == src_wsid:
                    cluster_pass = 1
                else:
                    sibs = sib_map.get(src_wsid)
                    if sibs is not None and top1 in sibs:
                        cluster_pass = 1
                    else:
                        cluster_pass = 0

            # --- intralemma_pass: top-1 *within senses sharing this lemma* ---
            # Trivially passes for monosemes; the real test is on polysemes.
            sibs_idx = lemma_groups.get(src_lemma)
            intralemma_pass = None
            is_monoseme = False
            if sibs_idx is None or len(sibs_idx) <= 1:
                # Monoseme: only one sense for this lemma. Auto-pass.
                intralemma_pass = 1
                is_monoseme = True
            else:
                # Polyseme: compute self vs siblings only.
                sib_sims = vecs[sibs_idx] @ vecs[src_i]   # (S,)
                # find which row in sibs_idx is self
                self_pos_arr = np.where(sibs_idx == src_i)[0]
                if len(self_pos_arr) == 0:
                    # shouldn't happen, but defensive
                    intralemma_pass = 0
                else:
                    self_pos = int(self_pos_arr[0])
                    # is self the argmax?
                    intralemma_pass = 1 if int(np.argmax(sib_sims)) == self_pos else 0

            # accumulate stats
            n_strict += strict_pass
            n_topk += topk_pass
            if cluster_pass == 1:
                n_cluster_passing += 1
            if is_monoseme:
                n_intralemma_monoseme += 1
            else:
                n_intralemma_polysemous += 1
                n_intralemma_passing += intralemma_pass

            if self_rank is None:
                rank_hist["miss"] += 1
            elif self_rank == 1:
                rank_hist["1"] += 1
            elif self_rank <= 5:
                rank_hist["2-5"] += 1
            elif self_rank <= 10:
                rank_hist["6-10"] += 1
            else:
                rank_hist["11+"] += 1

            # relaxed_pass kept for back-compat with consumers of the
            # old column: same semantics as cluster_pass when clusters
            # exist, otherwise same as strict_pass.
            if has_clusters:
                relaxed_pass = cluster_pass if cluster_pass is not None else strict_pass
            else:
                relaxed_pass = strict_pass

            reason = _classify_reason(
                strict_pass, topk_pass, intralemma_pass, cluster_pass,
                has_clusters,
            )

            conn.execute(
                """
                INSERT OR REPLACE INTO quality_audit (
                    wsid, audit_run_id, audit_phase, embedding_method,
                    self_rank, top_k_canonical_ids_json, top_k_distances_json,
                    strict_pass, relaxed_pass, intralemma_pass, topk_pass,
                    cluster_pass, reason, audited_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    src_wsid, audit_run_id, audit_phase, embedding_method,
                    self_rank,
                    json.dumps(tk_cids),
                    json.dumps([round(float(d), 6) for d in tk_dists]),
                    strict_pass, relaxed_pass, intralemma_pass, topk_pass,
                    cluster_pass, reason, now,
                ),
            )

        # commit + progress per batch
        conn.commit()
        elapsed = time.time() - t_start
        done = batch_end
        rate = done / max(elapsed, 0.001)
        remain = (n_samples - done) / max(rate, 0.001)
        print(
            f"  [{done:,}/{n_samples:,}] "
            f"strict={n_strict:,}  topk={n_topk:,}  "
            f"intralemma_poly={n_intralemma_passing:,}/{n_intralemma_polysemous:,}  "
            f"{rate:.0f}/s  eta={remain/60:.1f}m"
        )

    return {
        "n_strict": n_strict,
        "n_topk": n_topk,
        "n_intralemma_passing": n_intralemma_passing,
        "n_intralemma_polysemous": n_intralemma_polysemous,
        "n_intralemma_monoseme": n_intralemma_monoseme,
        "n_cluster_passing": n_cluster_passing,
        "rank_hist": rank_hist,
    }


def _classify_reason(strict, topk, intralemma, cluster, has_clusters):
    if strict:
        return "top1_self"
    if has_clusters and cluster == 1:
        return "top1_content_identical"
    if intralemma == 1:
        return "intralemma_top1_only"
    if topk:
        return "in_topk_only"
    return "miss"


# ----------------------------------------------------------------------
# main
# ----------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", default="sgf_lexicon.db")
    p.add_argument("--embedding-method", required=True,
                   help="Which embedding_method to audit (e.g., bge-small-en-v1)")
    p.add_argument("--audit-phase", required=True,
                   choices=["first_pass", "production", "rebuild"])
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--sample", type=int, default=None,
                   help="Audit a random sample of N senses (default: all)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--audit-run-id", default=None,
                   help="Identifier for this run (default: phase_<phase>_<timestamp>)")
    p.add_argument("--limit-population", type=int, default=None,
                   help="Only load the first N embeddings (for testing on huge DBs)")
    p.add_argument("--wsids", default=None,
                   help="Comma-separated wsids to audit (full lexicon is "
                        "still loaded as the comparison matrix, but only "
                        "these specific senses are scored). For per-sense "
                        "closed-loop repair workflows.")
    p.add_argument("--batch-size", type=int, default=512,
                   help="Number of query rows per matmul batch (memory/speed tradeoff)")
    args = p.parse_args()

    db_path = Path(args.target)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    if args.audit_run_id is None:
        args.audit_run_id = f"{args.audit_phase}_{int(time.time())}"

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA busy_timeout = 60000")
    conn.execute("PRAGMA journal_mode = WAL")

    if not ensure_quality_audit_columns(conn):
        return 1

    print(f"Target:           {db_path.resolve()}")
    print(f"Embedding method: {args.embedding_method}")
    print(f"Audit phase:      {args.audit_phase}")
    print(f"Top-K:            {args.top_k}")
    print(f"Batch size:       {args.batch_size}")
    print(f"Audit run id:     {args.audit_run_id}")

    loaded = load_embeddings(conn, args.embedding_method, args.limit_population)
    if loaded is None:
        print("Nothing to audit.", file=sys.stderr)
        return 1
    wsids, cids, lemmas, vecs, lemma_groups = loaded
    N = len(wsids)

    sib_map, has_clusters = load_cluster_membership(conn, wsids)
    if has_clusters:
        print(f"  cluster sibling map: {len(sib_map):,} senses in clusters")

    # Pick population
    if args.wsids:
        only = {int(x) for x in args.wsids.split(",") if x.strip()}
        sample_idx = [i for i, w in enumerate(wsids) if int(w) in only]
        print(f"  --wsids filter: auditing {len(sample_idx)}/{len(only)} "
              f"requested senses present in the matrix")
        if not sample_idx:
            print("  no requested wsids have embeddings; nothing to audit.",
                  file=sys.stderr)
            return 1
    elif args.sample and args.sample < N:
        rng = random.Random(args.seed)
        sample_idx = rng.sample(range(N), args.sample)
        sample_idx.sort()
    else:
        sample_idx = list(range(N))

    t0 = time.time()
    stats = audit_batched(
        wsids, cids, lemmas, vecs, lemma_groups, sib_map, has_clusters,
        sample_idx, args.top_k, args.batch_size, args.embedding_method,
        args.audit_run_id, args.audit_phase, conn, t0,
    )

    n = len(sample_idx)
    poly = stats["n_intralemma_polysemous"]
    print()
    print("=" * 64)
    print("AUDIT COMPLETE")
    print("=" * 64)
    print(f"  audited:                  {n:,}")
    print(f"  wall time:                {time.time()-t0:.1f}s")
    print()
    print(f"  STRICT pass (full lex):   {stats['n_strict']:,}  "
          f"({100*stats['n_strict']/n:.2f}%)")
    print(f"  TOP-{args.top_k} pass (full lex):    "
          f"{stats['n_topk']:,}  ({100*stats['n_topk']/n:.2f}%)")
    if poly > 0:
        print(f"  INTRALEMMA pass (polyseme):  "
              f"{stats['n_intralemma_passing']:,}/{poly:,}  "
              f"({100*stats['n_intralemma_passing']/poly:.2f}% of polysemes)")
    print(f"  monosemes (auto-pass):    {stats['n_intralemma_monoseme']:,}")
    if has_clusters:
        print(f"  CLUSTER pass (full lex):  {stats['n_cluster_passing']:,}  "
              f"({100*stats['n_cluster_passing']/n:.2f}%)")
    else:
        print(f"  CLUSTER pass:             SKIPPED (run Stage 9/10 first)")
    print()
    print("  self-rank histogram (full-lexicon top-K):")
    for key in ["1", "2-5", "6-10", "11+", "miss"]:
        print(f"    {key:>6}: {stats['rank_hist'][key]:,}")
    print()
    print(f"  audit_run_id: {args.audit_run_id}")
    print("=" * 64)
    print()
    print("READING THE NUMBERS")
    print("-" * 64)
    print("  STRICT pass models cross-language retrieval (Part 7.5):")
    print("    the production query is a foreign-language token with no")
    print("    lemma overlap; this is the strictest test.")
    print()
    print("  INTRALEMMA pass models grounding mode (Part 7.4):")
    print("    the lemma is known; the test is 'can my embedding pick the")
    print("    right sense among lemma-mates?'. THIS IS THE DOMINANT")
    print("    INTRA-LANGUAGE PRODUCTION CRITERION.")
    print()
    print("  TOP-K pass is a relaxed cross-language criterion: 'did I land")
    print("    in the right neighborhood, even if not exactly self?'")
    print()
    print("  CLUSTER pass models snap-to-standard policy (Part 7.2):")
    print("    'top-1 is self OR a content-identical sibling.' Only")
    print("    meaningful after Stage 9/10 build clusters.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
