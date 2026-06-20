"""iterate_microglosses.py -- deterministic iterative microgloss generator.

The Bundle 2 entry point. For each in-scope sense:
    1. Load sense context (gloss, lemma-mates, linkages, examples, tags)
    2. Tournament: run 8 deterministic strategies, audit each, keep best
    3. If tournament finds a winner -> write assignment, done
    4. If no winner -> optionally fall back to LLM improver (if --llm-wrapper)

Scope selection (in priority order):
    --wsids               : explicit comma-separated wsids
    --wsids-file          : file of wsids, one per line
    --target-audit-failures : pull from quality_audit.intralemma_pass = 0
    --show-assignment WSID : diagnostic, no work performed
    (default)             : all senses missing a current assignment row

Modes:
    --dry-run        : pick first in-scope sense, print full tournament,
                       do not write to DB
    --revisit        : re-tournament senses that already have a current
                       assignment (use after embedder upgrade)
    --no-llm-fallback : skip the LLM step even when --llm-wrapper is set

Streaming output: one line per sense as it commits. Friendly progress
every ~2s for long runs.
"""

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import polysemy_tier as pt
import candidate_strategies as cs
import microgloss_audit as ma_audit
import microgloss_assignment as mga


HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Sense context loading
# ---------------------------------------------------------------------------

def _load_linkages(conn, wsid):
    """Return dict {synonyms, antonyms, hypernyms, hyponyms, related,
    coordinate_terms} for one wsid. Empty lists when absent."""
    out = {
        "synonyms": [], "antonyms": [], "hypernyms": [],
        "hyponyms": [], "related": [], "coordinate_terms": [],
    }
    try:
        row = conn.execute(
            "SELECT linkages_json FROM wiktionary_source "
            "WHERE source_sense_id = ?", (wsid,)
        ).fetchone()
    except sqlite3.OperationalError:
        return out
    if not row or not row[0]:
        return out
    try:
        parsed = json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return out
    if not isinstance(parsed, list):
        return out
    for item in parsed:
        if not isinstance(item, dict):
            continue
        t = item.get("type") or item.get("linkage_type")
        w = item.get("word")
        if t in out and w and w not in out[t]:
            out[t].append(w)
    return out


def _load_examples(conn, wsid):
    try:
        row = conn.execute(
            "SELECT examples_json FROM wiktionary_source "
            "WHERE source_sense_id = ?", (wsid,)
        ).fetchone()
    except sqlite3.OperationalError:
        return []
    if not row or not row[0]:
        return []
    try:
        parsed = json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return []
    out = []
    for ex in parsed:
        if isinstance(ex, str):
            out.append(ex.strip())
        elif isinstance(ex, dict) and ex.get("type") != "quotation":
            text = (ex.get("text") or ex.get("english") or "").strip()
            if text:
                out.append(text)
    return out


def _load_tags(conn, wsid):
    out = set()
    try:
        row = conn.execute(
            "SELECT tags_json, topics_json FROM wiktionary_source "
            "WHERE source_sense_id = ?", (wsid,)
        ).fetchone()
    except sqlite3.OperationalError:
        return []
    if not row:
        return []
    for blob in row:
        if not blob:
            continue
        try:
            arr = json.loads(blob)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(arr, list):
            for item in arr:
                if isinstance(item, str) and item.strip():
                    out.add(item.strip().lower())
    return sorted(out)


def load_sense_context(conn, wsid):
    """Assemble the full sense_context dict consumed by the strategies
    and the tournament."""
    row = conn.execute("""
        SELECT lemma, pos_simple, gloss, microgloss, canonical_id,
               register, temporal_status, social_status, specificity
          FROM sgf_lexicon WHERE wiktionary_source_id = ?
    """, (wsid,)).fetchone()
    if not row:
        return None
    (lemma, pos_simple, gloss, mg, cid,
     register, temporal_status, social_status, specificity) = row

    lemma_mates_raw = conn.execute("""
        SELECT wiktionary_source_id, gloss, microgloss
          FROM sgf_lexicon
         WHERE lower(lemma) = lower(?)
           AND wiktionary_source_id != ?
    """, (lemma, wsid)).fetchall()
    lemma_mates = [
        {"wsid": r[0], "gloss": r[1] or "", "microgloss": r[2] or ""}
        for r in lemma_mates_raw
    ]

    linkages = _load_linkages(conn, wsid)
    examples = _load_examples(conn, wsid)
    tags = _load_tags(conn, wsid)

    return {
        "wsid":              wsid,
        "canonical_id":      cid,
        "lemma":             lemma,
        "pos_simple":        pos_simple,
        "gloss":             gloss or "",
        "examples":          examples,
        "tags":              tags,
        "register":          register,
        "temporal_status":   temporal_status,
        "social_status":     social_status,
        "specificity":       specificity,
        "lemma_mates":       lemma_mates,
        "cousins":           [],  # filled in by lexicon_search if needed
        "synonyms":          linkages["synonyms"],
        "antonyms":          linkages["antonyms"],
        "hypernyms":         linkages["hypernyms"],
        "hyponyms":          linkages["hyponyms"],
        "coordinate_terms":  linkages["coordinate_terms"],
        "related":           linkages["related"],
    }


# ---------------------------------------------------------------------------
# Scope selection
# ---------------------------------------------------------------------------

def _select_unassigned(conn):
    """Senses with no current microgloss_assignment row."""
    cur = conn.execute("""
        SELECT sl.wiktionary_source_id
          FROM sgf_lexicon sl
          LEFT JOIN microgloss_assignment ma
            ON ma.wsid = sl.wiktionary_source_id
           AND ma.superseded_by IS NULL
         WHERE sl.canonical_id IS NOT NULL
           AND ma.assignment_id IS NULL
    """)
    return [row[0] for row in cur.fetchall()]


def _select_revisit(conn):
    """All senses that have a current assignment (re-tournament them)."""
    cur = conn.execute("""
        SELECT DISTINCT wsid
          FROM microgloss_assignment
         WHERE superseded_by IS NULL
    """)
    return [row[0] for row in cur.fetchall()]


def _select_audit_failed(conn, embedder, audit_phase):
    """Same query as improve_microgloss._get_audit_failed_wsids."""
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(quality_audit)")
    cols = {row[1] for row in cur.fetchall()}
    if "intralemma_pass" not in cols:
        print("ERROR: quality_audit.intralemma_pass column missing. "
              "Run quality_audit.py first.", file=sys.stderr)
        return []
    cur.execute("""
        SELECT wsid FROM quality_audit
         WHERE intralemma_pass = 0
           AND audit_phase = ?
           AND embedding_method = ?
           AND audit_run_id = (
               SELECT audit_run_id FROM quality_audit
                WHERE audit_phase = ? AND embedding_method = ?
                ORDER BY audited_at DESC LIMIT 1
           )
    """, (audit_phase, embedder, audit_phase, embedder))
    return [row[0] for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Diagnostic: --show-assignment
# ---------------------------------------------------------------------------

def show_assignment_main(args):
    """Print the current assignment row for one sense and exit."""
    db_path = Path(args.target)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1
    conn = sqlite3.connect(db_path)
    try:
        key = args.show_assignment.strip()
        if key.isdigit():
            wsid = int(key)
        else:
            row = conn.execute(
                "SELECT wiktionary_source_id FROM sgf_lexicon "
                "WHERE canonical_id = ?", (key,)).fetchone()
            if not row:
                print(f"No entry for canonical_id={key!r}", file=sys.stderr)
                return 2
            wsid = int(row[0])

        record = mga.get_current_assignment(conn, wsid)
        if not record:
            print(f"No current assignment for wsid={wsid}")
            return 0

        print("=" * 60)
        print(f"wsid                  : {wsid}")
        print(f"assignment_id         : {record['assignment_id']}")
        print(f"microgloss            : {record['microgloss']}")
        print(f"strategy              : {record['strategy']}")
        print(f"polysemy_tier         : {record['polysemy_tier']}")
        print(f"audit_t1              : passed={record['audit_t1_passed']}  "
              f"rank={record['audit_t1_rank']}  "
              f"margin={record['audit_t1_margin']}")
        print(f"audit_t2              : passed={record['audit_t2_passed']}  "
              f"rank={record['audit_t2_rank']}/"
              f"{record['audit_t2_cluster_size']}  "
              f"quantile={record['audit_t2_quantile']}")
        print(f"n_strategies_tried    : {record['n_strategies_tried']}")
        print(f"embedder              : {record['embedder_at_assignment']}")
        print(f"assigned_at           : {record['assigned_at']}")
        cands = record.get("tournament_candidates_json")
        if cands:
            print("=" * 60)
            print("Tournament candidates:")
            try:
                arr = json.loads(cands)
                for c in arr:
                    flag = "WIN " if c["microgloss"] == record["microgloss"] \
                        else "    "
                    print(f"  [{flag}] {c['strategy']:24s} "
                          f"{c['microgloss']:40s} "
                          f"t1={c['t1_passed']} r={c['t1_rank']} "
                          f"m={c['t1_margin']}  "
                          f"t2={c['t2_passed']} r={c['t2_rank']} "
                          f"q={c['t2_quantile']}  score={c['score']}")
            except json.JSONDecodeError:
                print("  (could not parse)")
        return 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Main run loop
# ---------------------------------------------------------------------------

def _make_embed_fn(embedder, use_lexicon_search=True):
    """Build an embed_fn(text) -> np.ndarray closure."""
    if not use_lexicon_search:
        return None
    import lexicon_search as ls
    if not ls.embedder_runtime_available():
        print("ERROR: onnxruntime + tokenizers required to embed text. "
              "Install: pip install onnxruntime tokenizers huggingface_hub",
              file=sys.stderr)
        return None
    return lambda text: ls.embed_text(text, embedder)


def _call_llm_improver(args, wsid):
    """Optionally invoke improve_microgloss.py for one wsid via subprocess
    and return the new microgloss the improver wrote, or None on failure.

    This is the LLM fallback path. We deliberately keep it as a process
    boundary so the deterministic path has zero LLM dependency.
    """
    import subprocess
    cmd = [
        sys.executable, str(HERE / "improve_microgloss.py"),
        "--target", args.target,
        "--llm-wrapper", args.llm_wrapper,
        "--wsids", str(wsid),
        "--workers", "1",
        "--tier", args.llm_tier,
        "--embedding-method", args.embedder,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=120)
    except subprocess.TimeoutExpired:
        print(f"  LLM improver timeout for wsid={wsid}")
        return None
    if result.returncode != 0:
        print(f"  LLM improver returned {result.returncode} for wsid={wsid}")
        return None
    # Re-read the new microgloss directly from the DB.
    conn = sqlite3.connect(args.target)
    try:
        row = conn.execute(
            "SELECT microgloss FROM sgf_lexicon WHERE wiktionary_source_id = ?",
            (wsid,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--target", default="sgf_lexicon.db")
    p.add_argument("--embedder", default="bge-large-en-v1",
                   help="Which embedder to use for the T1/T2 audits.")
    p.add_argument("--limit", type=int, default=None,
                   help="Process at most N senses (handy for smoke tests).")

    # Scope selection (mutually exclusive in practice)
    p.add_argument("--wsids", default=None,
                   help="Comma-separated wsids to process. Overrides all.")
    p.add_argument("--wsids-file", default=None,
                   help="File of wsids, one per line.")
    p.add_argument("--target-audit-failures", action="store_true",
                   help="Process only senses that failed the most recent "
                        "quality_audit run (intralemma_pass = 0).")
    p.add_argument("--audit-phase", default="production",
                   choices=["first_pass", "production", "rebuild"])
    p.add_argument("--revisit", action="store_true",
                   help="Re-tournament senses that already have a current "
                        "assignment (use after upgrading the embedder).")

    # LLM fallback wiring
    p.add_argument("--llm-wrapper", default=None,
                   help="Path to LLM wrapper script (enables fallback path).")
    p.add_argument("--llm-tier", default="strong",
                   help="LLM tier for fallback. Default: strong.")
    p.add_argument("--no-llm-fallback", action="store_true",
                   help="Never call the LLM improver, even on tournament fail.")

    p.add_argument("--dry-run", action="store_true",
                   help="Process the first in-scope sense and print the "
                        "full tournament; no DB writes.")
    p.add_argument("--show-assignment", metavar="CANONICAL_ID_OR_WSID",
                   default=None,
                   help="Diagnostic: print current assignment + tournament "
                        "history for one sense and exit.")
    args = p.parse_args()

    if args.show_assignment:
        return show_assignment_main(args)

    db_path = Path(args.target)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    mga.ensure_assignment_schema(conn)

    # ---- scope selection ----
    if args.wsids:
        in_scope = [int(x) for x in args.wsids.split(",") if x.strip()]
        print(f"--wsids: {len(in_scope)} senses")
    elif args.wsids_file:
        path = Path(args.wsids_file)
        if not path.exists():
            print(f"--wsids-file not found: {path}", file=sys.stderr)
            return 1
        in_scope = [
            int(line.strip())
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        print(f"--wsids-file: {len(in_scope)} senses")
    elif args.target_audit_failures:
        in_scope = _select_audit_failed(conn, args.embedder, args.audit_phase)
        print(f"--target-audit-failures: {len(in_scope):,} senses "
              f"(phase={args.audit_phase}, embedder={args.embedder})")
    elif args.revisit:
        in_scope = _select_revisit(conn)
        print(f"--revisit: {len(in_scope):,} senses with current assignments")
    else:
        in_scope = _select_unassigned(conn)
        print(f"unassigned scope: {len(in_scope):,} senses without "
              f"current assignment")

    if args.limit:
        in_scope = in_scope[: args.limit]
        print(f"--limit: capped at {len(in_scope):,} senses")
    if not in_scope:
        print("Nothing to do.")
        return 0

    # ---- polysemy counts (one query, used per sense) ----
    print("Loading polysemy counts ...")
    polysemy_counts = pt.load_lemma_polysemy_counts(conn)

    # ---- lexicon for embedder access ----
    print(f"Loading lexicon for embedder={args.embedder} ...")
    try:
        import lexicon_search as ls
        lexicon_ctx = ls.load_lexicon(db_path, verbose=False)
    except Exception as e:
        print(f"ERROR: could not load lexicon: {e}", file=sys.stderr)
        return 1

    # ---- embed_fn (real or skip-if-missing) ----
    embed_fn = _make_embed_fn(args.embedder)
    if embed_fn is None and not args.dry_run:
        # Without an embedder we can't audit; abort early.
        return 1

    # ---- dry-run ----
    if args.dry_run:
        wsid = in_scope[0]
        print()
        print("=" * 60)
        print(f"DRY RUN -- tournament for wsid={wsid}")
        print("=" * 60)
        ctx_sense = load_sense_context(conn, wsid)
        if ctx_sense is None:
            print(f"  no context loaded for wsid={wsid}")
            return 0
        print(f"  lemma: {ctx_sense['lemma']}  pos: {ctx_sense['pos_simple']}")
        print(f"  gloss: {ctx_sense['gloss'][:200]}")
        print()
        print("Candidates (no audit; --dry-run skips embedding):")
        for name, cands in cs.all_candidates(ctx_sense):
            if cands:
                for c in cands:
                    print(f"  [{name}]  {c}")
            else:
                print(f"  [{name}]  (no candidate)")
        return 0

    # ---- main loop ----
    print()
    print(f"Processing {len(in_scope):,} senses ...")
    print()

    t0 = time.time()
    last_report = t0
    n_won = 0
    n_llm_fallback = 0
    n_unresolved = 0
    strategy_wins = {}

    cluster_cache = {}

    for i, wsid in enumerate(in_scope):
        ctx_sense = load_sense_context(conn, wsid)
        if ctx_sense is None:
            n_unresolved += 1
            continue
        lemma_lower = ctx_sense["lemma"].lower()
        polysemy_n = polysemy_counts.get(lemma_lower, 1)

        audit_fn = lambda cand, w: ma_audit.audit_candidate(  # noqa: E731
            conn, lexicon_ctx, cand, w, args.embedder,
            polysemy_n, embed_fn=embed_fn, cluster_cache=cluster_cache,
        )

        result = mga.tournament(
            conn, lexicon_ctx, ctx_sense, wsid, args.embedder,
            polysemy_n, cs.STRATEGIES, audit_fn=audit_fn,
            embed_fn=embed_fn, cluster_cache=cluster_cache,
        )

        if result["winner"] is not None:
            mga.write_assignment(conn, wsid, result["winner"],
                                 result, args.embedder)
            n_won += 1
            strat = result["winner"]["strategy"]
            strategy_wins[strat] = strategy_wins.get(strat, 0) + 1
            sys.stdout.write(
                f"  wsid={wsid}  {ctx_sense['lemma']}  "
                f"WIN [{strat}] {result['winner']['microgloss']}\n")
            sys.stdout.flush()
        elif args.llm_wrapper and not args.no_llm_fallback:
            # LLM fallback
            new_mg = _call_llm_improver(args, wsid)
            if new_mg:
                # Audit the LLM's output and record it as an assignment.
                audit_for_llm = ma_audit.audit_candidate(
                    conn, lexicon_ctx, new_mg, wsid, args.embedder,
                    polysemy_n, embed_fn=embed_fn,
                    cluster_cache=cluster_cache,
                )
                mga.write_llm_fallback_assignment(
                    conn, wsid, new_mg, audit_for_llm, args.embedder,
                    result["n_strategies_tried"],
                )
                n_llm_fallback += 1
                sys.stdout.write(
                    f"  wsid={wsid}  {ctx_sense['lemma']}  LLM "
                    f"{new_mg}  (t1={audit_for_llm['t1_passed']} "
                    f"t2={audit_for_llm['t2_passed']})\n")
                sys.stdout.flush()
            else:
                n_unresolved += 1
                sys.stdout.write(
                    f"  wsid={wsid}  {ctx_sense['lemma']}  UNRESOLVED "
                    "(LLM also failed)\n")
                sys.stdout.flush()
        else:
            n_unresolved += 1
            sys.stdout.write(
                f"  wsid={wsid}  {ctx_sense['lemma']}  UNRESOLVED "
                "(no LLM fallback configured)\n")
            sys.stdout.flush()

        now = time.time()
        if now - last_report >= 2.0:
            processed = i + 1
            elapsed = now - t0
            rate = processed / elapsed if elapsed > 0 else 0
            eta_min = ((len(in_scope) - processed) / rate / 60
                       if rate > 0 else 0)
            print(f"  ... {processed:,}/{len(in_scope):,} "
                  f"({100.0 * processed / len(in_scope):.1f}%) "
                  f"{rate:.1f}/s  ETA {eta_min:.1f} min")
            last_report = now

    elapsed = time.time() - t0
    print()
    print("=" * 60)
    print(f"DONE in {elapsed/60:.1f} min")
    print(f"  deterministic wins  : {n_won:,}")
    print(f"  LLM fallback wins   : {n_llm_fallback:,}")
    print(f"  unresolved          : {n_unresolved:,}")
    print()
    if strategy_wins:
        print("Strategy win counts:")
        for strat, count in sorted(strategy_wins.items(),
                                    key=lambda x: -x[1]):
            print(f"  {strat:30s} {count:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
