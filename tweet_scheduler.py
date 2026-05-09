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
from social_distributor import SocialDistributor, XPostingPause
logger.debug("[5.5/6] SocialDistributor imported.")

logger.debug("[6/6] Importing Remove Duplicates...")
from remove_duplicates import remove_duplicates
logger.debug("[6.5/6] Remove Duplicates imported.")

DB_PATH = "news.db"
INTERVAL_SECONDS = int(os.getenv('SCHEDULER_INTERVAL_SECONDS', '7200'))  # 2 hours
QUIET_START = int(os.getenv('SCHEDULER_QUIET_START', '4'))   # 4 AM
QUIET_END = int(os.getenv('SCHEDULER_QUIET_END', '9'))       # 9 AM
TIMEZONE = pytz.timezone(os.getenv('SCHEDULER_TIMEZONE', 'Europe/Berlin'))
VERSION = "2.5.2"
FB_DAILY_LIMIT = int(os.getenv('FB_DAILY_LIMIT', '8'))  # Max Facebook posts per day
FB_BACKOFF_MAX_HOURS = int(os.getenv('FB_BACKOFF_MAX_HOURS', '48'))  # Maximum backoff window
FB_GAP_SECONDS = int(os.getenv('FB_GAP_SECONDS', '10800'))  # 3 hours between FB posts
FB_TIMEZONE = pytz.timezone(os.getenv('FB_TIMEZONE', 'Europe/London'))  # UK time
IG_ENABLED = os.getenv('IG_ENABLED', 'false').lower() == 'true'  # Disabled during suspension
IG_GAP_SECONDS = int(os.getenv('IG_GAP_SECONDS', '10800'))  # 3 hours between IG posts
META_POSTING_ENABLED = os.getenv('META_POSTING_ENABLED', 'false').lower() == 'true'
X_FAILURE_BACKOFF_SECONDS = int(os.getenv('X_FAILURE_BACKOFF_SECONDS', '3600'))
X_DAILY_LIMIT = int(os.getenv('X_DAILY_LIMIT', '3'))

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

# ── Hybrid ranking query (reusable) ─────────────────────────────────
_HYBRID_RANK_SQL = """
    (importance_score +
        CASE
            WHEN published_at > datetime('now', '-6 hours') THEN 20
            WHEN published_at > datetime('now', '-12 hours') THEN 10
            ELSE 0
        END
    ) as hybrid_rank
"""

def _get_next_article_for(platform_col, max_age_days=None):
    """Get the next unshared article for a given platform column.
    
    Args:
        platform_col: DB column tracking share state (e.g. 'shared_on_ig')
        max_age_days: If set, only consider articles published within this many days.
    """
    conn = get_db_connection()
    age_filter = ""
    if max_age_days:
        age_filter = f"AND published_at > datetime('now', '-{int(max_age_days)} days')"
    query = f'''
        SELECT *, {_HYBRID_RANK_SQL}
        FROM articles
        WHERE ({platform_col} = 0 OR {platform_col} IS NULL)
        AND is_published = 1
        AND published_at <= datetime('now', 'localtime')
        {age_filter}
        ORDER BY hybrid_rank DESC
        LIMIT 1
    '''
    article = conn.execute(query).fetchone()
    conn.close()
    return dict(article) if article else None

def get_next_article_to_share():
    return _get_next_article_for('shared_on_x')

def get_next_article_for_ig():
    return _get_next_article_for('shared_on_ig', max_age_days=3)

def get_next_article_for_fb():
    return _get_next_article_for('shared_on_fb', max_age_days=3)

def clear_stale_queue():
    """Marks all unshared articles older than 48 hours as 'Skipped' on X."""
    conn = get_db_connection()
    limit_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    count = conn.execute("UPDATE articles SET shared_on_x = 1 WHERE (shared_on_x = 0 OR shared_on_x IS NULL) AND published_at < ?", (limit_time,)).rowcount
    if count > 0:
        logger.info("🧹 Queue Maintenance: Cleared %d stale articles.", count)
    conn.commit()
    conn.close()

def _parse_timestamp(ts):
    """Parse an ISO or space-separated timestamp string into a UTC-aware datetime."""
    if not ts:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        if 'T' in ts:
            dt = datetime.fromisoformat(ts)
        else:
            dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)

def _get_last_post_time(col, time_col):
    """Get the last post time for a given platform."""
    conn = get_db_connection()
    row = conn.execute(f'SELECT {time_col} FROM articles WHERE {col} = 1 ORDER BY {time_col} DESC LIMIT 1').fetchone()
    conn.close()
    return _parse_timestamp(row[time_col] if row else None)

def get_last_post_time():
    return _get_last_post_time('shared_on_x', 'shared_at')


def get_x_posts_today(now_utc=None):
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    local_now = now_utc.astimezone(TIMEZONE)
    local_day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start_utc = local_day_start.astimezone(timezone.utc).isoformat()

    conn = get_db_connection()
    row = conn.execute(
        'SELECT COUNT(*) as cnt FROM articles WHERE shared_on_x = 1 AND shared_at >= ?',
        (day_start_utc,)
    ).fetchone()
    conn.close()
    return row['cnt'] if row else 0

def get_last_ig_post_time():
    return _get_last_post_time('shared_on_ig', 'shared_on_ig_at')

def get_last_fb_post_time():
    return _get_last_post_time('shared_on_fb', 'shared_on_fb_at')

def mark_as_shared(slug):
    conn = get_db_connection()
    now_str = datetime.now(timezone.utc).isoformat()
    conn.execute('UPDATE articles SET shared_on_x = 1, shared_at = ? WHERE slug = ?', (now_str, slug))
    conn.commit()
    conn.close()

def mark_as_shared_ig(slug):
    """Mark article as shared on Instagram with timestamp."""
    conn = get_db_connection()
    now_str = datetime.now(timezone.utc).isoformat()
    conn.execute('UPDATE articles SET shared_on_ig = 1, shared_on_ig_at = ? WHERE slug = ?', (now_str, slug))
    conn.commit()
    conn.close()

def mark_as_shared_fb(slug):
    """Mark article as shared on Facebook with timestamp."""
    conn = get_db_connection()
    now_str = datetime.now(timezone.utc).isoformat()
    conn.execute('UPDATE articles SET shared_on_fb = 1, shared_on_fb_at = ? WHERE slug = ?', (now_str, slug))
    conn.commit()
    conn.close()

def get_fb_posts_today():
    """Count Facebook posts made in the last 24 hours."""
    conn = get_db_connection()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    row = conn.execute(
        'SELECT COUNT(*) as cnt FROM articles WHERE shared_on_fb = 1 AND shared_on_fb_at > ?',
        (cutoff,)
    ).fetchone()
    conn.close()
    return row['cnt'] if row else 0

def _build_article_payload(article):
    """Build the distribution payload dict from a DB article row."""
    return {
        'headline': article['title'],
        'gist': article['gist'],
        'why_it_matters': article.get('why_it_matters', ''),
        'category': article.get('category', ''),
        'seo_slug': article['slug'],
        'source': article.get('source', ''),
        'hashtags': json.loads(article['hashtags']) if article.get('hashtags') else [],
        'thought_provoking_question': article.get('thought_provoking_question', ''),
        'image': article.get('image', ''),
    }


def _build_x_backoff_window(reason, seconds, now_utc=None):
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    until = now_utc + timedelta(seconds=max(0, int(seconds)))
    label = {
        'billing': 'billing/credits',
        'rate_limit': 'rate limit',
        'error': 'generic error',
    }.get(reason, reason or 'generic error')
    return until, label

# ── Main Loop ───────────────────────────────────────────────────────

def main_loop():
    logger.info("🚀 Starting Tweet Scheduler v%s", VERSION)
    logger.info("📡 Config: Interval %ds | Quiet %d-%d AM DE | FB Limit %d/day",
                INTERVAL_SECONDS, QUIET_START, QUIET_END, FB_DAILY_LIMIT)
    logger.info("📡 X cost control: daily limit %d | URLs %s",
                X_DAILY_LIMIT,
                "enabled" if os.getenv('X_INCLUDE_URL', 'false').lower() in {'1', 'true', 'yes', 'on'} else "disabled")
    logger.info("📡 Mode: DECOUPLED — each platform posts independently")
    if not META_POSTING_ENABLED:
        logger.info("📡 Meta posting disabled. Scheduler will post to X only.")
    distributor = SocialDistributor()

    # Facebook exponential backoff state
    fb_backoff_hours = 0
    fb_backoff_until = None

    # Instagram backoff state (rate limit recovery)
    ig_backoff_hours = 0
    ig_backoff_until = None

    # X backoff state (billing/rate-limit/error recovery)
    x_backoff_until = None
    x_backoff_reason = None

    while True:
        try:
            logger.info("💓 [Heartbeat] Scheduler Alive at %s", datetime.now().strftime('%H:%M:%S'))

            # 0. Daily Reset: Clear stale X queue
            clear_stale_queue()

            # --- WEEKLY WRAP AUTOMATION ---
            now = datetime.now()
            if now.weekday() == 6 and now.hour >= 18:
                conn = get_db_connection()
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

            # --- Deduplication safeguard ---
            try:
                remove_duplicates(seq_threshold=0.8, word_threshold=0.6)
            except Exception as e:
                logger.warning("⚠️ [Non-Critical] Deduplication error: %s", e)

            did_any_work = False

            # ═══════════════════════════════════════════════════════
            # PLATFORM 1: X (Twitter)
            # ═══════════════════════════════════════════════════════
            try:
                now_utc = datetime.now(timezone.utc)

                if x_backoff_until and now_utc < x_backoff_until:
                    remaining = (x_backoff_until - now_utc).total_seconds() / 60
                    logger.warning("🐦 [X] ⏸ Backoff active (%s): %.0f mins remaining.", x_backoff_reason, remaining)
                else:
                    if x_backoff_until and now_utc >= x_backoff_until:
                        x_backoff_until = None
                        x_backoff_reason = None

                    x_posts_today = get_x_posts_today(now_utc=now_utc)
                    if X_DAILY_LIMIT > 0 and x_posts_today >= X_DAILY_LIMIT:
                        next_reset_local = now_utc.astimezone(TIMEZONE).replace(
                            hour=0, minute=0, second=0, microsecond=0
                        ) + timedelta(days=1)
                        remaining = (next_reset_local.astimezone(timezone.utc) - now_utc).total_seconds() / 60
                        logger.info(
                            "🐦 [X] 🛑 Daily limit reached (%d/%d). Next reset in %.0f mins.",
                            x_posts_today,
                            X_DAILY_LIMIT,
                            remaining,
                        )
                    else:
                        last_x_time = get_last_post_time()
                        x_gap = (now_utc - last_x_time).total_seconds()

                        if x_gap < INTERVAL_SECONDS:
                            remaining = (INTERVAL_SECONDS - x_gap) / 60
                            logger.info("🐦 [X] ⏳ %.0f mins until next post.", remaining)
                        else:
                            x_article = get_next_article_to_share()
                            if x_article:
                                payload = _build_article_payload(x_article)
                                logger.info("🐦 [X] Posting: %s", x_article['title'][:60])
                                if distributor.post_to_x(payload):
                                    mark_as_shared(x_article['slug'])
                                    logger.info("🐦 [X] ✅ Posted successfully.")
                                    x_backoff_until = None
                                    x_backoff_reason = None
                                    did_any_work = True
                                else:
                                    x_backoff_until, x_backoff_reason = _build_x_backoff_window(
                                        'error',
                                        X_FAILURE_BACKOFF_SECONDS,
                                        now_utc=now_utc,
                                    )
                                    logger.warning(
                                        "🐦 [X] ⚠️ Post failed. Backoff engaged (%s) until %s.",
                                        x_backoff_reason,
                                        x_backoff_until.strftime('%H:%M UTC'),
                                    )
                            else:
                                logger.info("🐦 [X] 📭 No unshared articles.")
            except XPostingPause as x_pause:
                x_backoff_until, x_backoff_reason = _build_x_backoff_window(
                    x_pause.reason,
                    x_pause.retry_after_seconds,
                )
                logger.warning(
                    "🐦 [X] ⏸ Backoff engaged (%s) until %s.",
                    x_backoff_reason,
                    x_backoff_until.strftime('%H:%M UTC'),
                )
                logger.error("🐦 [X] ❌ Posting paused: %s", x_pause)
            except Exception as x_err:
                x_backoff_until, x_backoff_reason = _build_x_backoff_window(
                    'error',
                    X_FAILURE_BACKOFF_SECONDS,
                )
                logger.error("🐦 [X] ❌ Error: %s", x_err)
                logger.warning(
                    "🐦 [X] ⏸ Backoff engaged (%s) until %s.",
                    x_backoff_reason,
                    x_backoff_until.strftime('%H:%M UTC'),
                )

            time.sleep(2)  # Brief pause between platform API calls

            # ═══════════════════════════════════════════════════════
            # PLATFORM 2: Instagram
            # ═══════════════════════════════════════════════════════
            try:
                if not META_POSTING_ENABLED:
                    logger.info("📸 [IG] ⛔ DISABLED - Meta posting removed.")
                elif not IG_ENABLED:
                    logger.warning("📸 [IG] ⛔ DISABLED — account suspended. Set IG_ENABLED=true to re-enable.")
                elif ig_backoff_until and datetime.now(timezone.utc) < ig_backoff_until:
                    remaining = (ig_backoff_until - datetime.now(timezone.utc)).total_seconds() / 3600
                    logger.info("📸 [IG] ⏳ Backoff: %.1fh remaining.", remaining)
                else:
                    last_ig_time = get_last_ig_post_time()
                    ig_gap = (datetime.now(timezone.utc) - last_ig_time).total_seconds()

                    if ig_gap < IG_GAP_SECONDS:
                        remaining = (IG_GAP_SECONDS - ig_gap) / 60
                        logger.info("📸 [IG] ⏳ %.0f mins until next post.", remaining)
                    else:
                        ig_article = get_next_article_for_ig()
                        if ig_article:
                            # PRE-MARK to prevent duplicate posting on retry/crash
                            mark_as_shared_ig(ig_article['slug'])
                            payload = _build_article_payload(ig_article)
                            logger.info("📸 [IG] Posting: %s", ig_article['title'][:60])
                            if distributor.post_to_instagram(payload):
                                logger.info("📸 [IG] ✅ Posted successfully.")
                                ig_backoff_hours = 0
                                ig_backoff_until = None
                                did_any_work = True
                            else:
                                logger.warning("📸 [IG] ⚠️ Post failed or skipped (article marked to prevent duplicate).")
                        else:
                            logger.info("📸 [IG] 📭 No unshared articles.")
            except Exception as ig_err:
                logger.error("📸 [IG] ❌ Error: %s", ig_err)
                ig_backoff_hours = min(max(ig_backoff_hours * 2, 3), 24)
                ig_backoff_until = datetime.now(timezone.utc) + timedelta(hours=ig_backoff_hours)
                logger.warning("📸 [IG] Backoff engaged: %dh (until %s).", ig_backoff_hours, ig_backoff_until.strftime('%H:%M UTC'))

            time.sleep(2)  # Brief pause between platform API calls

            # ═══════════════════════════════════════════════════════
            # PLATFORM 3: Facebook (1 PM UK → every 3h → max 4/day)
            # ═══════════════════════════════════════════════════════
            try:
                uk_now = datetime.now(FB_TIMEZONE)

                # Gate 1: Exponential backoff (rate-limit recovery)
                if not META_POSTING_ENABLED:
                    logger.info("📘 [FB] ⛔ DISABLED - Meta posting removed.")
                elif fb_backoff_until and datetime.now(timezone.utc) < fb_backoff_until:
                    remaining = (fb_backoff_until - datetime.now(timezone.utc)).total_seconds() / 3600
                    logger.info("📘 [FB] ⏳ Backoff: %.1fh remaining.", remaining)

                # Gate 2: Daily limit
                elif get_fb_posts_today() >= FB_DAILY_LIMIT:
                    logger.info("📘 [FB] 🛑 Daily limit reached (%d/%d).", get_fb_posts_today(), FB_DAILY_LIMIT)

                # Gate 4: 3-hour gap between FB posts
                else:
                    last_fb_time = get_last_fb_post_time()
                    fb_gap = (datetime.now(timezone.utc) - last_fb_time).total_seconds()
                    if fb_gap < FB_GAP_SECONDS:
                        remaining = (FB_GAP_SECONDS - fb_gap) / 60
                        logger.info("📘 [FB] ⏳ %.0f mins until next FB post.", remaining)
                    else:
                        fb_today = get_fb_posts_today()
                        fb_article = get_next_article_for_fb()
                        if fb_article:
                            # PRE-MARK to prevent duplicate posting on retry/crash
                            mark_as_shared_fb(fb_article['slug'])
                            payload = _build_article_payload(fb_article)
                            logger.info("📘 [FB] Posting (%d/%d today): %s", fb_today + 1, FB_DAILY_LIMIT, fb_article['title'][:60])
                            if distributor.post_to_facebook(payload):
                                logger.info("📘 [FB] ✅ Posted successfully.")
                                fb_backoff_hours = 0
                                fb_backoff_until = None
                                did_any_work = True
                            else:
                                logger.warning("📘 [FB] ⚠️ Post failed or skipped (article marked to prevent duplicate).")
                        else:
                            logger.info("📘 [FB] 📭 No unshared articles.")
            except Exception as fb_err:
                logger.error("📘 [FB] ❌ Error: %s", fb_err)
                fb_backoff_hours = min(max(fb_backoff_hours * 2, 4), FB_BACKOFF_MAX_HOURS)
                fb_backoff_until = datetime.now(timezone.utc) + timedelta(hours=fb_backoff_hours)
                logger.warning("📘 [FB] Backoff engaged: %dh (until %s).", fb_backoff_hours, fb_backoff_until.strftime('%H:%M UTC'))

            # ═══════════════════════════════════════════════════════
            # Sleep until next heartbeat
            # ═══════════════════════════════════════════════════════
            if not did_any_work:
                logger.info("😴 No posts made this cycle. Sleeping 10 mins.")
                time.sleep(600)
            else:
                logger.info("✅ Cycle complete. Sleeping 10 mins.")
                time.sleep(600)

        except Exception as e:
            logger.error("⚠️ Scheduler Critical Error: %s", e)
            time.sleep(600)

if __name__ == "__main__":
    main_loop()
