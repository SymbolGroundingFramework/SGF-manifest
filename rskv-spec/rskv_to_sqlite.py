
#!/usr/bin/env python3
import argparse
import sqlite3
import os

# ==========================================
# LAYER 1 PRIMITIVES: RSKV REFERENCE PARSER
# ==========================================
def _unescape_rskv(value: str) -> str:
    if value == r"\N":
        return None
    return (
        value
        .replace(r"\---ROW---", "---ROW---")
        .replace(r"\\", "\\")
        .replace(r"\n", "\n")
        .replace(r"\#", "#")
    )

def parse_rskv(text: str) -> dict:
    sets = {}
    current_set = None
    current_row = {}

    def flush():
        nonlocal current_row
        if current_set and current_row:
            if current_set not in sets:
                sets[current_set] = {"schema": {}, "meta": {}, "rows": []}
            sets[current_set]["rows"].append(current_row)
            current_row = {}

    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if not line:
            continue

        if line.startswith("#SET: "):
            flush()
            current_set = line[5:].strip()
            if current_set not in sets:
                 sets[current_set] = {"schema": {}, "meta": {}, "rows": []}
            current_row = {}
            continue

        if line == "#ENDSET":
            flush()
            current_set = None
            current_row = {}
            continue

        if not current_set:
            continue

        if line.startswith("#SCHEMA:"):
            # Process schema line: key:type, key2:type2
            schema_line = line[8:].strip()
            for part in schema_line.split(","):
                if ":" in part:
                    k, t = part.split(":", 1)
                    sets[current_set]["schema"][k.strip()] = t.strip()
            continue

        if line.startswith("#META:"):
            continue

        if line.startswith("#") and ": " not in line:
             continue 

        if line == "---ROW---":
            flush()
            continue

        if ": " in line:
            key, value = line.split(": ", 1)
            current_row[key.strip()] = _unescape_rskv(value)
            continue

    flush()
    return sets

# ==========================================
# EXECUTION ENGINE: SQLITE INGESTION
# ==========================================
def run(input_file: str, db_file: str):
    if not os.path.exists(input_file):
        print(f"Error: Input file '{input_file}' not found.")
        return

    with open(input_file, 'r', encoding='utf-8') as f:
        rskv_text = f.read()

    parsed_data = parse_rskv(rskv_text)
    conn = sqlite3.connect(db_file)
    
    # Simple mapping of RSKV types to SQLite
    type_map = {
        "int": "INTEGER", "float": "REAL", "bool": "INTEGER",
        "date": "TEXT", "datetime": "TEXT", "json": "TEXT",
        "base64": "BLOB", "str": "TEXT"
    }

    for set_name, set_data in parsed_data.items():
        rows = set_data["rows"]
        if not rows:
            continue

        schema = set_data.get("schema", {})
        # If no schema is defined, infer columns from the first row
        columns = list(schema.keys()) if schema else list(rows[0].keys())

        col_defs = []
        for col in columns:
            type_hint = schema.get(col, "str")
            base_type = type_hint.split(":")[0] # Strip modifiers like :pk
            sql_type = type_map.get(base_type, "TEXT")
            col_defs.append(f'"{col}" {sql_type}')

        # Create table dynamically
        conn.execute(f'CREATE TABLE IF NOT EXISTS "{set_name}" ({", ".join(col_defs)})')

        # Insert data
        placeholders = ",".join("?" * len(columns))
        sql = f'INSERT INTO "{set_name}" ({",".join(f"{c}" for c in columns)}) VALUES ({placeholders})'
        
        data_tuples = []
        for row in rows:
            data_tuples.append(tuple(row.get(c) for c in columns))
            
        conn.executemany(sql, data_tuples)
        print(f"Inserted {len(rows)} records into table '{set_name}'.")

    conn.commit()
    conn.close()
    print(f"Successfully processed RSKV into '{db_file}'.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert RSKV text file to a SQLite database.")
    parser.add_argument("--input", required=True, help="Path to the input .txt file containing RSKV data.")
    parser.add_argument("--db", required=True, help="Path to the output .sqlite database file.")
    args = parser.parse_args()
    
    run(args.input, args.db)