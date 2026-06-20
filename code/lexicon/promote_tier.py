#!/usr/bin/env python3
"""
promote_tier.py -- utility

Sets maturity_tier on a selection of senses, either explicitly or by
re-inspecting the DB state. Use when:

- You've manually fixed a sense and want to promote it to 'improved'
  without re-running the LLM
- You want to force a re-audit of senses at a given tier (demote them
  back to 'embedded_v2' so Stage 8.5 sees them as audit candidates)
- You want to backfill from DB state after restoring a broken backup

USAGE
-----
Show the current tier distribution:
    python promote_tier.py --target sgf_lexicon.db --show

Force one sense to a specific tier:
    python promote_tier.py --target sgf_lexicon.db --wsid 12345 --tier improved

Bulk re-derive tiers from DB state (idempotent backfill):
    python promote_tier.py --target sgf_lexicon.db --backfill

Demote a tier so it can be re-processed:
    python promote_tier.py --target sgf_lexicon.db \\
        --demote-tier related --to-tier clustered --max-senses 5000

WARNING: --demote-tier and --force-promote are foot-guns. Use only
when you understand the consequence (re-processing cost, audit-trail
disruption).
"""

import argparse
import sqlite3
import sys
from pathlib import Path

TIER_ORDER = [
    "raw", "provisional", "embedded_v1", "improved",
    "embedded_v2", "clustered", "related",
]


def show_distribution(conn):
    print()
    print("Tier distribution:")
    total = 0
    for tier in TIER_ORDER:
        n = conn.execute(
            "SELECT COUNT(*) FROM sgf_lexicon WHERE maturity_tier = ?",
            (tier,),
        ).fetchone()[0]
        total += n
        print(f"  {tier:>14}: {n:>12,}")
    print(f"  {'TOTAL':>14}: {total:>12,}")


def backfill_from_state(conn):
    """Re-derive maturity_tier from DB state. Highest tier wins."""
    rules = [
        ("related",
         """UPDATE sgf_lexicon
              SET maturity_tier = 'related'
            WHERE wiktionary_source_id IN (
                SELECT DISTINCT source_wsid FROM sense_semantic_relation
            )"""),
        ("clustered",
         """UPDATE sgf_lexicon
              SET maturity_tier = 'clustered'
            WHERE maturity_tier != 'related'
              AND wiktionary_source_id IN (
                SELECT wsid FROM content_identical_member
            )"""),
        ("embedded_v2",
         """UPDATE sgf_lexicon
              SET maturity_tier = 'embedded_v2'
            WHERE maturity_tier NOT IN ('related','clustered')
              AND wiktionary_source_id IN (
                SELECT wiktionary_source_id FROM sense_embedding
                 WHERE embedding_method LIKE 'bge-large%'
                    OR embedding_method LIKE 'bge-m3%'
            )"""),
        ("improved",
         """UPDATE sgf_lexicon
              SET maturity_tier = 'improved'
            WHERE maturity_tier NOT IN ('related','clustered','embedded_v2')
              AND wiktionary_source_id IN (
                SELECT source_sense_id FROM sense_enrichment
                 WHERE enrichment_version = 'v4'
            )"""),
        ("embedded_v1",
         """UPDATE sgf_lexicon
              SET maturity_tier = 'embedded_v1'
            WHERE maturity_tier NOT IN ('related','clustered',
                                        'embedded_v2','improved')
              AND wiktionary_source_id IN (
                SELECT wiktionary_source_id FROM sense_embedding
                 WHERE embedding_method LIKE 'bge-small%'
            )"""),
        ("provisional",
         """UPDATE sgf_lexicon
              SET maturity_tier = 'provisional'
            WHERE maturity_tier NOT IN ('related','clustered','embedded_v2',
                                        'improved','embedded_v1')
              AND microgloss IS NOT NULL"""),
        ("raw",
         """UPDATE sgf_lexicon
              SET maturity_tier = 'raw'
            WHERE microgloss IS NULL"""),
    ]
    for tier, sql in rules:
        try:
            n = conn.execute(sql).rowcount
            if n > 0:
                print(f"  set tier={tier!r}: {n:,}")
        except sqlite3.OperationalError as e:
            print(f"  skipped {tier}: {e}")
    conn.commit()


def set_one(conn, wsid, tier):
    cur = conn.execute(
        "UPDATE sgf_lexicon SET maturity_tier = ? WHERE wiktionary_source_id = ?",
        (tier, wsid),
    )
    conn.commit()
    return cur.rowcount


def demote(conn, from_tier, to_tier, max_senses):
    if TIER_ORDER.index(to_tier) >= TIER_ORDER.index(from_tier):
        print(f"ERROR: --to-tier must be lower than --demote-tier", file=sys.stderr)
        return 0
    cur = conn.execute(
        """
        UPDATE sgf_lexicon
           SET maturity_tier = ?
         WHERE wiktionary_source_id IN (
             SELECT wiktionary_source_id FROM sgf_lexicon
              WHERE maturity_tier = ? LIMIT ?
         )
        """,
        (to_tier, from_tier, max_senses),
    )
    conn.commit()
    return cur.rowcount


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", default="sgf_lexicon.db")
    p.add_argument("--show", action="store_true", help="Print tier distribution and exit")
    p.add_argument("--backfill", action="store_true",
                   help="Re-derive maturity_tier from DB state")
    p.add_argument("--wsid", type=int, help="Operate on a single sense")
    p.add_argument("--tier", help="Target tier (used with --wsid)")
    p.add_argument("--demote-tier", help="Demote all senses at this tier ...")
    p.add_argument("--to-tier", help="... to this tier")
    p.add_argument("--max-senses", type=int, default=10000,
                   help="Cap on --demote-tier operations")
    args = p.parse_args()

    db = Path(args.target)
    if not db.exists():
        print(f"DB not found: {db}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db)
    conn.execute("PRAGMA busy_timeout = 60000")

    if args.show:
        show_distribution(conn)
        return 0

    if args.backfill:
        print("Backfilling maturity_tier from DB state ...")
        backfill_from_state(conn)
        show_distribution(conn)
        return 0

    if args.wsid is not None and args.tier:
        if args.tier not in TIER_ORDER:
            print(f"ERROR: invalid tier {args.tier!r}", file=sys.stderr)
            return 1
        n = set_one(conn, args.wsid, args.tier)
        print(f"Updated {n} row(s).")
        return 0

    if args.demote_tier and args.to_tier:
        if args.demote_tier not in TIER_ORDER or args.to_tier not in TIER_ORDER:
            print("ERROR: invalid tier name", file=sys.stderr)
            return 1
        n = demote(conn, args.demote_tier, args.to_tier, args.max_senses)
        print(f"Demoted {n:,} senses from {args.demote_tier} to {args.to_tier}.")
        return 0

    print("Nothing to do. Use --show, --backfill, --wsid + --tier, "
          "or --demote-tier + --to-tier.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
