import sqlite3
import time
import os
import json
from social_distributor import SocialDistributor
from dotenv import load_dotenv

load_dotenv()

import pytz
from datetime import datetime, timedelta
import sys

# Ensure logs appear immediately in Supervisor
sys.stdout.reconfigure(line_buffering=True)

DB_PATH = "news.db"
INTERVAL_SECONDS = 1800  # 30 minutes (Max 48 articles per day)
QUIET_START = 4   # 4 AM
QUIET_END = 9     # 9 AM
TIMEZONE = pytz.timezone("Europe/Berlin")
VERSION = "2.1.0-POWER-DEDUP"

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

def clear_stale_queue():
    """Marks all unshared articles from PREVIOUS days as 'Skipped' (shared_on_x = 1).
    This ensures that every morning we start with a fresh slate of news."""
    conn = get_db_connection()
    # Use local date comparison to find articles older than today
    count = conn.execute("UPDATE articles SET shared_on_x = 1 WHERE (shared_on_x = 0 OR shared_on_x IS NULL) AND date(published_at) < date('now', 'localtime')").rowcount
    if count > 0:
        print(f"🧹 Daily Reset: Cleared {count} stale articles from the queue.")
    conn.commit()
    conn.close()

def get_last_post_time():
    conn = get_db_connection()
    # Get the timestamp of the most recently shared article
    # We use shared_at if available, fallback to published_at if not
    row = conn.execute('SELECT shared_at FROM articles WHERE shared_on_x = 1 ORDER BY shared_at DESC LIMIT 1').fetchone()
    conn.close()
    if row and row['shared_at']:
        try:
            # Handle different timestamp formats (ISO or DB format)
            ts = row['shared_at']
            if 'T' in ts:
                return datetime.fromisoformat(ts).replace(tzinfo=None)
            return datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
        except:
            return datetime.min
    return datetime.min

def mark_as_shared(slug):
    conn = get_db_connection()
    # Set shared_on_x = 1 and shared_at to current time in UTC/System format
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute('UPDATE articles SET shared_on_x = 1, shared_at = ? WHERE slug = ?', (now_str, slug))
    conn.commit()
    conn.close()

from remove_duplicates import remove_duplicates

def main_loop():
    print(f"🚀 Starting Tweet Scheduler v{VERSION}")
    print(f"📡 Config: Interval 1h | Quiet Window {QUIET_START}-{QUIET_END} AM DE")
    distributor = SocialDistributor()

    while True:
        try:
            # 0. Daily Reset: Clear anything from previous days
            clear_stale_queue()

            # 1. Quiet Hours: Disabled (24/7 Operation)
            # now_de = datetime.now(TIMEZONE)
            # if QUIET_START <= now_de.hour < QUIET_END:
            #     ...

            # 2. Check 1-hour gap (Verified against Database)
            last_shared_time = get_last_post_time()
            time_since_last = (datetime.now() - last_shared_time).total_seconds()
            
            if time_since_last < INTERVAL_SECONDS:
                remaining = INTERVAL_SECONDS - time_since_last
                print(f"⏳ 1-hour gap active. {remaining/60:.0f} mins remaining until next allowed post.")
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
                    'seo_slug': article['slug'],
                    'source': article.get('source', ''),
                    'hashtags': json.loads(article['hashtags']) if article.get('hashtags') else [],
                    'thought_provoking_question': article.get('thought_provoking_question', '')
                }
                
                if distributor.post_to_x(article_for_dist):
                    mark_as_shared(article['slug'])
                    print(f"✅ Successfully shared. Next post in 1 hour.")
                else:
                    # If we hit a 429, we should be AGGRESSIVE about waiting.
                    # Usually, 429 resets in 15-60 mins, but sometimes it's daily.
                    print(f"⚠️ [RATE LIMIT / ERROR] Post failed. Cooling down for 1 hour to reset quotas...")
                    time.sleep(3600) # Full 1 hour cooldown
            else:
                print("📭 No unshared articles. Checking again in 30 mins...")
                time.sleep(1800)
                
        except Exception as e:
            print(f"⚠️ Scheduler Error: {e}")
            time.sleep(600)

if __name__ == "__main__":
    main_loop()
