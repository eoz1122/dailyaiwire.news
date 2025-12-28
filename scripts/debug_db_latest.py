import sqlite3

def check_db():
    conn = sqlite3.connect("news.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("--- LATEST 5 ARTICLES ---")
    cursor.execute("SELECT id, title, published_at, source FROM articles ORDER BY id DESC LIMIT 5")
    rows = cursor.fetchall()
    for row in rows:
        print(f"ID: {row['id']} | {row['title']} | {row['published_at']} | Source: {row['source']}")
    
    if not rows:
        print("No articles found in database.")
    
    conn.close()

if __name__ == "__main__":
    check_db()
