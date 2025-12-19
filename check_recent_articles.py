import sqlite3
import json

DB_PATH = "news.db"

def check_recent_articles():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, published_at, audio_male, audio_female, source_url FROM articles ORDER BY published_at DESC LIMIT 5")
    rows = cursor.fetchall()
    
    print(f"{'ID':<5} | {'Title':<40} | {'Published':<25} | {'Male Audio':<20} | {'Female Audio':<20}")
    print("-" * 120)
    for row in rows:
        print(f"{row[0]:<5} | {row[1][:40]:<40} | {row[2]:<25} | {str(row[3]):<20} | {str(row[4]):<20}")
    
    conn.close()

if __name__ == "__main__":
    check_recent_articles()
