"""
Batch Embed — Index all existing articles into Qdrant.

Run once to bootstrap the Editorial Compass:
    python batch_embed.py

This reads all articles from news.db and embeds them
into the Qdrant vector collection.
"""

import sys
import os
import time
import sqlite3

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from embedding_service import index_batch, get_collection_stats, DB_PATH


def main():
    print("=" * 60)
    print("DailyAIWire — Batch Article Embedding")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Count total articles
    total = conn.execute("SELECT COUNT(*) FROM articles WHERE is_published = 1").fetchone()[0]
    print(f"\n📊 Total published articles: {total}")

    # Check current vector count
    try:
        stats = get_collection_stats()
        existing = stats["total_vectors"]
        print(f"📦 Already indexed: {existing} vectors")
    except Exception:
        existing = 0

    if existing >= total:
        print("✅ All articles already indexed. Nothing to do.")
        conn.close()
        return

    # Fetch articles not yet indexed (fetch all, Qdrant upsert handles dedup by ID)
    BATCH_SIZE = 64
    offset = 0
    total_indexed = 0

    print(f"\n🚀 Starting batch embedding (batch size: {BATCH_SIZE})...\n")
    start_time = time.time()

    while True:
        rows = conn.execute("""
            SELECT id, title, gist, why_it_matters, category, source,
                   COALESCE(importance_score, 0) as importance_score
            FROM articles
            WHERE is_published = 1
            ORDER BY id ASC
            LIMIT ? OFFSET ?
        """, (BATCH_SIZE, offset)).fetchall()

        if not rows:
            break

        articles = [dict(r) for r in rows]
        count = index_batch(articles)
        total_indexed += count
        offset += BATCH_SIZE

        elapsed = time.time() - start_time
        rate = total_indexed / elapsed if elapsed > 0 else 0
        print(f"  ✅ Indexed {total_indexed}/{total} ({rate:.1f} articles/sec)")

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"🏁 Done! Indexed {total_indexed} articles in {elapsed:.1f}s")
    print(f"   Rate: {total_indexed / elapsed:.1f} articles/sec")

    # Final stats
    stats = get_collection_stats()
    print(f"\n📊 Collection stats:")
    print(f"   Vectors: {stats['total_vectors']}")
    print(f"   Model: {stats['model']}")
    print(f"   Dimensions: {stats['embedding_dim']}")

    conn.close()


if __name__ == "__main__":
    main()
