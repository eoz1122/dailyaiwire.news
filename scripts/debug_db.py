import sqlite3
import json

DB_PATH = "news.db"

def check_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Check table columns
    cursor.execute("PRAGMA table_info(articles)")
    columns = [col[1] for col in cursor.fetchall()]
    print(f"Columns in database: {columns}")
    
    # Check article count
    cursor.execute("SELECT COUNT(*) FROM articles")
    count = cursor.fetchone()[0]
    print(f"Total articles in DB: {count}")
    
    # Check a few articles
    cursor.execute("SELECT * FROM articles ORDER BY published_at DESC LIMIT 3")
    rows = cursor.fetchall()
    for i, row in enumerate(rows):
        print(f"\n--- Article {i+1} ---")
        print(f"Title: {row['title']}")
        print(f"Slug: {row['slug']}")
        print(f"Source: {row['source']}")
        print(f"ELI5: {row['eli5'][:50] if row['eli5'] else 'MISSING'}")
        print(f"Image: {row['image'][:50] if row['image'] else 'MISSING'}")
        print(f"Deep Analysis Length: {len(row['deep_analysis']) if row['deep_analysis'] else 0}")
    
    conn.close()

if __name__ == "__main__":
    check_db()
