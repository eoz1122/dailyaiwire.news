"""Permanent redirects for safely consolidating duplicate articles."""

from __future__ import annotations

import sqlite3
from typing import Optional

from db import get_db_connection


def ensure_article_redirects_table(
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    owns_connection = conn is None
    if conn is None:
        conn = get_db_connection()

    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS article_redirects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_slug TEXT NOT NULL UNIQUE,
                target_article_id INTEGER NOT NULL,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (target_article_id) REFERENCES articles(id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_article_redirects_target
            ON article_redirects(target_article_id)
            """
        )
        if owns_connection:
            conn.commit()
    finally:
        if owns_connection:
            conn.close()


def find_article_redirect(conn: sqlite3.Connection, source_slug: str):
    return conn.execute(
        """
        SELECT r.source_slug, a.id AS target_article_id, a.slug AS target_slug
        FROM article_redirects r
        JOIN articles a ON a.id = r.target_article_id
        WHERE r.source_slug = ?
          AND a.is_published = 1
        LIMIT 1
        """,
        (source_slug,),
    ).fetchone()


def consolidate_article_duplicate(
    *,
    duplicate_article_id: int,
    canonical_article_id: int,
    reason: str,
    conn: Optional[sqlite3.Connection] = None,
) -> dict:
    """Unpublish a duplicate and preserve its URL with a permanent redirect."""
    if duplicate_article_id == canonical_article_id:
        raise ValueError("Duplicate and canonical article IDs must differ")

    owns_connection = conn is None
    if conn is None:
        conn = get_db_connection()

    try:
        ensure_article_redirects_table(conn)
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")

        duplicate = conn.execute(
            "SELECT id, slug, is_published FROM articles WHERE id = ?",
            (duplicate_article_id,),
        ).fetchone()
        canonical = conn.execute(
            "SELECT id, slug, is_published FROM articles WHERE id = ?",
            (canonical_article_id,),
        ).fetchone()

        if duplicate is None:
            raise ValueError("Duplicate article does not exist")
        if canonical is None:
            raise ValueError("Canonical article does not exist")

        duplicate_slug = duplicate[1]
        canonical_slug = canonical[1]
        if not duplicate_slug or not canonical_slug:
            raise ValueError("Both articles must have slugs")
        if duplicate_slug == canonical_slug:
            raise ValueError("Duplicate and canonical slugs must differ")
        if int(canonical[2] or 0) != 1:
            raise ValueError("Canonical article must be published")

        conn.execute(
            """
            INSERT INTO article_redirects (source_slug, target_article_id, reason)
            VALUES (?, ?, ?)
            ON CONFLICT(source_slug) DO UPDATE SET
                target_article_id = excluded.target_article_id,
                reason = excluded.reason
            """,
            (duplicate_slug, canonical_article_id, (reason or "").strip()),
        )
        conn.execute(
            "UPDATE articles SET is_published = 0 WHERE id = ?",
            (duplicate_article_id,),
        )

        table_names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        if "carousel_slots" in table_names:
            conn.execute(
                "DELETE FROM carousel_slots WHERE article_id = ?",
                (duplicate_article_id,),
            )
        if "duplicate_review_queue" in table_names:
            conn.execute(
                """
                UPDATE duplicate_review_queue
                SET status = 'CONSOLIDATED',
                    reviewed_at = CURRENT_TIMESTAMP
                WHERE status = 'PENDING_REVIEW'
                  AND (
                      (keep_article_id = ? AND duplicate_article_id = ?)
                      OR
                      (keep_article_id = ? AND duplicate_article_id = ?)
                  )
                """,
                (
                    canonical_article_id,
                    duplicate_article_id,
                    duplicate_article_id,
                    canonical_article_id,
                ),
            )

        conn.commit()
        return {
            "source_slug": duplicate_slug,
            "target_slug": canonical_slug,
            "duplicate_article_id": duplicate_article_id,
            "canonical_article_id": canonical_article_id,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        if owns_connection:
            conn.close()
