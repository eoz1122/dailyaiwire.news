import sqlite3
import os

DB_PATH = "news.db"

def migrate_db():
    if not os.path.exists(DB_PATH):
        print(f"Database {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        print("Attempting to add 'thought_provoking_question' column to 'articles' table...")
        cursor.execute("ALTER TABLE articles ADD COLUMN thought_provoking_question TEXT")
        print("Successfully added 'thought_provoking_question' column.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("Column 'thought_provoking_question' already exists.")
        else:
            print(f"Error adding column: {e}")
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate_db()
