"""
Batch Google Indexing API — Re-index top articles.

Sends URL_UPDATED notifications for published articles, prioritized by
importance_score DESC. Respects the 200/day API quota.

Usage (on VPS):
    python scripts/batch_reindex.py              # First 200 articles
    python scripts/batch_reindex.py --offset 200  # Next 200
    python scripts/batch_reindex.py --all         # All (spread across quota)
"""
import os
import sys
import time
import sqlite3
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google_indexer import notify_google_index

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'news.db')
BASE_URL = "https://dailyaiwire.news"
DAILY_QUOTA = 200


def get_article_urls(limit=200, offset=0):
    """Fetch published article URLs ordered by importance."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute('''
        SELECT slug FROM articles
        WHERE is_published = 1
        ORDER BY importance_score DESC, published_at DESC
        LIMIT ? OFFSET ?
    ''', (limit, offset)).fetchall()
    conn.close()
    return [f"{BASE_URL}/article/{r['slug']}" for r in rows]


def get_lab_urls():
    """Fetch lab post URLs."""
    urls = []
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute('SELECT slug FROM blog_posts').fetchall()
        conn.close()
        urls = [f"{BASE_URL}/lab/{r['slug']}" for r in rows]
    except Exception:
        pass
    return urls


def main():
    parser = argparse.ArgumentParser(description='Batch re-index via Google Indexing API')
    parser.add_argument('--limit', type=int, default=DAILY_QUOTA,
                        help=f'Max URLs to notify (default: {DAILY_QUOTA})')
    parser.add_argument('--offset', type=int, default=0,
                        help='Offset for pagination (default: 0)')
    parser.add_argument('--include-lab', action='store_true',
                        help='Include lab/blog posts')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print URLs without sending notifications')
    args = parser.parse_args()

    # Gather URLs
    urls = get_article_urls(limit=args.limit, offset=args.offset)
    if args.include_lab:
        urls.extend(get_lab_urls())

    # Respect quota
    urls = urls[:DAILY_QUOTA]

    print(f"📡 Batch Re-Index: {len(urls)} URLs (offset={args.offset})")
    print(f"{'🔍 DRY RUN — no API calls' if args.dry_run else '🚀 LIVE — sending notifications'}")
    print("=" * 60)

    success = 0
    failed = 0
    for i, url in enumerate(urls, 1):
        if args.dry_run:
            print(f"  [{i}/{len(urls)}] {url}")
        else:
            try:
                notify_google_index(url, action="URL_UPDATED")
                success += 1
                # Small delay to avoid rate limits
                if i % 10 == 0:
                    time.sleep(1)
            except Exception as e:
                print(f"  ❌ Failed: {url} — {e}")
                failed += 1
                if "429" in str(e) or "quota" in str(e).lower():
                    print("  ⚠️ Quota exceeded. Stopping.")
                    break

    print("=" * 60)
    if args.dry_run:
        print(f"✅ Would notify {len(urls)} URLs")
    else:
        print(f"✅ Success: {success} | ❌ Failed: {failed}")


if __name__ == "__main__":
    main()
