import sqlite3

DB_PATH = "news.db"

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("Migrating database...")
    
    # 1. Add shared_at column to articles if it doesn't exist
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN shared_at TIMESTAMP")
        print("✅ Added 'shared_at' column to 'articles' table.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("ℹ️ 'shared_at' column already exists.")
        else:
            print(f"❌ Error adding column: {e}")

    # 2. Add shared_at column to blog_posts (for future use)
    try:
        cursor.execute("ALTER TABLE blog_posts ADD COLUMN shared_at TIMESTAMP")
        print("✅ Added 'shared_at' column to 'blog_posts' table.")
    except sqlite3.OperationalError:
        pass

    # 3. Initialize shared_at for already shared articles (using published_at as a proxy)
    cursor.execute("UPDATE articles SET shared_at = published_at WHERE shared_on_x = 1 AND shared_at IS NULL")
    
    conn.commit()
    conn.close()
    print("✨ Migration complete.")

if __name__ == "__main__":
    migrate()
