import sqlite3

DB_PATH = "news.db"

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get current columns
    cursor.execute("PRAGMA table_info(articles)")
    columns = [col[1] for col in cursor.fetchall()]
    print(f"Current columns: {columns}")
    
    new_columns = [
        ("eli5", "TEXT"),
        ("deep_analysis", "TEXT"),
        ("source", "TEXT"),
        ("source_url", "TEXT")
    ]
    
    for col_name, col_type in new_columns:
        if col_name not in columns:
            print(f"Adding column {col_name}...")
            cursor.execute(f"ALTER TABLE articles ADD COLUMN {col_name} {col_type}")
    
    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
