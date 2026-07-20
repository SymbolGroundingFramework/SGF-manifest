#!/usr/bin/env python3
"""
sgf_cli.py — the `sgf` command-line tool (v3.2)

Single-target lexicon lookups, sanity checks, status reports, plus
v3.2 inspection commands: ghosts, bridge-map, coverage.

Usage:
    python sgf_cli.py lookup TARGET [--context CTX] [--pos POS] [--json]
    python sgf_cli.py lookup TARGET --custom-lexicon CUSTOM_DB [--json]
    python sgf_cli.py status
    python sgf_cli.py check-config
    python sgf_cli.py ghosts [--db GHOST_DB] [--json]
    python sgf_cli.py show-synapse SYNAPSE_ID [--db DB] [--json]
    python sgf_cli.py coverage DOC_ID [--db DB] [--json]
    python sgf_cli.py bridge-map [--db BRIDGE_DB] [--json]

Examples:
    python sgf_cli.py lookup bank --context "I deposited money at the bank."
    python sgf_cli.py lookup Beethoven --custom-lexicon custom_lexicon_corp_001.db
    python sgf_cli.py ghosts
    python sgf_cli.py show-synapse syn_abc123
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sgflib import (
    load_config,
    lookup_in_lexicon,
    get_server_health,
)

try:
    import call_llm
    _HAVE_CALL_LLM = True
except Exception:
    _HAVE_CALL_LLM = False


# =============================================================================
# Small helpers
# =============================================================================

def _resolve_synapse_db_path(cfg, override):
    if override:
        return Path(override).expanduser()
    p = cfg.get("synapse_store", {}).get("path")
    if not p:
        raise RuntimeError("synapse_store.path missing from sgf.toml")
    return Path(p).expanduser()


def _resolve_custom_lexicon_path(cfg, override):
    if override:
        return Path(override).expanduser()
    p = cfg.get("custom_lexicon", {}).get("path")
    if p:
        return Path(p).expanduser()
    return None


def _resolve_ghost_db_path(cfg, override):
    if override:
        return Path(override).expanduser()
    p = cfg.get("ghost_registry", {}).get("path")
    if p:
        return Path(p).expanduser()
    # Derive from custom lexicon path
    cl_path = _resolve_custom_lexicon_path(cfg, None)
    if cl_path:
        return cl_path.parent / "ghost_registry.db"
    return None


def _print_kv(label, value):
    print(f"{label:<24} {value}")


def _format_ts(ts_str):
    """Format a timestamp string for display."""
    if not ts_str:
        return "-"
    return ts_str[:19]  # trim fractional seconds


# =============================================================================
# lookup
# =============================================================================

def cmd_lookup(args):
    cfg = load_config()

    llm_cfg = None
    if _HAVE_CALL_LLM and not args.no_llm:
        try:
            llm_cfg = call_llm.load_llm_config(cfg.get("_config_path"))
        except Exception:
            llm_cfg = None

    # Check custom lexicon first, if requested
    custom_result = None
    if args.custom_lexicon:
        cl_path = Path(args.custom_lexicon).expanduser()
        if cl_path.exists():
            try:
                conn = sqlite3.connect(str(cl_path))
                cur = conn.cursor()
                cur.execute(
                    "SELECT canonical_id, lemma, pos_ud, gloss, definition_tier, ref_count "
                    "FROM entry WHERE lemma = ? ORDER BY ref_count DESC LIMIT 5",
                    (args.target.lower(),)
                )
                rows = cur.fetchall()
                conn.close()
                if rows:
                    custom_result = []
                    for r in rows:
                        custom_result.append({
                            "canonical_id": r[0],
                            "lemma": r[1],
                            "pos_ud": r[2],
                            "gloss": r[3],
                            "definition_tier": r[4],
                            "ref_count": r[5],
                        })
            except sqlite3.OperationalError as e:
                print(f"[!] custom lexicon error: {e}", file=sys.stderr)

    # Standard lookup via search server
    result = lookup_in_lexicon(
        target=args.target,
        context=args.context or "",
        pos_hint=args.pos,
        cfg=cfg,
        enable_mint=not args.no_mint,
        llm_cfg=llm_cfg,
    )

    if args.json:
        output = {
            "search_server_result": result,
            "custom_lexicon_result": custom_result,
        }
        print(json.dumps(output, indent=2, default=str))
        return 0

    # Print Synapedia result
    print()
    _print_kv("Target:", result.get("target"))
    _print_kv("Context:", result.get("context") or "(none)")
    if result.get("pos_hint"):
        _print_kv("POS hint:", result["pos_hint"])
    print()
    _print_kv("Decision:",
              f"level {result.get('decision_level')}  "
              f"({result.get('decision_reason')})")
    _print_kv("Canonical ID:", result.get("canonical_id") or "(none)")
    _print_kv("Confidence:", f"{result.get('confidence', 0.0):.3f}")
    _print_kv("Minted:", result.get("minted"))
    _print_kv("Specificity:", result.get("specificity") or "(unset)")
    _print_kv("Maturity tier:", result.get("maturity_tier") or "(unset)")
    _print_kv("Snap-to-standard:", result.get("rewritten_to_standard"))
    if result.get("matched_canonical_id"):
        _print_kv("Pre-snap match:", result["matched_canonical_id"])
    print()

    # Print custom lexicon results if available
    if custom_result:
        print("Custom lexicon matches:")
        print(f"  {'canonical_id':<55}  {'tier':<18}  refs")
        print(f"  {'-'*55}  {'-'*18}  {'-'*4}")
        for cr in custom_result:
            print(f"  {cr['canonical_id']:<55}  {cr['definition_tier']:<18}  {cr['ref_count']}")

    # Candidates from search server
    cands = result.get("candidates") or []
    if cands:
        print("Candidates (from search server):")
        print(f"  {'cos':>6}  {'canonical_id':<55}  microgloss")
        print(f"  {'-'*6}  {'-'*55}  {'-'*30}")
        for c in cands:
            print(f"  {c.get('cosine', 0.0):>6.3f}  "
                  f"{c.get('canonical_id', ''):<55}  "
                  f"{c.get('microgloss', '')}")
    return 0


# =============================================================================
# status
# =============================================================================

def cmd_status(args):
    cfg = load_config()
    _print_kv("Config:", cfg.get("_config_path", "(unknown)"))
    _print_kv("Lexicon DB:", cfg.get("lexicon", {}).get("db_path", "(unset)"))
    _print_kv("Synapse DB:", cfg.get("synapse_store", {}).get("path", "(unset)"))
    _print_kv("Custom Lexicon:", cfg.get("custom_lexicon", {}).get("path", "(unset)"))
    _print_kv("Accuracy mode:", cfg.get("accuracy", {}).get("mode", "standard"))
    server_url = cfg.get("search_server", {}).get("url",
                                                  "http://127.0.0.1:8400")
    _print_kv("Search server:", server_url)
    print()

    # Search-server health
    try:
        health = get_server_health(cfg)
        _print_kv("Server status:", health.get("status", "unknown"))
        if "lexicon_rows" in health:
            _print_kv("Lexicon rows:", f"{health['lexicon_rows']:,}")
        if "embeddings_by_method" in health:
            print()
            print("Embeddings by method:")
            for method, count in health["embeddings_by_method"].items():
                print(f"  {method:<25}  {count:>10,}")
    except Exception as e:
        print(f"[!] search server unreachable: {e}")

    # Synapse store quick stats
    syn_path = cfg.get("synapse_store", {}).get("path")
    if syn_path and Path(syn_path).expanduser().exists():
        try:
            conn = sqlite3.connect(Path(syn_path).expanduser())
            conn.execute("PRAGMA query_only = ON")
            doc_n = conn.execute("SELECT COUNT(*) FROM document").fetchone()[0]
            syn_n = conn.execute("SELECT COUNT(*) FROM synapedia_synapse").fetchone()[0]
            ent_n = conn.execute("SELECT COUNT(*) FROM entity").fetchone()[0]
            grp_n = conn.execute("SELECT COUNT(*) FROM synapedia_group").fetchone()[0]
            link_n = conn.execute("SELECT COUNT(*) FROM synapedia_link").fetchone()[0]
            print()
            _print_kv("Documents:", f"{doc_n:,}")
            _print_kv("Synapses:", f"{syn_n:,}")
            _print_kv("Entities:", f"{ent_n:,}")
            _print_kv("Groups:", f"{grp_n:,}")
            _print_kv("Links:", f"{link_n:,}")
            conn.close()
        except sqlite3.OperationalError as e:
            print(f"[!] could not query synapse store: {e}")

    # Ghost registry quick stats
    ghost_path = _resolve_ghost_db_path(cfg, None)
    if ghost_path and ghost_path.exists():
        try:
            conn = sqlite3.connect(str(ghost_path))
            conn.execute("PRAGMA query_only = ON")
            total = conn.execute("SELECT COUNT(*) FROM ghost").fetchone()[0]
            unresolved = conn.execute(
                "SELECT COUNT(*) FROM ghost WHERE resolved_to_canonical_id IS NULL"
            ).fetchone()[0]
            print()
            _print_kv("Ghosts (total):", f"{total:,}")
            _print_kv("Ghosts (unresolved):", f"{unresolved:,}")
            conn.close()
        except sqlite3.OperationalError:
            pass

    return 0


# =============================================================================
# check-config
# =============================================================================

def cmd_check_config(args):
    try:
        cfg = load_config()
    except FileNotFoundError as e:
        print(f"[!] {e}")
        return 1

    print(f"Config loaded: {cfg.get('_config_path', '(unknown)')}")
    required = ["lexicon", "search_server", "llm", "lookup", "synapse_store"]
    missing = [s for s in required if s not in cfg]
    if missing:
        print(f"[!] Missing sections in sgf.toml: {missing}")
        return 1
    print(f"All required sections present: {required}")

    lex_path = cfg.get("lexicon", {}).get("db_path")
    if lex_path:
        p = Path(lex_path).expanduser()
        print(f"Lexicon DB exists: {p.exists()} ({p})")

    syn_path = cfg.get("synapse_store", {}).get("path")
    if syn_path:
        p = Path(syn_path).expanduser()
        print(f"Synapse store exists: {p.exists()} ({p})")

    cl_path = cfg.get("custom_lexicon", {}).get("path")
    if cl_path:
        p = Path(cl_path).expanduser()
        print(f"Custom lexicon exists: {p.exists()} ({p})")

    if _HAVE_CALL_LLM:
        llm_cfg = call_llm.load_llm_config(cfg.get("_config_path"))
        configured = call_llm.is_wrapper_configured(llm_cfg)
        print(f"LLM wrapper configured: {configured}  "
              f"(path={llm_cfg.get('wrapper_path', '')!r})")
    return 0


# =============================================================================
# ghosts
# =============================================================================

def cmd_ghosts(args):
    cfg = load_config()
    ghost_path = _resolve_ghost_db_path(cfg, args.db)
    if not ghost_path or not ghost_path.exists():
        print(f"[!] ghost registry not found at {ghost_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(ghost_path))
    conn.execute("PRAGMA query_only = ON")
    conn.row_factory = sqlite3.Row

    ghosts = [dict(r) for r in conn.execute(
        "SELECT ghost_id, surface_form, context, doc_id, detected_pattern, "
        "frequency, created_at, resolved_to_canonical_id "
        "FROM ghost ORDER BY frequency DESC, created_at DESC"
    ).fetchall()]
    conn.close()

    if args.json:
        print(json.dumps(ghosts, indent=2, default=str))
        return 0

    print()
    print(f"Ghost entries ({len(ghosts)} total)")
    print("-" * 100)
    print(f"  {'surface_form':<30}  {'pattern':<20}  {'freq':>4}  {'created':>19}  {'status'}")
    print(f"  {'-'*30}  {'-'*20}  {'-'*4}  {'-'*19}  {'-'*10}")
    for g in ghosts:
        status = "RESOLVED" if g.get("resolved_to_canonical_id") else "PENDING"
        surface = (g.get("surface_form") or "?")[:28]
        pattern = (g.get("detected_pattern") or "-")[:18]
        freq = g.get("frequency", 0)
        created = _format_ts(g.get("created_at", ""))
        print(f"  {surface:<30}  {pattern:<20}  {freq:>4}  {created:>19}  {status:<10}")
    return 0


# =============================================================================
# show-synapse
# =============================================================================

def cmd_show_synapse(args):
    cfg = load_config()
    db_path = _resolve_synapse_db_path(cfg, args.db)
    if not db_path.exists():
        print(f"[!] synapse DB does not exist at {db_path}")
        return 1

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA query_only = ON")
    conn.row_factory = sqlite3.Row

    # Look up in synapedia_synapse (v3.2) first, fall back to synapse (v1.2)
    syn_row = conn.execute(
        "SELECT * FROM synapedia_synapse WHERE synapse_id = ?", (args.synapse_id,)
    ).fetchone()
    if syn_row is None:
        syn_row = conn.execute(
            "SELECT * FROM synapse WHERE synapse_id = ?", (args.synapse_id,)
        ).fetchone()
    if syn_row is None:
        print(f"[!] no synapse found with id={args.synapse_id}")
        conn.close()
        return 1

    syn = dict(syn_row)

    # V3.2: use synapedia_spoke; v1.2 fallback: use synapse_spoke
    spokes = [dict(r) for r in conn.execute(
        "SELECT * FROM synapedia_spoke WHERE synapse_id = ? "
        "ORDER BY spoke_index", (args.synapse_id,)
    ).fetchall()]
    if not spokes:
        spokes = [dict(r) for r in conn.execute(
            "SELECT * FROM synapse_spoke WHERE synapse_id = ? "
            "ORDER BY spoke_index", (args.synapse_id,)
        ).fetchall()]

    # Frame from frame_json field
    frame_json_str = syn.get("frame_json")
    frame = json.loads(frame_json_str) if frame_json_str else {}

    if args.json:
        print(json.dumps({
            "synapse": syn,
            "spokes": spokes,
            "frame": frame,
        }, indent=2, default=str))
        conn.close()
        return 0

    print()
    print(f"Synapse {syn['synapse_id']}  (doc={syn.get('doc_id', '?')})")
    print("-" * 72)
    verb_lemma = syn.get("verb_lemma") or syn.get("predicate_surface", "")
    verb_cid = syn.get("verb_canonical_id") or "(unresolved)"
    _print_kv("Verb:", f"{verb_lemma}  -> {verb_cid}")
    _print_kv("Polarity:", syn.get("polarity"))
    _print_kv("Statement type:", syn.get("statement_type"))
    _print_kv("Epistemic status:", syn.get("epistemic_status"))
    _print_kv("Plane:", syn.get("plane"))
    _print_kv("Sentence id:", syn.get("source_sentence_id"))
    print()

    if spokes:
        print("Spokes:")
        for s in spokes:
            target_disp = (s.get("target_canonical_id")
                           or s.get("target_id")
                           or s.get("target_surface")
                           or "(none)")
            role = s.get("role", "?")
            ttype = s.get("target_type", "")
            ttype_str = f" [{ttype}]" if ttype else ""
            print(f"  [{s.get('spoke_index', 0):>2}] {role:<16} -> "
                  f"{target_disp}{ttype_str}")
        print()

    if frame:
        print("Frame:")
        for k in ("rhetorical_mode", "rhetorical_mood", "hedging_level",
                  "point_of_view", "speech_act", "scope",
                  "statement_type", "temporal_anchor"):
            v = frame.get(k)
            if v not in (None, ""):
                _print_kv(f"  {k}:", v)
    conn.close()
    return 0


# =============================================================================
# coverage
# =============================================================================

def cmd_coverage(args):
    cfg = load_config()
    db_path = _resolve_synapse_db_path(cfg, args.db)
    if not db_path.exists():
        print(f"[!] synapse DB does not exist at {db_path}")
        return 1

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA query_only = ON")
    conn.row_factory = sqlite3.Row

    doc_row = conn.execute(
        "SELECT * FROM document WHERE doc_id = ?", (args.doc_id,)
    ).fetchone()
    if doc_row is None:
        print(f"[!] no document found with id={args.doc_id}")
        conn.close()
        return 1

    entities = [dict(r) for r in conn.execute(
        "SELECT ent_id, preferred_canonical, type_hint, "
        "lexicon_canonical_id, lookup_decision_level, lookup_confidence, "
        "minted, specificity, maturity_tier, rewritten_to_standard, "
        "matched_canonical_id, nexus_namespace "
        "FROM entity WHERE doc_id = ? "
        "ORDER BY (minted DESC), preferred_canonical",
        (args.doc_id,)
    ).fetchall()]

    minted = [e for e in entities if e.get("minted")]
    matched = [e for e in entities if not e.get("minted")]
    snapped = [e for e in entities if e.get("rewritten_to_standard")]

    if args.json:
        print(json.dumps({
            "doc_id": args.doc_id,
            "total": len(entities),
            "matched": len(matched),
            "minted": len(minted),
            "snapped": len(snapped),
            "entities": entities,
        }, indent=2, default=str))
        conn.close()
        return 0

    print()
    print(f"Coverage for {args.doc_id}")
    print("-" * 72)
    _print_kv("Total entities:", len(entities))
    _print_kv("Matched (real):", len(matched))
    _print_kv("Minted (doc-local):", len(minted))
    _print_kv("Snap-to-standard:", len(snapped))
    print()

    if minted:
        print("Minted (no lexicon match):")
        print(f"  {'canonical_id':<50}  {'ns':<12}  type     reason")
        print(f"  {'-'*50}  {'-'*12}  {'-'*7}  {'-'*20}")
        for e in minted:
            cid = e.get("lexicon_canonical_id") or "(none)"
            ns = e.get("nexus_namespace") or "?"
            reason = "no_match" if e.get("lookup_decision_level") == 4 else \
                     f"level={e.get('lookup_decision_level')}"
            print(f"  {cid[:50]:<50}  {ns:<12}  "
                  f"{(e.get('type_hint') or '')[:7]:<7}  {reason}")
        print()

    if snapped:
        print("Snap-to-standard (rewritten):")
        print(f"  {'canonical_id':<45}  was -> now")
        print(f"  {'-'*45}  {'-'*25}")
        for e in snapped:
            cid = e.get("lexicon_canonical_id") or "(none)"
            prior = e.get("matched_canonical_id") or "(unknown)"
            print(f"  {e['preferred_canonical'][:45]:<45}  "
                  f"{prior}  ->  {cid}")
        print()

    conn.close()
    return 0


# =============================================================================
# bridge-map (stub)
# =============================================================================

def cmd_bridge_map(args):
    print("[!] bridge-map: not yet implemented (requires search-server integration)")
    print("    This command will show verified alignments between lexicons.")
    return 1


# =============================================================================
# main
# =============================================================================

def main():
    p = argparse.ArgumentParser(description="SGF/GLEAN command-line tool (v3.2)")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_look = sub.add_parser("lookup", help="Look up a target term in the lexicon")
    p_look.add_argument("target", help="The word or term to look up")
    p_look.add_argument("--context", help="Context sentence containing the target")
    p_look.add_argument("--pos", help="POS hint (noun, verb, adj, adv, name)")
    p_look.add_argument("--json", action="store_true",
                        help="Output JSON instead of table")
    p_look.add_argument("--no-llm", action="store_true",
                        help="Disable step 3 (LLM rerank)")
    p_look.add_argument("--no-mint", action="store_true",
                        help="Disable step 4 (mint)")
    p_look.add_argument("--custom-lexicon", default=None,
                        help="Path to custom lexicon DB for additional lookup")
    p_look.set_defaults(func=cmd_lookup)

    p_st = sub.add_parser("status", help="Show search-server + store status")
    p_st.set_defaults(func=cmd_status)

    p_cc = sub.add_parser("check-config", help="Validate sgf.toml")
    p_cc.set_defaults(func=cmd_check_config)

    p_gh = sub.add_parser("ghosts", help="List unresolved ghost entries")
    p_gh.add_argument("--db", help="Override ghost_registry.path")
    p_gh.add_argument("--json", action="store_true")
    p_gh.set_defaults(func=cmd_ghosts)

    p_show = sub.add_parser("show-synapse",
                            help="Inspect a single synapse by id")
    p_show.add_argument("synapse_id")
    p_show.add_argument("--db", help="Override synapse_store.path")
    p_show.add_argument("--json", action="store_true")
    p_show.set_defaults(func=cmd_show_synapse)

    p_cov = sub.add_parser("coverage",
                           help="Summarize entity coverage for a document")
    p_cov.add_argument("doc_id")
    p_cov.add_argument("--db", help="Override synapse_store.path")
    p_cov.add_argument("--json", action="store_true")
    p_cov.set_defaults(func=cmd_coverage)

    p_bm = sub.add_parser("bridge-map",
                          help="Inspect Bridge Map entries (not yet implemented)")
    p_bm.add_argument("--db", help="Override Bridge Map path")
    p_bm.add_argument("--json", action="store_true")
    p_bm.set_defaults(func=cmd_bridge_map)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())