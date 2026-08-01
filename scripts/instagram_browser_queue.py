#!/usr/bin/env python3
"""CLI boundary for browser-based DailyAIWire Instagram posting."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from db import DB_PATH
from services.instagram_browser_queue import ensure_schema, mark_failed, mark_posted, prepare_candidate


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manage browser-based DailyAIWire Instagram posting."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    next_parser = commands.add_parser("next", help="Return the next eligible article as JSON.")
    next_parser.add_argument("--lookback-hours", type=int, default=48)
    next_parser.add_argument(
        "--max-source-age-hours",
        type=int,
        default=int(os.getenv("INSTAGRAM_BROWSER_MAX_SOURCE_AGE_HOURS", "72")),
    )

    posted_parser = commands.add_parser("posted", help="Record a confirmed Instagram post.")
    posted_parser.add_argument("--article-id", required=True, type=int)
    posted_parser.add_argument("--post-url", required=True)

    failed_parser = commands.add_parser("failed", help="Record a failed browser post.")
    failed_parser.add_argument("--article-id", required=True, type=int)
    failed_parser.add_argument("--reason", required=True)

    args = parser.parse_args()
    conn = _connection()
    try:
        if args.command == "next":
            candidate = prepare_candidate(
                conn,
                lookback_hours=args.lookback_hours,
                max_source_age_hours=args.max_source_age_hours,
            )
            print(json.dumps(candidate, ensure_ascii=True))
        elif args.command == "posted":
            mark_posted(
                conn,
                article_id=args.article_id,
                instagram_post_url=args.post_url,
            )
            print(json.dumps({"status": "POSTED", "article_id": args.article_id}))
        else:
            mark_failed(conn, article_id=args.article_id, reason=args.reason)
            print(json.dumps({"status": "FAILED", "article_id": args.article_id}))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

