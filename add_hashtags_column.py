import sqlite3

# Add hashtags column to articles table
conn = sqlite3.connect('news.db')
cursor = conn.cursor()

try:
    cursor.execute('ALTER TABLE articles ADD COLUMN hashtags TEXT')
    conn.commit()
    print("✅ Added hashtags column to articles table")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("✅ Hashtags column already exists")
    else:
        print(f"❌ Error: {e}")

conn.close()
