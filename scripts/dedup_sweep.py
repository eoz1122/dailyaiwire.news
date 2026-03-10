#!/usr/bin/env python3
"""
Phase 2: Smart Deduplication — Historical Sweep Script

One-time scan of all indexed articles in Qdrant to find semantic duplicates.
Results are saved to a `duplicate_clusters` table in SQLite for admin review.

MUST RUN ON VPS (72.62.95.46) where Qdrant + bge-large model are loaded.

Usage:
    python scripts/dedup_sweep.py                          # Full scan, writes to DB
    python scripts/dedup_sweep.py --dry-run                # Preview only
    python scripts/dedup_sweep.py --threshold 0.90         # Custom threshold
    python scripts/dedup_sweep.py --dry-run --threshold 0.85
"""

import sys
import os
import json
import sqlite3
import argparse
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "news.db")


def ensure_table(conn):
    """Create the duplicate_clusters table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS duplicate_clusters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keeper_id INTEGER NOT NULL,
            keeper_title TEXT,
            articles_json TEXT NOT NULL,
            max_score REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            resolved_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def run_sweep(threshold: float = 0.88, dry_run: bool = False):
    """Execute the historical dedup sweep."""
    print("=" * 60)
    print(f"🧹 Phase 2: Smart Deduplication Sweep")
    print(f"   Threshold: {threshold}")
    print(f"   Mode: {'DRY RUN (preview only)' if dry_run else 'LIVE (writing to DB)'}")
    print(f"   Time: {datetime.utcnow().isoformat()}Z")
    print("=" * 60)

    # Import from parent project
    from embedding_service import find_all_duplicates, get_collection_stats

    # Show current corpus stats
    stats = get_collection_stats()
    print(f"\n📦 Corpus: {stats['total_vectors']} vectors in '{stats['collection']}'")
    print(f"   Model: {stats['model']} ({stats['embedding_dim']}d)\n")

    # Run the scan
    clusters = find_all_duplicates(threshold=threshold)

    if not clusters:
        print("\n✅ No duplicates found! Corpus is clean.")
        return

    # Print summary
    total_dupes = sum(len(c['articles']) - 1 for c in clusters)
    print(f"\n{'=' * 60}")
    print(f"📊 SWEEP RESULTS")
    print(f"   Clusters:     {len(clusters)}")
    print(f"   Total dupes:  {total_dupes} articles to review")
    print(f"   Top score:    {clusters[0]['max_score']}")
    print(f"{'=' * 60}\n")

    # Show top 10 clusters
    print("🔝 Top Duplicate Clusters:\n")
    for i, cluster in enumerate(clusters[:10]):
        print(f"  Cluster {i+1} (score: {cluster['max_score']}):")
        print(f"    Keep → [{cluster['keeper_id']}] {cluster['keeper_title']}")
        for art in cluster['articles']:
            if art['id'] == cluster['keeper_id']:
                continue
            print(f"    Dupe → [{art['id']}] {art['title']} (sim: {art['score']})")
        print()

    if len(clusters) > 10:
        print(f"  ... and {len(clusters) - 10} more clusters.\n")

    if dry_run:
        print("🏁 DRY RUN complete. No changes written to database.")
        return

    # Write to database
    print("💾 Writing clusters to database...")
    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)

    # Clear previous pending results (re-scan replaces old data)
    conn.execute("DELETE FROM duplicate_clusters WHERE status = 'pending'")

    for cluster in clusters:
        conn.execute(
            "INSERT INTO duplicate_clusters (keeper_id, keeper_title, articles_json, max_score) VALUES (?, ?, ?, ?)",
            (
                cluster['keeper_id'],
                cluster['keeper_title'],
                json.dumps(cluster['articles']),
                cluster['max_score']
            )
        )

    conn.commit()
    conn.close()

    print(f"✅ {len(clusters)} clusters saved to `duplicate_clusters` table.")
    print(f"   Review at: https://dailyaiwire.news/admin/duplicates")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DailyAIWire Smart Deduplication Sweep")
    parser.add_argument("--threshold", type=float, default=0.88,
                        help="Cosine similarity threshold (default: 0.88)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview results without writing to database")
    args = parser.parse_args()

    run_sweep(threshold=args.threshold, dry_run=args.dry_run)
