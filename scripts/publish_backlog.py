
import sqlite3
import time
import sys
import os
import json
from datetime import datetime
from datetime import timedelta

# Add parent directory to path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from social_distributor import SocialDistributor

DB_PATH = "news.db"

def catch_up_posting():
    print("🚀 Starting Backlog Catch-Up Publisher...")
    
    # Initialize Distributor
    try:
        distributor = SocialDistributor()
    except Exception as e:
        print(f"❌ Failed to init SocialDistributor: {e}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Calculate cutoff time (14 hours ago to be safe for "last 12 hours")
    cutoff = (datetime.utcnow() - timedelta(hours=14)).isoformat()
    
    # Get unshared articles from this window
    print(f"🔍 Searching for unshared articles since {cutoff}...")
    cursor = conn.execute('''
        SELECT * FROM articles 
        WHERE published_at > ? 
        AND (shared_on_x = 0 OR shared_on_x IS NULL)
        ORDER BY importance_score DESC, published_at ASC
    ''', (cutoff,))
    
    articles = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    if not articles:
        print("✅ No backlog found! You are all caught up.")
        return

    print(f"found {len(articles)} missed articles.")
    print("⚡ Will post them with a delay to prevent rate limits.")
    
    i = 0
    while i < len(articles):
        art = articles[i]
        print(f"\n[{i+1}/{len(articles)}] Posting: {art['title']}")
        
        # On-the-fly Source Cleanup (Fixes old entries in DB)
        real_source = art.get('source', '')
        if real_source in ["Hacker News (AI)", "Google News", "Papers with Code"]:
             try:
                from urllib.parse import urlparse
                domain = urlparse(art['source_url']).netloc.replace('www.', '')
                if domain:
                    real_source = domain.split('.')[0].title()
                    overrides = {
                        'Bbc': 'BBC News', 'Ycombinator': 'Hacker News', 'Github': 'GitHub',
                        'Arxiv': 'ArXiv', 'Youtube': 'YouTube', 'Nytimes': 'NY Times',
                        'Wsj': 'WSJ', 'Cnbc': 'CNBC', 'Techcrunch': 'TechCrunch'
                    }
                    real_source = overrides.get(real_source, real_source)
             except Exception:
                pass

        # Prepare payload
        payload = {
            'headline': art['title'],
            'gist': art['gist'],
            'seo_slug': art['slug'],
            'source': real_source,
            'hashtags': json.loads(art['hashtags']) if art.get('hashtags') else [],
            'thought_provoking_question': art.get('thought_provoking_question', '')
        }
        
        try:
            success = distributor.post_to_x(payload)
            if success:
                # Update DB
                conn = sqlite3.connect(DB_PATH)
                conn.execute('UPDATE articles SET shared_on_x = 1, shared_at = ? WHERE slug = ?', 
                           (datetime.utcnow().isoformat(), art['slug']))
                conn.commit()
                conn.close()
                print("✅ Published successfully!")
                i += 1 # Move to next
                print("⏳ Waiting 120 seconds...")
                time.sleep(120)
            else:
                print("⚠️ Failed to publish (False returned).")
                i += 1
                time.sleep(10)
        except Exception as e:
            if "429" in str(e):
                print("🛑 RATE LIMIT HIT (429). Sleeping for 15 minutes before retrying...")
                time.sleep(900)
                # Do not increment i, retry same article
            else:
                print(f"❌ Error publishing: {e}")
                i += 1
                time.sleep(10)


    print("\n🎉 Backlog cleared!")

if __name__ == "__main__":
    catch_up_posting()
