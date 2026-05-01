#!/usr/bin/env python3
"""
Retry the latest failed Google Indexing API notifications.
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from google_indexer import notify_google_index
from services.indexing_audit import fetch_retry_candidates


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Retry latest failed Google Indexing API notifications."
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--include-skipped",
        action="store_true",
        help="Also retry skipped rows, usually only useful after fixing credentials.",
    )
    args = parser.parse_args()

    statuses = ("failed", "quota_exceeded", "skipped") if args.include_skipped else (
        "failed",
        "quota_exceeded",
    )
    candidates = fetch_retry_candidates(limit=args.limit, retry_statuses=statuses)

    if not candidates:
        print("No indexing retry candidates found.")
        return 0

    for row in candidates:
        print(f"Retrying {row['action']} {row['url']} after {row['status']}")
        if not args.dry_run:
            notify_google_index(row["url"], action=row["action"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
