#!/usr/bin/env python3
"""
generate_microglosses.py

Stage 3 of the SGF lexicon build pipeline.

Runs the lexicon-agnostic sibling-IDF microgloss algorithm (microgloss.py,
ALGORITHM_VERSION = "v4") across every (lemma, pos_simple) group in
sgf_lexicon, writing back microgloss and canonical_id.

NOTE:
  - Harvests structured metadata (register, temporal_status, social_status)
    from Wiktionary tags via lexicon_metadata.harvest_metadata_from_tags()
  - Computes sparse_data_flag (1 if Wiktionary signal is thin)
  - Preserves provisional values in microgloss_provisional /
    canonical_id_provisional columns (the live columns hold the current
    best; provisional preserves what Stage 3 wrote so a later improver
    pass can be compared against it)
  - Canonical_id includes register: en.<lemma>.<microgloss>.<pos>.<register>
    instead of the form en.<lemma>.<microgloss>.<pos>.core
  - Sets embedding_text_needs_rebuild = 1 when microgloss/metadata changes

The runner walks sgf_lexicon ordered by (_norm_for_id(lemma),
_norm(pos_simple), wsid), joining to wiktionary_source for the tags/
examples/etymology/linkages needed for metadata harvest.

CANONICAL ID FORMAT
------------------------
canonical_id = en.{lemma}.{microgloss}.{pos_simple}.{register}

where register is one of the 9 controlled register values. Default
"neutral" for senses with no register-relevant Wiktionary tag.

SIDE EFFECTS
------------
For every row whose microgloss or metadata changes, the runner clears
embedding_text_v1 and embedding_text_v2, sets
embedding_text_needs_rebuild = 1, and (existing behavior) clears the
legacy embedding_text + embedding_text_version columns.

USAGE
-----
    python generate_microglosses.py --target sgf_lexicon.db
    python generate_microglosses.py --target sgf_lexicon.db --limit 5000
    python generate_microglosses.py --target sgf_lexicon.db --rewrite-all
    python generate_microglosses.py --target sgf_lexicon.db --dry-run --lemma washington

REQUIREMENTS
------------
The target DB must have been migrated to v2 schema. Run:
    python apply_schema.py
before running this script.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from microgloss import (  # noqa: E402
    MicroglossGenerator,
    WIKTIONARY_XREF_EXTENSIONS,
    _norm,
    _norm_for_id,
)
from lexicon_metadata import (  # noqa: E402
    harvest_metadata_from_tags,
    compute_sparse_data_flag,
)

XREF_EXTRA = WIKTIONARY_XREF_EXTENSIONS

ALGORITHM_VERSION = "v4"
CANONICAL_ID_VERSION = "v3"  # namespace replaces register as 5th field


def build_canonical_id(lemma, microgloss, pos_simple, namespace):
    """Build a canonical_id from its five components.

    Format: en.<lemma>.<microgloss>.<pos>.<namespace>

    The 5th field changed from register to namespace. Register
    moved to its own structured column; namespace identifies which
    lexicon a canonical_id belongs to ('core' default, 'business',
    'medical', 'corpus.<name>', etc.).

    LEMMA: _norm_for_id (light) preserves apostrophes, diacritics,
    trailing punctuation, with deterministic hex fallback for
    pure-unicode lemmas.

    POS, NAMESPACE: _norm (aggressive) is fine because these are
    fixed small vocabularies.

    MICROGLOSS is already sanitized by the generator.
    """
    return (
        f"en.{_norm_for_id(lemma)}."
        f"{microgloss}."
        f"{_norm(pos_simple)}."
        f"{_norm(namespace or 'core')}"
    )


def check_v3_schema(conn):
    """Verify v2 + v3 columns exist; fail with a helpful message if not."""
    cur = conn.execute("PRAGMA table_info(sgf_lexicon)")
    cols = {row[1] for row in cur.fetchall()}
    required = {
        "microgloss_provisional", "canonical_id_provisional",
        "register", "temporal_status", "social_status",
        "sparse_data_flag", "embedding_text_needs_rebuild",
        "namespace",  # v3
    }
    missing = required - cols
    if missing:
        print(f"ERROR: target DB is missing required columns: {sorted(missing)}",
              file=sys.stderr)
        if "namespace" in missing:
            print("Run: python apply_schema.py --target <your-db>",
                  file=sys.stderr)
        else:
            print("Run: python apply_schema.py --target <your-db>",
                  file=sys.stderr)
        sys.exit(1)


def process_group(rows, write_cur, dry_run, verbose, rewrite_all):
    """Process one (_norm_for_id(lemma), _norm(pos_simple)) batch of rows.

    Each row tuple:
        (wsid, lemma, pos_simple, gloss,
         current_microgloss, current_version, current_canonical_id,
         tags_json, examples_json, etymology_text, linkages_json,
         current_register, current_temporal, current_social,
         current_sparse_flag, current_provisional_mg, namespace)

    ALL rows are ingested for sibling-IDF correctness. Rows already at
    current ALGORITHM_VERSION are NOT rewritten unless rewrite_all,
    but their microglosses are seeded into the generator so newly
    generated ones cannot collide.

    Returns (n_processed, n_changed).
    """
    if not rows:
        return 0, 0

    gen = MicroglossGenerator(xref_patterns_extra=XREF_EXTRA)

    # Phase 1: ingest all senses for sibling-IDF
    for r in rows:
        _wsid, lemma, pos, gloss = r[0], r[1], r[2], r[3]
        gen.add_sibling(lemma, pos, gloss or "")

    # Phase 1.5: seed _emitted with already-final microglosses
    minted_cids_in_batch = set()
    if not rewrite_all:
        for r in rows:
            wsid, lemma, pos, _gloss = r[0], r[1], r[2], r[3]
            current_mg, current_ver, current_cid = r[4], r[5], r[6]
            if current_ver == ALGORITHM_VERSION and current_mg:
                key = (_norm_for_id(lemma or ""), _norm(pos or ""))
                gen._emitted[key].add(current_mg)
                if current_cid:
                    minted_cids_in_batch.add(current_cid)

    # Phase 2: generate for pending rows
    n_changed = 0
    for r in rows:
        (wsid, lemma, pos, gloss,
         current_mg, current_ver, current_cid,
         tags_json, examples_json, etymology_text, linkages_json,
         current_register, current_temporal, current_social,
         current_sparse, current_provisional_mg, namespace) = r
        namespace = namespace or "core"

        # Always harvest metadata fresh (it's deterministic and cheap)
        meta = harvest_metadata_from_tags(tags_json)
        register = meta["register"]
        temporal_status = meta["temporal_status"]
        social_status = meta["social_status"]
        sparse_flag = compute_sparse_data_flag(
            tags_json, examples_json, etymology_text, linkages_json
        )

        # Skip microgloss regen if the row is at current version and we're
        # not in rewrite mode. But we still UPDATE the metadata if it
        # changed (metadata harvest is deterministic; only changes when
        # the upstream Wiktionary tags change, which is rare but possible
        # if wiktionary_source was rebuilt).
        skip_mg = (
            not rewrite_all
            and current_ver == ALGORITHM_VERSION
            and current_mg
        )

        if skip_mg:
            new_mg = current_mg
            new_cid = current_cid
        else:
            new_mg = gen.generate(lemma, pos, gloss or "")
            new_cid = build_canonical_id(lemma, new_mg, pos, namespace)

            # Defensive: numeric suffix if cid collides within this batch
            if new_cid in minted_cids_in_batch:
                i = 2
                while f"{new_cid}_{i}" in minted_cids_in_batch:
                    i += 1
                new_mg = f"{new_mg}_{i}"
                new_cid = build_canonical_id(lemma, new_mg, pos, namespace)
            minted_cids_in_batch.add(new_cid)

        # Determine what actually changed so we know whether to write
        mg_changed = (new_mg != current_mg)
        cid_changed = (new_cid != current_cid)
        register_changed = (register != current_register)
        temporal_changed = (temporal_status != current_temporal)
        social_changed = (social_status != current_social)
        sparse_changed = (sparse_flag != current_sparse)

        any_change = (
            mg_changed or cid_changed or register_changed or
            temporal_changed or social_changed or sparse_changed or
            current_ver != ALGORITHM_VERSION
        )

        if not any_change:
            continue

        n_changed += 1
        if verbose and n_changed <= 30:
            print(f"  {lemma}/{pos}  mg={current_mg!r}->{new_mg!r}  "
                  f"reg={current_register}->{register}  "
                  f"temp={current_temporal}->{temporal_status}  "
                  f"soc={current_social}->{social_status}")

        if dry_run:
            continue

        # Preserve provisional values: if microgloss_provisional is
        # still NULL, populate it now. After the improver runs and
        # changes the live microgloss, the provisional value is
        # preserved for comparison.
        provisional_mg = current_provisional_mg or new_mg
        provisional_cid = build_canonical_id(lemma, provisional_mg, pos, namespace)

        try:
            # also advance maturity_tier to 'provisional' if it
            # was still 'raw'. Higher tiers are left alone so we don't
            # demote a sense the improver already promoted.
            write_cur.execute("""
                UPDATE sgf_lexicon
                SET microgloss = ?,
                    microgloss_version = ?,
                    canonical_id = ?,
                    microgloss_provisional = COALESCE(microgloss_provisional, ?),
                    canonical_id_provisional = COALESCE(canonical_id_provisional, ?),
                    register = ?,
                    temporal_status = ?,
                    social_status = ?,
                    sparse_data_flag = ?,
                    embedding_text = NULL,
                    embedding_text_version = NULL,
                    embedding_text_v1 = NULL,
                    embedding_text_v1_version = NULL,
                    embedding_text_v2 = NULL,
                    embedding_text_v2_version = NULL,
                    embedding_text_needs_rebuild = 1,
                    maturity_tier = CASE
                        WHEN maturity_tier IN ('raw') THEN 'provisional'
                        ELSE maturity_tier
                    END
                WHERE wiktionary_source_id = ?
            """, (new_mg, ALGORITHM_VERSION, new_cid,
                  provisional_mg, provisional_cid,
                  register, temporal_status, social_status, sparse_flag,
                  wsid))
        except Exception as e:
            sys.stderr.write(
                f"WARN: skipping wsid={wsid} lemma={lemma!r} "
                f"pos={pos!r} new_cid={new_cid!r}: "
                f"{type(e).__name__}: {e}\n"
            )

    return len(rows), n_changed


def run(db_path, limit, rewrite_all, only_lemma, dry_run):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    check_v3_schema(conn)

    read_cur = conn.cursor()
    write_cur = conn.cursor()

    # Check wiktionary_source exists; if not, metadata harvest can't run
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='wiktionary_source'"
    )
    has_ws = cur.fetchone() is not None
    if not has_ws:
        print("WARNING: wiktionary_source table not found in target DB.",
              file=sys.stderr)
        print("Metadata harvest will default all rows to neutral/live/unmarked.",
              file=sys.stderr)
        print("Run build_wiktionary_source.py to enable proper metadata.",
              file=sys.stderr)

    where = []
    params = []
    if only_lemma:
        where.append("LOWER(sl.lemma) = LOWER(?)")
        params.append(only_lemma)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    print("Loading rows into memory ...")
    if has_ws:
        sql = f"""
            SELECT sl.wiktionary_source_id, sl.lemma, sl.pos_simple, sl.gloss,
                   sl.microgloss, sl.microgloss_version, sl.canonical_id,
                   ws.tags_json, ws.examples_json, ws.etymology_text, ws.linkages_json,
                   sl.register, sl.temporal_status, sl.social_status,
                   sl.sparse_data_flag, sl.microgloss_provisional,
                   sl.namespace
            FROM sgf_lexicon sl
            LEFT JOIN wiktionary_source ws
                ON ws.source_sense_id = sl.wiktionary_source_id
            {where_sql}
        """
    else:
        # Fallback: no wiktionary_source table; metadata will default
        sql = f"""
            SELECT sl.wiktionary_source_id, sl.lemma, sl.pos_simple, sl.gloss,
                   sl.microgloss, sl.microgloss_version, sl.canonical_id,
                   NULL, NULL, NULL, NULL,
                   sl.register, sl.temporal_status, sl.social_status,
                   sl.sparse_data_flag, sl.microgloss_provisional,
                   sl.namespace
            FROM sgf_lexicon sl
            {where_sql}
        """

    all_rows = read_cur.execute(sql, params).fetchall()
    print(f"Loaded {len(all_rows):,} rows; sorting by canonical group key ...")

    all_rows.sort(key=lambda r: (_norm_for_id(r[1] or ""), _norm(r[2] or ""), r[0]))
    print("Sorted. Starting microgloss generation ...")
    print()

    if dry_run:
        print("DRY RUN: not writing.")

    t_start = time.time()
    last_print = t_start
    n_groups_done = 0
    n_rows_done = 0
    n_rows_changed = 0
    total_rows = len(all_rows)

    current_key = None
    current_rows = []
    stopped = False

    def flush_group():
        nonlocal n_groups_done, n_rows_done, n_rows_changed
        if not current_rows:
            return
        processed, changed = process_group(
            current_rows, write_cur, dry_run,
            verbose=(only_lemma is not None),
            rewrite_all=rewrite_all,
        )
        n_rows_done += processed
        n_rows_changed += changed
        n_groups_done += 1

    for row in all_rows:
        lemma, pos = row[1], row[2]
        row_key = (_norm_for_id(lemma or ""), _norm(pos or ""))
        if current_key is None:
            current_key = row_key
        if row_key != current_key:
            flush_group()
            current_rows = []
            current_key = row_key

            now = time.time()
            if (now - last_print) >= 10.0:
                if not dry_run:
                    conn.commit()
                elapsed = now - t_start
                rate = n_rows_done / elapsed if elapsed > 0 else 0
                pct = 100.0 * n_rows_done / max(1, total_rows)
                eta_min = (total_rows - n_rows_done) / rate / 60 if rate > 0 else 0
                print(f"  groups {n_groups_done:,}  "
                      f"rows {n_rows_done:,}/{total_rows:,} ({pct:.1f}%)  "
                      f"changed {n_rows_changed:,}  "
                      f"({rate:.0f}/s, ETA {eta_min:.0f} min)")
                last_print = now

            if limit and n_rows_done >= limit:
                print(f"  reached --limit={limit:,}; stopping")
                stopped = True
                break

        current_rows.append(row)

    if not stopped and current_rows:
        flush_group()

    if not dry_run:
        conn.commit()

    elapsed = time.time() - t_start
    print()
    print("=" * 60)
    print(f"MICROGLOSS {ALGORITHM_VERSION} + v2 METADATA GENERATION COMPLETE"
          + (" (DRY-RUN)" if dry_run else ""))
    print("=" * 60)
    print(f"  groups processed       : {n_groups_done:,}")
    print(f"  rows processed         : {n_rows_done:,}")
    print(f"  rows changed           : {n_rows_changed:,}")
    print(f"  elapsed                : {elapsed/60:.1f} min")
    print(f"  rate                   : {n_rows_done/max(1,elapsed):.0f} rows/s")

    # Report metadata distribution
    if not dry_run:
        cur = conn.execute(
            "SELECT register, COUNT(*) FROM sgf_lexicon GROUP BY register ORDER BY 2 DESC LIMIT 10"
        )
        print()
        print("  register distribution (top 10):")
        for reg, count in cur.fetchall():
            print(f"    {reg or '(null)':<14} : {count:,}")

        cur = conn.execute(
            "SELECT temporal_status, COUNT(*) FROM sgf_lexicon GROUP BY temporal_status ORDER BY 2 DESC LIMIT 10"
        )
        print()
        print("  temporal_status distribution:")
        for ts, count in cur.fetchall():
            print(f"    {ts or '(null)':<14} : {count:,}")

        cur = conn.execute(
            "SELECT social_status, COUNT(*) FROM sgf_lexicon GROUP BY social_status ORDER BY 2 DESC LIMIT 10"
        )
        print()
        print("  social_status distribution:")
        for ss, count in cur.fetchall():
            print(f"    {ss or '(null)':<14} : {count:,}")

        cur = conn.execute(
            "SELECT COUNT(*) FROM sgf_lexicon WHERE sparse_data_flag = 1"
        )
        n_sparse = cur.fetchone()[0]
        print()
        print(f"  sparse-data senses: {n_sparse:,} ({100.0*n_sparse/max(1,n_rows_done):.1f}%)")

    print()
    if not dry_run and n_rows_changed > 0:
        print("Next steps:")
        print(f"  python build_embedding_texts.py --target {db_path.name} --pass v1")
        print(f"  python compute_embeddings.py --target {db_path.name} --embedding-method bge-small-en-v1 --device dml")
    print("=" * 60)

    conn.close()
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[3])
    p.add_argument("--target", default="sgf_lexicon.db")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--rewrite-all", action="store_true",
                   help="Regenerate every microgloss regardless of version")
    p.add_argument("--lemma", default=None,
                   help="Limit work to a single lemma (case-insensitive)")
    p.add_argument("--dry-run", action="store_true",
                   help="Show changes without writing")
    args = p.parse_args()

    db_path = Path(args.target)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    print(f"Target:      {db_path.resolve()}")
    print(f"Algorithm:   {ALGORITHM_VERSION}")
    print(f"Rewrite-all: {args.rewrite_all}")
    print(f"Lemma:       {args.lemma if args.lemma else '(all)'}")
    print(f"Dry-run:     {args.dry_run}")
    print()

    return run(
        db_path=db_path,
        limit=args.limit,
        rewrite_all=args.rewrite_all,
        only_lemma=args.lemma,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
