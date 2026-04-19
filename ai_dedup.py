import sqlite3
import os
from dotenv import load_dotenv

import ai_config
import db
from services.ai_gateway import AIGateway
from services.ai_schemas import DuplicateReviewPayload
from services.duplicate_review import flag_duplicate_pair

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

def ai_deduplicate():
    print("🤖 AI Deduplication Agent Initialized...")
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print(f"❌ GEMINI_API_KEY not found in .env ({os.path.join(os.path.dirname(__file__), '.env')})\n   Please ensure GEMINI_API_KEY is set.")
        return

    conn = sqlite3.connect(db.DB_PATH)
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
    
    article_map = {article_id: title for article_id, title in articles}
    titles_list = [f"{a[0]}: {a[1]}" for a in articles]
    
    # Process in batches if needed, but for <100 articles, one shot is fine.
    print(f"checking {len(articles)} headlines for semantic matching...")

    prompt = """
    Analyze the following list of news headlines (Format: "ID: Title").
    Identify pairs that are identifying the EXACT SAME story/event, even if worded differently.
    
    Example:
    "101: Colleges use AI for grading" matches "98: AI Essay Grading in College Admissions"
    
    Return a STRICT JSON object with a key "duplicate_pairs" containing objects with:
    - keep_id: the newer ID to keep
    - delete_id: the older duplicate ID
    - reason: short explanation
    
    Format:
    {
        "duplicate_pairs": [
            {"keep_id": 101, "delete_id": 98, "reason": "same story"}
        ]
    }
    
    HEADLINES:
    """ + "\n".join(titles_list[:100]) # Limit to 100 recent

    try:
        gateway = AIGateway(
            model_name='gemini-2.5-flash',
            system_instruction=ai_config.get_system_instruction("Deduplicator"),
            generation_config={"response_mime_type": "application/json"},
            logger_name='ai_dedup',
        )
        payload, _response = gateway.generate_structured(
            prompt,
            DuplicateReviewPayload,
            prompt_type="semantic_dedup_legacy"
        )
        duplicate_pairs = payload.duplicate_pairs

        if not duplicate_pairs:
            print("✅ AI found no duplicates.")
        else:
            print(f"⚠️ AI flagged {len(duplicate_pairs)} duplicate pairs for review.")
            for pair in duplicate_pairs:
                if pair.keep_id not in article_map or pair.delete_id not in article_map:
                    continue
                print(f"   - Review keep {pair.keep_id}, duplicate {pair.delete_id}: {pair.reason}")
                flag_duplicate_pair(
                    keep_article_id=pair.keep_id,
                    keep_title=article_map[pair.keep_id],
                    duplicate_article_id=pair.delete_id,
                    duplicate_title=article_map[pair.delete_id],
                    detection_method="AI_SEMANTIC",
                    reason=pair.reason,
                )
            print("📝 Review queue updated.")

    except Exception as e:
        print(f"AI Check Failed: {e}")
        
    conn.close()

if __name__ == "__main__":
    ai_deduplicate()
