import sys
import os
import time
import json
import sqlite3
import logging

from datetime import datetime, timedelta, timezone
import pytz

from dotenv import load_dotenv
load_dotenv()

from logging_config import setup_logging
setup_logging()

logger = logging.getLogger('scheduler')

# Force unbuffered output for supervisor logs
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

logger.debug("[1/6] Core imports started (sys, os) - PID: %d", os.getpid())
logger.debug("[2/6] Standard libraries imported")
logger.debug("[3/6] Date/Time libraries imported")
logger.debug("[4/6] Dotenv loaded")

logger.debug("[5/6] Importing SocialDistributor...")
from social_distributor import SocialDistributor
logger.debug("[5.5/6] SocialDistributor imported.")

logger.debug("[6/6] Importing Remove Duplicates...")
from remove_duplicates import remove_duplicates
logger.debug("[6.5/6] Remove Duplicates imported.")

DB_PATH = "news.db"
INTERVAL_SECONDS = 7200  # 2 hours
QUIET_START = 4   # 4 AM
QUIET_END = 9     # 9 AM
TIMEZONE = pytz.timezone("Europe/Berlin")
VERSION = "2.3.0"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_next_article_to_share():
    conn = get_db_connection()
    # Hybrid Logic: Importance + Freshness
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
        WHERE (shared_on_x = 0 OR shared_on_x IS NULL) 
        AND is_published = 1
        AND published_at <= datetime('now', 'localtime')
        ORDER BY hybrid_rank DESC
        LIMIT 1
    '''
    article = conn.execute(query).fetchone()
    conn.close()
    return dict(article) if article else None

def clear_stale_queue():
    """Marks all unshared articles older than 48 hours as 'Skipped'."""
    conn = get_db_connection()
    limit_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    count = conn.execute("UPDATE articles SET shared_on_x = 1 WHERE (shared_on_x = 0 OR shared_on_x IS NULL) AND published_at < ?", (limit_time,)).rowcount
    if count > 0:
        logger.info("🧹 Queue Maintenance: Cleared %d stale articles.", count)
    conn.commit()
    conn.close()

def get_last_post_time():
    conn = get_db_connection()
    row = conn.execute('SELECT shared_at FROM articles WHERE shared_on_x = 1 ORDER BY shared_at DESC LIMIT 1').fetchone()
    conn.close()
    if row and row['shared_at']:
        try:
            ts = row['shared_at']
            if 'T' in ts:
                dt = datetime.fromisoformat(ts)
            else:
                dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
            
            # Force UTC if naive
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            return datetime.min.replace(tzinfo=timezone.utc)
    return datetime.min.replace(tzinfo=timezone.utc)

def mark_as_shared(slug):
    conn = get_db_connection()
    now_str = datetime.now(timezone.utc).isoformat()
    conn.execute('UPDATE articles SET shared_on_x = 1, shared_at = ? WHERE slug = ?', (now_str, slug))
    conn.commit()
    conn.close()

def mark_as_shared_ig(slug):
    """Mark article as shared on Instagram."""
    conn = get_db_connection()
    conn.execute('UPDATE articles SET shared_on_ig = 1 WHERE slug = ?', (slug,))
    conn.commit()
    conn.close()

def mark_as_shared_fb(slug):
    """Mark article as shared on Facebook."""
    conn = get_db_connection()
    conn.execute('UPDATE articles SET shared_on_fb = 1 WHERE slug = ?', (slug,))
    conn.commit()
    conn.close()

def main_loop():
    logger.info("🚀 Starting Tweet Scheduler v%s", VERSION)
    logger.info("📡 Config: Interval 2h | Quiet Window %d-%d AM DE", QUIET_START, QUIET_END)
    distributor = SocialDistributor()

    while True:
        try:
            logger.info("💓 [Heartbeat] Scheduler Alive at %s", datetime.now().strftime('%H:%M:%S'))

            # 0. Daily Reset: Clear anything from previous days
            clear_stale_queue()
            
            # --- WEEKLY WRAP AUTOMATION ---
            # Every Sunday at 18:00 (or first check after), generate draft
            now = datetime.now()
            if now.weekday() == 6 and now.hour >= 18: 
                # Check directly in DB if we made one this week
                conn = get_db_connection()
                # Look for a newsletter created in the last 24 hours
                last_24h = (now - timedelta(days=1)).isoformat()
                row = conn.execute("SELECT id FROM newsletters WHERE created_at > ?", (last_24h,)).fetchone()
                conn.close()
                
                if not row:
                    logger.info("🗞️ It's Sunday Evening! Triggering Weekly Wrap Synthesis...")
                    try:
                        import weekly_curator
                        weekly_curator.generate_newsletter_draft()
                    except Exception as e:
                        logger.error("❌ Failed to auto-generate weekly wrap: %s", e)
            # -------------------------------

            # 2. Check 2-hour gap (Verified against Database)
            last_shared_time = get_last_post_time()
            time_since_last = (datetime.now(timezone.utc) - last_shared_time).total_seconds()
            
            if time_since_last < INTERVAL_SECONDS:
                remaining = INTERVAL_SECONDS - time_since_last
                logger.info("⏳ GAP CONTROL: %.0f mins remaining until next allowed post.", remaining/60)
                time.sleep(min(remaining, 600)) 
                continue

            # 3. Final safeguard: Clean up any semantic duplicates
            # WRAPPED IN TRY/EXCEPT TO PREVENT MAIN LOOP CRASH
            try:
                remove_duplicates(seq_threshold=0.8, word_threshold=0.6)
            except Exception as e:
                logger.warning("⚠️ [Non-Critical] Deduplication error: %s", e)
            
            article = get_next_article_to_share()
            
            if article:
                logger.info("📡 Found unshared article: %s", article['title'])
                logger.info("⏰ Article published at: %s", article['published_at'])
                
                article_for_dist = {
                    'headline': article['title'],
                    'gist': article['gist'],
                    'seo_slug': article['slug'],
                    'source': article.get('source', ''),
                    'hashtags': json.loads(article['hashtags']) if article.get('hashtags') else [],
                    'thought_provoking_question': article.get('thought_provoking_question', ''),
                    'image': article.get('image', ''),
                }
                
                logger.info("🚀 Attempting to post to X...")
                if distributor.post_to_x(article_for_dist):
                    mark_as_shared(article['slug'])
                    logger.info("✅ Successfully shared on X. Waiting %.0f mins.", INTERVAL_SECONDS/60)
                    time.sleep(4) # Rate Limit Safety
                else:
                    logger.warning("⚠️ [X ERROR] Post failed. Cooling down for 1 hour...")
                    time.sleep(3600)
                
                # --- INSTAGRAM DISTRIBUTION ---
                try:
                    if not article.get('shared_on_ig'):
                        logger.info("📸 Attempting to post to Instagram...")
                        if distributor.post_to_instagram(article_for_dist):
                            mark_as_shared_ig(article['slug'])
                            logger.info("✅ Successfully shared on Instagram.")
                        else:
                            logger.warning("⚠️ [IG SKIP] Instagram post failed or skipped.")
                except Exception as ig_err:
                    logger.error("❌ [IG ERROR] Instagram distribution failed: %s", ig_err)
                
                # --- FACEBOOK DISTRIBUTION ---
                try:
                    if not article.get('shared_on_fb'):
                        logger.info("📘 Attempting to post to Facebook...")
                        if distributor.post_to_facebook(article_for_dist):
                            mark_as_shared_fb(article['slug'])
                            logger.info("✅ Successfully shared on Facebook.")
                        else:
                            logger.warning("⚠️ [FB SKIP] Facebook post failed or skipped.")
                except Exception as fb_err:
                    logger.error("❌ [FB ERROR] Facebook distribution failed: %s", fb_err) 
            else:
                logger.info("📭 Queue is empty (0 unshared articles). Checking again in 10 mins...")
                time.sleep(600)
                
        except Exception as e:
            logger.error("⚠️ Scheduler Critical Error: %s", e)
            time.sleep(600)

if __name__ == "__main__":
    main_loop()
