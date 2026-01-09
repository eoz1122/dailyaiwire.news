import sqlite3
import json
from datetime import datetime

DB_PATH = "news.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def simulate_selection():
    conn = get_db_connection()
    try:
        # Check total unshared articles
        total_unshared = conn.execute("SELECT COUNT(*) FROM articles WHERE shared_on_x = 0 OR shared_on_x IS NULL").fetchone()[0]
        print(f"Total unshared articles in DB: {total_unshared}")

        # Run the exact query from scheduler
        query = '''
            SELECT id, title, published_at, importance_score,
            (importance_score + 
                CASE 
                    WHEN published_at > datetime('now', '-6 hours') THEN 20 
                    WHEN published_at > datetime('now', '-12 hours') THEN 10 
                    ELSE 0 
                END
            ) as hybrid_rank 
            FROM articles 
            WHERE shared_on_x = 0 OR shared_on_x IS NULL 
            ORDER BY hybrid_rank DESC 
            LIMIT 5
        '''
        results = conn.execute(query).fetchall()
        
        if not results:
            print("❌ Query returned NO results.")
        else:
            print(f"✅ Query returned local candidates:")
            for row in results:
                print(f" - [Rank: {row['hybrid_rank']}] {row['title']} (Pub: {row['published_at']})")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    simulate_selection()
