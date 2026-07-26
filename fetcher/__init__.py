"""
Fetcher Package — DailyAIWire.news Intelligence Service
Orchestration module: main() and main_loop() entry points.

Decomposed from the original 1,341-line fetcher.py monolith into
focused sub-modules (2026-03-10, Phase 5 R3).

Sub-modules:
  - db_init.py      — Schema creation, migrations, metadata helpers
  - sources.py      — RSS fetching, AI headline filtering, fuzzy dedup
  - content.py      — URL content extraction + SSRF protection
  - spam.py         — Keyword/heuristic/blocklist spam defense
  - ai_processor.py — Gemini batch processing + prompt template
  - persistence.py  — save_to_db, social queue, Google/Qdrant indexing
"""
import os
import sys
import time
import logging
from datetime import datetime, date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from logging_config import setup_logging
setup_logging()

logger = logging.getLogger('fetcher')

# Force unbuffered output for supervisor logs
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

from fetcher.db_init import init_db, update_last_scan_timestamp
from fetcher.sources import fetch_all_sources
from fetcher.ai_processor import process_batch
from fetcher.persistence import save_to_db, process_social_queue
from remove_duplicates import remove_duplicates
from social_distributor import SocialDistributor
from db import get_db_connection
from services.indexing_promotions import promote_next_article


def _count_analyzed_articles_for_day(target_day: date) -> int:
    """Count article-analysis inputs already attempted for a UTC day."""
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT prompt_text
            FROM ai_logs
            WHERE prompt_type = 'article_analysis'
              AND date(timestamp) = ?
            """,
            (target_day.isoformat(),),
        ).fetchall()
    finally:
        conn.close()

    total = 0
    for row in rows:
        prompt_text = row["prompt_text"] or ""
        total += prompt_text.count("ARTICLE ID:")
    return total


def _limit_articles_for_cycle(new_articles, *, per_cycle_cap: int, daily_cap: int, analyzed_today: int):
    """Apply per-cycle and optional daily caps to expensive analysis volume."""
    capped = list(new_articles[:per_cycle_cap])
    if daily_cap <= 0:
        return capped

    remaining_today = max(daily_cap - analyzed_today, 0)
    return capped[:remaining_today]


def main():
    """Single fetch cycle: aggregate → filter → process → save."""
    logger.info("Initializing Database...")
    init_db()

    try:
        promoted = promote_next_article()
        if promoted:
            logger.info(
                "Google recovery promotion for %s: %s (%d verified views)",
                promoted["promoted_on"],
                promoted["slug"],
                promoted["verified_views_at_promotion"],
            )
        else:
            logger.warning("No quality-eligible article is available for Google recovery promotion.")
    except Exception as exc:
        logger.error("Google recovery promotion failed without blocking fetch: %s", exc)

    # Record scan start time
    scan_start_time = datetime.utcnow()

    logger.info("Aggregating Intelligence from Multiple Sources...")
    new_articles = fetch_all_sources()

    if not new_articles:
        logger.info("Everything up to date. No new intelligence to process.")
        # Advance frontier even if no articles passed the high-signal filter
        update_last_scan_timestamp(scan_start_time)
        return

    logger.info("New High-Signal Articles to Process: %d", len(new_articles))

    # Process in batches for efficiency
    # HARD LIMIT: Never process more than 16 articles per cycle to prevent token spikes
    MAX_ARTICLES_PER_CYCLE = int(os.getenv('FETCHER_MAX_ARTICLES', '16'))
    DAILY_ANALYSIS_CAP = int(os.getenv('FETCHER_MAX_ANALYZED_ARTICLES_PER_DAY', '0'))
    analyzed_today = _count_analyzed_articles_for_day(datetime.utcnow().date()) if DAILY_ANALYSIS_CAP > 0 else 0

    limited_articles = _limit_articles_for_cycle(
        new_articles,
        per_cycle_cap=MAX_ARTICLES_PER_CYCLE,
        daily_cap=DAILY_ANALYSIS_CAP,
        analyzed_today=analyzed_today,
    )

    if DAILY_ANALYSIS_CAP > 0:
        remaining_today = max(DAILY_ANALYSIS_CAP - analyzed_today, 0)
        logger.info(
            "Daily analysis budget: %d/%d used, %d remaining.",
            analyzed_today,
            DAILY_ANALYSIS_CAP,
            remaining_today,
        )

    if not limited_articles:
        if DAILY_ANALYSIS_CAP > 0 and analyzed_today >= DAILY_ANALYSIS_CAP:
            logger.warning(
                "⚠️ Daily article-analysis cap reached (%d). Skipping expensive processing until tomorrow.",
                DAILY_ANALYSIS_CAP,
            )
        else:
            logger.warning("⚠️ No articles left after analysis caps. Skipping expensive processing.")
        update_last_scan_timestamp(scan_start_time)
        return

    if len(new_articles) > len(limited_articles):
        logger.warning(
            "⚠️ Analysis cap reached! Truncating %d candidate articles to %d",
            len(new_articles),
            len(limited_articles),
        )
        new_articles = limited_articles

    batch_size = int(os.getenv('FETCHER_BATCH_SIZE', '3'))
    distributor = SocialDistributor()
    total_posts_sent = 0
    articles_saved = 0

    for i in range(0, len(new_articles), batch_size):
        batch = new_articles[i:i + batch_size]
        logger.info("Processing batch %d (%d articles)...", i//batch_size + 1, len(batch))
        processed = process_batch(batch)
        if processed:
            # Save WITHOUT audio generation (pass None for audio_gen)
            save_result = save_to_db(
                processed,
                batch,
                distributor,
                social_limit=5,
                posts_count=total_posts_sent,
                audio_gen=None,
            )
            total_posts_sent = save_result.posts_count
            articles_saved += save_result.articles_saved
            logger.info(
                "Saved %d articles from batch. Social posts sent so far: %d",
                save_result.articles_saved,
                total_posts_sent,
            )

        # Sleep 15s between batches to avoid rate limits
        time.sleep(15)

    # Save timestamp only after full processing attempt
    update_last_scan_timestamp(scan_start_time)

    # Run deduplication BEFORE generating expensive audio
    logger.info("Running deduplication before audio generation...")
    remove_duplicates(seq_threshold=0.8, word_threshold=0.6)

    # Now generate audio only for articles that survived deduplication
    if articles_saved > 0:
        logger.info("Generating audio for %d deduplicated articles...", articles_saved)
        from generate_missing_audio import generate_audio_for_recent_articles
        generate_audio_for_recent_articles(limit=articles_saved)


def main_loop():
    """Runs the main fetcher loop with queued social posting."""
    logger.info("Starting DailyAIWire Intelligence Service...")

    last_fetch_time = 0
    fetch_interval = 7200  # 2 hours

    while True:
        try:
            current_time = time.time()

            # Run Fetcher if interval passed
            if current_time - last_fetch_time > fetch_interval:
                logger.info("⏰ Starting scheduled fetch cycle at %s", time.strftime('%H:%M:%S'))
                main()
                last_fetch_time = time.time()

            # Social posting is now handled exclusively by tweet_scheduler.py
            # process_social_queue()

            # Sleep for 1 minute before next tick
            time.sleep(60)

        except KeyboardInterrupt:
            logger.info("Intelligence Service stopped by user.")
            break
        except Exception as e:
            logger.error("Error in main loop: %s", e)
            logger.info("Retrying in 1 minute...")
            time.sleep(60)
