"""Persistent, demand-led article promotion for Google recovery mode."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from db import get_db_connection
from services.indexability import score_article


PROMOTION_FRESHNESS_DAYS = 30


def ensure_google_index_promotions_table(conn: Optional[sqlite3.Connection] = None) -> None:
    owns_connection = conn is None
    if conn is None:
        conn = get_db_connection()

    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS google_index_promotions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL UNIQUE,
                promoted_on TEXT NOT NULL UNIQUE,
                verified_views_at_promotion INTEGER NOT NULL DEFAULT 0,
                raw_views_at_promotion INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (article_id) REFERENCES articles(id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_google_index_promotions_promoted_on
            ON google_index_promotions(promoted_on)
            """
        )
        if owns_connection:
            conn.commit()
    finally:
        if owns_connection:
            conn.close()


def _promotion_for_day(conn: sqlite3.Connection, target_day: date):
    return conn.execute(
        """
        SELECT p.*, a.slug, a.title
        FROM google_index_promotions p
        JOIN articles a ON a.id = p.article_id
        WHERE p.promoted_on = ?
        LIMIT 1
        """,
        (target_day.isoformat(),),
    ).fetchone()


def promote_next_article(
    *,
    target_day: Optional[date] = None,
    as_of: Optional[datetime] = None,
    conn: Optional[sqlite3.Connection] = None,
):
    """Promote at most one strong article after a 24-hour observation window."""
    as_of = as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    else:
        as_of = as_of.astimezone(timezone.utc)
    target_day = target_day or as_of.date()
    published_before = (as_of - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    recent_cutoff = (as_of - timedelta(days=PROMOTION_FRESHNESS_DAYS)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    owns_connection = conn is None
    if conn is None:
        conn = get_db_connection()
    conn.row_factory = sqlite3.Row

    try:
        ensure_google_index_promotions_table(conn)
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")

        existing = _promotion_for_day(conn, target_day)
        if existing:
            conn.commit()
            return dict(existing)

        candidates = conn.execute(
            """
            SELECT a.id, a.slug, a.title, a.image, a.social_image, a.category,
                   a.gist, a.why_it_matters, a.bull_case, a.bear_case,
                   a.key_details, a.deep_analysis, a.source, a.source_url,
                   a.published_at, a.importance_score, a.compass_score,
                   COALESCE(a.verified_views, 0) AS verified_views,
                   COALESCE(a.views, 0) AS views
            FROM articles a
            LEFT JOIN google_index_promotions p ON p.article_id = a.id
            WHERE a.is_published = 1
              AND a.published_at IS NOT NULL
              AND datetime(replace(a.published_at, 'T', ' ')) <= datetime(?)
              AND p.article_id IS NULL
            ORDER BY CASE
                         WHEN datetime(replace(a.published_at, 'T', ' ')) >= datetime(?)
                         THEN 0 ELSE 1
                     END,
                     COALESCE(a.verified_views, 0) DESC,
                     COALESCE(a.views, 0) DESC,
                     (a.importance_score * COALESCE(a.compass_score, 0.7)) DESC,
                     a.published_at DESC,
                     a.id DESC
            """,
            (published_before, recent_cutoff),
        ).fetchall()

        selected = next(
            (candidate for candidate in candidates if score_article(dict(candidate)).sitemap_eligible),
            None,
        )
        if selected is None:
            conn.commit()
            return None

        conn.execute(
            """
            INSERT OR IGNORE INTO google_index_promotions (
                article_id, promoted_on, verified_views_at_promotion,
                raw_views_at_promotion
            ) VALUES (?, ?, ?, ?)
            """,
            (
                selected["id"],
                target_day.isoformat(),
                selected["verified_views"],
                selected["views"],
            ),
        )
        promoted = _promotion_for_day(conn, target_day)
        conn.commit()
        return dict(promoted) if promoted else None
    except Exception:
        conn.rollback()
        raise
    finally:
        if owns_connection:
            conn.close()


def is_article_promoted(article_id: int, conn: Optional[sqlite3.Connection] = None) -> bool:
    owns_connection = conn is None
    if conn is None:
        conn = get_db_connection()

    try:
        try:
            row = conn.execute(
                "SELECT 1 FROM google_index_promotions WHERE article_id = ? LIMIT 1",
                (article_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc).lower():
                raise
            ensure_google_index_promotions_table(conn)
            conn.commit()
            row = conn.execute(
                "SELECT 1 FROM google_index_promotions WHERE article_id = ? LIMIT 1",
                (article_id,),
            ).fetchone()
        return row is not None
    finally:
        if owns_connection:
            conn.close()


def fetch_promoted_articles(
    conn: Optional[sqlite3.Connection] = None,
    *,
    limit: Optional[int] = None,
):
    owns_connection = conn is None
    if conn is None:
        conn = get_db_connection()
    conn.row_factory = sqlite3.Row

    try:
        query = """
        SELECT a.*, p.promoted_on
        FROM google_index_promotions p
        JOIN articles a ON a.id = p.article_id
        WHERE a.is_published = 1
        ORDER BY p.promoted_on DESC, p.id DESC
        """
        params: tuple[Any, ...] = ()
        if limit is not None:
            query += " LIMIT ?"
            params = (max(0, int(limit)),)
        try:
            return conn.execute(query, params).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc).lower():
                raise
            ensure_google_index_promotions_table(conn)
            conn.commit()
            return conn.execute(query, params).fetchall()
    finally:
        if owns_connection:
            conn.close()
