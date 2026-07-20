import json
import sqlite3
from urllib.parse import unquote

conn = sqlite3.connect("wikipedia.db")
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS articles (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        title       TEXT    NOT NULL UNIQUE,
        abstract    TEXT    NOT NULL,
        title_clean TEXT
    )
""")

print("Loading JSON... (this may take a moment)")
with open("abstracts.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"Inserting {len(data)} articles into SQLite...")
batch = []
count = 0

for title, abstract in data.items():
    title_clean = unquote(title.replace("_", " "))
    batch.append((title, abstract, title_clean))
    count += 1
    
    if len(batch) >= 10000:
        cur.executemany(
            "INSERT OR IGNORE INTO articles (title, abstract, title_clean) VALUES (?, ?, ?)",
            batch
        )
        conn.commit()
        batch = []
        print(f"  Inserted {count} articles...")

if batch:
    cur.executemany(
        "INSERT OR IGNORE INTO articles (title, abstract, title_clean) VALUES (?, ?, ?)",
        batch
    )
    conn.commit()

cur.execute("SELECT COUNT(*) FROM articles")
print(f"Done! Total in DB: {cur.fetchone()[0]} articles")
conn.close()