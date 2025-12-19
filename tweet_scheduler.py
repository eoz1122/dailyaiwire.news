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
    # Get the oldest unshared article
    article = conn.execute('SELECT * FROM articles WHERE shared_on_x = 0 OR shared_on_x IS NULL ORDER BY published_at DESC LIMIT 1').fetchone()
    conn.close()
    return dict(article) if article else None

def mark_as_shared(slug):
    conn = get_db_connection()
    conn.execute('UPDATE articles SET shared_on_x = 1 WHERE slug = ?', (slug,))
    conn.commit()
    conn.close()

def main_loop():
    print("🚀 Starting Tweet Scheduler (Every 15 mins)...")
    distributor = SocialDistributor()

    while True:
        try:
            article = get_next_article_to_share()
            
            if article:
                print(f"found article to share: {article['title']}")
                # Construct article object expected by distributor
                # Distributor expects: headline, gist, seo_slug
                # The DB has: title, gist, slug
                
                # Adapting keys
                article_for_dist = {
                    'headline': article['title'],
                    'gist': article['gist'],
                    'seo_slug': article['slug']
                }
                
                success = distributor.post_to_x(article_for_dist)
                
                if success:
                    mark_as_shared(article['slug'])
                    print(f"✅ Marked '{article['title']}' as shared.")
                else:
                    print(f"❌ Failed to share '{article['title']}'. Will retry later.")
            else:
                print("📭 No new articles to share.")
                
        except Exception as e:
            print(f"❌ Error in scheduler: {e}")
            
        print(f"Sleeping for {INTERVAL_SECONDS} seconds...")
        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    print("🚀 Immediate Twitter Test on Startup...")
    # Run once immediately
    distributor = SocialDistributor()
    try:
        conn = get_db_connection()
        article = conn.execute('SELECT * FROM articles WHERE shared_on_x = 0 ORDER BY published_at ASC LIMIT 1').fetchone()
        if article:
            print(f"🐦 Immediate Post: {article['title']}")
            # Adapt keys for distributor
            article_for_dist = {
                'headline': article['title'],
                'gist': article['gist'],
                'seo_slug': article['slug']
            }
            if distributor.post_to_x(article_for_dist):
                conn.execute('UPDATE articles SET shared_on_x = 1 WHERE id = ?', (article['id'],))
                conn.commit()
                print("✅ Immediate post success.")
        conn.close()
    except Exception as e:
        print(f"❌ Immediate post failed: {e}")

    # Enter loop
    main_loop()
