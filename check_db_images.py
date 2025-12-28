import sqlite3
import os

def check_images():
    conn = sqlite3.connect('news.db')
    conn.row_factory = sqlite3.Row
    
    print("--- Searching for images containing 'static' ---")
    arts = conn.execute("SELECT id, title, image FROM articles WHERE image LIKE '%static%'").fetchall()
    for a in arts:
        print(f"ID: {a['id']}, Title: {a['title']}, Image: {a['image']}")
    
    print("\n--- Summary of Image Types ---")
    all_arts = conn.execute("SELECT image FROM articles").fetchall()
    local_count = 0
    external_count = 0
    none_count = 0
    for a in all_arts:
        img = a['image']
        if not img:
            none_count += 1
        elif '/static/' in img:
            local_count += 1
        else:
            external_count += 1
    
    print(f"Local (/static/): {local_count}")
    print(f"External: {external_count}")
    print(f"None/Empty: {none_count}")
    
    conn.close()

if __name__ == "__main__":
    check_images()
