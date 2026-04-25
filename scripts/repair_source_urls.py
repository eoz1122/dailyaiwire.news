#!/usr/bin/env python3
"""
One-off utility to repair known broken source feed URLs in the local DB.
Safe to run multiple times (idempotent).
"""
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db import DB_PATH


REPAIRS = {
    ("Cambridge University AI", "https://www.cam.ac.uk/topics/artificial-intelligence/feed"):
        "https://www.cam.ac.uk/taxonomy/term/51032/feed",
    ("DeepMind", "https://deepmind.com/blog/feed/basic/"):
        "https://deepmind.google/blog/rss.xml",
    ("Meta AI (FAIR)", "https://ai.meta.com/blog/rss.xml"):
        "https://research.facebook.com/feed/",
    ("Microsoft Research", "https://www.microsoft.com/en-us/research/feed/"):
        "https://azure.microsoft.com/en-us/blog/feed/",
}


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    updated = 0

    for (name, old_url), new_url in REPAIRS.items():
        cur.execute(
            "UPDATE sources SET url = ? WHERE name = ? AND url = ?",
            (new_url, name, old_url),
        )
        updated += cur.rowcount or 0

    conn.commit()
    conn.close()
    print(f"Repaired source URLs: {updated}")


if __name__ == "__main__":
    main()
