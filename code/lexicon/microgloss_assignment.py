"""microgloss_assignment.py -- tournament scoring + DB read/write.

The tournament:
    Each candidate microgloss for a given wsid runs through audit_candidate.
    Score formula:
        score = m1 + 0.5 * m2 - 0.02 * token_count
    where:
        m1 = T1 margin (top-1 score minus top-2 score in lemma-filtered)
        m2 = T2 margin (top-1 cluster score minus top-2 cluster score)
        token_count = how many underscore-separated tokens are in the
                      candidate. Shorter wins ties.

Hard floors that any winner must satisfy:
    m1 >= 0.04 OR t1_passed (the threshold check is the real gate; the
                            margin floor is a sanity check on noisy ties)
    m2 >= 0.02 OR t2_passed

Preferred-threshold fast path (skips remaining strategies if hit):
    m1 >= 0.10 AND m2 >= 0.05

DB writes:
    On commit, we INSERT a new row into microgloss_assignment with
    superseded_by = NULL. If a prior current row exists for this wsid,
    we set its superseded_by to the new row's assignment_id in the same
    transaction. The current sgf_lexicon.microgloss field is also
    updated to the new value (so search keeps working without a
    separate join).
"""

import json
import sqlite3
import time


# ---------------------------------------------------------------------------
# Tournament scoring
# ---------------------------------------------------------------------------

TOKEN_PENALTY = 0.02
HARD_FLOOR_M1 = 0.04
HARD_FLOOR_M2 = 0.02
PREFERRED_M1 = 0.10
PREFERRED_M2 = 0.05


def _token_count(microgloss):
    if not microgloss:
        return 0
    return len([t for t in str(microgloss).split("_") if t])


def _t2_margin(audit_result):
    """Estimate the T2 margin. We don't have direct access to the second-
    best score in the audit result; approximate it from rank + score.
    A first-place candidate (rank 1) with a known score gets credit for
    the full score; lower ranks get 0 (we cannot reward them).
    """
    rank = audit_result.get("t2_rank")
    score = audit_result.get("t2_score")
    if rank is None or score is None:
        return 0.0
    if rank == 1:
        return float(score)
    # Penalize by rank: rank 2 gets half credit, rank 3 a third, etc.
    return float(score) / float(rank)


def score_candidate(microgloss, audit_result):
    """Compute the tournament score for one candidate.

    The score is what the tournament SORTS BY; it is not the pass/fail
    gate. A candidate with score 0.0 can still win the tournament if
    it is the only one that passed the audit. Conversely, a high-
    scoring candidate that did not pass the audit cannot win.
    """
    m1 = float(audit_result.get("t1_margin") or 0.0)
    m2 = _t2_margin(audit_result)
    tokens = _token_count(microgloss)
    return m1 + 0.5 * m2 - TOKEN_PENALTY * tokens


def _candidate_meets_hard_floors(audit_result):
    """Any winner must clear the noisy-tie sanity floors OR have
    passed the formal audit threshold (which is stricter)."""
    m1_ok = (audit_result.get("t1_passed")
             or (audit_result.get("t1_margin") or 0.0) >= HARD_FLOOR_M1)
    m2_ok = (audit_result.get("t2_passed")
             or _t2_margin(audit_result) >= HARD_FLOOR_M2)
    return m1_ok and m2_ok


def _is_preferred(audit_result):
    """Preferred fast-path threshold: stop trying more strategies if hit."""
    return ((audit_result.get("t1_margin") or 0.0) >= PREFERRED_M1
            and _t2_margin(audit_result) >= PREFERRED_M2)


def tournament(conn, lexicon_ctx, sense_context, wsid, embedder,
               polysemy_n, strategies, audit_fn, embed_fn=None,
               cluster_cache=None, stop_at_first_preferred=True):
    """Run every strategy's candidates through the audit, return the
    full tournament record.

    Arguments:
        strategies : iterable of (strategy_name, generator_fn)
        audit_fn   : callable(candidate_text, wsid) -> audit_result dict.
                     Pass microgloss_audit.audit_candidate bound with the
                     conn/lexicon_ctx/embedder/polysemy_n params, or a
                     test stub.
        stop_at_first_preferred : if True, terminate the tournament as
                     soon as a candidate hits the preferred-threshold
                     fast-path. Saves audit calls on easy senses.

    Returns dict:
        winner       : {strategy, microgloss, audit, score} or None
        candidates   : list of all attempted [{strategy, microgloss, audit, score}]
        n_strategies_tried : how many strategies produced a candidate that
                             was audited (not just the registry length)
    """
    all_results = []
    best = None
    n_strategies_tried = 0
    for strategy_name, gen_fn in strategies:
        candidates = gen_fn(sense_context)
        if not candidates:
            continue
        n_strategies_tried += 1
        for cand in candidates:
            audit_result = audit_fn(cand, wsid)
            score = score_candidate(cand, audit_result)
            rec = {
                "strategy":   strategy_name,
                "microgloss": cand,
                "audit":      audit_result,
                "score":      score,
            }
            all_results.append(rec)
            # Winner must pass audit AND clear hard floors AND score
            # higher than current best.
            qualifies = (audit_result.get("passed")
                         and _candidate_meets_hard_floors(audit_result))
            if qualifies and (best is None or score > best["score"]):
                best = rec
        # Early termination on preferred threshold
        if (stop_at_first_preferred and best
                and _is_preferred(best["audit"])):
            break

    return {
        "winner":              best,
        "candidates":          all_results,
        "n_strategies_tried":  n_strategies_tried,
    }


# ---------------------------------------------------------------------------
# DB helpers: read + write microgloss_assignment
# ---------------------------------------------------------------------------

def ensure_assignment_schema(conn):
    """Create microgloss_assignment table + indexes if not present.

    Idempotent. Used by iterate_microglosses.py at startup so the user
    does not have to remember to re-run schema.sql.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS microgloss_assignment (
            assignment_id              INTEGER PRIMARY KEY AUTOINCREMENT,
            wsid                       INTEGER NOT NULL,
            microgloss                 TEXT    NOT NULL,
            strategy                   TEXT    NOT NULL,
            audit_t1_passed            INTEGER NOT NULL,
            audit_t1_rank              INTEGER,
            audit_t1_margin            REAL,
            audit_t2_passed            INTEGER NOT NULL,
            audit_t2_rank              INTEGER,
            audit_t2_cluster_size      INTEGER,
            audit_t2_quantile          REAL,
            polysemy_tier              TEXT,
            tournament_candidates_json TEXT,
            n_strategies_tried         INTEGER,
            assigned_at                INTEGER NOT NULL,
            embedder_at_assignment     TEXT,
            superseded_by              INTEGER,
            FOREIGN KEY (superseded_by)
                REFERENCES microgloss_assignment(assignment_id)
        );
        CREATE INDEX IF NOT EXISTS idx_ma_wsid
            ON microgloss_assignment(wsid);
        CREATE INDEX IF NOT EXISTS idx_ma_current
            ON microgloss_assignment(wsid)
            WHERE superseded_by IS NULL;
        CREATE INDEX IF NOT EXISTS idx_ma_strategy
            ON microgloss_assignment(strategy);
        CREATE INDEX IF NOT EXISTS idx_ma_t1_passed
            ON microgloss_assignment(audit_t1_passed);
        CREATE INDEX IF NOT EXISTS idx_ma_t2_passed
            ON microgloss_assignment(audit_t2_passed);
        CREATE INDEX IF NOT EXISTS idx_ma_tier
            ON microgloss_assignment(polysemy_tier);
    """)


def get_current_assignment(conn, wsid):
    """Return the current (superseded_by IS NULL) assignment row for wsid,
    or None if none exists."""
    cur = conn.execute("""
        SELECT assignment_id, microgloss, strategy,
               audit_t1_passed, audit_t1_rank, audit_t1_margin,
               audit_t2_passed, audit_t2_rank, audit_t2_cluster_size,
               audit_t2_quantile, polysemy_tier,
               tournament_candidates_json, n_strategies_tried,
               assigned_at, embedder_at_assignment
          FROM microgloss_assignment
         WHERE wsid = ? AND superseded_by IS NULL
         ORDER BY assigned_at DESC LIMIT 1
    """, (wsid,))
    row = cur.fetchone()
    if not row:
        return None
    cols = ("assignment_id", "microgloss", "strategy",
            "audit_t1_passed", "audit_t1_rank", "audit_t1_margin",
            "audit_t2_passed", "audit_t2_rank", "audit_t2_cluster_size",
            "audit_t2_quantile", "polysemy_tier",
            "tournament_candidates_json", "n_strategies_tried",
            "assigned_at", "embedder_at_assignment")
    return dict(zip(cols, row))


def write_assignment(conn, wsid, winner, tournament_record, embedder,
                     update_sgf_lexicon=True):
    """Write a new assignment row for wsid; supersede any prior current row.

    `winner` is the tournament's winning {strategy, microgloss, audit, score}
    dict. If `winner` is None (tournament failed entirely), this raises
    ValueError -- the LLM fallback path handles that case separately.

    Returns the new assignment_id.
    """
    if winner is None:
        raise ValueError("write_assignment called with no winner; "
                         "use write_llm_fallback_assignment instead.")

    audit = winner["audit"]
    candidates_payload = json.dumps([
        {
            "strategy":     c["strategy"],
            "microgloss":   c["microgloss"],
            "t1_passed":    bool(c["audit"].get("t1_passed")),
            "t1_rank":      c["audit"].get("t1_rank"),
            "t1_margin":    c["audit"].get("t1_margin"),
            "t2_passed":    bool(c["audit"].get("t2_passed")),
            "t2_rank":      c["audit"].get("t2_rank"),
            "t2_quantile":  c["audit"].get("t2_quantile"),
            "score":        c["score"],
        }
        for c in tournament_record["candidates"]
    ], separators=(",", ":"))

    now_ts = int(time.time())
    # Begin a transaction so superseding-prior + inserting-new is atomic.
    cur = conn.cursor()
    cur.execute("BEGIN")
    try:
        cur.execute("""
            INSERT INTO microgloss_assignment
                (wsid, microgloss, strategy,
                 audit_t1_passed, audit_t1_rank, audit_t1_margin,
                 audit_t2_passed, audit_t2_rank, audit_t2_cluster_size,
                 audit_t2_quantile, polysemy_tier,
                 tournament_candidates_json, n_strategies_tried,
                 assigned_at, embedder_at_assignment, superseded_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """, (
            wsid,
            winner["microgloss"],
            winner["strategy"],
            1 if audit.get("t1_passed") else 0,
            audit.get("t1_rank"),
            audit.get("t1_margin"),
            1 if audit.get("t2_passed") else 0,
            audit.get("t2_rank"),
            audit.get("cluster_size"),
            audit.get("t2_quantile"),
            audit.get("polysemy_tier"),
            candidates_payload,
            tournament_record["n_strategies_tried"],
            now_ts,
            embedder,
        ))
        new_id = cur.lastrowid

        cur.execute("""
            UPDATE microgloss_assignment
               SET superseded_by = ?
             WHERE wsid = ? AND superseded_by IS NULL
               AND assignment_id != ?
        """, (new_id, wsid, new_id))

        if update_sgf_lexicon:
            cur.execute("""
                UPDATE sgf_lexicon
                   SET microgloss = ?,
                       updated_at = ?
                 WHERE wiktionary_source_id = ?
            """, (winner["microgloss"], now_ts, wsid))

        conn.commit()
        return new_id
    except Exception:
        conn.rollback()
        raise


def write_llm_fallback_assignment(conn, wsid, microgloss, audit_result,
                                  embedder, n_strategies_tried,
                                  update_sgf_lexicon=True):
    """Record an LLM-fallback assignment. Same shape as write_assignment
    but strategy is forced to 'llm_improver' and tournament_candidates_json
    is the (single-row) LLM record."""
    now_ts = int(time.time())
    payload = json.dumps([{
        "strategy":    "llm_improver",
        "microgloss":  microgloss,
        "t1_passed":   bool(audit_result.get("t1_passed")),
        "t1_rank":     audit_result.get("t1_rank"),
        "t1_margin":   audit_result.get("t1_margin"),
        "t2_passed":   bool(audit_result.get("t2_passed")),
        "t2_rank":     audit_result.get("t2_rank"),
        "t2_quantile": audit_result.get("t2_quantile"),
        "score":       None,
    }], separators=(",", ":"))

    cur = conn.cursor()
    cur.execute("BEGIN")
    try:
        cur.execute("""
            INSERT INTO microgloss_assignment
                (wsid, microgloss, strategy,
                 audit_t1_passed, audit_t1_rank, audit_t1_margin,
                 audit_t2_passed, audit_t2_rank, audit_t2_cluster_size,
                 audit_t2_quantile, polysemy_tier,
                 tournament_candidates_json, n_strategies_tried,
                 assigned_at, embedder_at_assignment, superseded_by)
            VALUES (?, ?, 'llm_improver',
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """, (
            wsid, microgloss,
            1 if audit_result.get("t1_passed") else 0,
            audit_result.get("t1_rank"),
            audit_result.get("t1_margin"),
            1 if audit_result.get("t2_passed") else 0,
            audit_result.get("t2_rank"),
            audit_result.get("cluster_size"),
            audit_result.get("t2_quantile"),
            audit_result.get("polysemy_tier"),
            payload,
            n_strategies_tried,
            now_ts,
            embedder,
        ))
        new_id = cur.lastrowid

        cur.execute("""
            UPDATE microgloss_assignment
               SET superseded_by = ?
             WHERE wsid = ? AND superseded_by IS NULL
               AND assignment_id != ?
        """, (new_id, wsid, new_id))

        if update_sgf_lexicon:
            cur.execute("""
                UPDATE sgf_lexicon
                   SET microgloss = ?,
                       updated_at = ?
                 WHERE wiktionary_source_id = ?
            """, (microgloss, now_ts, wsid))

        conn.commit()
        return new_id
    except Exception:
        conn.rollback()
        raise
