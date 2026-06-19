#!/usr/bin/env python3
import argparse
import sqlite3

# ==========================================
# LAYER 1 PRIMITIVES: RSKV EMITTER
# ==========================================
def escape_rskv(value) -> str:
    if value is None:
        return r"\N"
    
    val_str = str(value)
    
    if val_str == "":
        return ""
        
    return (
        val_str
        .replace("\\", r"\\")
        .replace("\n", r"\n")
        .replace("---ROW---", r"\---ROW---")
    )

def emit_rskv_for_table(cursor, table_name: str) -> str:
    output = []
    output.append(f"#SET: {table_name}")
    
    # Extract schema to build the #SCHEMA line
    cursor.execute(f"PRAGMA table_info('{table_name}')")
    columns_info = cursor.fetchall()
    
    # Map basic SQLite types back to RSKV
    schema_parts = []
    column_names = []
    for col in columns_info:
        col_name = col[1]
        col_type = col[2].upper()
        column_names.append(col_name)
        
        if "INT" in col_type:
            rskv_type = "int"
        elif "REAL" in col_type or "FLOA" in col_type:
            rskv_type = "float"
        elif "BLOB" in col_type:
            rskv_type = "base64"
        else:
            rskv_type = "str"
            
        schema_parts.append(f"{col_name}:{rskv_type}")
        
    output.append(f"#SCHEMA: {', '.join(schema_parts)}")
    
    # Query all rows
    cursor.execute(f"SELECT * FROM '{table_name}'")
    rows = cursor.fetchall()
    
    for i, row in enumerate(rows):
        for col_name, value in zip(column_names, row):
            output.append(f"{col_name}: {escape_rskv(value)}")
            
        if i < len(rows) - 1:
            output.append("---ROW---")
            
    output.append("#ENDSET\n")
    return "\n".join(output)

# ==========================================
# EXECUTION ENGINE: SQLITE EXTRACTION
# ==========================================
def run(db_file: str, output_file: str):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # Get all user tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row[0] for row in cursor.fetchall()]
    
    if not tables:
        print(f"Warning: No tables found in database '{db_file}'.")
        conn.close()
        return

    full_output = []
    for table in tables:
        rskv_block = emit_rskv_for_table(cursor, table)
        full_output.append(rskv_block)
        print(f"Extracted table '{table}'.")

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("\n".join(full_output))
        
    conn.close()
    print(f"Successfully wrote RSKV data to '{output_file}'.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert SQLite database to an RSKV text file.")
    parser.add_argument("--db", required=True, help="Path to the input .sqlite database file.")
    parser.add_argument("--output", required=True, help="Path to the output .txt file for RSKV data.")
    args = parser.parse_args()
    
    run(args.db, args.output)