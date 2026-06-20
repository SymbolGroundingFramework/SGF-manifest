#!/usr/bin/env python3
"""
sgf_cli.py — the `sgf` command-line tool

Single-target lexicon lookups, sanity checks, status reports.

Usage:
    python sgf_cli.py lookup TARGET [--context CTX] [--pos POS] [--surrounding S] [--json]
    python sgf_cli.py status
    python sgf_cli.py check-config

Examples:
    python sgf_cli.py lookup bank --context "I deposited money at the bank."
    python sgf_cli.py lookup bank --context "We sat on the bank under the willow."
    python sgf_cli.py lookup Beethoven --context "Beethoven moved to Vienna in 1792."
    python sgf_cli.py lookup car --pos noun --context "Tom's car was red."
    python sgf_cli.py status
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sgflib import LexiconClient, load_config


def cmd_lookup(args) -> int:
    cfg = load_config()
    lex = LexiconClient(cfg, embedding_method=args.method)
    try:
        result = lex.lookup(
            target=args.target,
            context=args.context or "",
            pos_hint=args.pos,
            surrounding=args.surrounding or "",
            enable_llm=not args.no_llm,
            enable_mint=not args.no_mint,
        )
    finally:
        lex.close()

    if args.json:
        print(json.dumps(result.as_dict(), indent=2))
        return 0

    # Human-readable output
    print()
    print(f"Target:       {result.target}")
    print(f"Context:      {result.context}")
    if result.pos_hint:
        print(f"POS hint:     {result.pos_hint}")
    print(f"Method:       {lex.method}")
    print()
    print(f"Decision:     level {result.decision_level}  ({result.decision_reason})")
    print(f"Canonical ID: {result.canonical_id}")
    print(f"Confidence:   {result.confidence:.3f}")
    print(f"Minted:       {result.minted}")
    print()
    if result.candidates:
        print("Candidates:")
        print(f"  {'cos':>6}  {'canonical_id':<55}  microgloss")
        print(f"  {'-' * 6}  {'-' * 55}  {'-' * 30}")
        for c in result.candidates:
            print(f"  {c.cosine:>6.3f}  {c.canonical_id:<55}  {c.microgloss}")
    return 0


def cmd_status(args) -> int:
    cfg = load_config()
    print(f"Config:       {cfg.config_path}")
    print(f"Lexicon DB:   {cfg.lexicon_db_path}")
    print(f"Synapse DB:   {cfg.synapse_store_path}")
    print(f"Default emb:  {cfg.default_embedding_method}")
    print()

    if not cfg.lexicon_db_path.exists():
        print(f"[!] Lexicon DB does not exist at {cfg.lexicon_db_path}")
        return 1

    conn = sqlite3.connect(cfg.lexicon_db_path)
    conn.execute("PRAGMA query_only = ON")

    sl = cfg.raw["lexicon"]["schema"]
    cur = conn.execute(f"SELECT COUNT(*) FROM {sl['parent_table']}")
    n_lex = cur.fetchone()[0]
    print(f"Lexicon rows:           {n_lex:,}")

    try:
        cur = conn.execute(f"""
            SELECT {sl['embed_method_col']}, COUNT(*)
            FROM {sl['embed_table']}
            GROUP BY {sl['embed_method_col']}
        """)
        rows = cur.fetchall()
        if rows:
            print()
            print("Embeddings by method:")
            for method, count in rows:
                pct = 100.0 * count / n_lex if n_lex else 0
                print(f"  {method:<25}  {count:>10,}  ({pct:.1f}% of lexicon)")
    except sqlite3.OperationalError as e:
        print(f"[!] could not query embeddings: {e}")

    conn.close()
    return 0


def cmd_check_config(args) -> int:
    try:
        cfg = load_config()
    except FileNotFoundError as e:
        print(f"[!] {e}")
        return 1

    print(f"Config loaded: {cfg.config_path}")
    required_sections = ["lexicon", "embedder", "llm", "lookup", "synapse_store"]
    missing = [s for s in required_sections if s not in cfg.raw]
    if missing:
        print(f"[!] Missing sections in sgf.toml: {missing}")
        return 1
    print(f"All required sections present: {required_sections}")
    print(f"Lexicon DB exists: {cfg.lexicon_db_path.exists()} ({cfg.lexicon_db_path})")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="SGF/GLEAN command-line tool")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_look = sub.add_parser("lookup", help="Look up a target term in the lexicon")
    p_look.add_argument("target", help="The word or term to look up")
    p_look.add_argument("--context", help="Context sentence containing the target")
    p_look.add_argument("--surrounding", help="Surrounding sentences for extra context")
    p_look.add_argument("--pos", help="POS hint (noun, verb, adj, adv, name)")
    p_look.add_argument("--method", help="Override default embedding_method")
    p_look.add_argument("--json", action="store_true", help="Output JSON instead of table")
    p_look.add_argument("--no-llm", action="store_true",
                        help="Disable step 3 (LLM rerank). Cascade stops at step 2.")
    p_look.add_argument("--no-mint", action="store_true",
                        help="Disable step 4 (mint). Returns no match instead.")
    p_look.set_defaults(func=cmd_lookup)

    p_st = sub.add_parser("status", help="Show lexicon + embeddings status")
    p_st.set_defaults(func=cmd_status)

    p_cc = sub.add_parser("check-config", help="Validate sgf.toml")
    p_cc.set_defaults(func=cmd_check_config)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
