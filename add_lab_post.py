import sqlite3
import json
from slugify import slugify
import sys

DB_PATH = "news.db"

def add_post(title, subtitle, content, image=None):
    slug = slugify(title)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO blog_posts (slug, title, subtitle, content, image)
            VALUES (?, ?, ?, ?, ?)
        ''', (slug, title, subtitle, content, image))
        conn.commit()
        print(f"✅ Successfully added Lab Post: {title}")
        print(f"URL: /lab/{slug}")
    except sqlite3.IntegrityError:
        print(f"❌ Error: A post with the slug '{slug}' already exists.")
    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python add_lab_post.py \"Title\" \"Subtitle\" \"Content (HTML)\" [\"Image_URL\"]")
    else:
        title = sys.argv[1]
        subtitle = sys.argv[2]
        content = sys.argv[3]
        image = sys.argv[4] if len(sys.argv) > 4 else None
        add_post(title, subtitle, content, image)
