#!/usr/bin/env python3
"""
Seed Ad-Reference Vectors — DailyAIWire.news

Populates the Qdrant `ad_reference_vectors` collection with promotional
content patterns. Safe to re-run (uses upsert).

Usage:
    python scripts/seed_ad_vectors.py
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from embedding_service import seed_ad_references, get_collection_stats


def main():
    print("=" * 60)
    print("  DailyAIWire — Ad-Reference Vector Seeder")
    print("=" * 60)

    count = seed_ad_references()
    stats = get_collection_stats()

    print()
    print(f"✅ Done. Ad-reference collection now has {stats['ad_reference_vectors']} vectors.")
    print(f"📦 Editorial corpus has {stats['total_vectors']} vectors.")
    print(f"🧠 Model: {stats['model']}")


if __name__ == "__main__":
    main()
