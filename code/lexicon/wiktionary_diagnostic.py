#!/usr/bin/env python3
"""
wiktionary_diagnostic.py

Diagnose why specific lemmas have fewer senses in sgf_lexicon than expected.

Run this AGAINST wiktionary_lexicon.db (the raw Wiktextract DB) and sgf_lexicon.db
side-by-side. It compares what Wiktextract emitted to what landed in
sgf_lexicon and explains the gaps.

Usage:
    python wiktionary_diagnostic.py \\
        --source wiktionary_lexicon.db \\
        --target sgf_lexicon.db \\
        --words washington roosevelt louisiana mistake bank pig blue

For each word it prints:
    1. How many entries Wiktextract has for that word across all lang_codes
    2. How many of those are lang_code='en'
    3. For each English entry: pos, sense_count, full glosses list
    4. How many of those senses survived into sgf_lexicon
    5. Which senses were DROPPED and why

Use this to decide what to fix upstream in build_wiktionary_source.py and
build_sgf_lexicon.py.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def safe_load(blob):
    if not blob:
        return None
    try:
        return json.loads(blob)
    except (json.JSONDecodeError, TypeError):
        return None


def diagnose_word(
    src_conn: sqlite3.Connection,
    tgt_conn: sqlite3.Connection,
    word: str,
) -> None:
    print()
    print("=" * 70)
    print(f"WORD: {word!r}")
    print("=" * 70)

    # 1. All entries for this word across all languages
    src_cur = src_conn.cursor()
    src_cur.execute("""
        SELECT id, word, pos, lang_code, etymology_text
        FROM entries
        WHERE LOWER(word) = LOWER(?)
        ORDER BY lang_code, pos, id
    """, (word,))
    entries = src_cur.fetchall()

    if not entries:
        print(f"  Wiktextract has NO entries for {word!r}.")
        print(f"  This word is genuinely absent from your Wiktionary dump.")
        return

    print(f"\nWiktextract entries for {word!r}: {len(entries)}")
    by_lang: dict[str, list] = {}
    for e in entries:
        by_lang.setdefault(e[3], []).append(e)
    for lang, group in by_lang.items():
        pos_list = [g[2] for g in group]
        print(f"  lang_code={lang!r}: {len(group)} entries  pos={pos_list}")

    # 2. English entries deep dive
    en_entries = by_lang.get("en", [])
    if not en_entries:
        print(f"\n  No lang_code='en' entries. All entries are in other languages.")
        print(f"  Your build_wiktionary_source.py only loads lang_code='en',")
        print(f"  so this word will not appear in sgf_lexicon.")
        return

    print(f"\nEnglish entries: {len(en_entries)}")
    total_senses_in_source = 0
    glosses_per_sense: dict[int, list[str]] = {}
    for ent_id, w, pos, lc, etym in en_entries:
        print(f"\n  entry_id={ent_id}  pos={pos!r}")
        # Senses under this entry
        s_cur = src_conn.cursor()
        s_cur.execute("""
            SELECT id, sense_index, glosses_json, raw_glosses_json,
                   tags_json, categories_json
            FROM senses
            WHERE entry_id = ?
            ORDER BY sense_index
        """, (ent_id,))
        senses = s_cur.fetchall()
        total_senses_in_source += len(senses)
        print(f"    senses in source: {len(senses)}")
        for s_id, s_idx, g_json, rg_json, t_json, c_json in senses:
            glosses = safe_load(g_json) or []
            raw_glosses = safe_load(rg_json) or []
            tags = safe_load(t_json) or []
            preferred = raw_glosses[0] if raw_glosses else (glosses[0] if glosses else None)
            extras = []
            if len(raw_glosses) > 1:
                extras.append(f"+{len(raw_glosses)-1} more raw_glosses")
            if not raw_glosses and len(glosses) > 1:
                extras.append(f"+{len(glosses)-1} more glosses")
            glosses_per_sense[s_id] = list(raw_glosses) if raw_glosses else list(glosses)
            extras_str = (" (" + ", ".join(extras) + ")") if extras else ""
            tags_str = f"  tags={tags}" if tags else ""
            print(f"      sense_id={s_id} idx={s_idx}: {preferred!r}{extras_str}{tags_str}")

    print(f"\n  Total English senses in source: {total_senses_in_source}")

    # 3. What landed in sgf_lexicon
    tgt_cur = tgt_conn.cursor()
    tgt_cur.execute("""
        SELECT sl.wiktionary_source_id, sl.lemma, sl.pos_wiktionary,
               sl.pos_simple, sl.gloss, sl.microgloss, sl.canonical_id
        FROM sgf_lexicon sl
        WHERE LOWER(sl.lemma) = LOWER(?)
        ORDER BY sl.wiktionary_source_id
    """, (word,))
    sgf_rows = tgt_cur.fetchall()
    print(f"\n  Senses landed in sgf_lexicon: {len(sgf_rows)}")
    landed_ids: set[int] = set()
    for row in sgf_rows:
        src_id, lemma, pos_w, pos_s, gloss, mg, cid = row
        landed_ids.add(src_id)
        print(f"      src_sense_id={src_id} pos_simple={pos_s} gloss={gloss[:80]!r}")

    # 4. Gap analysis
    expected_ids = set(glosses_per_sense.keys())
    missing_ids = expected_ids - landed_ids
    if missing_ids:
        print(f"\n  GAP: {len(missing_ids)} source senses did not make it into sgf_lexicon:")
        for sid in sorted(missing_ids):
            tgt_cur.execute(
                "SELECT first_gloss, glosses_json, raw_glosses_json, tags_json, pos "
                "FROM wiktionary_source WHERE source_sense_id = ?",
                (sid,),
            )
            ws_row = tgt_cur.fetchone()
            if ws_row is None:
                print(f"      src_sense_id={sid}: NOT in wiktionary_source either")
                print(f"        -> this means build_wiktionary_source.py skipped it,")
                print(f"           probably because lang_code != 'en' was filtered out")
                continue
            fg, gj, rgj, tj, p = ws_row
            if not fg:
                print(f"      src_sense_id={sid}: in wiktionary_source but first_gloss is NULL")
                print(f"        glosses_json={gj!r}")
                print(f"        raw_glosses_json={rgj!r}")
                print(f"        -> build_sgf_lexicon.py drops rows where first_gloss is empty.")
                continue
            print(f"      src_sense_id={sid}: in wiktionary_source, first_gloss={fg!r}")
            print(f"        BUT did not make it to sgf_lexicon. Check resume-skip and PK conflicts.")
    else:
        print(f"\n  All source senses landed. No gap in projection.")

    # 5. Extra gloss bullets that got dropped
    multi_gloss_senses = [(sid, gs) for sid, gs in glosses_per_sense.items() if len(gs) > 1]
    if multi_gloss_senses:
        print(f"\n  Senses with multiple gloss bullets (we only kept the first):")
        for sid, gs in multi_gloss_senses:
            print(f"      src_sense_id={sid}: {len(gs)} bullets")
            for i, g in enumerate(gs):
                tag = "[KEPT]" if i == 0 else "[DROPPED]"
                print(f"        {tag} {g[:120]!r}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source", default="wiktionary_lexicon.db",
                   help="Raw Wiktextract wiktionary_lexicon.db (produced by load_wiktionary_jsonl.py)")
    p.add_argument("--target", default="sgf_lexicon.db",
                   help="Projected sgf_lexicon.db")
    p.add_argument("--words", nargs="+", required=True,
                   help="Words to diagnose")
    args = p.parse_args()

    src_path = Path(args.source)
    tgt_path = Path(args.target)
    if not src_path.exists():
        print(f"wiktionary_lexicon.db not found: {src_path}", file=sys.stderr)
        return 1
    if not tgt_path.exists():
        print(f"sgf_lexicon.db not found: {tgt_path}", file=sys.stderr)
        return 1

    src_conn = sqlite3.connect(src_path)
    src_conn.execute("PRAGMA query_only = ON")
    tgt_conn = sqlite3.connect(tgt_path)
    tgt_conn.execute("PRAGMA query_only = ON")

    try:
        for word in args.words:
            diagnose_word(src_conn, tgt_conn, word)
    finally:
        src_conn.close()
        tgt_conn.close()

    print()
    print("=" * 70)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 70)
    print("Common causes of missing senses:")
    print("  1. Wiktextract did not emit that sense at all (rare).")
    print("  2. The sense lives under lang_code != 'en' and was filtered out.")
    print("  3. The sense's first_gloss is NULL and build_sgf_lexicon.py")
    print("     drops it because the WHERE clause requires non-empty gloss.")
    print("  4. The sense is one of N gloss bullets under a single sense_id,")
    print("     and we only kept bullet 0 via extract_first_gloss().")
    print("  5. The lemma is a Proper noun and the relevant POS block was")
    print("     emitted under a different lang_code or skipped by Wiktextract.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
