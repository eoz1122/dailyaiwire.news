import sqlite3
import google.generativeai as genai
import os
import json
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

DB_PATH = "news.db"

def ai_deduplicate():
    print("🤖 AI Deduplication Agent Initialized...")
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print(f"❌ GEMINI_API_KEY not found in .env ({os.path.join(os.path.dirname(__file__), '.env')})\n   Please ensure GEMINI_API_KEY is set.")
        return

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Fetch all titles
    cursor.execute("SELECT id, title FROM articles ORDER BY id DESC")
    articles = cursor.fetchall()
    
    if not articles:
        print("No articles found.")
        return

    # Map ID to Title for deletion
    # We want to keep the NEWEST (Lower ID in desc? No, Higher ID is newer).
    # ORDER BY id DESC means Index 0 is Newest.
    # If duplicates found, we usually keep the NEWEST (most recent fetch) or OLDEST (original)?
    # User had duplicates. Usually keep the one with better metadata? 
    # Let's keep the NEWEST (First in list). Delete older versions.
    
    titles_list = [f"{a[0]}: {a[1]}" for a in articles]
    
    # Process in batches if needed, but for <100 articles, one shot is fine.
    print(f"checking {len(articles)} headlines for semantic matching...")

    prompt = """
    Analyze the following list of news headlines (Format: "ID: Title").
    Identify pairs that are identifying the EXACT SAME story/event, even if worded differently.
    
    Example:
    "101: Colleges use AI for grading" matches "98: AI Essay Grading in College Admissions"
    
    Return a STRICT JSON object with a key "duplicates_to_delete" containing a list of IDs to delete.
    Always keep the ID that appears HIGHER/FIRST in the list (the newer one). Delete the older ID.
    
    Format:
    {
        "duplicates_to_delete": [98, 55, ...]
    }
    
    HEADLINES:
    """ + "\n".join(titles_list[:100]) # Limit to 100 recent

    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        data = json.loads(response.text)
        ids_to_delete = data.get("duplicates_to_delete", [])
        
        if not ids_to_delete:
            print("✅ AI found no duplicates.")
        else:
            print(f"⚠️ AI Identified {len(ids_to_delete)} duplicates to remove: {ids_to_delete}")
            
            # Verify they exist
            cursor.execute(f"SELECT id, title FROM articles WHERE id IN ({','.join(map(str, ids_to_delete))})")
            confirm_rows = cursor.fetchall()
            for r in confirm_rows:
                print(f"   - Deleting ID {r[0]}: {r[1]}")
            
            # Execute
            cursor.execute(f"DELETE FROM articles WHERE id IN ({','.join(map(str, ids_to_delete))})")
            conn.commit()
            print("✨ Cleanup complete.")

    except Exception as e:
        print(f"AI Check Failed: {e}")
        
    conn.close()

if __name__ == "__main__":
    ai_deduplicate()
