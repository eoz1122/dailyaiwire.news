# Version 2.2.2 - Fixed SDK for fetcher.py compatibility
import re
import sqlite3
import difflib
import os
import hashlib
from dotenv import load_dotenv

import ai_config
import db
from services.ai_gateway import AIGateway
from services.ai_schemas import DuplicateReviewPayload
from services.duplicate_review import flag_duplicate_pair

load_dotenv()

DEDUP_SIGNATURE_RETENTION_DAYS = int(os.getenv("AI_DEDUP_SIGNATURE_RETENTION_DAYS", "7"))

def tokenize(text):
    if not text: return set()
    return set(re.findall(r'\w+', text.lower()))

def get_jaccard_sim(t1, t2):
    s1 = tokenize(t1)
    s2 = tokenize(t2)
    if not s1 or not s2: return 0.0
    return len(s1 & s2) / len(s1 | s2)


def ensure_ai_dedup_run_table(cursor):
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_dedup_runs (
            prompt_hash TEXT PRIMARY KEY,
            article_count INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')


def _dedup_signature(articles):
    payload = "\n".join(f"{article_id}:{title}" for article_id, title in articles)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _claim_ai_dedup_signature(cursor, articles):
    ensure_ai_dedup_run_table(cursor)
    cursor.execute(
        "DELETE FROM ai_dedup_runs WHERE created_at < datetime('now', ?)",
        (f"-{DEDUP_SIGNATURE_RETENTION_DAYS} days",),
    )
    signature = _dedup_signature(articles)
    cursor.execute(
        "INSERT OR IGNORE INTO ai_dedup_runs (prompt_hash, article_count) VALUES (?, ?)",
        (signature, len(articles)),
    )
    return cursor.rowcount == 1

def ai_deduplicate(recent_only=True):
    """Uses Gemini to identify semantically identical topics.
    
    Args:
        recent_only: If True, only checks articles added in the last hour.
    """
    if not os.getenv("GEMINI_API_KEY"):
        print("⚠️ Skipping AI Deduplication: GEMINI_API_KEY missing.")
        return

    print("🤖 AI Deduplication Agent Scanning for Semantic Duplicates...")

    conn = sqlite3.connect(db.DB_PATH)
    cursor = conn.cursor()
    
    if recent_only:
        cursor.execute("""
            SELECT id, title FROM articles 
            WHERE datetime(published_at) >= datetime('now', '-1 hour')
            ORDER BY id DESC
        """)
        print("   (Checking only articles from last hour to protect published content)")
    else:
        cursor.execute("SELECT id, title FROM articles ORDER BY id DESC LIMIT 100")

    articles = cursor.fetchall()

    if len(articles) < 2:
        conn.close()
        return

    if recent_only and not _claim_ai_dedup_signature(cursor, articles):
        conn.commit()
        conn.close()
        print("⏭️ AI dedup skipped: recent headline set already reviewed.")
        return
    conn.commit()

    article_map = {article_id: title for article_id, title in articles}
    titles_list = [f"{a[0]}: {a[1]}" for a in articles]
    
    prompt = """
    Analyze the following list of news headlines (Format: "ID: Title").
    Identify pairs that are identifying the EXACT SAME story/event/topic, even if worded differently.
    
    Examples of duplicates:
    - "OpenAI Sora API Released" and "Sora Video Generation coming to all users"
    - "Nvidia hits all time high" and "NVDA Stock surges to record levels"
    
    Return a STRICT JSON object with a key "duplicate_pairs" containing objects with:
    - keep_id: the NEWEST ID to keep (the one that appears FIRST/HIGHER in the list)
    - delete_id: the older duplicate ID
    - reason: short explanation
    
    Format:
    {
        "duplicate_pairs": [
            {"keep_id": 101, "delete_id": 98, "reason": "same Sora launch story"}
        ]
    }
    
    HEADLINES:
    """ + "\n".join(titles_list)

    try:
        gateway = AIGateway(
            model_name=ai_config.ROUTINE_MODEL,
            system_instruction=ai_config.get_system_instruction("Deduplicator"),
            generation_config={"response_mime_type": "application/json", "temperature": 0},
            logger_name='remove_duplicates',
        )

        payload, _response = gateway.generate_structured(
            prompt,
            DuplicateReviewPayload,
            prompt_type="semantic_dedup"
        )

        duplicate_pairs = payload.duplicate_pairs

        if duplicate_pairs:
            print(f"⚠️ AI flagged {len(duplicate_pairs)} semantic duplicate pairs for review.")
            for pair in duplicate_pairs:
                if pair.keep_id not in article_map or pair.delete_id not in article_map:
                    continue
                flag_duplicate_pair(
                    keep_article_id=pair.keep_id,
                    keep_title=article_map[pair.keep_id],
                    duplicate_article_id=pair.delete_id,
                    duplicate_title=article_map[pair.delete_id],
                    detection_method="AI_SEMANTIC",
                    reason=pair.reason,
                )
            print("📝 Duplicate review queue updated.")
        else:
            print("✅ AI found no semantic duplicates.")

    except Exception as e:
        print(f"❌ AI Deduplication Failed: {e}")
        
    conn.close()

def remove_duplicates(seq_threshold=0.8, word_threshold=0.6, recent_only=True):
    """Standard fuzzy deduplication followed by AI semantic check."""
    conn = sqlite3.connect(db.DB_PATH)
    cursor = conn.cursor()
    
    if recent_only:
        cursor.execute("""
            SELECT id, title, slug FROM articles 
            WHERE datetime(published_at) >= datetime('now', '-1 hour')
            ORDER BY id ASC
        """)
        print("Scanning recent articles (last hour) for fuzzy duplicates...")
    else:
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
    
    # AI Check with safety wrap
    try:
        ai_deduplicate(recent_only=recent_only)
    except Exception as e:
        print(f"❌ Critical Error in AI Deduplication: {e}")

if __name__ == "__main__":
    remove_duplicates()
