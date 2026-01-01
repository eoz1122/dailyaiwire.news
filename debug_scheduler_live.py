import sys
import os
import sqlite3
import datetime
import time

# Force unbuffered IO
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

print("🔍 DEBUG: Starting Scheduler Diagnostic...")

# Import local modules
try:
    from social_distributor import SocialDistributor
    print("✅ Imported SocialDistributor")
except ImportError as e:
    print(f"❌ Failed to import SocialDistributor: {e}")

try:
    from remove_duplicates import remove_duplicates
    print("✅ Imported remove_duplicates")
except ImportError as e:
    print(f"❌ Failed to import remove_duplicates: {e}")

DB_PATH = "news.db"

def check_db():
    print(f"🔍 DEBUG: Checking database at {DB_PATH}...")
    if not os.path.exists(DB_PATH):
        print(f"❌ Database file not found!")
        return
    
    try:
        conn = sqlite3.connect(DB_PATH)
        curr = conn.cursor()
        curr.execute("SELECT COUNT(*) FROM articles WHERE shared_on_x = 0 OR shared_on_x IS NULL")
        count = curr.fetchone()[0]
        print(f"✅ Database connection successful. Unshared articles: {count}")
        conn.close()
    except Exception as e:
        print(f"❌ Database error: {e}")

def get_next_article():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    query = '''
        SELECT *, 
        (importance_score + 
            CASE 
                WHEN published_at > datetime('now', '-6 hours') THEN 20 
                WHEN published_at > datetime('now', '-12 hours') THEN 10 
                ELSE 0 
            END
        ) as hybrid_rank 
        FROM articles 
        WHERE shared_on_x = 0 OR shared_on_x IS NULL 
        ORDER BY hybrid_rank DESC
        LIMIT 1
    '''
    article = conn.execute(query).fetchone()
    conn.close()
    return dict(article) if article else None

def run_diagnostic():
    check_db()
    
    print("\n🔍 DEBUG: Testing Deduplication (Potential Hang Point)...")
    start_time = time.time()
    try:
        # Run dedupe logic (this is where we suspect the hang)
        # We pass recent_only=True to match production default
        remove_duplicates(recent_only=True)
        print(f"✅ Deduplication finished in {time.time() - start_time:.2f} seconds")
    except Exception as e:
        print(f"❌ Deduplication crashed: {e}")
    except KeyboardInterrupt:
        print("❌ Deduplication interrupted manually (HANG CONFIRMED)")
        return

    print("\n🔍 DEBUG: Fetching next article...")
    article = get_next_article()
    
    if article:
        print(f"✅ Found candidate: {article['title']}")
        print(f"   Published: {article['published_at']}")
        print(f"   Slug: {article['slug']}")
    else:
        print("⚠️ No unshared articles found (Queue Empty)")

    print("\n🏁 Diagnostic Complete.")

if __name__ == "__main__":
    run_diagnostic()
