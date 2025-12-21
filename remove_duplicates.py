import sqlite3
import difflib

DB_PATH = "news.db"

def remove_duplicates(threshold=0.85):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Fetch all articles
    cursor.execute("SELECT id, title, slug FROM articles ORDER BY id ASC")
    articles = cursor.fetchall()
    
    print(f"Checking {len(articles)} articles for duplicates...")
    
    to_delete = []
    seen_titles = [] # List of (id, title, slug)
    
    for current_id, current_title, current_slug in articles:
        is_dup = False
        for seen_id, seen_title, seen_slug in seen_titles:
            similarity = difflib.SequenceMatcher(None, current_title, seen_title).ratio()
            if similarity > threshold:
                print(f"❌ Duplicate Found:\n   Original ({seen_id}): {seen_title}\n   Duplicate ({current_id}): {current_title}\n   Similarity: {similarity:.2f}")
                to_delete.append(current_id)
                is_dup = True
                break
        
        if not is_dup:
            seen_titles.append((current_id, current_title, current_slug))
            
    if not to_delete:
        print("✅ No duplicates found.")
    else:
        print(f"\n🗑️ Deleting {len(to_delete)} duplicate articles...")
        # Delete in batch
        cursor.execute(f"DELETE FROM articles WHERE id IN ({','.join(map(str, to_delete))})")
        conn.commit()
        print("Done.")

    conn.close()

if __name__ == "__main__":
    remove_duplicates()
