#!/usr/bin/env python3
"""
load_wiktionary_to_db.py — Load raw Wiktionary JSONL into a SQLite database.

Reads a Kaikki.org JSONL dump (already decompressed) and stores it as
normalized SQLite tables. This is a faithful mirror of the JSONL structure
for later processing by import_wiktionary_to_synapedia.py.

KEY DESIGN DECISIONS:
- Multiple entries per (word, pos) are ALLOWED. Etymology number disambiguates.
- The pos field may be a string ("noun") or a list (["noun", "verb"]) — both handled.
- Redirect entries are stored but flagged (redirect_target is non-NULL).
- Categories are stripped of language prefixes (en:, de:, fr:) generically.

USAGE:
    # Simple English extract (~72K entries)
    python load_wiktionary_to_db.py --source simple-extract.jsonl.gz --target wiktionary_raw.db

    # Full English (~1.7M entries)
    python load_wiktionary_to_db.py --source raw-wiktextract-data.jsonl --target wiktionary_raw.db

    # Test first 1000 entries
    python load_wiktionary_to_db.py --source simple-extract.jsonl --limit 1000
"""

import argparse
import json
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

# ── Known POS values (from Kaikki/Wiktionary) ──────────────────────
KNOWN_POS = {
    "noun", "verb", "adjective", "adverb", "pronoun", "preposition",
    "conjunction", "interjection", "determiner", "article", "numeral",
    "particle", "postposition", "circumposition", "contraction",
    "abbreviation", "affix", "prefix", "suffix", "infix", "circumfix",
    "phrase", "idiom", "proverb", "letter", "character", "symbol",
    "punctuation", "diacritical_mark", "root", "hanzi", "kanji", "hanja",
    "name", "given_name", "surname", "place_name", "proper_noun",
    "initialism", "acronym", "romanization", "interfix", "combining_form",
    "counter", "classifier", "adposition", "adnominal", "adjectival",
    "adverbial", "gerund", "participle", "infinitive", "supine",
    "transfix", "simulfix", "duplifix", "transfix", "ambifix",
    "preverb", "prepositional_phrase", "verb_phrase", "noun_phrase",
    "adjective_phrase", "adverb_phrase", "conjunction_phrase",
    "interjection_phrase", "determiner_phrase", "numeral_phrase",
    "particle_phrase", "postposition_phrase", "circumposition_phrase",
    "contraction_phrase", "abbreviation_phrase", "affix_phrase",
    "prefix_phrase", "suffix_phrase", "infix_phrase", "circumfix_phrase",
    "phrase_phrase", "idiom_phrase", "proverb_phrase", "letter_phrase",
    "character_phrase", "symbol_phrase", "punctuation_phrase",
    "diacritical_mark_phrase", "root_phrase", "hanzi_phrase",
    "kanji_phrase", "hanja_phrase", "name_phrase", "given_name_phrase",
    "surname_phrase", "place_name_phrase", "proper_noun_phrase",
    "initialism_phrase", "acronym_phrase", "romanization_phrase",
    "interfix_phrase", "combining_form_phrase", "counter_phrase",
    "classifier_phrase", "adposition_phrase", "adnominal_phrase",
    "adjectival_phrase", "adverbial_phrase", "gerund_phrase",
    "participle_phrase", "infinitive_phrase", "supine_phrase",
    "unknown",
}

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

DROP TABLE IF EXISTS wiktionary_sense;
DROP TABLE IF EXISTS wiktionary_entry;

CREATE TABLE wiktionary_entry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT NOT NULL,
    pos TEXT NOT NULL,                       -- may be "noun" or "noun,verb" (comma-joined)
    lang TEXT,                               -- e.g., "English"
    lang_code TEXT DEFAULT 'en',             -- e.g., "en"
    etymology_number INTEGER,                -- NULL if not numbered, 1, 2, 3... for distinct etymologies
    etymology_text TEXT,                     -- raw etymology text from Wiktionary
    is_redirect INTEGER DEFAULT 0,           -- 1 if this is a redirect entry
    redirect_target TEXT,                    -- non-NULL if this entry redirects to another word
    raw_entry_json TEXT NOT NULL,            -- full JSON object for debugging
    source_line INTEGER,                     -- line number in the source file
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE wiktionary_sense (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL,
    sense_index INTEGER NOT NULL,            -- 0-based position within the senses array
    gloss TEXT,                              -- cleaned gloss (joined from glosses list)
    raw_gloss TEXT,                          -- raw_glosses if available, else same as gloss
    tags_json TEXT,                          -- JSON list of usage tags (e.g. ["slang", "US"])
    categories_json TEXT,                    -- JSON list of categories (e.g. ["Tools", "Hardware"])
    examples_json TEXT,                      -- JSON list of example sentences
    synonyms_json TEXT,                      -- JSON list of synonyms (from the sense)
    alt_of_json TEXT,                        -- JSON list of "alternative form of" relations
    form_of_json TEXT,                       -- JSON list of "form of" relations
    links_json TEXT,                         -- JSON list of external links
    raw_sense_json TEXT NOT NULL,            -- full sense JSON for debugging
    FOREIGN KEY (entry_id) REFERENCES wiktionary_entry(id) ON DELETE CASCADE
);

CREATE INDEX idx_entry_word ON wiktionary_entry(word);
CREATE INDEX idx_entry_pos ON wiktionary_entry(pos);
CREATE INDEX idx_entry_word_pos ON wiktionary_entry(word, pos);
CREATE INDEX idx_entry_lang_code ON wiktionary_entry(lang_code);
CREATE INDEX idx_entry_redirect ON wiktionary_entry(is_redirect) WHERE is_redirect = 1;
CREATE INDEX idx_sense_entry ON wiktionary_sense(entry_id);
CREATE INDEX idx_sense_gloss ON wiktionary_sense(gloss) WHERE gloss IS NOT NULL AND gloss != '';
"""


# ── Helpers ─────────────────────────────────────────────────────────

def dumps(obj):
    """JSON dump with ensure_ascii=False, returning None for None input."""
    return json.dumps(obj, ensure_ascii=False) if obj is not None else None


def normalize_pos(pos_raw):
    """Normalize POS field which may be a string or list.
    
    Kaikki format can have pos as a string ("noun") or a list (["noun", "verb"]).
    We join lists with comma for storage, and validate against known POS values.
    Returns (normalized_pos, is_valid).
    """
    if pos_raw is None:
        return "unknown", False
    
    if isinstance(pos_raw, list):
        # Filter out None/invalid, then deduplicate preserving order
        seen = set()
        cleaned = []
        for p in pos_raw:
            if p and p not in seen:
                cleaned.append(p)
                seen.add(p)
        if not cleaned:
            return "unknown", False
        pos_str = ",".join(cleaned)
        # Valid if at least one POS is known
        is_valid = any(p in KNOWN_POS for p in cleaned)
        return pos_str, is_valid
    
    if isinstance(pos_raw, str):
        pos_raw = pos_raw.strip().lower()
        if not pos_raw:
            return "unknown", False
        is_valid = pos_raw in KNOWN_POS
        return pos_raw, is_valid
    
    return "unknown", False


def clean_categories(categories, lang_code="en"):
    """Strip language prefix from category names.
    
    Wiktionary categories often have a prefix like "en:Tools", "de:Werkzeuge".
    We strip the prefix generically (any XX: pattern) and deduplicate.
    """
    if not categories:
        return None
    
    cleaned = []
    seen = set()
    for cat in categories:
        if not cat:
            continue
        # Strip any XX: prefix (language code + colon)
        if ":" in cat:
            # Only strip if the prefix is a known language code pattern (2-3 letters)
            prefix, remainder = cat.split(":", 1)
            if prefix.isalpha() and len(prefix) <= 3:
                cat = remainder
        cat = cat.strip()
        if cat and cat not in seen:
            cleaned.append(cat)
            seen.add(cat)
    
    return cleaned if cleaned else None


def extract_synonyms(sense):
    """Extract synonyms from a sense object.
    
    Kaikki format stores synonyms as a list of dicts with 'word' and 'sense' keys.
    """
    synonyms = sense.get("synonyms", [])
    if not synonyms:
        return None
    
    result = []
    seen = set()
    for syn in synonyms:
        if isinstance(syn, dict):
            word = syn.get("word", "") or syn.get("sense", "") or ""
        elif isinstance(syn, str):
            word = syn
        else:
            continue
        word = word.strip()
        if word and word not in seen:
            result.append(word)
            seen.add(word)
    
    return result if result else None


def extract_examples(sense):
    """Extract example sentences from a sense object.
    
    Examples can be dicts with 'text' and 'english' keys, or plain strings.
    """
    examples = sense.get("examples", [])
    if not examples:
        return None
    
    result = []
    for ex in examples:
        if isinstance(ex, dict):
            text = ex.get("text", "") or ex.get("english", "") or ""
        elif isinstance(ex, str):
            text = ex
        else:
            continue
        text = text.strip()
        if text:
            result.append(text)
    
    return result if result else None


# ── Main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Load raw Wiktionary JSONL into a normalized SQLite database."
    )
    parser.add_argument("--source", required=True,
                        help="Path to decompressed .jsonl file (.jsonl, .jsonl.gz, .jsonl.zst)")
    parser.add_argument("--target", default="wiktionary_raw.db",
                        help="Output SQLite database path")
    parser.add_argument("--limit", type=int, default=None,
                        help="Stop after N entries (for testing)")
    parser.add_argument("--batch", type=int, default=5000,
                        help="Batch commit size (default: 5000)")
    parser.add_argument("--lang-code", default="en",
                        help="Filter by language code (default: 'en'). Set to empty string for all languages.")
    parser.add_argument("--include-redirects", action="store_true",
                        help="Include redirect entries (default: skip them)")
    args = parser.parse_args()

    # Handle empty string → None for lang filter
    lang_filter = args.lang_code.strip() if args.lang_code.strip() else None

    src_path = Path(args.source)
    if not src_path.exists():
        print(f"ERROR: Source file not found: {src_path}", file=sys.stderr)
        return 1

    t0 = time.time()
    conn = sqlite3.connect(str(args.target))
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    cur = conn.cursor()

    file_size = src_path.stat().st_size
    print(f"Source: {src_path} ({file_size:,} bytes)")
    print(f"Target: {args.target}")
    print(f"Filter: lang_code{'=' + lang_filter if lang_filter else '=NONE (all languages)'}")
    if args.limit:
        print(f"Limit:  {args.limit} entries")
    if args.include_redirects:
        print(f"Redirects: INCLUDED")
    else:
        print(f"Redirects: SKIPPED")
    print()

    # ── Open file (handle .gz, .zst, plain) ──────────────────────
    f = None
    try:
        src_str = str(src_path)
        if src_str.endswith(".gz"):
            import gzip
            f = gzip.open(src_str, "rt", encoding="utf-8")
        elif src_str.endswith(".zst"):
            import zstandard
            dctx = zstandard.ZstdDecompressor()
            f = dctx.stream_reader(open(src_str, "rb"))
        else:
            f = open(src_str, "r", encoding="utf-8")
    except ImportError as e:
        print(f"ERROR: Required library not available: {e}", file=sys.stderr)
        print("Install with: pip install zstandard (for .zst files)", file=sys.stderr)
        return 1

    # ── Processing loop ──────────────────────────────────────────
    entries = 0
    senses = 0
    skipped_lang = 0
    skipped_redirect = 0
    skipped_parse = 0
    skipped_no_word = 0
    pos_counts = Counter()
    redirect_count = 0
    multi_pos_count = 0

    batch_entries = []
    batch_senses = []
    # We'll accumulate and flush in batches

    sense_counter = 0  # global counter for sense_id generation

    for line_no, line in enumerate(f, 1):
        if args.limit and entries >= args.limit:
            break

        # Handle bytes (zstd decompressor may yield bytes)
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")
        line = line.strip()
        if not line:
            continue

        # ── Parse JSON ───────────────────────────────────────
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            skipped_parse += 1
            continue

        # ── Required fields ──────────────────────────────────
        word = obj.get("word") or obj.get("lemma") or ""
        if not word:
            skipped_no_word += 1
            continue

        # ── Language filter ──────────────────────────────────
        lang = obj.get("lang", "") or obj.get("lang_code", "") or ""
        lang_code = obj.get("lang_code", "") or obj.get("lang", "") or ""
        if lang_code and lang_filter:
            if lang_code.lower() != lang_filter.lower():
                skipped_lang += 1
                continue

        # ── POS normalization ─────────────────────────────────
        pos_raw = obj.get("pos", "")
        pos, pos_valid = normalize_pos(pos_raw)
        if not pos_valid:
            pos = "unknown"  # Still store it, but flagged as unknown

        # ── Redirect handling ─────────────────────────────────
        redirect_target = obj.get("redirect") or ""
        is_redirect = 1 if redirect_target else 0
        if is_redirect:
            redirect_count += 1
            if not args.include_redirects:
                skipped_redirect += 1
                continue

        # ── Etymology number ──────────────────────────────────
        # Kaikki entries may have an "etymology_number" field (1, 2, 3...)
        # or an "etymology" text field.
        etymology_number = obj.get("etymology_number")
        etymology_text = obj.get("etymology_text") or obj.get("etymology") or ""

        # ── Track POS for stats ───────────────────────────────
        if "," in pos:
            multi_pos_count += 1
        for p in pos.split(","):
            pos_counts[p] += 1

        # ── Insert entry ──────────────────────────────────────
        cur.execute("""
            INSERT INTO wiktionary_entry
            (word, pos, lang, lang_code, etymology_number, etymology_text,
             is_redirect, redirect_target, raw_entry_json, source_line)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            word, pos,
            obj.get("lang") or "",
            lang_code or "en",
            etymology_number,
            etymology_text,
            is_redirect,
            redirect_target if redirect_target else None,
            dumps(obj),
            line_no,
        ))
        entry_id = cur.lastrowid
        entries += 1

        # ── Insert senses ─────────────────────────────────────
        senses_list = obj.get("senses", [])
        if not senses_list:
            # Still record one empty sense so the entry is findable
            senses_list = [{}]

        for si, sense in enumerate(senses_list):
            glosses = sense.get("glosses", [])
            raw_glosses = sense.get("raw_glosses", [])
            gloss = " ".join(glosses) if glosses else ""
            raw_gloss = " ".join(raw_glosses) if raw_glosses else gloss

            categories = clean_categories(sense.get("categories"), lang_code)
            examples = extract_examples(sense)
            synonyms = extract_synonyms(sense)

            cur.execute("""
                INSERT INTO wiktionary_sense
                (entry_id, sense_index, gloss, raw_gloss,
                 tags_json, categories_json, examples_json,
                 synonyms_json, alt_of_json, form_of_json, links_json,
                 raw_sense_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry_id, si, gloss, raw_gloss,
                dumps(sense.get("tags")),
                dumps(categories),
                dumps(examples),
                dumps(synonyms),
                dumps(sense.get("alt_of")),
                dumps(sense.get("form_of")),
                dumps(sense.get("links")),
                dumps(sense),
            ))
            senses += 1

        # ── Periodic commit ───────────────────────────────────
        if entries % args.batch == 0:
            conn.commit()
            elapsed = time.time() - t0
            rate = entries / elapsed if elapsed > 0 else 0
            print(f"  {entries:>8,} entries | {senses:>10,} senses | "
                  f"{rate:>5,.0f} entries/s        ", end="\r")

    # ── Final flush ──────────────────────────────────────────────
    conn.commit()
    elapsed = time.time() - t0
    rate = entries / elapsed if elapsed > 0 else 0

    # ── Final stats ──────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"LOAD COMPLETE in {elapsed:.1f}s")
    print(f"{'='*60}")
    print(f"  Entries loaded:       {entries:>10,}")
    print(f"  Senses loaded:        {senses:>10,}")
    print(f"  Avg senses/entry:     {senses/entries:>7.2f}" if entries else "")
    print(f"  Processing rate:      {rate:>10,.0f} entries/s")
    print()
    print(f"  Skipped (language):   {skipped_lang:>10,}")
    print(f"  Skipped (redirect):   {skipped_redirect:>10,}")
    print(f"  Skipped (parse err):  {skipped_parse:>10,}")
    print(f"  Skipped (no word):    {skipped_no_word:>10,}")
    if is_redirect:
        print(f"  Redirects stored:     {redirect_count:>10,}")
    print()
    print(f"  Multi-POS entries:    {multi_pos_count:>10,}")
    print()
    print("  POS distribution (top 20):")
    for pos_str, count in pos_counts.most_common(20):
        print(f"    {pos_str:>20s}: {count:>10,}")

    # ── Verify entry count ───────────────────────────────────────
    actual_entries = cur.execute("SELECT COUNT(*) FROM wiktionary_entry").fetchone()[0]
    actual_senses = cur.execute("SELECT COUNT(*) FROM wiktionary_sense").fetchone()[0]
    print()
    print(f"  Verified in DB:       {actual_entries:>10,} entries")
    print(f"  Verified in DB:       {actual_senses:>10,} senses")

    # ── Check for duplicate (word, pos) ──────────────────────────
    dup_count = cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT word, pos, COUNT(*) as cnt
            FROM wiktionary_entry
            GROUP BY word, pos
            HAVING cnt > 1
        )
    """).fetchone()[0]
    print(f"  (word, pos) with >1 entry: {dup_count:>10,} (expected for polysemy)")

    # ── Cleanup ──────────────────────────────────────────────────
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    if f:
        f.close()

    print(f"\nOutput: {Path(args.target).resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
