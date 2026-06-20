#!/usr/bin/env python3
"""
build_embedding_texts.py

Stage 4 (--pass v1) and Stage 7 (--pass v2) of the SGF lexicon pipeline.

Builds the structured embedding_text for each sgf_lexicon row.

PASSES
------
--pass v1   First-pass embedding_text. Built from Wiktionary fields +
            metadata (register, temporal_status, social_status).
            No LLM enrichment included. Output written to
            embedding_text_v1 column.

--pass v2   Production embedding_text. Same as v1 but ALSO appends
            LLM enrichment fields (sense_summary, core_meaning, etc.)
            from the most recent sense_enrichment row if available. Output written to
            embedding_text_v2 column.

WHEN TO USE EACH
----------------
After Stage 3 (generate_microglosses.py), run:
    build_embedding_texts.py --pass v1
to assemble the first-pass embedding_text that the improver will use
for cousin discovery.

After Stage 6 (improve_microgloss.py), run:
    build_embedding_texts.py --pass v2
to incorporate the improver's enrichment into the production embedding_text.

FORMAT
------
v1 embedding_text (pipe-delimited):

  iso_lang:en
  lemma:<lemma>
  microgloss:<microgloss>
  pos:<pos_simple>
  gloss:<gloss, truncated to 240 chars>
  register:<register>
  temporal:<temporal_status>
  social:<social_status>
  [tags:<comma-separated semantic tags>]
  [synonyms:<from Wiktionary linkages>]
  [example:<one Wiktionary example>]

v2 embedding_text: v1 fields PLUS appended enrichment fields:

  [enrich_summary:...]
  [enrich_core:...]
  [enrich_cooccur:...]
  [enrich_uses:...]
  [enrich_synonyms:...]
  [enrich_isa:...]
  [enrich_domain:...]

SIDE EFFECTS
------------
For any row whose embedding_text just changed, this script DELETES any
existing sense_embedding rows for that wsid. This ensures
compute_embeddings.py re-embeds the row on its next run.

USAGE
-----
    python build_embedding_texts.py --target sgf_lexicon.db --pass v1
    python build_embedding_texts.py --target sgf_lexicon.db --pass v2
    python build_embedding_texts.py --target sgf_lexicon.db --pass v1 --limit 1000
    python build_embedding_texts.py --target sgf_lexicon.db --pass v1 --dry-run
"""

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

EMBEDDING_TEXT_VERSION_V1 = "v2-meta-v1"   # v1 format with metadata included
EMBEDDING_TEXT_VERSION_V2 = "v2-enriched"  # v1 + enrichment fields

BATCH_SIZE = 5000

GLOSS_MAX_CHARS = 600
EXAMPLE_MAX_CHARS = 160
MAX_SYNONYMS = 15
MAX_EXAMPLES = 4
MAX_ANTONYMS = 8
MAX_HYPERNYMS = 6
MAX_HYPONYMS = 8
MAX_RELATED = 8
MAX_COORDINATE_TERMS = 8

# Per-enrichment-field truncation
ENRICH_SUMMARY_MAX = 200
ENRICH_CORE_MAX = 400
ENRICH_COOCCUR_MAX = 200
ENRICH_USES_MAX = 500
ENRICH_SYNONYMS_MAX = 200
ENRICH_ISA_MAX = 120
ENRICH_DOMAIN_MAX = 60

# Wiktionary topic / tag values that carry domain/semantic signal
SEMANTIC_TAGS = frozenset({
    "medicine", "medical", "anatomy", "biology", "botany", "zoology",
    "chemistry", "physics", "mathematics", "geometry", "statistics",
    "computing", "programming", "electronics", "engineering",
    "law", "legal", "finance", "economics", "accounting", "business",
    "music", "art", "literature", "linguistics", "grammar", "rhetoric",
    "military", "weapons", "nautical", "aviation", "automotive",
    "sports", "games", "chess", "cards",
    "religion", "christianity", "judaism", "islam", "buddhism", "hinduism",
    "philosophy", "psychology", "sociology", "anthropology",
    "cooking", "food", "agriculture", "horticulture",
    "geography", "geology", "astronomy", "meteorology",
    "architecture", "construction", "carpentry", "masonry",
})


# ===========================================================================
# Schema bootstrapping
# ===========================================================================

def ensure_v2_schema(conn):
    """Verify that v2 columns exist. Fail loudly if migration wasn't run."""
    cur = conn.execute("PRAGMA table_info(sgf_lexicon)")
    cols = {row[1] for row in cur.fetchall()}
    required = {
        "embedding_text_v1", "embedding_text_v1_version", "embedding_text_v1_built_at",
        "embedding_text_v2", "embedding_text_v2_version", "embedding_text_v2_built_at",
        "embedding_text_needs_rebuild",
        "register", "temporal_status", "social_status",
    }
    missing = required - cols
    if missing:
        print(f"ERROR: target DB is missing v2 columns: {sorted(missing)}",
              file=sys.stderr)
        print("Run: python apply_schema.py --target <your-db>",
              file=sys.stderr)
        sys.exit(1)


# ===========================================================================
# Text utilities
# ===========================================================================

def truncate(s, max_chars):
    if not s:
        return ""
    s = str(s)
    if len(s) <= max_chars:
        return s
    cut = s[:max_chars]
    last_space = cut.rfind(" ")
    if last_space > max_chars // 2:
        cut = cut[:last_space]
    return cut.rstrip(" ,.;:-") + "..."


def sanitize_for_pipe(s):
    """Replace pipes and newlines with spaces (preserve pipe-delim structure)."""
    if not s:
        return ""
    return str(s).replace("|", " ").replace("\n", " ").replace("\r", " ").strip()


def parse_json_list(blob):
    if not blob:
        return []
    try:
        v = json.loads(blob)
    except (json.JSONDecodeError, TypeError):
        return []
    return v if isinstance(v, list) else []


def extract_semantic_tags(tags_json, topics_json):
    keep = set()
    for blob in (tags_json, topics_json):
        for item in parse_json_list(blob):
            if isinstance(item, str):
                low = item.lower().strip()
                if low in SEMANTIC_TAGS:
                    keep.add(low)
    return sorted(keep)


def extract_examples(examples_json, limit=MAX_EXAMPLES):
    out = []
    for ex in parse_json_list(examples_json):
        if isinstance(ex, str):
            text = ex.strip()
        elif isinstance(ex, dict):
            if ex.get("type") == "quotation":
                continue
            text = (ex.get("text") or ex.get("english") or "").strip()
        else:
            continue
        if text:
            out.append(truncate(text, EXAMPLE_MAX_CHARS))
            if len(out) >= limit:
                break
    return out


def extract_example(examples_json):
    """Backwards-compat single-example accessor."""
    examples = extract_examples(examples_json, limit=1)
    return examples[0] if examples else ""


def bulk_load_synonyms_from_target(conn):
    """If the linkages live in a separate wiktionary_lexicon DB you must
    pass it via --wiktionary-source. Otherwise we use what's in the
    target's wiktionary_source.linkages_json column.

    Returns dict[int, list[str]].
    """
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT source_sense_id, linkages_json
            FROM wiktionary_source
            WHERE linkages_json IS NOT NULL AND linkages_json != ''
        """)
    except sqlite3.OperationalError:
        return {}

    out = {}
    for sid, blob in cur:
        try:
            parsed = json.loads(blob)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(parsed, list):
            continue
        syns = []
        for item in parsed:
            if isinstance(item, dict):
                t = item.get("type") or item.get("linkage_type")
                w = item.get("word")
                if t == "synonyms" and w and w not in syns:
                    syns.append(w)
                    if len(syns) >= MAX_SYNONYMS:
                        break
        if syns:
            out[sid] = syns
    return out


# Linkage types we extract from Wiktionary. Each maps to a max count and
# the label we use in the embedding text (`<label>:term,term,...`).
_LINKAGE_TYPES = (
    ("synonyms",         MAX_SYNONYMS,         "synonyms"),
    ("antonyms",         MAX_ANTONYMS,         "antonyms"),
    ("hypernyms",        MAX_HYPERNYMS,        "hypernyms"),
    ("hyponyms",         MAX_HYPONYMS,         "hyponyms"),
    ("related",          MAX_RELATED,          "related"),
    ("coordinate_terms", MAX_COORDINATE_TERMS, "coords"),
)


def bulk_load_linkages_from_target(conn):
    """Load all linkage types from wiktionary_source.linkages_json.

    Returns dict[int, dict[str, list[str]]]:
        {source_sense_id: {"synonyms": [...], "antonyms": [...], ...}}
    """
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT source_sense_id, linkages_json
            FROM wiktionary_source
            WHERE linkages_json IS NOT NULL AND linkages_json != ''
        """)
    except sqlite3.OperationalError:
        return {}

    type_caps = {t[0]: t[1] for t in _LINKAGE_TYPES}
    wanted_types = set(type_caps.keys())

    out = {}
    for sid, blob in cur:
        try:
            parsed = json.loads(blob)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(parsed, list):
            continue
        by_type = {}
        for item in parsed:
            if not isinstance(item, dict):
                continue
            t = item.get("type") or item.get("linkage_type")
            if t not in wanted_types:
                continue
            w = item.get("word")
            if not w:
                continue
            bucket = by_type.setdefault(t, [])
            if w in bucket:
                continue
            if len(bucket) >= type_caps[t]:
                continue
            bucket.append(w)
        if by_type:
            out[sid] = by_type
    return out


# ===========================================================================
# Enrichment text parsing (v4 schema)
# ===========================================================================

def parse_v4_enrichment_row(row):
    """Parse a sense_enrichment v4 row tuple into a dict of enrichment fields."""
    (improved_microgloss, improved_definition,
     register, temporal_status, social_status,
     social_notes, domain, biographical_metadata_json, rationale) = row

    fields = {
        "sense_summary":  improved_definition or "",
        "core_meaning":   improved_definition or "",
        "cooccurrences":  "",
        "typical_uses":   "",
        "synonyms":       "",
        "is_a_chain":     "",
        "domain":         domain or "",
    }
    return fields


def parse_v3_enrichment_text(enrichment_text):
    """Parse the v3 enrichment_text labelled-lines format into a dict."""
    fields = {
        "sense_summary":  "", "core_meaning":   "", "cooccurrences":  "",
        "typical_uses":   "", "synonyms":       "", "is_a_chain":     "",
        "domain":         "",
    }
    if not enrichment_text:
        return fields

    known_labels = set(fields.keys())
    current = None
    buf = []

    def flush():
        if current is None:
            return
        joined = " ".join(buf).strip()
        if joined:
            existing = fields.get(current, "")
            fields[current] = (existing + " " + joined).strip() if existing else joined

    for raw in enrichment_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if ":" in line:
            head, _, tail = line.partition(":")
            label = head.strip().lower().replace(" ", "_")
            if label in known_labels:
                flush()
                current = label
                buf = [tail.strip()] if tail.strip() else []
                continue
        if current is not None:
            buf.append(line)
    flush()
    return fields


# ===========================================================================
# Text assembly
# ===========================================================================

def build_text(lemma, pos_simple, microgloss, gloss,
               register, temporal_status, social_status,
               tags_json, topics_json, examples_json,
               synonyms, enrichment_fields=None, linkages=None):
    """Assemble the structured embedding_text. Returns the final string.

    enrichment_fields=None  -> v1 format (no enrichment appended)
    enrichment_fields=dict  -> v2 format (enrichment fields appended)
    """
    # The canonical microgloss uses underscores (so the canonical_id
    # `lang.lemma.microgloss.pos.namespace` parses cleanly). The embedder,
    # however, was trained on natural English, so we feed it a spaced
    # version. canonical_ids stay untouched everywhere they are read.
    microgloss_for_embed = microgloss.replace("_", " ") if microgloss else microgloss

    parts = [
        "iso_lang:en",
        f"lemma:{sanitize_for_pipe(lemma)}",
        f"microgloss:{sanitize_for_pipe(microgloss_for_embed)}",
        f"pos:{sanitize_for_pipe(pos_simple)}",
        f"gloss:{sanitize_for_pipe(truncate(gloss, GLOSS_MAX_CHARS))}",
        f"register:{sanitize_for_pipe(register or 'neutral')}",
        f"temporal:{sanitize_for_pipe(temporal_status or 'live')}",
        f"social:{sanitize_for_pipe(social_status or 'unmarked')}",
    ]

    sem_tags = extract_semantic_tags(tags_json, topics_json)
    if sem_tags:
        parts.append(f"tags:{','.join(sem_tags)}")

    # Linkages: prefer the structured `linkages` dict if provided
    # (covers all linkage types). Else fall back to legacy `synonyms`.
    if linkages:
        for t, cap, label in _LINKAGE_TYPES:
            vals = linkages.get(t) or []
            clean = [s.strip() for s in vals if s and s.strip()][:cap]
            if clean:
                parts.append(
                    f"{label}:{','.join(sanitize_for_pipe(s) for s in clean)}")
    elif synonyms:
        clean = [s.strip() for s in synonyms if s and s.strip()][:MAX_SYNONYMS]
        if clean:
            parts.append(f"synonyms:{','.join(sanitize_for_pipe(s) for s in clean)}")

    examples = extract_examples(examples_json, limit=MAX_EXAMPLES)
    for i, ex_text in enumerate(examples):
        label = "example" if i == 0 else f"example_{i+1}"
        parts.append(f"{label}:{sanitize_for_pipe(ex_text)}")

    # v2 format: append enrichment fields
    if enrichment_fields:
        e = enrichment_fields
        if e.get("sense_summary"):
            parts.append(f"enrich_summary:{sanitize_for_pipe(truncate(e['sense_summary'], ENRICH_SUMMARY_MAX))}")
        if e.get("core_meaning") and e.get("core_meaning") != e.get("sense_summary"):
            parts.append(f"enrich_core:{sanitize_for_pipe(truncate(e['core_meaning'], ENRICH_CORE_MAX))}")
        if e.get("cooccurrences"):
            parts.append(f"enrich_cooccur:{sanitize_for_pipe(truncate(e['cooccurrences'], ENRICH_COOCCUR_MAX))}")
        if e.get("typical_uses"):
            parts.append(f"enrich_uses:{sanitize_for_pipe(truncate(e['typical_uses'], ENRICH_USES_MAX))}")
        if e.get("synonyms"):
            parts.append(f"enrich_synonyms:{sanitize_for_pipe(truncate(e['synonyms'], ENRICH_SYNONYMS_MAX))}")
        if e.get("is_a_chain"):
            parts.append(f"enrich_isa:{sanitize_for_pipe(truncate(e['is_a_chain'], ENRICH_ISA_MAX))}")
        if e.get("domain"):
            parts.append(f"enrich_domain:{sanitize_for_pipe(truncate(e['domain'], ENRICH_DOMAIN_MAX))}")

    return "|".join(parts)


# ===========================================================================
# Pending-row selection
# ===========================================================================

def materialize_pending(conn, pass_mode, limit):
    """Pull pending rows into memory. pass_mode is 'v1' or 'v2'."""
    print("  materializing pending rows into memory...")
    t0 = time.time()

    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='wiktionary_source'")
    has_ws = cur.fetchone() is not None

    target_col = "embedding_text_v1" if pass_mode == "v1" else "embedding_text_v2"
    target_ver = EMBEDDING_TEXT_VERSION_V1 if pass_mode == "v1" else EMBEDDING_TEXT_VERSION_V2

    if pass_mode == "v1":
        # v1 pass: rebuild rows where v1 is missing or stale, OR where the
        # needs_rebuild flag is set
        where_clause = f"""
            sl.microgloss IS NOT NULL
            AND (
                sl.embedding_text_v1 IS NULL
                OR sl.embedding_text_v1_version IS NULL
                OR sl.embedding_text_v1_version != '{target_ver}'
                OR sl.embedding_text_needs_rebuild = 1
            )
        """
        ws_join = ""
        ws_cols = "NULL, NULL, NULL, NULL"
        if has_ws:
            ws_join = "LEFT JOIN wiktionary_source ws ON ws.source_sense_id = sl.wiktionary_source_id"
            ws_cols = "ws.tags_json, ws.topics_json, ws.examples_json, ws.linkages_json"

        # v1 pass returns no enrichment data; pad with 9 NULLs to match
        # the v2 SELECT's 9 enrichment columns (improved_microgloss,
        # improved_definition, register, temporal_status, social_status,
        # social_notes, domain, biographical_metadata_json, rationale).
        # If you add or remove an enrichment column, update BOTH the
        # v2 SELECT and this NULL-padding count in lockstep, or the
        # unpack in run() will throw ValueError.
        sql = f"""
            SELECT
                sl.wiktionary_source_id,
                sl.lemma, sl.pos_simple, sl.microgloss, sl.gloss,
                sl.register, sl.temporal_status, sl.social_status,
                {ws_cols},
                NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
            FROM sgf_lexicon sl
            {ws_join}
            WHERE {where_clause}
        """
    else:
        # v2 pass: same as v1 PLUS join sense_enrichment for v4 or v3 fields
        where_clause = f"""
            sl.microgloss IS NOT NULL
            AND (
                sl.embedding_text_v2 IS NULL
                OR sl.embedding_text_v2_version IS NULL
                OR sl.embedding_text_v2_version != '{target_ver}'
                OR sl.embedding_text_needs_rebuild = 1
            )
        """
        ws_join = ""
        ws_cols = "NULL, NULL, NULL, NULL"
        if has_ws:
            ws_join = "LEFT JOIN wiktionary_source ws ON ws.source_sense_id = sl.wiktionary_source_id"
            ws_cols = "ws.tags_json, ws.topics_json, ws.examples_json, ws.linkages_json"

        sql = f"""
            SELECT
                sl.wiktionary_source_id,
                sl.lemma, sl.pos_simple, sl.microgloss, sl.gloss,
                sl.register, sl.temporal_status, sl.social_status,
                {ws_cols},
                se4.improved_microgloss, se4.improved_definition,
                se4.register, se4.temporal_status, se4.social_status,
                se4.social_notes, se4.domain,
                se4.biographical_metadata_json, se4.rationale
            FROM sgf_lexicon sl
            {ws_join}
            LEFT JOIN sense_enrichment se4
                ON se4.source_sense_id = sl.wiktionary_source_id
                AND se4.enrichment_version = 'v4'
                AND se4.improved_microgloss IS NOT NULL
            WHERE {where_clause}
        """

    if limit:
        sql += f" LIMIT {int(limit)}"

    cur.execute(sql)
    rows = cur.fetchall()
    elapsed = time.time() - t0
    print(f"  materialized {len(rows):,} rows ({elapsed:.1f}s)")
    return rows


def count_pending(conn, pass_mode):
    target_ver = EMBEDDING_TEXT_VERSION_V1 if pass_mode == "v1" else EMBEDDING_TEXT_VERSION_V2
    target_col = "embedding_text_v1" if pass_mode == "v1" else "embedding_text_v2"
    ver_col = "embedding_text_v1_version" if pass_mode == "v1" else "embedding_text_v2_version"
    cur = conn.execute(f"""
        SELECT COUNT(*) FROM sgf_lexicon
        WHERE microgloss IS NOT NULL
          AND (
            {target_col} IS NULL
            OR {ver_col} IS NULL
            OR {ver_col} != ?
            OR embedding_text_needs_rebuild = 1
          )
    """, (target_ver,))
    return cur.fetchone()[0]


# ===========================================================================
# Build loop
# ===========================================================================

def run(conn, link_map, rows, pass_mode, dry_run):
    """link_map: dict[int, dict[str, list[str]]] -- per-sense linkages."""
    write_cur = conn.cursor()
    processed = 0
    n_enriched = 0
    t_start = time.time()
    last_report = t_start
    update_batch = []

    target_col = "embedding_text_v1" if pass_mode == "v1" else "embedding_text_v2"
    ver_col = "embedding_text_v1_version" if pass_mode == "v1" else "embedding_text_v2_version"
    ts_col = "embedding_text_v1_built_at" if pass_mode == "v1" else "embedding_text_v2_built_at"
    target_ver = EMBEDDING_TEXT_VERSION_V1 if pass_mode == "v1" else EMBEDDING_TEXT_VERSION_V2
    n_total = len(rows)
    now_ts = int(time.time())

    for row in rows:
        (wsid, lemma, pos_simple, microgloss, gloss,
         register, temporal_status, social_status,
         tags_json, topics_json, examples_json, linkages_json,
         improved_microgloss, improved_definition,
         e_register, e_temporal, e_social,
         social_notes, domain,
         biographical_metadata_json, rationale) = row

        # For v2 pass: use improved values if present
        if pass_mode == "v2" and improved_microgloss:
            microgloss = improved_microgloss
            if e_register:
                register = e_register
            if e_temporal:
                temporal_status = e_temporal
            if e_social:
                social_status = e_social

        linkages = link_map.get(wsid) if link_map else None
        synonyms = (linkages or {}).get("synonyms", []) if linkages else []

        enrichment_fields = None
        if pass_mode == "v2" and improved_microgloss:
            enrichment_fields = parse_v4_enrichment_row((
                improved_microgloss, improved_definition,
                e_register, e_temporal, e_social,
                social_notes, domain, biographical_metadata_json, rationale,
            ))
            n_enriched += 1

        text = build_text(
            lemma=lemma, pos_simple=pos_simple,
            microgloss=microgloss, gloss=gloss,
            register=register, temporal_status=temporal_status,
            social_status=social_status,
            tags_json=tags_json, topics_json=topics_json,
            examples_json=examples_json,
            synonyms=synonyms,
            enrichment_fields=enrichment_fields,
            linkages=linkages,
        )

        update_batch.append((text, target_ver, now_ts, wsid))
        processed += 1

        if len(update_batch) >= BATCH_SIZE:
            if not dry_run:
                _flush(conn, write_cur, target_col, ver_col, ts_col, update_batch, pass_mode)
            update_batch = []

            now = time.time()
            if now - last_report >= 2.0:
                elapsed = now - t_start
                rate = processed / elapsed if elapsed > 0 else 0
                eta_min = (n_total - processed) / rate / 60 if rate > 0 else 0
                print(f"  built {processed:,}/{n_total:,} "
                      f"({100.0 * processed / n_total:.1f}%)  "
                      f"{rate:,.0f} rows/s  ETA {eta_min:.1f} min")
                last_report = now

    if update_batch and not dry_run:
        _flush(conn, write_cur, target_col, ver_col, ts_col, update_batch, pass_mode)

    return processed, n_enriched


def _flush(conn, cur, target_col, ver_col, ts_col, batch, pass_mode):
    """Write one batch. For v2 pass, also clear needs_rebuild flag and delete
    stale sense_embedding rows."""
    cur.executemany(f"""
        UPDATE sgf_lexicon
        SET {target_col} = ?,
            {ver_col} = ?,
            {ts_col} = ?
        WHERE wiktionary_source_id = ?
    """, batch)

    if pass_mode == "v2":
        # On v2 pass, clear the needs_rebuild flag and delete stale embeddings
        wsids = [b[3] for b in batch]
        placeholders = ",".join("?" * len(wsids))
        cur.execute(
            f"UPDATE sgf_lexicon SET embedding_text_needs_rebuild = 0 "
            f"WHERE wiktionary_source_id IN ({placeholders})",
            wsids,
        )
        cur.executemany(
            "DELETE FROM sense_embedding WHERE wiktionary_source_id = ?",
            [(w,) for w in wsids],
        )
    conn.commit()


# ===========================================================================
# Diagnostic: --show-embedding-text
# ===========================================================================

def show_embedding_text_main(args):
    """Print the embedding text for one lexicon entry and exit.

    Looks up the entry by canonical_id or by integer wsid, builds the v1
    and v2 embedding texts in-memory from current DB state, and prints
    them alongside the stored values (if any). Useful for diagnosing why
    a search query matched (or failed to match) a given sense.
    """
    db_path = Path(args.target)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    key = args.show_embedding_text.strip()
    conn = sqlite3.connect(db_path)
    try:
        # Resolve key -> wsid. Accept an integer wsid or a canonical_id.
        wsid = None
        if key.isdigit():
            wsid = int(key)
            row = conn.execute(
                "SELECT 1 FROM sgf_lexicon WHERE wiktionary_source_id = ?",
                (wsid,)).fetchone()
            if not row:
                print(f"No entry found for wsid={wsid}", file=sys.stderr)
                return 2
        else:
            row = conn.execute(
                "SELECT wiktionary_source_id FROM sgf_lexicon "
                "WHERE canonical_id = ?", (key,)).fetchone()
            if not row:
                print(f"No entry found for canonical_id={key!r}",
                      file=sys.stderr)
                return 2
            wsid = int(row[0])

        cur = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='wiktionary_source'")
        has_ws = cur.fetchone() is not None
        ws_cols = ("ws.tags_json, ws.topics_json, ws.examples_json"
                   if has_ws else "NULL, NULL, NULL")
        ws_join = ("LEFT JOIN wiktionary_source ws "
                   "ON ws.source_sense_id = sl.wiktionary_source_id"
                   if has_ws else "")
        sl_row = conn.execute(f"""
            SELECT
                sl.canonical_id,
                sl.lemma, sl.pos_simple, sl.microgloss, sl.gloss,
                sl.register, sl.temporal_status, sl.social_status,
                {ws_cols},
                sl.embedding_text_v1, sl.embedding_text_v1_version,
                sl.embedding_text_v2, sl.embedding_text_v2_version
            FROM sgf_lexicon sl
            {ws_join}
            WHERE sl.wiktionary_source_id = ?
        """, (wsid,)).fetchone()
        if not sl_row:
            print(f"No row returned for wsid={wsid}", file=sys.stderr)
            return 2

        (canonical_id, lemma, pos_simple, microgloss, gloss,
         register, temporal_status, social_status,
         tags_json, topics_json, examples_json,
         stored_v1, stored_v1_ver, stored_v2, stored_v2_ver) = sl_row

        # Pull linkages for this single wsid.
        linkages = None
        if has_ws:
            lk_row = conn.execute(
                "SELECT linkages_json FROM wiktionary_source "
                "WHERE source_sense_id = ?", (wsid,)).fetchone()
            if lk_row and lk_row[0]:
                type_caps = {t[0]: t[1] for t in _LINKAGE_TYPES}
                wanted_types = set(type_caps.keys())
                try:
                    parsed = json.loads(lk_row[0])
                except (json.JSONDecodeError, TypeError):
                    parsed = []
                if isinstance(parsed, list):
                    by_type = {}
                    for item in parsed:
                        if not isinstance(item, dict):
                            continue
                        t = item.get("type") or item.get("linkage_type")
                        if t not in wanted_types:
                            continue
                        w = item.get("word")
                        if not w:
                            continue
                        bucket = by_type.setdefault(t, [])
                        if w in bucket or len(bucket) >= type_caps[t]:
                            continue
                        bucket.append(w)
                    linkages = by_type if by_type else None

        # Pull v4 enrichment if present (for v2 build).
        enrichment_fields = None
        e_row = conn.execute("""
            SELECT improved_microgloss, improved_definition,
                   register, temporal_status, social_status,
                   social_notes, domain,
                   biographical_metadata_json, rationale
            FROM sense_enrichment
            WHERE source_sense_id = ?
              AND enrichment_version = 'v4'
              AND improved_microgloss IS NOT NULL
            ORDER BY rowid DESC LIMIT 1
        """, (wsid,)).fetchone()
        microgloss_v2 = microgloss
        register_v2 = register
        temporal_v2 = temporal_status
        social_v2 = social_status
        if e_row:
            (imp_mg, imp_def, e_reg, e_tmp, e_soc,
             e_notes, e_dom, e_bio, e_rat) = e_row
            if imp_mg:
                microgloss_v2 = imp_mg
            if e_reg:
                register_v2 = e_reg
            if e_tmp:
                temporal_v2 = e_tmp
            if e_soc:
                social_v2 = e_soc
            enrichment_fields = parse_v4_enrichment_row(e_row)

        synonyms = (linkages or {}).get("synonyms", []) if linkages else []

        text_v1 = build_text(
            lemma=lemma, pos_simple=pos_simple,
            microgloss=microgloss, gloss=gloss,
            register=register, temporal_status=temporal_status,
            social_status=social_status,
            tags_json=tags_json, topics_json=topics_json,
            examples_json=examples_json,
            synonyms=synonyms,
            enrichment_fields=None,
            linkages=linkages,
        )
        text_v2 = build_text(
            lemma=lemma, pos_simple=pos_simple,
            microgloss=microgloss_v2, gloss=gloss,
            register=register_v2, temporal_status=temporal_v2,
            social_status=social_v2,
            tags_json=tags_json, topics_json=topics_json,
            examples_json=examples_json,
            synonyms=synonyms,
            enrichment_fields=enrichment_fields,
            linkages=linkages,
        )

        link_summary = "none"
        if linkages:
            link_summary = ", ".join(
                f"{t}={len(v)}" for t, v in sorted(linkages.items()))

        print("=" * 60)
        print(f"canonical_id : {canonical_id}")
        print(f"wsid         : {wsid}")
        print(f"lemma        : {lemma}  pos: {pos_simple}")
        print(f"microgloss   : {microgloss}")
        if microgloss_v2 != microgloss:
            print(f"  (v2 improved : {microgloss_v2})")
        print(f"register     : {register or 'neutral'}  "
              f"temporal: {temporal_status or 'live'}  "
              f"social: {social_status or 'unmarked'}")
        print(f"linkages     : {link_summary}")
        print("=" * 60)
        print("\n--- BUILT v1 (current code) ---")
        print(text_v1)
        print(f"\n  length: {len(text_v1):,} chars, "
              f"{text_v1.count('|') + 1} fields")

        if stored_v1 and stored_v1 != text_v1:
            print("\n--- STORED v1 (stale; rerun --pass v1) ---")
            print(stored_v1)
            print(f"  version: {stored_v1_ver}")
        elif stored_v1:
            print("\n  stored v1 matches built v1")
        else:
            print("\n  no stored v1 yet (run --pass v1)")

        print("\n--- BUILT v2 (current code) ---")
        print(text_v2)
        print(f"\n  length: {len(text_v2):,} chars, "
              f"{text_v2.count('|') + 1} fields")

        if stored_v2 and stored_v2 != text_v2:
            print("\n--- STORED v2 (stale; rerun --pass v2) ---")
            print(stored_v2)
            print(f"  version: {stored_v2_ver}")
        elif stored_v2:
            print("\n  stored v2 matches built v2")
        else:
            print("\n  no stored v2 yet (run --pass v2)")

        return 0
    finally:
        conn.close()


# ===========================================================================
# Main
# ===========================================================================

def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[3])
    p.add_argument("--target", default="sgf_lexicon.db")
    p.add_argument("--pass", dest="pass_mode", required=False,
                   choices=["v1", "v2"], default=None,
                   help="v1 = first-pass (no LLM enrichment); v2 = production (with enrichment)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--dry-run", action="store_true",
                   help="Print 5 sample texts and exit without writing.")
    p.add_argument("--show-embedding-text", dest="show_embedding_text",
                   metavar="CANONICAL_ID_OR_WSID", default=None,
                   help="Diagnostic: print the embedding text for one entry "
                        "and exit. Accepts a canonical_id or an integer wsid.")
    args = p.parse_args()

    if args.show_embedding_text is not None:
        return show_embedding_text_main(args)

    if args.pass_mode is None:
        p.error("--pass is required (v1 or v2) unless --show-embedding-text is used")

    db_path = Path(args.target)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    print(f"Target: {db_path.resolve()}")
    print(f"Pass:   {args.pass_mode}")
    print(f"Version tag: "
          + (EMBEDDING_TEXT_VERSION_V1 if args.pass_mode == "v1"
             else EMBEDDING_TEXT_VERSION_V2))
    print()

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 30000")

    try:
        ensure_v2_schema(conn)

        pending = count_pending(conn, args.pass_mode)
        print(f"Rows pending {args.pass_mode}: {pending:,}")
        print()

        if pending == 0:
            print("Nothing to do.")
            return 0

        link_map = bulk_load_linkages_from_target(conn)
        if link_map:
            type_counts = {}
            for by_type in link_map.values():
                for t in by_type:
                    type_counts[t] = type_counts.get(t, 0) + 1
            type_summary = ", ".join(
                f"{t}={c:,}" for t, c in sorted(type_counts.items()))
            print(f"  loaded linkages for {len(link_map):,} senses "
                  f"({type_summary})")

        rows = materialize_pending(conn, args.pass_mode, args.limit)
        print()

        if args.dry_run:
            print("=" * 60)
            print("DRY RUN -- showing first 5 built embedding_text values")
            print("=" * 60)
            for i, row in enumerate(rows[:5]):
                wsid, lemma = row[0], row[1]
                pos_simple, microgloss, gloss = row[2], row[3], row[4]
                register, temporal_status, social_status = row[5], row[6], row[7]
                tags_json, topics_json, examples_json, linkages_json = row[8:12]
                improved_microgloss = row[12]
                linkages = link_map.get(wsid) if link_map else None
                synonyms = (linkages or {}).get("synonyms", []) if linkages else []
                enrichment_fields = None
                if args.pass_mode == "v2" and improved_microgloss:
                    enrichment_fields = parse_v4_enrichment_row(row[12:])
                    if improved_microgloss:
                        microgloss = improved_microgloss
                text = build_text(
                    lemma=lemma, pos_simple=pos_simple,
                    microgloss=microgloss, gloss=gloss,
                    register=register, temporal_status=temporal_status,
                    social_status=social_status,
                    tags_json=tags_json, topics_json=topics_json,
                    examples_json=examples_json,
                    synonyms=synonyms,
                    enrichment_fields=enrichment_fields,
                    linkages=linkages,
                )
                print(f"\n--- row {i+1} (wsid={wsid}, lemma={lemma}) ---")
                print(text)
            print()
            print("Dry-run complete. No DB changes were written.")
            return 0

        processed, n_enriched = run(conn, link_map, rows, args.pass_mode, args.dry_run)

        print()
        print("=" * 60)
        print(f"EMBEDDING TEXT BUILD --pass {args.pass_mode} COMPLETE")
        print("=" * 60)
        print(f"  processed this run            : {processed:,}")
        if args.pass_mode == "v2":
            print(f"  with enrichment appended      : {n_enriched:,}")
        print(f"  output db                     : {db_path.resolve()}")
        print()
        if args.pass_mode == "v1":
            print("Next step:")
            print(f"  python compute_embeddings.py --target {db_path.name} "
                  f"--embedding-method bge-small-en-v1 --device dml")
        else:
            print("Stale sense_embedding rows were deleted for every rebuilt row.")
            print("Next step:")
            print(f"  python compute_embeddings.py --target {db_path.name} "
                  f"--embedding-method bge-large-en-v1 --device dml")
        print("=" * 60)

    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
