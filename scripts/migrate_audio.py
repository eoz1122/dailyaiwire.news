import sqlite3
import os

DB_PATH = "news.db"

def migrate():
    if not os.path.exists(DB_PATH):
        print("Database not found. Initial run will create it.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get current columns
    cursor.execute("PRAGMA table_info(articles)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'audio_male' not in columns:
        print("Adding audio_male column...")
        cursor.execute("ALTER TABLE articles ADD COLUMN audio_male TEXT")
        
    if 'audio_female' not in columns:
        print("Adding audio_female column...")
        cursor.execute("ALTER TABLE articles ADD COLUMN audio_female TEXT")
        
    conn.commit()
    conn.close()
    print("Migration check complete.")

if __name__ == "__main__":
    migrate()
