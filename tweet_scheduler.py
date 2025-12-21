import sqlite3
import time
import os
from social_distributor import SocialDistributor
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "news.db"
INTERVAL_SECONDS = 900  # 15 minutes

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_next_article_to_share():
    conn = get_db_connection()
    # Get the oldest unshared article (ASC) to maintain chronological order on the timeline
    article = conn.execute('SELECT * FROM articles WHERE shared_on_x = 0 OR shared_on_x IS NULL ORDER BY published_at ASC LIMIT 1').fetchone()
    conn.close()
    return dict(article) if article else None

def mark_as_shared(slug):
    conn = get_db_connection()
    conn.execute('UPDATE articles SET shared_on_x = 1 WHERE slug = ?', (slug,))
    conn.commit()
    conn.close()

def main_loop():
    print("🚀 Starting Tweet Scheduler (Interval: 15 mins)...")
    distributor = SocialDistributor()

    while True:
        try:
            article = get_next_article_to_share()
            
            if article:
                print(f"📡 Next up for X: {article['title']}")
                
                # Adapting keys for SocialDistributor
                article_for_dist = {
                    'headline': article['title'],
                    'gist': article['gist'],
                    'seo_slug': article['slug']
                }
                
                success = distributor.post_to_x(article_for_dist)
                
                if success:
                    mark_as_shared(article['slug'])
                    print(f"✅ Successfully shared and marked in DB.")
                else:
                    print(f"❌ Post failed. Will retry next cycle.")
            else:
                print("📭 No unshared articles in the wire.")
                
        except Exception as e:
            print(f"⚠️ Scheduler Error: {e}")
            
        print(f"💤 Sleeping for {INTERVAL_SECONDS/60:.0f} minutes...")
        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    # Removed the immediate post test here as it often results in duplicates 
    # when main_loop() starts immediately after.
    main_loop()
