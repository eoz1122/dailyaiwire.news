import sqlite3

DB_PATH = "news.db"

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN shared_on_x BOOLEAN DEFAULT 0")
        print("✅ Added 'shared_on_x' column to articles table.")
    except sqlite3.OperationalError:
        print("ℹ️ 'shared_on_x' column already exists.")
        
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
