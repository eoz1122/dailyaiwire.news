import sqlite3
import os

DB_PATH = "news.db"

def inspect_db():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute('SELECT id, title, published_at FROM articles ORDER BY id DESC LIMIT 25').fetchall()
    conn.close()
    
    print(f"{'ID':<5} | {'Published':<12} | {'Title'}")
    print("-" * 80)
    for r in rows:
        print(f"{r[0]:<5} | {r[2]:<12} | {r[1][:60]}...")

if __name__ == "__main__":
    inspect_db()
