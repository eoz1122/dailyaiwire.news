
import sqlite3
import json
import os
from datetime import datetime, timedelta
from social_distributor import SocialDistributor
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "news.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def debug_run():
    print("🔍 Debugging Scheduler Logic...")
    
    # 1. Check DB Connection
    try:
        conn = get_db_connection()
        print("✅ DB Connection OK")
    except Exception as e:
        print(f"❌ DB Connection Failed: {e}")
        return

    # 2. Check Unshared Count
    try:
        count = conn.execute('SELECT count(*) FROM articles WHERE shared_on_x = 0 OR shared_on_x IS NULL').fetchone()[0]
        print(f"📊 Unshared Articles: {count}")
    except Exception as e:
        print(f"❌ Failed to count unshared: {e}")

    # 3. Check Last Shared
    try:
        last = conn.execute('SELECT shared_at FROM articles WHERE shared_on_x = 1 ORDER BY shared_at DESC LIMIT 1').fetchone()
        print(f"🕒 Last Shared Timestamp: {last['shared_at'] if last else 'NEVER'}")
    except Exception as e:
        print(f"❌ Failed to get last shared: {e}")

    # 4. Attempt Fetch Next
    print("👇 Fetching next article candidate...")
    article = conn.execute('SELECT * FROM articles WHERE shared_on_x = 0 OR shared_on_x IS NULL ORDER BY importance_score DESC, published_at DESC LIMIT 1').fetchone()
    
    if not article:
        print("❌ TOP PRIORITY: No article found to post!")
        return
        
    art_dict = dict(article)
    print(f"📄 Candidate: {art_dict['title']}")
    print(f"   Slug: {art_dict['slug']}")
    
    # 5. Simulate Post (Dry Run first check distributor init)
    print("🛠 Initializing SocialDistributor...")
    try:
        dist = SocialDistributor()
    except Exception as e:
        print(f"❌ SocialDistributor Init Failed: {e}")
        return

    print("🚀 Attempting POST to X (Live Test)...")
    article_for_dist = {
        'headline': art_dict['title'],
        'gist': art_dict['gist'],
        'seo_slug': art_dict['slug'],
        'source': art_dict.get('source', ''),
        'hashtags': json.loads(art_dict['hashtags']) if art_dict.get('hashtags') else [],
        'thought_provoking_question': art_dict.get('thought_provoking_question', '')
    }
    
    try:
        result = dist.post_to_x(article_for_dist)
        if result:
            print("✅ POST SUCCESS (Simulated or Real)")
            # Don't actually update DB in debug unless asked, to avoid messing state
        else:
            print("❌ POST FAILED (distributor returned False)")
    except Exception as e:
        print(f"❌ POST ERROR: {e}")

if __name__ == "__main__":
    debug_run()
