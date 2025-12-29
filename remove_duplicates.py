import re
import sqlite3
import difflib
import os
import json
import google.generativeai as genai
import warnings
warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "news.db"

def tokenize(text):
    if not text: return set()
    return set(re.findall(r'\w+', text.lower()))

def get_jaccard_sim(t1, t2):
    s1 = tokenize(t1)
    s2 = tokenize(t2)
    if not s1 or not s2: return 0.0
    return len(s1 & s2) / len(s1 | s2)

def ai_deduplicate(recent_only=True):
    """Uses Gemini 2.0 to identify semantically identical topics that fuzzy matching missed.
    
    Args:
        recent_only: If True, only checks articles added in the last hour (safe for published content)
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("⚠️ Skipping AI Deduplication: GEMINI_API_KEY missing.")
        return

    print("🤖 AI Deduplication Agent Scanning for Semantic Duplicates...")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if recent_only:
        # Only check articles added in the last hour (safe for batch processing)
        cursor.execute("""
            SELECT id, title FROM articles 
            WHERE datetime(published_at) >= datetime('now', '-1 hour')
            ORDER BY id DESC
        """)
        print("   (Checking only articles from last hour to protect published content)")
    else:
        # Check the 100 most recent articles (legacy behavior)
        cursor.execute("SELECT id, title FROM articles ORDER BY id DESC LIMIT 100")
    
    articles = cursor.fetchall()
    
    if len(articles) < 2:
        conn.close()
        return

    titles_list = [f"{a[0]}: {a[1]}" for a in articles]
    
    prompt = """
    Analyze the following list of news headlines (Format: "ID: Title").
    Identify pairs that are identifying the EXACT SAME story/event/topic, even if worded differently.
    
    Examples of duplicates:
    - "OpenAI Sora API Released" and "Sora Video Generation coming to all users"
    - "Nvidia hits all time high" and "NVDA Stock surges to record levels"
    
    Return a STRICT JSON object with a key "duplicates_to_delete" containing a list of IDs to delete.
    If multiple IDs refer to the same story, KEEP the NEWEST ID (the one that appears FIRST/HIGHER in the list) AND DELETE the older ones.
    
    Format:
    {
        "duplicates_to_delete": [ID1, ID2, ...]
    }
    
    HEADLINES:
    """ + "\n".join(titles_list)

    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        data = json.loads(response.text)
        ids_to_delete = data.get("duplicates_to_delete", [])
        
        if ids_to_delete:
            print(f"⚠️ AI Identified {len(ids_to_delete)} semantic duplicates for removal.")
            cursor.execute(f"DELETE FROM articles WHERE id IN ({','.join(map(str, ids_to_delete))})")
            conn.commit()
            print("✨ Semantic cleanup complete.")
        else:
            print("✅ AI found no semantic duplicates.")

    except Exception as e:
        print(f"❌ AI Deduplication Failed: {e}")
        
    conn.close()

def remove_duplicates(seq_threshold=0.8, word_threshold=0.6, recent_only=True):
    """Standard fuzzy deduplication followed by AI semantic check.
    
    Args:
        seq_threshold: Sequence similarity threshold (0-1)
        word_threshold: Jaccard word similarity threshold (0-1)
        recent_only: If True, only checks articles from last hour (safe and efficient)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if recent_only:
        # Only check articles added in the last hour
        cursor.execute("""
            SELECT id, title, slug FROM articles 
            WHERE datetime(published_at) >= datetime('now', '-1 hour')
            ORDER BY id ASC
        """)
        print("Scanning recent articles (last hour) for fuzzy duplicates...")
    else:
        # Legacy: Check ALL articles (very slow for large databases)
        cursor.execute("SELECT id, title, slug FROM articles ORDER BY id ASC")
        print(f"Scanning ALL articles for fuzzy duplicates...")
    
    articles = cursor.fetchall()
    
    if not articles:
        conn.close()
        return

    print(f"   Found {len(articles)} articles to check.")
    
    to_delete = []
    seen_titles = [] 
    
    for current_id, current_title, current_slug in articles:
        is_dup = False
        for seen_id, seen_title, seen_slug in seen_titles:
            seq_sim = difflib.SequenceMatcher(None, current_title, seen_title).ratio()
            word_sim = get_jaccard_sim(current_title, seen_title)

            if seq_sim > seq_threshold or word_sim > word_threshold:
                print(f"❌ Found Fuzzy Duplicate: '{current_title}'")
                to_delete.append(current_id)
                is_dup = True
                break
        
        if not is_dup:
            seen_titles.append((current_id, current_title, current_slug))
            
    if to_delete:
        cursor.execute(f"DELETE FROM articles WHERE id IN ({','.join(map(str, to_delete))})")
        conn.commit()
        print(f"🗑️ Removed {len(to_delete)} fuzzy duplicates.")
    else:
        print("✅ No fuzzy duplicates found.")
    
    conn.close()
    
    # Now run the smarter AI check (also limited to recent)
    ai_deduplicate(recent_only=recent_only)

if __name__ == "__main__":
    remove_duplicates()
