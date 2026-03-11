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
from datetime import datetime

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
    print("Initializing Database...")
    init_db()

    # Record scan start time
    scan_start_time = datetime.utcnow()

    print("Aggregating Intelligence from Multiple Sources...")
    new_articles = fetch_all_sources()

    if not new_articles:
        print("Everything up to date. No new intelligence to process.")
        # Advance frontier even if no articles passed the high-signal filter
        update_last_scan_timestamp(scan_start_time)
        return

    print(f"New High-Signal Articles to Process: {len(new_articles)}")

    # Process in batches for efficiency
    # HARD LIMIT: Never process more than 16 articles per cycle to prevent token spikes
    MAX_ARTICLES_PER_CYCLE = 16
    if len(new_articles) > MAX_ARTICLES_PER_CYCLE:
        print(f"⚠️ Cap reached! Truncating {len(new_articles)} articles to {MAX_ARTICLES_PER_CYCLE}")
        new_articles = new_articles[:MAX_ARTICLES_PER_CYCLE]

    batch_size = 4
    distributor = SocialDistributor()
    total_posts_sent = 0
    articles_saved = 0

    for i in range(0, len(new_articles), batch_size):
        batch = new_articles[i:i + batch_size]
        print(f"Processing batch {i//batch_size + 1} ({len(batch)} articles)...")
        processed = process_batch(batch)
        if processed:
            # Save WITHOUT audio generation (pass None for audio_gen)
            total_posts_sent = save_to_db(processed, batch, distributor, social_limit=5, posts_count=total_posts_sent, audio_gen=None)
            articles_saved += len(processed)
            print(f"Saved {len(processed)} articles from batch. Social posts sent so far: {total_posts_sent}")

        # Sleep 15s between batches to avoid rate limits
        time.sleep(15)

    # Save timestamp only after full processing attempt
    update_last_scan_timestamp(scan_start_time)

    # Run deduplication BEFORE generating expensive audio
    print("Running deduplication before audio generation...")
    remove_duplicates(seq_threshold=0.8, word_threshold=0.6)

    # Now generate audio only for articles that survived deduplication
    if articles_saved > 0:
        print(f"Generating audio for {articles_saved} deduplicated articles...")
        from generate_missing_audio import generate_audio_for_recent_articles
        generate_audio_for_recent_articles(limit=articles_saved)


def main_loop():
    """Runs the main fetcher loop with queued social posting."""
    print("Starting DailyAIWire Intelligence Service...")

    last_fetch_time = 0
    fetch_interval = 7200  # 2 hours

    while True:
        try:
            current_time = time.time()

            # Run Fetcher if interval passed
            if current_time - last_fetch_time > fetch_interval:
                print(f"⏰ Starting scheduled fetch cycle at {time.strftime('%H:%M:%S')}")
                main()
                last_fetch_time = time.time()

            # Social posting is now handled exclusively by tweet_scheduler.py
            # process_social_queue()

            # Sleep for 1 minute before next tick
            time.sleep(60)

        except KeyboardInterrupt:
            print("\nIntelligence Service stopped by user.")
            break
        except Exception as e:
            print(f"Error in main loop: {e}")
            print("Retrying in 1 minute...")
            time.sleep(60)
