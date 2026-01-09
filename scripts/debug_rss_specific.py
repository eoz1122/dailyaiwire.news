import sqlite3
import os

DB_PATH = "news.db"

def inspect_specific_articles():
    conn = sqlite3.connect(DB_PATH)
    # Search for the specific articles mentioned by the user
    query = """
    SELECT id, title, published_at, slug 
    FROM articles 
    WHERE title LIKE '%Kurdistan%' 
       OR title LIKE '%Geoffrey Hinton%' 
       OR title LIKE '%Funding Fortress%'
    ORDER BY id DESC
    """
    rows = conn.execute(query).fetchall()
    conn.close()
    
    print(f"{'ID':<5} | {'Published':<12} | {'Title'}")
    print("-" * 80)
    for r in rows:
        print(f"{r[0]:<5} | {r[2]:<12} | {r[1][:60]}...")
        
    print("\n--- Top 10 Most Recent IDs in DB ---")
    conn = sqlite3.connect(DB_PATH)
    rows_top = conn.execute('SELECT id, title, published_at FROM articles ORDER BY id DESC LIMIT 10').fetchall()
    for r in rows_top:
        print(f"{r[0]:<5} | {r[2]:<12} | {r[1][:60]}...")
    conn.close()

if __name__ == "__main__":
    inspect_specific_articles()
