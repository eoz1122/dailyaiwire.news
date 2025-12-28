import sqlite3
import json

DB_PATH = "news.db"

def check_twitter_status():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    print("--- Twitter Sharing Status ---")
    shared = conn.execute('SELECT COUNT(*) FROM articles WHERE shared_on_x = 1').fetchone()[0]
    unshared = conn.execute('SELECT COUNT(*) FROM articles WHERE shared_on_x = 0 OR shared_on_x IS NULL').fetchone()[0]
    total = conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
    
    print(f"Total Articles: {total}")
    print(f"Shared on X: {shared}")
    print(f"Unshared: {unshared}")
    
    print("\n--- Recent articles and their slugs ---")
    recent = conn.execute('SELECT id, title, slug, shared_on_x, published_at FROM articles ORDER BY published_at DESC LIMIT 10').fetchall()
    for row in recent:
        print(f"ID: {row['id']} | Status: {row['shared_on_x']} | Date: {row['published_at']} | Title: {row['title'][:50]}... | Slug: {row['slug']}")

    print("\n--- Checking for Potential Duplicates (Same Title) ---")
    dupes = conn.execute('SELECT title, COUNT(*) as count FROM articles GROUP BY title HAVING count > 1').fetchall()
    if dupes:
        for row in dupes:
            print(f"Title: {row['title']} | Count: {row['count']}")
    else:
        print("No duplicate titles found.")

    conn.close()

if __name__ == "__main__":
    check_twitter_status()
