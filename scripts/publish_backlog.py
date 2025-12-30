
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
    print("⚡ Will post them with a 90 second delay between each to prevent rate limits.")
    
    for i, art in enumerate(articles):
        print(f"\n[{i+1}/{len(articles)}] Posting: {art['title']}")
        
        # Prepare payload
        payload = {
            'headline': art['title'],
            'gist': art['gist'],
            'seo_slug': art['slug'],
            'source': art.get('source', ''),
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
            else:
                print("⚠️ Failed to publish.")
        except Exception as e:
            print(f"❌ Error publishing: {e}")
            
        if i < len(articles) - 1:
            print("⏳ Waiting 90 seconds...")
            time.sleep(90)

    print("\n🎉 Backlog cleared!")

if __name__ == "__main__":
    catch_up_posting()
