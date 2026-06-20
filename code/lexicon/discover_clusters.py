#!/usr/bin/env python3
"""
discover_clusters.py -- Stage 9 -- cluster discovery

For senses that ARE NOT already members of any content_identical_group
(at audience_tier='general'), find the embedding-space cluster of
strongly-related senses and propose them as a candidate content-
identical group. Standard-form selection happens in Stage 10
(select_standard_forms.py).

WHY THIS EXISTS
---------------
The improver (Stage 6) declares content-identical pairs for the
in-scope, high-frequency vocabulary. Many words outside that scope
still have content-identical relatives in the lexicon -- this stage
discovers them at scale using the production embedding (bge-large).

ALGORITHM
---------
Walk seeds in descending frequency order (Part 14 frontier strategy).
For each unassigned seed sense:
  1. Find top-K nearest neighbors by cosine.
  2. Filter to neighbors above STRONG_THRESHOLD (default 0.92).
  3. Apply metadata-coherence guards:
       - same pos_simple
       - same lemma is rejected (lemma-mates are NOT cousins)
       - require microgloss-token overlap above min-token-overlap
  4. Confirm the cluster's centroid coherence: max distance from
     centroid to any member <= COHERENCE_THRESHOLD (default 0.15
     measured as 1 - cosine).
  5. Open a candidate content_identical_group at audience_tier=
     'general', add the seed + all qualifying neighbors as members
     (add_method='cluster_discovery_v3', selection_method left null
     for Stage 10 to fill).

PERFORMANCE
-----------
The top-K nearest-neighbor lookup is the inner loop. For each seed,
we compute that seed's similarity to all N senses. Naively this is
O(N) per seed and O(N * |seeds|) overall. We BATCH the queries: B
seed rows times the (N x D) embedding matrix gives a (B x N)
similarity matrix in one BLAS call. The argpartition step then
extracts top-K per row. This converts a Python-loop-bound inner
kernel into a BLAS-bound one -- roughly 1000x faster on a CPU.

Above ~200K senses, swap in FAISS; only the batched-topk call site
needs to change.

The previous version of this script iterated all vectors in pure
Python for every seed. At 1.7M senses that would never finish; even at
72K it was slow enough to be unusable. The fix is implementation,
not algorithm.

RESUMABILITY
------------
After processing each seed, write a row to cluster_discovery_progress.
A resume run skips seeds already in that table for the same
discovery_run_id.

MANY-TO-MANY MEMBERSHIP
-----------------------
A sense may be in multiple groups across different audience_tiers.
Within a single audience_tier, a sense is in at most ONE group. The
discovery stage only writes 'general' tier; specialty groups are
declared explicitly via the improver.

USAGE
-----
    python discover_clusters.py --target sgf_lexicon.db \\
        --embedding-method bge-large-en-v1 \\
        [--strong-threshold 0.92] [--coherence-threshold 0.15] \\
        [--top-k 20] [--limit-seeds 50000] \\
        [--batch-size 512] [--discovery-run-id MY_RUN]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np


STRONG_THRESHOLD_DEFAULT = 0.92
COHERENCE_THRESHOLD_DEFAULT = 0.15
TOP_K_DEFAULT = 20
BATCH_SIZE_DEFAULT = 256


def microgloss_token_overlap(mg_a, mg_b):
    if not mg_a or not mg_b:
        return 0
    a = set((mg_a or "").split("_"))
    b = set((mg_b or "").split("_"))
    if not a or not b:
        return 0
    return len(a & b) / min(len(a), len(b))


def load_population(conn, embedding_method):
    """Load embeddings + metadata into NumPy arrays.

    Returns:
        wsids   : (N,) int64
        lemmas  : (N,) object array of strings
        poses   : (N,) object array of strings
        mgs     : (N,) object array of strings
        cids    : (N,) object array of strings
        vecs    : (N, D) float32, L2-normalized
    """
    print()
    print("Loading embeddings ...")
    t_load = time.time()
    cur = conn.execute(
        """
        SELECT sl.wiktionary_source_id, sl.lemma, sl.pos_simple,
               sl.microgloss, sl.canonical_id, se.embed
          FROM sense_embedding se
          JOIN sgf_lexicon sl
            ON sl.wiktionary_source_id = se.wiktionary_source_id
         WHERE se.embedding_method = ?
           AND se.embed IS NOT NULL
           AND sl.canonical_id IS NOT NULL
        """,
        (embedding_method,),
    )
    wsids_l, lemmas_l, poses_l, mgs_l, cids_l, blobs = [], [], [], [], [], []
    expected_dim = None
    for w, lm, ps, mg, cid, blob in cur:
        if blob is None:
            continue
        n = len(blob) // 4
        if expected_dim is None:
            expected_dim = n
        if n != expected_dim:
            continue
        wsids_l.append(w)
        lemmas_l.append(lm or "")
        poses_l.append(ps or "")
        mgs_l.append(mg or "")
        cids_l.append(cid)
        blobs.append(blob)

    N = len(wsids_l)
    if N == 0:
        return None

    D = expected_dim
    vecs = np.empty((N, D), dtype=np.float32)
    for i, blob in enumerate(blobs):
        vecs[i] = np.frombuffer(blob, dtype="<f4", count=D)
    # Normalize defensively.
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    vecs = vecs / norms

    wsids = np.array(wsids_l, dtype=np.int64)
    lemmas = np.array(lemmas_l, dtype=object)
    poses = np.array(poses_l, dtype=object)
    mgs = np.array(mgs_l, dtype=object)
    cids = np.array(cids_l, dtype=object)
    print(f"  Loaded {N:,} senses (dim={D}) in {time.time()-t_load:.1f}s")
    return wsids, lemmas, poses, mgs, cids, vecs


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", default="sgf_lexicon.db")
    p.add_argument("--embedding-method", required=True)
    p.add_argument("--strong-threshold", type=float, default=STRONG_THRESHOLD_DEFAULT)
    p.add_argument("--coherence-threshold", type=float,
                   default=COHERENCE_THRESHOLD_DEFAULT,
                   help="Max (1 - cosine) from centroid to any member")
    p.add_argument("--top-k", type=int, default=TOP_K_DEFAULT)
    p.add_argument("--min-token-overlap", type=float, default=0.2,
                   help="Minimum microgloss-token overlap fraction to accept")
    p.add_argument("--limit-seeds", type=int, default=None,
                   help="Process at most N seed senses")
    p.add_argument("--batch-size", type=int, default=BATCH_SIZE_DEFAULT,
                   help="Number of seeds per matmul batch")
    p.add_argument("--discovery-run-id", default=None)
    p.add_argument("--dry-run", action="store_true",
                   help="Don't write content_identical_group rows")
    args = p.parse_args()

    if args.discovery_run_id is None:
        args.discovery_run_id = f"cluster_discovery_{int(time.time())}"

    db_path = Path(args.target)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 60000")

    if not conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='cluster_discovery_progress'"
    ).fetchone():
        print(
            "ERROR: cluster_discovery_progress table missing. "
            "Run: python apply_schema.py",
            file=sys.stderr,
        )
        return 1

    print(f"Target:               {db_path.resolve()}")
    print(f"Embedding method:     {args.embedding_method}")
    print(f"Strong threshold:     {args.strong_threshold:.3f}")
    print(f"Coherence threshold:  {args.coherence_threshold:.3f}")
    print(f"Top-K:                {args.top_k}")
    print(f"Batch size:           {args.batch_size}")
    print(f"Discovery run id:     {args.discovery_run_id}")

    loaded = load_population(conn, args.embedding_method)
    if loaded is None:
        print("Nothing to do.", file=sys.stderr)
        return 1
    wsids, lemmas, poses, mgs, cids, vecs = loaded
    N = len(wsids)

    # Frequency order (highest first)
    print("Sorting seeds by frequency ...")
    try:
        freq = {}
        for r in conn.execute("SELECT lemma, frequency_rank FROM lemma_frequency"):
            freq[r[0]] = r[1] or 10**9
    except sqlite3.OperationalError:
        freq = {}
    order = sorted(range(N), key=lambda i: freq.get(lemmas[i].lower(), 10**9))

    already_done = set(
        r[0] for r in conn.execute(
            "SELECT wsid FROM cluster_discovery_progress WHERE discovery_run_id = ?",
            (args.discovery_run_id,),
        )
    )
    print(f"  Skipping {len(already_done):,} seeds already processed in this run.")

    print("Computing membership map ...")
    in_general_group = set(
        r[0] for r in conn.execute(
            """
            SELECT cim.wsid
              FROM content_identical_member cim
              JOIN content_identical_group cig
                ON cig.group_id = cim.group_id
             WHERE cig.audience_tier = 'general'
            """
        )
    )
    print(f"  {len(in_general_group):,} senses already in a general-tier group.")

    # wsid -> row index map for fast lookup during dynamic skipping
    wsid_to_idx = {int(w): i for i, w in enumerate(wsids)}

    seed_idxs = [
        i for i in order
        if int(wsids[i]) not in already_done and int(wsids[i]) not in in_general_group
    ]
    if args.limit_seeds is not None:
        seed_idxs = seed_idxs[: args.limit_seeds]
    print(f"  {len(seed_idxs):,} seeds to process.")

    n_clusters = 0
    n_members_added = 0
    n_singleton = 0
    t0 = time.time()

    seed_arr = np.array(seed_idxs, dtype=np.int64)
    K = max(args.top_k, 2)

    for batch_start in range(0, len(seed_arr), args.batch_size):
        batch_end = min(batch_start + args.batch_size, len(seed_arr))
        batch_idxs = seed_arr[batch_start:batch_end]
        # Skip seeds that got swept into someone else's cluster during a
        # prior batch in this run.
        active_mask = np.array(
            [int(wsids[i]) not in in_general_group for i in batch_idxs],
            dtype=bool,
        )
        if not active_mask.any():
            continue
        active_idxs = batch_idxs[active_mask]

        Q = vecs[active_idxs]                          # (B, D)
        sims = Q @ vecs.T                              # (B, N)
        # zero out self by setting diagonal-equivalent to -inf
        for b, src_i in enumerate(active_idxs):
            sims[b, src_i] = -np.inf
        # top-K
        part_idx = np.argpartition(-sims, kth=K-1, axis=1)[:, :K]
        row_arange = np.arange(part_idx.shape[0])[:, None]
        part_sims = sims[row_arange, part_idx]
        order_in_topk = np.argsort(-part_sims, axis=1)
        topk_idx = part_idx[row_arange, order_in_topk]
        topk_sims = part_sims[row_arange, order_in_topk]

        # Per-seed processing
        for b, src_i in enumerate(active_idxs):
            src_i = int(src_i)
            seed_wsid = int(wsids[src_i])

            # If a prior seed in this batch swept this seed into a
            # cluster (rare but possible), skip.
            if seed_wsid in in_general_group:
                conn.execute(
                    "INSERT OR IGNORE INTO cluster_discovery_progress "
                    "(wsid, processed_at, discovery_run_id, cluster_count) "
                    "VALUES (?, ?, ?, 0)",
                    (seed_wsid, int(time.time()), args.discovery_run_id),
                )
                continue

            cand_indices = topk_idx[b]
            cand_sims = topk_sims[b]

            # Filter candidates
            filtered = []
            for ci, cos in zip(cand_indices, cand_sims):
                ci = int(ci)
                cos = float(cos)
                if cos < args.strong_threshold:
                    continue
                if poses[ci] != poses[src_i]:
                    continue
                if lemmas[ci].lower() == lemmas[src_i].lower():
                    continue   # lemma-mate, not a cousin
                if int(wsids[ci]) in in_general_group:
                    continue
                overlap = microgloss_token_overlap(mgs[src_i], mgs[ci])
                if overlap < args.min_token_overlap:
                    continue
                filtered.append((ci, cos))

            if not filtered:
                n_singleton += 1
                _mark_singleton(conn, seed_wsid, args.discovery_run_id)
                continue

            # Coherence test: centroid of (seed + filtered)
            member_idxs = [src_i] + [ci for ci, _ in filtered]
            member_vecs = vecs[np.array(member_idxs, dtype=np.int64)]
            c = member_vecs.mean(axis=0)
            cnorm = np.linalg.norm(c)
            if cnorm > 0:
                c = c / cnorm
            # distance from each member to centroid
            mem_dists = 1.0 - (member_vecs @ c)
            coherent = [
                member_idxs[k] for k in range(len(member_idxs))
                if mem_dists[k] <= args.coherence_threshold
            ]
            if len(coherent) < 2:
                n_singleton += 1
                _mark_singleton(conn, seed_wsid, args.discovery_run_id)
                continue

            # Final centroid + max distance on coherent subset
            final_vecs = vecs[np.array(coherent, dtype=np.int64)]
            fc = final_vecs.mean(axis=0)
            fcnorm = np.linalg.norm(fc)
            if fcnorm > 0:
                fc = fc / fcnorm
            final_dists = 1.0 - (final_vecs @ fc)
            max_dist = float(final_dists.max())

            if args.dry_run:
                print(
                    f"  [dry] seed={lemmas[src_i]!r}/{mgs[src_i]!r} "
                    f"+ {len(coherent)-1} member(s) "
                    f"(max_dist={max_dist:.4f})"
                )
                continue

            now = int(time.time())
            cur_ins = conn.execute(
                """
                INSERT INTO content_identical_group (
                    audience_tier, selection_method, centroid_distance,
                    rationale, discovered_at
                ) VALUES ('general', NULL, ?, ?, ?)
                """,
                (
                    max_dist,
                    f"cluster_discovery_v3 seed={cids[src_i]}",
                    now,
                ),
            )
            gid = cur_ins.lastrowid

            for k, mi in enumerate(coherent):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO content_identical_member (
                        group_id, wsid, added_at, add_method, confidence
                    ) VALUES (?, ?, ?, 'cluster_discovery_v3', ?)
                    """,
                    (gid, int(wsids[mi]), now,
                     round(float(1.0 - final_dists[k]), 4)),
                )
                in_general_group.add(int(wsids[mi]))
                conn.execute(
                    """
                    UPDATE sgf_lexicon
                       SET maturity_tier = 'clustered'
                     WHERE wiktionary_source_id = ?
                       AND maturity_tier IN ('raw','provisional','embedded_v1',
                                             'improved','embedded_v2')
                    """,
                    (int(wsids[mi]),),
                )

            n_clusters += 1
            n_members_added += len(coherent)

            conn.execute(
                "INSERT OR IGNORE INTO cluster_discovery_progress "
                "(wsid, processed_at, discovery_run_id, cluster_count) "
                "VALUES (?, ?, ?, ?)",
                (seed_wsid, now, args.discovery_run_id, 1),
            )

        # commit + progress per batch
        conn.commit()
        elapsed = time.time() - t0
        done = batch_end
        rate = done / max(elapsed, 0.001)
        remain = (len(seed_arr) - done) / max(rate, 0.001)
        print(
            f"  [{done:,}/{len(seed_arr):,}] "
            f"clusters={n_clusters:,} "
            f"members={n_members_added:,} "
            f"singletons={n_singleton:,}  "
            f"{rate:.0f}/s  eta={remain/60:.1f}m"
        )
    conn.commit()

    print()
    print("=" * 60)
    print("CLUSTER DISCOVERY COMPLETE")
    print("=" * 60)
    print(f"  seeds processed:     {len(seed_arr):,}")
    print(f"  clusters created:    {n_clusters:,}")
    print(f"  members added:       {n_members_added:,}")
    print(f"  singletons:          {n_singleton:,}")
    print(f"  discovery_run_id:    {args.discovery_run_id}")
    print(f"  elapsed:             {(time.time()-t0)/60:.1f} min")
    print()
    print("Next: python select_standard_forms.py "
          f"--target {db_path.name} --llm-wrapper <wrapper>")
    return 0


def _mark_singleton(conn, seed_wsid, discovery_run_id):
    """Record a seed as processed-with-no-cluster and advance its tier."""
    conn.execute(
        "INSERT OR IGNORE INTO cluster_discovery_progress "
        "(wsid, processed_at, discovery_run_id, cluster_count) "
        "VALUES (?, ?, ?, 0)",
        (seed_wsid, int(time.time()), discovery_run_id),
    )
    conn.execute(
        """
        UPDATE sgf_lexicon
           SET maturity_tier = 'clustered'
         WHERE wiktionary_source_id = ?
           AND maturity_tier IN ('raw','provisional','embedded_v1',
                                 'improved','embedded_v2')
        """,
        (seed_wsid,),
    )


if __name__ == "__main__":
    sys.exit(main())
