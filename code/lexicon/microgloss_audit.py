"""microgloss_audit.py -- the two-test audit for a microgloss candidate.

T1: lemma-filtered top-K. Embed the candidate microgloss, search
    *within the lemma's senses only*, check that the right wsid lands
    in the top-K (where K depends on the polysemy tier).

T2: lemma-free in-cluster rank. Embed the same candidate, search the
    full lexicon, then filter results to the wsid's "close cousin"
    cluster, check that the right wsid lands in the top-K within that
    cluster (or in the top quartile, for high-polyseme lemmas).

The cluster is built once per (wsid, embedder) and cached. The cluster
*always includes the lemma's other senses first* (those are the
disambiguation targets that matter most), then expands to Wiktionary-
declared synonyms, hypernyms, hyponyms, related, coordinate_terms, up
to the tier's cluster cap. Members are ranked by embedding cosine to
the candidate, so the test focuses on "can you separate from your
closest competitors" rather than "can you beat 200 distant cousins".

Pure functions over a passed lexicon_ctx + audit_thresholds. The DB
helpers are intentionally small and import-free of FastAPI/server code
so the module can be unit-tested without the full pipeline.
"""

import json
import sqlite3

import polysemy_tier as pt


# ---------------------------------------------------------------------------
# Cluster construction
# ---------------------------------------------------------------------------

# Linkage types we pull from wiktionary_source.linkages_json when
# building the close-cousin cluster. Order matters for the seed-side
# ordering (synonyms first, then coords, then hypernyms, then
# hyponyms/related). After seeding we re-rank by cosine, so the order
# is just a tie-breaker for which surface forms get LOOKED UP first
# when many are available.
_LINKAGE_TYPES_FOR_CLUSTER = (
    "synonyms", "coordinate_terms", "hypernyms", "hyponyms", "related",
)


def build_close_cousin_cluster(conn, lexicon_ctx, wsid, embedder, cap):
    """Build the close-cousin cluster for `wsid`.

    Returns: list of wsids (excluding `wsid` itself), length <= cap.

    Strategy:
        1. Start with the lemma's other senses (lemma-mates).
        2. Add Wiktionary-declared linkage targets that resolve to a
           wsid in the lexicon. Lookup is by lemma + (optionally) the
           same pos_simple.
        3. De-duplicate.
        4. If the candidate pool is larger than `cap`, rank by cosine
           similarity to `wsid`'s own vector and keep the top `cap`.
        5. If smaller than `cap`, return what we have (don't pad with
           noise; an under-filled cluster is honest and the audit will
           still work).

    The audit uses the *candidate microgloss* (not wsid's stored
    vector) to re-rank inside this cluster, but for cluster
    *membership* we use wsid's stored vector so the membership is
    stable across audit attempts.
    """
    senses = lexicon_ctx["senses"]
    if wsid not in senses:
        return []

    sense = senses[wsid]
    lemma = sense["lemma"]
    pos = sense["pos_simple"]
    lemma_index = lexicon_ctx["lemma_index"]

    # Seed: other senses of this lemma (same lemma, any pos). These are
    # what the lemma-filtered T1 test already covers, but T2 needs them
    # too because the right sense should beat its own lemma-mates on a
    # lemma-free query.
    candidate_set = set()
    for w in lemma_index.get(lemma.lower(), []):
        if w != wsid:
            candidate_set.add(w)

    # Expand: pull linkage targets from wiktionary_source for this wsid.
    try:
        row = conn.execute(
            "SELECT linkages_json FROM wiktionary_source "
            "WHERE source_sense_id = ?", (wsid,)
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    if row and row[0]:
        try:
            parsed = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            parsed = []
        if isinstance(parsed, list):
            wanted = set(_LINKAGE_TYPES_FOR_CLUSTER)
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                t = item.get("type") or item.get("linkage_type")
                if t not in wanted:
                    continue
                w_lemma = (item.get("word") or "").strip().lower()
                if not w_lemma:
                    continue
                for w in lemma_index.get(w_lemma, []):
                    if w == wsid:
                        continue
                    candidate_set.add(w)

    candidates = list(candidate_set)
    if len(candidates) <= cap:
        return candidates

    # Too many candidates -- rank by cosine to wsid's own vector and
    # keep the closest `cap`. This is the "close-cousin" part: we want
    # the candidates that look most like the right sense, because they
    # are the ones that most threaten to outrank it on a lemma-free
    # query.
    emb = lexicon_ctx["embedders"].get(embedder)
    if emb is None:
        return candidates[:cap]
    wsid_to_idx = emb["wsid_to_idx"]
    if wsid not in wsid_to_idx:
        return candidates[:cap]
    import numpy as np
    self_vec = emb["vectors"][wsid_to_idx[wsid]]
    scored = []
    for w in candidates:
        idx = wsid_to_idx.get(w)
        if idx is None:
            continue
        sim = float(emb["vectors"][idx] @ self_vec)
        scored.append((sim, w))
    scored.sort(reverse=True)
    return [w for _, w in scored[:cap]]


# ---------------------------------------------------------------------------
# T1 audit: lemma-filtered top-K
# ---------------------------------------------------------------------------

def audit_t1(lexicon_ctx, candidate_text, wsid, embedder, thresholds,
             embed_fn=None):
    """Lemma-filtered top-K audit.

    Embeds `candidate_text`, runs a lemma-restricted top-K, and reports
    where `wsid` landed.

    Returns dict:
        passed       : bool
        rank         : 1-indexed rank of wsid within lemma-filtered top-K,
                       or None if wsid was not in the top-K considered
        margin       : score(top-1) - score(top-2), or None if N < 2
        top_score    : score of the top-1 candidate, or None
        n_candidates : how many lemma-mates were in scope

    `embed_fn` is an optional override; if None, lexicon_search.embed_text
    is used. The override makes this testable without ONNX runtime.
    """
    import lexicon_search as ls
    senses = lexicon_ctx["senses"]
    if wsid not in senses:
        return {"passed": False, "rank": None, "margin": None,
                "top_score": None, "n_candidates": 0}
    sense = senses[wsid]
    lemma = sense["lemma"]

    # How many senses share this lemma? That's the universe T1 ranks in.
    lemma_mates = lexicon_ctx["lemma_index"].get(lemma.lower(), [])
    n_candidates = len(lemma_mates)
    if n_candidates == 0:
        return {"passed": False, "rank": None, "margin": None,
                "top_score": None, "n_candidates": 0}

    # Embed the candidate.
    if embed_fn is None:
        embed_fn = lambda t: ls.embed_text(t, embedder)  # noqa: E731
    qv = embed_fn(candidate_text)

    # K = number of lemma-mates (so we always learn rank of wsid).
    results = ls.topk(lexicon_ctx, qv, embedder, k=n_candidates,
                      lemma_restrict=lemma)
    if not results:
        return {"passed": False, "rank": None, "margin": None,
                "top_score": None, "n_candidates": n_candidates}

    # Find wsid's rank.
    rank = None
    for i, (w, _score) in enumerate(results):
        if w == wsid:
            rank = i + 1
            break
    top_score = float(results[0][1])
    margin = (float(results[0][1]) - float(results[1][1])
              if len(results) >= 2 else None)

    max_rank = int(thresholds.get("t1_max_rank", 1))
    passed = rank is not None and rank <= max_rank

    return {"passed": passed, "rank": rank, "margin": margin,
            "top_score": top_score, "n_candidates": n_candidates}


# ---------------------------------------------------------------------------
# T2 audit: lemma-free, in-cluster rank
# ---------------------------------------------------------------------------

def audit_t2(lexicon_ctx, candidate_text, wsid, embedder, thresholds,
             cluster_wsids, embed_fn=None, top_k_full=200):
    """Lemma-free in-cluster rank audit.

    Embeds `candidate_text`, runs a top-K lemma-free search (K=top_k_full),
    filters to (wsid + cluster_wsids), and reports where wsid landed
    inside that filtered set.

    Returns dict:
        passed       : bool
        rank         : 1-indexed rank of wsid within the cluster
        cluster_size : len(cluster_wsids) + 1 (the +1 is wsid itself)
        quantile     : 0.0 = best (rank 1), 1.0 = worst (rank == cluster_size)
        score        : the cosine score wsid achieved

    A candidate "passes" if EITHER:
        - rank <= t2_max_rank, OR
        - quantile <= t2_max_quantile (when configured), OR
        - the rank threshold is None (some tiers only gate on quantile)
    AND the wsid's score is >= t2_score_floor (when configured).
    """
    import lexicon_search as ls
    senses = lexicon_ctx["senses"]
    if wsid not in senses:
        return {"passed": False, "rank": None, "cluster_size": 0,
                "quantile": None, "score": None}

    cluster = list(cluster_wsids)
    if wsid not in cluster:
        cluster = cluster + [wsid]
    cluster_set = set(cluster)
    cluster_size = len(cluster_set)

    if embed_fn is None:
        embed_fn = lambda t: ls.embed_text(t, embedder)  # noqa: E731
    qv = embed_fn(candidate_text)

    results = ls.topk(lexicon_ctx, qv, embedder, k=top_k_full,
                      lemma_restrict=None)
    # Filter to cluster, preserving global rank order.
    cluster_results = [(w, s) for (w, s) in results if w in cluster_set]

    # If some cluster members did not appear in the global top-K (their
    # score was below the K-th result), append them at the tail in
    # arbitrary order. They count as "below the visible top" for the
    # purpose of rank, which is the conservative call.
    seen = {w for (w, _) in cluster_results}
    for w in cluster:
        if w not in seen:
            cluster_results.append((w, None))

    rank = None
    score = None
    for i, (w, s) in enumerate(cluster_results):
        if w == wsid:
            rank = i + 1
            score = s
            break

    if rank is None:
        return {"passed": False, "rank": None,
                "cluster_size": cluster_size, "quantile": None,
                "score": None}

    # Quantile: 0.0 if rank == 1, 1.0 if rank == cluster_size. Guard
    # against div-by-zero when cluster has 1 element (only wsid itself).
    if cluster_size <= 1:
        quantile = 0.0
    else:
        quantile = (rank - 1) / (cluster_size - 1)

    # Pass logic: at least one of the rank/quantile gates must pass,
    # AND the score floor (if set) must be met.
    max_rank = thresholds.get("t2_max_rank")
    max_quantile = thresholds.get("t2_max_quantile")
    score_floor = float(thresholds.get("t2_score_floor", 0.0) or 0.0)

    pass_by_rank = max_rank is not None and rank <= int(max_rank)
    pass_by_quantile = (max_quantile is not None
                        and quantile <= float(max_quantile))
    rank_or_quantile_ok = pass_by_rank or pass_by_quantile
    score_ok = (score_floor <= 0.0
                or (score is not None and score >= score_floor))

    passed = rank_or_quantile_ok and score_ok

    return {"passed": passed, "rank": rank, "cluster_size": cluster_size,
            "quantile": quantile, "score": score}


# ---------------------------------------------------------------------------
# Combined audit: T1 + T2 for a single candidate
# ---------------------------------------------------------------------------

def audit_candidate(conn, lexicon_ctx, candidate_text, wsid, embedder,
                    polysemy_n, embed_fn=None, cluster_cache=None):
    """Run T1 + T2 audit on `candidate_text` for `wsid`.

    Returns dict combining T1 and T2 outputs with a top-level pass flag.

    `cluster_cache` is an optional dict {wsid: [cluster_wsids]} used to
    avoid rebuilding the cluster across multiple candidate attempts for
    the same wsid. The cluster does not depend on the candidate text,
    so the cache hit rate per wsid equals the number of strategies the
    tournament tries before terminating.
    """
    tier = pt.classify_polysemy(polysemy_n)
    thresholds = pt.audit_thresholds_for_tier(tier)
    cap = pt.cluster_cap_for_tier(tier)

    if cluster_cache is not None and wsid in cluster_cache:
        cluster = cluster_cache[wsid]
    else:
        cluster = build_close_cousin_cluster(
            conn, lexicon_ctx, wsid, embedder, cap)
        if cluster_cache is not None:
            cluster_cache[wsid] = cluster

    t1 = audit_t1(lexicon_ctx, candidate_text, wsid, embedder,
                  thresholds, embed_fn=embed_fn)
    t2 = audit_t2(lexicon_ctx, candidate_text, wsid, embedder,
                  thresholds, cluster, embed_fn=embed_fn)

    return {
        "polysemy_tier":  tier,
        "polysemy_n":     int(polysemy_n),
        "cluster_size":   t2["cluster_size"],
        "t1_passed":      bool(t1["passed"]),
        "t1_rank":        t1["rank"],
        "t1_margin":      t1["margin"],
        "t1_top_score":   t1["top_score"],
        "t1_n":           t1["n_candidates"],
        "t2_passed":      bool(t2["passed"]),
        "t2_rank":        t2["rank"],
        "t2_quantile":    t2["quantile"],
        "t2_score":       t2["score"],
        "passed":         bool(t1["passed"] and t2["passed"]),
        "thresholds":     thresholds,
    }
