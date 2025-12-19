import sqlite3
import datetime

DB_PATH = "news.db"

def check_recent():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Check for articles added in the last hour
    # SQLite CURRENT_TIMESTAMP is in UTC. local time is 10:47.
    # Let's just check the last 10 articles regardless of time.
    cursor.execute("SELECT id, title, published_at FROM articles ORDER BY id DESC LIMIT 10")
    rows = cursor.fetchall()
    
    for row in rows:
        print(f"ID: {row[0]} | Title: {row[1]} | Published: {row[2]}")
    
    conn.close()

if __name__ == "__main__":
    check_recent()
