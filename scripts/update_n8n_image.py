import sqlite3
import os

DB_PATH = "news.db"

def update_image():
    print("🖼️ Updating n8n image...")
    conn = sqlite3.connect(DB_PATH)
    # Update articles with 'Automation' or 'n8n' in title
    conn.execute("UPDATE articles SET image = '/static/n8n.png' WHERE title LIKE '%Automation%' OR title LIKE '%n8n%'")
    rows = conn.total_changes
    conn.commit()
    conn.close()
    if rows > 0:
        print(f"✅ Updated {rows} articles with new n8n image.")
    else:
        print("⚠️ No matching articles found to update.")

if __name__ == "__main__":
    update_image()
