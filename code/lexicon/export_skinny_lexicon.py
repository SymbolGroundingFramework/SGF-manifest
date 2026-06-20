#!/usr/bin/env python3
"""
export_skinny_lexicon.py -- carve a development/demo lexicon out of the
full sgf_lexicon.db, split into two files:

  1. sgf_lexicon_meta_<N>k.db
        sgf_lexicon + lemma_frequency + build_meta  (no embeddings)
  2. sgf_lexicon_embed_<N>k_<method>.db
        sense_embedding rows only, for one chosen embedding method

Why split: GitHub's 100MB per-file limit means a single skinny DB with
embeddings blows the limit fast. Splitting lets the meta file ship in the
regular repo and the embed file ship via a GitHub Release (2GB limit).

Selection axis: top N lemmas by lemma_frequency.frequency_rank ASC.
We pull ALL senses for each selected lemma (never slice mid-lemma,
otherwise polysemy gets crippled).

Usage:
    python export_skinny_lexicon.py \
        --source D:/lexicon/sgf_lexicon.db \
        --top-lemmas 10000 \
        --embedding-method bge-small-en-v1 \
        --outdir D:/lexicon/skinny

    # Preview only -- don't actually create files:
    python export_skinny_lexicon.py --top-lemmas 10000 --dry-run

Outputs are named automatically as:
    <outdir>/sgf_lexicon_meta_<N>k.db
    <outdir>/sgf_lexicon_embed_<N>k_<method_safe>.db

Where method_safe replaces hyphens with underscores
(e.g. bge-small-en-v1 -> bge_small_en_v1).
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path


# ---------- helpers ----------------------------------------------------

def fmt_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024 or unit == "GB":
            return f"{nbytes:,.1f} {unit}" if unit != "B" else f"{nbytes:,} B"
        nbytes /= 1024
    return f"{nbytes:.1f} GB"


def format_n_label(n: int) -> str:
    """10000 -> '10k', 5000 -> '5k', 500 -> '500'."""
    if n >= 1000 and n % 1000 == 0:
        return f"{n // 1000}k"
    if n >= 1000:
        return f"{n / 1000:.1f}k".replace(".0k", "k")
    return str(n)


def method_to_filename(method: str) -> str:
    """bge-small-en-v1 -> bge_small_en_v1."""
    return method.replace("-", "_").replace(".", "_")


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def copy_table_schema(src: sqlite3.Connection, tgt: sqlite3.Connection,
                      table_name: str) -> None:
    """Copy CREATE TABLE and CREATE INDEX statements for one table."""
    rows = src.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE sql IS NOT NULL AND tbl_name = ? "
        "ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END",
        (table_name,)
    ).fetchall()
    for (sql,) in rows:
        if not sql:
            continue
        try:
            tgt.execute(sql)
        except sqlite3.OperationalError as e:
            print(f"  WARN: could not create from: {sql[:80]}... ({e})",
                  flush=True)


def get_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def apply_bulk_pragmas(conn: sqlite3.Connection) -> None:
    """Speed up bulk inserts. Safe because the script is idempotent --
    if it crashes, you just rerun and the file is rebuilt."""
    conn.execute("PRAGMA synchronous = OFF")
    conn.execute("PRAGMA journal_mode = MEMORY")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA cache_size = -200000")  # ~200 MB page cache


def chunked_insert(tgt: sqlite3.Connection, table: str, columns: list[str],
                   row_iter, batch_size: int = 5000,
                   progress_every: int = 10000) -> int:
    placeholders = ",".join("?" * len(columns))
    insert_sql = (f"INSERT OR REPLACE INTO {table} "
                  f"({','.join(columns)}) VALUES ({placeholders})")
    batch = []
    total = 0
    last_progress = 0
    for row in row_iter:
        batch.append(row)
        if len(batch) >= batch_size:
            tgt.executemany(insert_sql, batch)
            total += len(batch)
            batch = []
            if total - last_progress >= progress_every:
                print(f"      inserted {total:,} ...", flush=True)
                last_progress = total
    if batch:
        tgt.executemany(insert_sql, batch)
        total += len(batch)
    return total


# ---------- main -------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--source", default="D:/lexicon/sgf_lexicon.db",
                   help="Full lexicon DB to read from.")
    p.add_argument("--outdir", default="D:/lexicon/skinny",
                   help="Directory to write the skinny DB files into.")
    p.add_argument("--top-lemmas", type=int, required=True,
                   help="Top N lemmas by frequency_rank to include "
                        "(all senses per lemma are kept).")
    p.add_argument("--embedding-method", default="bge-small-en-v1",
                   help="Which embedding method's vectors to export "
                        "(default: bge-small-en-v1).")
    p.add_argument("--dry-run", action="store_true",
                   help="Project sizes and stop; do not create files. "
                        "Forces row-count projection (otherwise skipped).")
    p.add_argument("--project", action="store_true",
                   help="Run the row-count projection step before copying. "
                        "Off by default (slow on large DBs). "
                        "Automatically on for --dry-run.")
    args = p.parse_args()

    src_path = Path(args.source)
    if not src_path.exists():
        print(f"ERROR: source DB not found: {src_path}", file=sys.stderr)
        return 1

    outdir = Path(args.outdir)
    if not args.dry_run:
        outdir.mkdir(parents=True, exist_ok=True)

    n_label = format_n_label(args.top_lemmas)
    method_safe = method_to_filename(args.embedding_method)
    meta_path = outdir / f"sgf_lexicon_meta_{n_label}.db"
    embed_path = outdir / f"sgf_lexicon_embed_{n_label}_{method_safe}.db"

    print("=" * 70)
    print("Skinny lexicon export")
    print("=" * 70)
    print(f"  source:     {src_path}")
    print(f"  top lemmas: {args.top_lemmas:,}")
    print(f"  method:     {args.embedding_method}")
    print(f"  meta out:   {meta_path}")
    print(f"  embed out:  {embed_path}")
    print(f"  dry run:    {args.dry_run}")
    print()

    src = sqlite3.connect(str(src_path))
    src.row_factory = sqlite3.Row

    # -- Sanity: required tables present
    for required in ("sgf_lexicon", "sense_embedding", "lemma_frequency"):
        if not table_exists(src, required):
            print(f"ERROR: source DB missing required table: {required}",
                  file=sys.stderr)
            return 1

    # -- Step 1: pick the top N lemmas ---------------------------------
    print("[1/6] selecting top lemmas ...", flush=True)
    t0 = time.time()
    top_lemmas = [
        r["lemma"].lower()
        for r in src.execute(
            "SELECT lemma FROM lemma_frequency "
            "ORDER BY frequency_rank ASC LIMIT ?",
            (args.top_lemmas,)
        )
    ]
    lemma_set = set(top_lemmas)
    print(f"      {len(top_lemmas):,} lemmas selected ({time.time()-t0:.1f}s)")
    if top_lemmas:
        print(f"      first 10: {top_lemmas[:10]}")
        print(f"      last  10: {top_lemmas[-10:]}")
    print()

    if not lemma_set:
        print("ERROR: no lemmas selected. lemma_frequency empty?",
              file=sys.stderr)
        return 1

    # -- Step 2: project sense count + embed count ---------------------
    print("[2/6] projecting row counts ...", flush=True)
    t0 = time.time()

    # Stage the chosen lemmas into a temp table so SQLite can use the
    # indexes on sgf_lexicon.lemma and sense_embedding.embedding_method.
    # Trying to do this with Python-side filtering or massive IN-lists
    # is orders of magnitude slower.
    # NOCASE collation lets SQLite use the lemma index on sgf_lexicon
    # without per-row LOWER(). This is the speed-critical bit.
    src.execute("DROP TABLE IF EXISTS temp._skinny_lemmas")
    src.execute(
        "CREATE TEMP TABLE _skinny_lemmas ("
        "lemma TEXT PRIMARY KEY COLLATE NOCASE)"
    )
    src.executemany(
        "INSERT OR IGNORE INTO temp._skinny_lemmas(lemma) VALUES (?)",
        [(l,) for l in top_lemmas],
    )

    do_projection = args.project or args.dry_run
    if not do_projection:
        print("      [skipped -- pass --project to include]")
        n_senses_proj = -1
        n_embeds_proj = -1
    else:
        n_senses_proj = src.execute("""
            SELECT COUNT(*) FROM sgf_lexicon sl
            JOIN temp._skinny_lemmas sk ON sk.lemma = sl.lemma COLLATE NOCASE
        """).fetchone()[0]

        n_embeds_proj = src.execute("""
            SELECT COUNT(*) FROM sense_embedding se
            JOIN sgf_lexicon sl ON sl.wiktionary_source_id = se.wiktionary_source_id
            JOIN temp._skinny_lemmas sk ON sk.lemma = sl.lemma COLLATE NOCASE
            WHERE se.embedding_method = ?
        """, (args.embedding_method,)).fetchone()[0]

        print(f"      sgf_lexicon rows projected:   {n_senses_proj:,}")
        print(f"      sense_embedding rows ({args.embedding_method}): "
              f"{n_embeds_proj:,}")

    # Get the embedding dim by peeking one row.
    peek = src.execute(
        "SELECT embedding_dim, embed FROM sense_embedding "
        "WHERE embedding_method = ? LIMIT 1",
        (args.embedding_method,)
    ).fetchone()
    if peek is None:
        print(f"ERROR: no sense_embedding rows for method "
              f"{args.embedding_method!r}", file=sys.stderr)
        return 1
    embed_dim = peek["embedding_dim"]
    blob_bytes = len(peek["embed"])

    print(f"      embed dim: {embed_dim}, blob bytes: {blob_bytes}")
    if n_senses_proj >= 0:
        embed_db_size_proj = int(n_embeds_proj * blob_bytes * 1.25)
        meta_bytes_proj = int(
            (n_senses_proj * 400 + len(lemma_set) * 30) * 1.20
        )
        print(f"      projected embed DB size: {fmt_size(embed_db_size_proj)}")
        print(f"      projected meta  DB size: {fmt_size(meta_bytes_proj)}")

        GH_HARD = 100 * 1024 * 1024
        GH_SOFT = 50 * 1024 * 1024
        for name, size in (("meta", meta_bytes_proj),
                           ("embed", embed_db_size_proj)):
            if size > GH_HARD:
                print(f"      WARN: projected {name} DB > 100 MB. "
                      f"GitHub regular Git will REJECT this file. "
                      f"Use GitHub Releases for this artifact.")
            elif size > GH_SOFT:
                print(f"      NOTE: projected {name} DB > 50 MB. "
                      f"GitHub will accept but warn.")
    print(f"      (step took {time.time()-t0:.1f}s)")
    print()

    if args.dry_run:
        print("Dry run requested. Stopping before creating files.")
        return 0

    # -- Step 3: create + populate META DB ------------------------------
    if meta_path.exists():
        print(f"[3/6] meta file exists, deleting: {meta_path}", flush=True)
        meta_path.unlink()

    print(f"[3/6] creating meta DB ...", flush=True)
    t0 = time.time()
    meta_db = sqlite3.connect(str(meta_path))
    apply_bulk_pragmas(meta_db)
    copy_table_schema(src, meta_db, "sgf_lexicon")
    copy_table_schema(src, meta_db, "lemma_frequency")
    if table_exists(src, "build_meta"):
        copy_table_schema(src, meta_db, "build_meta")
    meta_db.commit()

    sgf_cols = get_columns(src, "sgf_lexicon")
    print(f"      copying sgf_lexicon rows ...")

    def gen_lexicon_rows():
        # JOIN against the temp lemma table so SQLite uses indexes.
        cur = src.execute(f"""
            SELECT {','.join('sl.' + c for c in sgf_cols)} FROM sgf_lexicon sl
            JOIN temp._skinny_lemmas sk ON sk.lemma = sl.lemma COLLATE NOCASE
            ORDER BY sl.wiktionary_source_id
        """)
        for row in cur:
            yield tuple(row)

    inserted_lex = chunked_insert(
        meta_db, "sgf_lexicon", sgf_cols, gen_lexicon_rows()
    )
    meta_db.commit()
    print(f"      {inserted_lex:,} sgf_lexicon rows copied")

    print(f"      copying lemma_frequency rows ...")
    lf_cols = get_columns(src, "lemma_frequency")

    def gen_freq_rows():
        cur = src.execute(f"""
            SELECT {','.join('lf.' + c for c in lf_cols)} FROM lemma_frequency lf
            JOIN temp._skinny_lemmas sk ON sk.lemma = lf.lemma COLLATE NOCASE
        """)
        for row in cur:
            yield tuple(row)

    inserted_freq = chunked_insert(
        meta_db, "lemma_frequency", lf_cols, gen_freq_rows()
    )
    meta_db.commit()
    print(f"      {inserted_freq:,} lemma_frequency rows copied")

    if table_exists(src, "build_meta"):
        bm_cols = get_columns(src, "build_meta")
        cur = src.execute(f"SELECT {','.join(bm_cols)} FROM build_meta")
        chunked_insert(meta_db, "build_meta", bm_cols,
                       (tuple(r) for r in cur))
        meta_db.execute(
            "INSERT OR REPLACE INTO build_meta(key, value) VALUES (?, ?)",
            ("skinny_top_lemmas", str(args.top_lemmas)),
        )
        meta_db.execute(
            "INSERT OR REPLACE INTO build_meta(key, value) VALUES (?, ?)",
            ("skinny_built_at", str(int(time.time()))),
        )
        meta_db.commit()

    print(f"      VACUUM meta DB ...")
    meta_db.execute("VACUUM")
    meta_db.close()
    actual_meta_size = meta_path.stat().st_size
    print(f"      meta DB done: {fmt_size(actual_meta_size)} "
          f"({time.time()-t0:.1f}s)")
    print()

    # -- Step 4: collect matching sense IDs (kept as a temp table) -----
    print(f"[4/6] staging matching wiktionary_source_id values ...",
          flush=True)
    t0 = time.time()
    src.execute("DROP TABLE IF EXISTS temp._skinny_ids")
    src.execute("CREATE TEMP TABLE _skinny_ids (id INTEGER PRIMARY KEY)")
    src.execute("""
        INSERT OR IGNORE INTO temp._skinny_ids(id)
        SELECT sl.wiktionary_source_id FROM sgf_lexicon sl
        JOIN temp._skinny_lemmas sk ON sk.lemma = sl.lemma COLLATE NOCASE
    """)
    n_ids = src.execute("SELECT COUNT(*) FROM temp._skinny_ids").fetchone()[0]
    print(f"      {n_ids:,} ids in scope ({time.time()-t0:.1f}s)")
    print()

    # -- Step 5: create + populate EMBED DB ----------------------------
    if embed_path.exists():
        print(f"[5/6] embed file exists, deleting: {embed_path}", flush=True)
        embed_path.unlink()

    print(f"[5/6] creating embed DB ...", flush=True)
    t0 = time.time()
    embed_db = sqlite3.connect(str(embed_path))
    apply_bulk_pragmas(embed_db)
    copy_table_schema(src, embed_db, "sense_embedding")
    # Tag where this came from -- helps users avoid mismatches.
    embed_db.execute(
        "CREATE TABLE IF NOT EXISTS embed_meta "
        "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    embed_db.execute(
        "INSERT OR REPLACE INTO embed_meta(key, value) VALUES (?, ?)",
        ("embedding_method", args.embedding_method),
    )
    embed_db.execute(
        "INSERT OR REPLACE INTO embed_meta(key, value) VALUES (?, ?)",
        ("embedding_dim", str(embed_dim)),
    )
    embed_db.execute(
        "INSERT OR REPLACE INTO embed_meta(key, value) VALUES (?, ?)",
        ("skinny_top_lemmas", str(args.top_lemmas)),
    )
    embed_db.execute(
        "INSERT OR REPLACE INTO embed_meta(key, value) VALUES (?, ?)",
        ("skinny_built_at", str(int(time.time()))),
    )
    embed_db.commit()

    se_cols = get_columns(src, "sense_embedding")
    print(f"      copying sense_embedding rows ...")

    def gen_embed_rows():
        # Drive from the temp ID table so SQLite does a tiny outer loop
        # over our 92k IDs and does indexed lookups into sense_embedding.
        # The JOIN syntax confused the optimizer into scanning sense_embedding
        # (1.76M rows) first. Reformulating as a correlated subquery via
        # the explicit ID outer loop forces the right plan.
        cols_sql = ','.join('se.' + c for c in se_cols)
        outer = src.execute("SELECT id FROM temp._skinny_ids ORDER BY id")
        method = args.embedding_method
        # Use a separate cursor for the per-ID lookups so we can iterate
        # the outer cursor lazily without conflicts.
        inner_cur = src.cursor()
        lookup_sql = (f"SELECT {cols_sql} FROM sense_embedding se "
                      f"WHERE se.wiktionary_source_id = ? "
                      f"AND se.embedding_method = ?")
        for (sid,) in outer:
            for row in inner_cur.execute(lookup_sql, (sid, method)):
                yield tuple(row)

    inserted_embeds = chunked_insert(
        embed_db, "sense_embedding", se_cols, gen_embed_rows()
    )
    embed_db.commit()
    print(f"      {inserted_embeds:,} sense_embedding rows copied")

    print(f"      VACUUM embed DB ...")
    embed_db.execute("VACUUM")
    embed_db.close()
    actual_embed_size = embed_path.stat().st_size
    print(f"      embed DB done: {fmt_size(actual_embed_size)} "
          f"({time.time()-t0:.1f}s)")
    print()

    # -- Step 6: summary ------------------------------------------------
    print("[6/6] SUMMARY")
    print("=" * 70)
    print(f"  meta  DB : {meta_path}")
    print(f"             {fmt_size(actual_meta_size)}, "
          f"{inserted_lex:,} senses, {inserted_freq:,} freq rows")
    print(f"  embed DB : {embed_path}")
    print(f"             {fmt_size(actual_embed_size)}, "
          f"{inserted_embeds:,} embeddings ({args.embedding_method})")
    print()
    print("  To use:")
    print(f"    Edit sgf.toml [lexicon] section so:")
    print(f"      db_path        = \"{meta_path.as_posix()}\"")
    print(f"      embed_db_path  = \"{embed_path.as_posix()}\"")
    print(f"      default_embedding_method = \"{args.embedding_method}\"")
    print()
    print("  NOTE: sgflib currently expects a single DB. Until the split-DB")
    print("  loader is implemented in sgflib (planned), either:")
    print("     a) merge the two skinny DBs into one for testing:")
    print(f"        sqlite3 {meta_path.name} \".restore '{embed_path.name}'\"  # no, see docs")
    print("        -- or just ATTACH at runtime --")
    print("     b) keep using the full lexicon for now and treat these")
    print("        files as the GitHub-ready publication artifacts.")
    print()

    src.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
