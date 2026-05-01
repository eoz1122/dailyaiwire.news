#!/usr/bin/env python3
"""
Move text-heavy social cards out of the onsite article image field.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import db


FALLBACKS = {
    "LLMs": ["/static/fallbacks/llms_0.jpg", "/static/fallbacks/llms_1.jpg", "/static/fallbacks/llms_2.jpg"],
    "Robotics": ["/static/fallbacks/robotics_0.jpg", "/static/fallbacks/robotics_1.jpg", "/static/fallbacks/robotics_2.jpg"],
    "Business": ["/static/fallbacks/business_0.jpg", "/static/fallbacks/business_1.jpg", "/static/fallbacks/business_2.jpg"],
    "Tools": ["/static/fallbacks/tools_0.jpg", "/static/fallbacks/tools_1.jpg", "/static/fallbacks/tools_2.jpg"],
    "Policy": ["/static/fallbacks/policy_0.jpg"],
    "Science": ["/static/fallbacks/science_0.jpg", "/static/fallbacks/science_1.jpg", "/static/fallbacks/science_2.jpg"],
    "Security": ["/static/fallbacks/security_0.jpg", "/static/fallbacks/security_1.jpg", "/static/fallbacks/security_2.jpg"],
    "Society": ["/static/fallbacks/society_0.jpg", "/static/fallbacks/society_1.jpg", "/static/fallbacks/society_2.jpg"],
    "Ethics": ["/static/fallbacks/ethics_0.jpg", "/static/fallbacks/ethics_1.jpg", "/static/fallbacks/ethics_2.jpg"],
    "AI Agents": ["/static/fallbacks/agents_0.jpg", "/static/fallbacks/agents_1.jpg", "/static/fallbacks/agents_2.jpg"],
}


def ensure_social_image_column(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(articles)").fetchall()}
    if "social_image" not in columns:
        conn.execute("ALTER TABLE articles ADD COLUMN social_image TEXT")


def deterministic_fallback(slug: str, category: str | None) -> str:
    images = FALLBACKS.get(category or "", FALLBACKS["Tools"])
    digest = hashlib.sha256((slug or "").encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(images)
    return images[index]


def backfill_social_images(db_path: str = db.DB_PATH) -> int:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    changed = 0
    try:
        ensure_social_image_column(conn)
        rows = conn.execute(
            """
            SELECT id, slug, image, social_image, category
            FROM articles
            WHERE image LIKE '/static/img/social/%'
            """
        ).fetchall()

        for row in rows:
            social_image = row["social_image"] or row["image"]
            display_image = deterministic_fallback(row["slug"], row["category"])
            conn.execute(
                """
                UPDATE articles
                SET image = ?, social_image = ?
                WHERE id = ?
                """,
                (display_image, social_image, row["id"]),
            )
            changed += 1

        conn.commit()
    finally:
        conn.close()

    return changed


def main() -> int:
    changed = backfill_social_images()
    print(f"Backfilled {changed} article image rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
