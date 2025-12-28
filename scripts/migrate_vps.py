import sqlite3
import os

def migrate():
    db_path = 'news.db'
    if not os.path.exists(db_path):
        print(f"❌ Database {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"🔍 Checking schema for {db_path}...")
    
    # Check if narration_script exists
    try:
        cursor.execute("SELECT narration_script FROM articles LIMIT 1")
        print("✅ Column 'narration_script' already exists.")
    except sqlite3.OperationalError:
        print("➕ Adding column 'narration_script' to 'articles' table...")
        try:
            cursor.execute("ALTER TABLE articles ADD COLUMN narration_script TEXT")
            conn.commit()
            print("✨ Migration successful!")
        except Exception as e:
            print(f"❌ Migration failed: {e}")

    conn.close()

if __name__ == "__main__":
    migrate()
