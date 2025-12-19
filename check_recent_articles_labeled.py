import sqlite3
import datetime

DB_PATH = "news.db"

def check_recent_articles():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, published_at, audio_male, audio_female, source_url FROM articles ORDER BY published_at DESC LIMIT 5")
    rows = cursor.fetchall()
    
    now = datetime.datetime.now()
    print(f"Current local time: {now}")
    
    for row in rows:
        print(f"ID: {row[0]}")
        print(f"Title: {row[1]}")
        print(f"Published: {row[2]}")
        print(f"Male Audio: {row[3]}")
        print(f"Female Audio: {row[4]}")
        print("-" * 20)
    
    conn.close()

if __name__ == "__main__":
    check_recent_articles()
