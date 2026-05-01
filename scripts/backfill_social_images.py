#!/usr/bin/env python3
"""
Move text-heavy social cards out of the onsite article image field.
"""
from __future__ import annotations

import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import db
from services.image_fallbacks import deterministic_fallback, needs_fallback_repair


def ensure_social_image_column(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(articles)").fetchall()}
    if "social_image" not in columns:
        conn.execute("ALTER TABLE articles ADD COLUMN social_image TEXT")


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
               OR image LIKE '/static/fallbacks/%'
            """
        ).fetchall()

        for row in rows:
            image = row["image"] or ""
            is_social_card = image.startswith("/static/img/social/")
            if not is_social_card and not needs_fallback_repair(image):
                continue

            social_image = row["social_image"]
            if is_social_card:
                social_image = social_image or image

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
