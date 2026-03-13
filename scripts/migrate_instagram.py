"""
Migration: Add shared_on_ig column to articles table.
Tracks whether an article has been shared on Instagram.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "news.db")


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if column already exists
    columns = [col[1] for col in cursor.execute("PRAGMA table_info(articles)").fetchall()]
    if "shared_on_ig" in columns:
        print("✅ Column 'shared_on_ig' already exists. Nothing to do.")
        conn.close()
        return

    cursor.execute("ALTER TABLE articles ADD COLUMN shared_on_ig BOOLEAN DEFAULT 0")
    conn.commit()
    print("✅ Added 'shared_on_ig' column to articles table.")
    conn.close()


if __name__ == "__main__":
    migrate()
