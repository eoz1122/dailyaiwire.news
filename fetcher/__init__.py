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
from datetime import datetime

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


def main():
    """Single fetch cycle: aggregate → filter → process → save."""
    logger.info("Initializing Database...")
    init_db()

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
    if len(new_articles) > MAX_ARTICLES_PER_CYCLE:
        logger.warning("⚠️ Cap reached! Truncating %d articles to %d", len(new_articles), MAX_ARTICLES_PER_CYCLE)
        new_articles = new_articles[:MAX_ARTICLES_PER_CYCLE]

    batch_size = int(os.getenv('FETCHER_BATCH_SIZE', '4'))
    distributor = SocialDistributor()
    total_posts_sent = 0
    articles_saved = 0

    for i in range(0, len(new_articles), batch_size):
        batch = new_articles[i:i + batch_size]
        logger.info("Processing batch %d (%d articles)...", i//batch_size + 1, len(batch))
        processed = process_batch(batch)
        if processed:
            # Save WITHOUT audio generation (pass None for audio_gen)
            total_posts_sent = save_to_db(processed, batch, distributor, social_limit=5, posts_count=total_posts_sent, audio_gen=None)
            articles_saved += len(processed)
            logger.info("Saved %d articles from batch. Social posts sent so far: %d", len(processed), total_posts_sent)

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
