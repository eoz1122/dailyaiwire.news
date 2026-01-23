import sqlite3
import os

DB_PATH = "news.db"

def migrate():
    print("🚀 Starting Migration: Add 'article_metadata' to newsletters table...")
    
    if not os.path.exists(DB_PATH):
        print(f"❌ Database file {DB_PATH} not found!")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if column exists
        cursor.execute("PRAGMA table_info(newsletters)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if 'article_metadata' in columns:
            print("⚠️ Column 'article_metadata' already exists. Skipping.")
        else:
            cursor.execute("ALTER TABLE newsletters ADD COLUMN article_metadata TEXT")
            print("✅ Added column 'article_metadata' successfully.")
            
        conn.commit()
    except Exception as e:
        print(f"❌ Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
