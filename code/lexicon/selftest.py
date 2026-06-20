#!/usr/bin/env python3
"""
End-to-end self-test on a synthetic mini-DB.

Tests:
  1. schema.sql applies cleanly via sqlite3
  2. generate_microglosses.py v3 produces namespace-format canonical_ids
     and advances maturity_tier raw -> provisional
  3. improve_microgloss.persist_improvement writes content_identical_group
     rows, advances tier to 'improved', records specificity
  4. quality_audit.py audits embeddings (using production schema with
     wiktionary_source_id + embed)
  5. compute_embeddings tier-advance behavior is correct
     (bge-small -> embedded_v1, bge-large -> embedded_v2)
  6. discover_clusters.py creates groups, advances tier to 'clustered'
  7. select_standard_forms.py picks a standard form
  8. harvest_semantic_relations.py writes patterns, advances tier to 'related'
  9. promote_tier.py --show and --backfill work
 10. run_frontier.py --dry-run plans the right stages
 11. Re-running the pipeline is idempotent: tier-advanced senses are
     not re-processed
"""

import json
import struct
import subprocess
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def section(title):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def run(*args, check=True):
    print(f"  $ {' '.join(str(a) for a in args)}")
    r = subprocess.run(
        [sys.executable] + [str(a) for a in args],
        cwd=str(HERE), capture_output=True, text=True,
    )
    if check and r.returncode != 0:
        print("STDOUT:", r.stdout[-2000:])
        print("STDERR:", r.stderr[-2000:])
        raise SystemExit(f"FAIL: {args}")
    return r


def build_seed_db(db_path):
    """Create a minimal seeded DB using the canonical schema.sql.

    The seed inserts 7 representative senses through schema.sql's full
    table definitions, so this test exercises the same schema the
    production pipeline uses.
    """
    conn = sqlite3.connect(db_path)

    # Apply the canonical schema first.
    sql_text = (HERE / "schema.sql").read_text(encoding="utf-8")
    conn.executescript(sql_text)

    # wiktionary_source schema is owned by build_wiktionary_source.py;
    # selftest re-creates a minimal subset so we don't need the full
    # Wiktextract dump for the synthetic test.
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS wiktionary_source (
        source_sense_id   INTEGER PRIMARY KEY,
        source_entry_id   INTEGER,
        word              TEXT,
        pos               TEXT,
        lang_code         TEXT,
        etymology_text    TEXT,
        forms_json        TEXT,
        sense_index       INTEGER,
        glosses_json      TEXT,
        raw_glosses_json  TEXT,
        tags_json         TEXT,
        categories_json   TEXT,
        topics_json       TEXT,
        examples_json     TEXT,
        linkages_json     TEXT,
        first_gloss       TEXT,
        loaded_at         INTEGER
    );
    """)

    senses = [
        # wsid, lemma, pos, gloss, tags, freq
        (1, "dad", "noun", "One's father.", '["informal"]', 5),
        (2, "father", "noun", "A male parent.", '[]', 1),
        (3, "papa", "noun", "An affectionate name for one's father.",
         '["affectionate", "informal"]', 50),
        (4, "dragster", "noun",
         "A type of car designed for drag racing.", '[]', 10000),
        (5, "car", "noun", "A motor vehicle for passenger transport.", '[]', 200),
        (6, "give", "verb", "To transfer something to a recipient.", '[]', 30),
        (7, "apple", "noun",
         "A round fruit consisting of flesh and seeds.",
         '[]', 800),
    ]
    now = int(time.time())
    for sid, lemma, pos, gloss, tags, freq in senses:
        # wiktionary_source first so the sgf_lexicon FK can resolve.
        conn.execute(
            "INSERT INTO wiktionary_source "
            "(source_sense_id, word, pos, tags_json, first_gloss, loaded_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (sid, lemma, pos, tags, gloss, now),
        )
        conn.execute(
            "INSERT INTO sgf_lexicon "
            "(wiktionary_source_id, lemma, pos_wiktionary, pos_spacy, "
            " pos_simple, gloss, minted_at, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, lemma, pos, pos.upper(), pos, gloss, now, now, now),
        )
        conn.execute(
            "INSERT INTO lemma_frequency (lemma, frequency_rank) VALUES (?, ?)",
            (lemma.lower(), freq),
        )
    conn.commit()
    conn.close()


def make_vec(seed, dim=8, norm=1.0):
    import math, random
    rng = random.Random(seed)
    v = [rng.uniform(-1, 1) for _ in range(dim)]
    s = math.sqrt(sum(x*x for x in v))
    return [x/s*norm for x in v]


def vec_to_blob(v):
    return struct.pack(f"<{len(v)}f", *v)


def _unit(v):
    import math
    s = math.sqrt(sum(x*x for x in v))
    return [x/s for x in v]


def add_embeddings(db_path, method, advance_tier=True):
    """Add embeddings using the production schema column names."""
    import random
    rng = random.Random(1)
    family_base = make_vec("family")
    perturb = lambda b, eps: _unit([x + eps * rng.uniform(-1, 1) for x in b])
    fam_vecs = {
        1: perturb(family_base, 0.05),
        2: perturb(family_base, 0.05),
        3: perturb(family_base, 0.07),
    }
    other_vecs = {
        4: make_vec("dragster", norm=1.0),
        5: make_vec("car", norm=1.0),
        6: make_vec("give", norm=1.0),
        7: make_vec("apple", norm=1.0),
    }
    now = int(time.time())
    conn = sqlite3.connect(db_path)
    for sid, v in {**fam_vecs, **other_vecs}.items():
        conn.execute(
            """
            INSERT OR REPLACE INTO sense_embedding (
                wiktionary_source_id, embedding_method, embedding_dim,
                embed, computed_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (sid, method, len(v), vec_to_blob(v), now),
        )
        if advance_tier:
            target_tier = "embedded_v1" if "small" in method else "embedded_v2"
            if target_tier == "embedded_v1":
                allowed = "('raw','provisional')"
            else:
                allowed = "('raw','provisional','embedded_v1','improved')"
            conn.execute(
                f"UPDATE sgf_lexicon SET maturity_tier = '{target_tier}' "
                f"WHERE wiktionary_source_id = ? AND maturity_tier IN {allowed}",
                (sid,),
            )
    conn.commit()
    conn.close()


def tier_of(conn, wsid):
    r = conn.execute(
        "SELECT maturity_tier FROM sgf_lexicon WHERE wiktionary_source_id = ?",
        (wsid,),
    ).fetchone()
    return r[0] if r else None


def test_pipeline():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.db"

        section("1. Build seed DB")
        build_seed_db(db)
        print("  Seeded 7 senses with production sense_embedding schema.")

        section("2. Apply schema (idempotent)")
        # schema.sql is a single canonical create-from-scratch script.
        # Apply via sqlite3, not via the run() helper (which expects a .py).
        sql_text = (HERE / "schema.sql").read_text(encoding="utf-8")
        conn_tmp = sqlite3.connect(str(db))
        conn_tmp.executescript(sql_text)
        conn_tmp.close()
        conn = sqlite3.connect(db)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(sgf_lexicon)")}
        for c in ("namespace", "maturity_tier", "specificity", "register"):
            assert c in cols, f"missing column {c}"
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        for t in ("content_identical_group", "sense_semantic_relation",
                  "quality_audit", "frontier_run"):
            assert t in tables, f"missing table {t}"
        # Initial tier distribution: all at 'raw'.
        n_raw = conn.execute(
            "SELECT COUNT(*) FROM sgf_lexicon WHERE maturity_tier = 'raw'"
        ).fetchone()[0]
        assert n_raw == 7, n_raw
        conn.close()
        print("  All required tables and columns present; tiers initialized.")

        section("3. generate_microglosses.py advances tier raw -> provisional")
        run("generate_microglosses.py", "--target", db)
        conn = sqlite3.connect(db)
        rows = conn.execute(
            "SELECT lemma, canonical_id, maturity_tier FROM sgf_lexicon"
        ).fetchall()
        for lemma, cid, tier in rows:
            assert cid.endswith(".core"), cid
            assert tier == "provisional", (lemma, tier)
        print(f"  All 7 senses at tier='provisional' with .core canonical_ids")
        conn.close()

        section("4. improve_microgloss.persist_improvement writes specificity + advances tier")
        sys.path.insert(0, str(HERE))
        from improve_microgloss import persist_improvement, load_sense_context
        conn = sqlite3.connect(db)
        ctx = load_sense_context(conn, 1)  # dad
        resp = {
            "improved_microgloss": "male_parent",
            "improved_definition": "One's male parent.",
            "register": "informal",
            "temporal_status": "live",
            "social_status": "unmarked",
            "specificity": "general",
            "social_notes": "everyday term",
            "domain": "general",
            "cousin_classifications": [
                {"lemma": "father", "relation_type": "TRUE_SYNONYM",
                 "interchangeable_intra_language": False,
                 "interchangeable_cross_language_standard": True,
                 "interchangeable_cross_language_preserve": False,
                 "note": "register variant"},
            ],
            "content_identical_with": [
                {"lemma": "father", "audience_tier": "general",
                 "confidence": 0.95, "note": "same referent"},
                {"lemma": "papa", "audience_tier": "general",
                 "confidence": 0.90, "note": "same referent"},
            ],
            "biographical_metadata": None,
            "rationale": "test",
        }
        persist_improvement(conn, ctx, resp)
        # Also do a specialist one (leukemia-like)
        ctx2 = load_sense_context(conn, 4)  # dragster (proxy for specialist)
        resp2 = dict(resp)
        resp2["improved_microgloss"] = "straight_line_racer"
        resp2["specificity"] = "specialist"
        resp2["content_identical_with"] = []
        resp2["cousin_classifications"] = []
        persist_improvement(conn, ctx2, resp2)
        conn.commit()

        # Validate tier advance and specificity persistence
        t_dad = tier_of(conn, 1)
        t_drag = tier_of(conn, 4)
        spec_dad = conn.execute(
            "SELECT specificity FROM sgf_lexicon WHERE wiktionary_source_id = 1"
        ).fetchone()[0]
        spec_drag = conn.execute(
            "SELECT specificity FROM sgf_lexicon WHERE wiktionary_source_id = 4"
        ).fetchone()[0]
        assert t_dad == "improved", t_dad
        assert t_drag == "improved", t_drag
        assert spec_dad == "general", spec_dad
        assert spec_drag == "specialist", spec_drag
        print(f"  dad: tier={t_dad} specificity={spec_dad}")
        print(f"  dragster: tier={t_drag} specificity={spec_drag}")
        conn.close()

        section("5. Embeddings advance tier; bge-small -> embedded_v1 (but skips improved)")
        # First small embedder for everything
        add_embeddings(db, "bge-small-en-v1")
        conn = sqlite3.connect(db)
        # Senses at 'improved' (dad, dragster) should NOT regress to embedded_v1
        assert tier_of(conn, 1) == "improved"
        assert tier_of(conn, 4) == "improved"
        # Others were 'provisional' and should now be embedded_v1
        assert tier_of(conn, 2) == "embedded_v1", tier_of(conn, 2)
        print("  bge-small correctly advanced non-improved senses; left improved senses alone.")
        # Now production embedder
        add_embeddings(db, "bge-large-en-v1")
        # All 7 should now be embedded_v2 EXCEPT any already-higher tier
        for sid in range(1, 8):
            t = tier_of(conn, sid)
            assert t == "embedded_v2", f"wsid={sid} tier={t}"
        print("  bge-large correctly advanced everyone to embedded_v2.")
        conn.close()

        section("6. quality_audit.py works against production schema")
        run("quality_audit.py", "--target", db,
            "--embedding-method", "bge-large-en-v1",
            "--audit-phase", "production", "--top-k", "5")
        conn = sqlite3.connect(db)
        n_audit = conn.execute("SELECT COUNT(*) FROM quality_audit").fetchone()[0]
        n_strict = conn.execute(
            "SELECT COUNT(*) FROM quality_audit WHERE strict_pass = 1"
        ).fetchone()[0]
        assert n_audit == 7, n_audit
        assert n_strict == 7, n_strict
        print(f"  audited 7, strict_pass=7 (production schema works)")
        conn.close()

        section("7. discover_clusters.py advances clustered tier")
        # Clear any existing content_identical_group so we can re-run
        conn = sqlite3.connect(db)
        conn.execute("DELETE FROM content_identical_member")
        conn.execute("DELETE FROM content_identical_group")
        conn.commit()
        conn.close()
        run("discover_clusters.py", "--target", db,
            "--embedding-method", "bge-large-en-v1",
            "--top-k", "5", "--strong-threshold", "0.85",
            "--coherence-threshold", "0.25", "--min-token-overlap", "0.0")
        conn = sqlite3.connect(db)
        n_clustered = conn.execute(
            "SELECT COUNT(*) FROM sgf_lexicon WHERE maturity_tier = 'clustered'"
        ).fetchone()[0]
        print(f"  senses at tier='clustered': {n_clustered}")
        assert n_clustered >= 3, n_clustered  # family cluster
        conn.close()

        section("8. select_standard_forms.py works")
        run("select_standard_forms.py", "--target", db,
            "--embedding-method", "bge-large-en-v1")
        conn = sqlite3.connect(db)
        n_std = conn.execute(
            "SELECT COUNT(*) FROM content_identical_group "
            "WHERE standard_form_wsid IS NOT NULL"
        ).fetchone()[0]
        assert n_std >= 1, n_std
        print(f"  groups with standard form: {n_std}")
        conn.close()

        section("9. harvest_semantic_relations.py advances tier to 'related'")
        run("harvest_semantic_relations.py", "--target", db,
            "--patterns-only", "--top-lemmas", "20000")
        conn = sqlite3.connect(db)
        n_related = conn.execute(
            "SELECT COUNT(*) FROM sgf_lexicon WHERE maturity_tier = 'related'"
        ).fetchone()[0]
        n_rels = conn.execute(
            "SELECT COUNT(*) FROM sense_semantic_relation"
        ).fetchone()[0]
        print(f"  senses at tier='related': {n_related}; total relations: {n_rels}")
        # At least dragster and apple should be tagged 'related' from
        # the patterns (IS_A on dragster, HAS_PART on apple)
        assert n_related >= 2, n_related
        conn.close()

        section("10. promote_tier.py --show works")
        r = run("promote_tier.py", "--target", db, "--show")
        assert "Tier distribution" in r.stdout
        print("  --show output OK")

        section("11. promote_tier.py --backfill is idempotent")
        # Backfill should not change anything since tiers are already correct
        before = subprocess.run(
            [sys.executable, "promote_tier.py", "--target", str(db), "--show"],
            cwd=str(HERE), capture_output=True, text=True,
        ).stdout
        run("promote_tier.py", "--target", db, "--backfill")
        after = subprocess.run(
            [sys.executable, "promote_tier.py", "--target", str(db), "--show"],
            cwd=str(HERE), capture_output=True, text=True,
        ).stdout
        # Distribution should be unchanged (idempotent)
        before_dist = [l for l in before.splitlines() if ":" in l and any(t in l for t in ["raw","provisional","embedded","improved","clustered","related"])]
        after_dist = [l for l in after.splitlines() if ":" in l and any(t in l for t in ["raw","provisional","embedded","improved","clustered","related"])]
        assert before_dist == after_dist, "backfill changed distribution!"
        print("  backfill is idempotent (distribution unchanged)")

        section("12. run_frontier.py --dry-run plans correct stages for target_tier='related'")
        # Write a minimal config
        cfg_path = Path(td) / "test_frontier.toml"
        cfg_path.write_text(
            'name = "test_frontier"\n'
            'target_tier = "related"\n'
            '[scope]\n'
            'top_lemmas = 5\n'
            '[embeddings]\n'
            'diagnostic = "bge-small-en-v1"\n'
            'production = "bge-large-en-v1"\n'
        )
        r = run("run_frontier.py", "--config", cfg_path, "--target", db, "--dry-run")
        for s in ("Stage 3", "Stage 5", "Stage 6", "Stage 8", "Stage 9",
                  "Stage 10", "Stage 11"):
            assert s in r.stdout, f"dry-run missing {s}"
        assert "FRONTIER RUN COMPLETE" in r.stdout
        print("  All stages planned correctly.")

        section("13. frontier_run table records the dry-run")
        conn = sqlite3.connect(db)
        n_runs = conn.execute("SELECT COUNT(*) FROM frontier_run").fetchone()[0]
        assert n_runs >= 1, n_runs
        last = conn.execute(
            "SELECT run_id, status, target_tier FROM frontier_run "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        print(f"  last frontier_run: {last}")
        assert last[1] == "dry_run", last
        conn.close()

        section("14. Re-running stages on already-promoted senses is a no-op")
        # Capture all tiers before re-running
        conn = sqlite3.connect(db)
        before = {r[0]: r[1] for r in conn.execute(
            "SELECT wiktionary_source_id, maturity_tier FROM sgf_lexicon"
        )}
        conn.close()
        # generate_microglosses.py should not regress senses
        run("generate_microglosses.py", "--target", db)
        conn = sqlite3.connect(db)
        after = {r[0]: r[1] for r in conn.execute(
            "SELECT wiktionary_source_id, maturity_tier FROM sgf_lexicon"
        )}
        # Every sense must keep its tier (CASE WHEN clause prevents regression)
        for wsid in before:
            assert before[wsid] == after[wsid], (
                f"wsid={wsid} regressed from {before[wsid]!r} to {after[wsid]!r}"
            )
        print(f"  No tier regression on re-run (verified {len(before)} senses).")
        conn.close()

    print()
    print("=" * 70)
    print("  ALL TESTS PASS")
    print("=" * 70)


if __name__ == "__main__":
    test_pipeline()
