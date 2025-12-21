import re

def tokenize(text):
    return set(re.findall(r'\w+', text.lower()))

def get_jaccard_sim(t1, t2):
    s1 = tokenize(t1)
    s2 = tokenize(t2)
    if not s1 or not s2: return 0.0
    return len(s1 & s2) / len(s1 | s2)

def remove_duplicates(seq_threshold=0.75, word_threshold=0.5):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Fetch all articles at once
    cursor.execute("SELECT id, title, slug FROM articles ORDER BY id ASC")
    articles = cursor.fetchall()
    
    print(f"Loaded {len(articles)} articles from the database.")
    print(f"Scanning for duplicates (Sequence > {seq_threshold} OR Word Overlap > {word_threshold})...")
    
    to_delete = []
    seen_titles = [] # List of (id, title, slug)
    
    for current_id, current_title, current_slug in articles:
        is_dup = False
        for seen_id, seen_title, seen_slug in seen_titles:
            # 1. Sequence Matcher (Character/Order based)
            seq_sim = difflib.SequenceMatcher(None, current_title, seen_title).ratio()
            
            # 2. Jaccard (Word Overlap based - ignores order)
            word_sim = get_jaccard_sim(current_title, seen_title)

            # Verbose check
            if seq_sim > 0.6 or word_sim > 0.4:
                 print(f"🔍 Checking:\n   A: {seen_title}\n   B: {current_title}\n   Seq: {seq_sim:.2f} | Word: {word_sim:.2f}")

            if seq_sim > seq_threshold or word_sim > word_threshold:
                print(f"❌ MARKED FOR DELETION (Duplicate of {seen_id}):\n   Title: {current_title}")
                to_delete.append(current_id)
                is_dup = True
                break
        
        if not is_dup:
            seen_titles.append((current_id, current_title, current_slug))
            
    if not to_delete:
        print("✅ No duplicates found.")
    else:
        print(f"\n🗑️ Deleting {len(to_delete)} duplicate articles...")
        cursor.execute(f"DELETE FROM articles WHERE id IN ({','.join(map(str, to_delete))})")
        conn.commit()
        print("Done.")

    conn.close()

if __name__ == "__main__":
    remove_duplicates()
