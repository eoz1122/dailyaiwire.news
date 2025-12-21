import sqlite3
import time
import os
from social_distributor import SocialDistributor
from dotenv import load_dotenv

load_dotenv()

import pytz
from datetime import datetime, timedelta

DB_PATH = "news.db"
INTERVAL_SECONDS = 14400  # 4 hours (Max 6 articles per day)
QUIET_START = 4   # 4 AM
QUIET_END = 9     # 9 AM
TIMEZONE = pytz.timezone("Europe/Berlin")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_next_article_to_share():
    conn = get_db_connection()
    # Breaking News First: Prioritize the absolute newest unshared article (DESC).
    # Older unshared articles stay in the queue and are only used as 'fillers' 
    # if no fresher intelligence has arrived by the next posting window.
    article = conn.execute('SELECT * FROM articles WHERE shared_on_x = 0 OR shared_on_x IS NULL ORDER BY published_at DESC LIMIT 1').fetchone()
    conn.close()
    return dict(article) if article else None

def mark_as_shared(slug):
    conn = get_db_connection()
    conn.execute('UPDATE articles SET shared_on_x = 1 WHERE slug = ?', (slug,))
    conn.commit()
    conn.close()

from remove_duplicates import remove_duplicates

def main_loop():
    print(f"🚀 Starting Tweet Scheduler (Interval: 4h | Quiet: {QUIET_START}-{QUIET_END} AM DE)...")
    distributor = SocialDistributor()
    last_post_time = datetime.min

    while True:
        try:
            # 1. Check Time Window (Europe/Berlin)
            now_de = datetime.now(TIMEZONE)
            current_hour = now_de.hour
            
            if QUIET_START <= current_hour < QUIET_END:
                print(f"😴 Quiet Period in DE ({current_hour}:00). Waiting for 9 AM...")
                # Sleep until 9 AM
                target = now_de.replace(hour=QUIET_END, minute=0, second=0, microsecond=0)
                wait_seconds = (target - now_de).total_seconds()
                time.sleep(max(wait_seconds, 60))
                continue

            # 2. Check 4-hour gap
            time_since_last = (datetime.now() - last_post_time).total_seconds()
            if time_since_last < INTERVAL_SECONDS:
                remaining = INTERVAL_SECONDS - time_since_last
                # Small sleep to check again rather than huge sleep to be more responsive to restarts
                time.sleep(min(remaining, 600)) 
                continue

            # 3. Final safeguard: Clean up any semantic duplicates
            remove_duplicates(seq_threshold=0.8, word_threshold=0.6)
            
            article = get_next_article_to_share()
            
            if article:
                print(f"📡 Next up for X: {article['title']}")
                
                article_for_dist = {
                    'headline': article['title'],
                    'gist': article['gist'],
                    'seo_slug': article['slug']
                }
                
                if distributor.post_to_x(article_for_dist):
                    mark_as_shared(article['slug'])
                    last_post_time = datetime.now()
                    print(f"✅ Successfully shared. Next post in 4 hours (if window allows).")
                else:
                    print(f"❌ Post failed. Will retry in 10 mins.")
                    time.sleep(600)
            else:
                print("📭 No unshared articles. Checking again in 10 mins...")
                time.sleep(600)
                
        except Exception as e:
            print(f"⚠️ Scheduler Error: {e}")
            time.sleep(600)

if __name__ == "__main__":
    main_loop()
