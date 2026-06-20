#!/usr/bin/env python3
"""
apply_schema.py  --  apply schema.sql to a SQLite database.

Stage 2.7 of the SGF lexicon pipeline. Uses Python's stdlib sqlite3 so
no external sqlite3 CLI tool is required.

The script is idempotent: every CREATE in schema.sql uses
'IF NOT EXISTS', so running it twice is harmless. Run it on a fresh DB
to create all tables, or on an existing DB to add anything missing.

Usage:
    python apply_schema.py
        (defaults: --schema schema.sql --target sgf_lexicon.db)

    python apply_schema.py --target other.db --schema other_schema.sql
"""

import argparse
import sqlite3
import sys
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument(
        "--schema",
        default="schema.sql",
        help="Path to the schema SQL file (default: schema.sql)",
    )
    p.add_argument(
        "--target",
        default="sgf_lexicon.db",
        help="Path to the target SQLite DB (default: sgf_lexicon.db)",
    )
    args = p.parse_args()

    schema_path = Path(args.schema)
    db_path = Path(args.target)

    if not schema_path.exists():
        print(f"ERROR: schema file not found: {schema_path}", file=sys.stderr)
        return 2

    sql_text = schema_path.read_text(encoding="utf-8")

    print(f"Schema:  {schema_path}")
    print(f"Target:  {db_path}")
    print()

    fresh = not db_path.exists()
    conn = sqlite3.connect(db_path)
    try:
        # Capture table count before/after to report what changed
        before = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        )}
        conn.executescript(sql_text)
        conn.commit()
        after = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        )}
    except sqlite3.Error as e:
        print(f"ERROR applying schema: {e}", file=sys.stderr)
        conn.close()
        return 3
    finally:
        conn.close()

    new_tables = sorted(after - before)
    if fresh:
        print(f"Created fresh DB with {len(after)} tables:")
    elif new_tables:
        print(f"Added {len(new_tables)} new table(s) to existing DB:")
    else:
        print(f"DB already had all {len(after)} tables. No changes needed.")

    for t in sorted(after if fresh else new_tables):
        print(f"  - {t}")

    print()
    print(f"Done. SQLite DB at: {db_path.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
