"""Selection and audit helpers for browser-based DailyAIWire X posting."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS x_browser_post_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL,
            article_slug TEXT NOT NULL,
            category TEXT,
            status TEXT NOT NULL CHECK(status IN ('POSTED', 'FAILED')),
            x_status_url TEXT,
            failure_reason TEXT,
            attempted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            posted_at TEXT,
            FOREIGN KEY(article_id) REFERENCES articles(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_x_browser_post_audit_attempted_at
        ON x_browser_post_audit(attempted_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_x_browser_post_audit_status_category
        ON x_browser_post_audit(status, category, attempted_at)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_x_browser_post_audit_status_url
        ON x_browser_post_audit(x_status_url)
        WHERE x_status_url IS NOT NULL
        """
    )


def _as_dict(row: sqlite3.Row | tuple[Any, ...], columns: list[str]) -> dict[str, Any]:
    if isinstance(row, sqlite3.Row):
        return dict(row)
    return dict(zip(columns, row))


def select_next_candidate(
    conn: sqlite3.Connection,
    *,
    now: datetime | None = None,
    lookback_hours: int = 48,
    recent_category_count: int = 2,
    failed_retry_cooldown_hours: int = 24,
) -> dict[str, Any] | None:
    """Return the highest-ranked eligible article while avoiding recent categories."""
    ensure_schema(conn)
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=lookback_hours)
    failed_retry_cutoff = now - timedelta(hours=failed_retry_cooldown_hours)

    recent_rows = conn.execute(
        """
        SELECT category
        FROM x_browser_post_audit
        WHERE status = 'POSTED' AND category IS NOT NULL AND category != ''
        ORDER BY COALESCE(posted_at, attempted_at) DESC, id DESC
        LIMIT ?
        """,
        (recent_category_count,),
    ).fetchall()
    recent_categories = {
        row["category"] if isinstance(row, sqlite3.Row) else row[0]
        for row in recent_rows
    }

    rows = conn.execute(
        """
        SELECT
            id, slug, title, category, why_it_matters,
            importance_score, published_at
        FROM articles
        WHERE is_published = 1
          AND COALESCE(shared_on_x, 0) = 0
          AND datetime(published_at) >= datetime(?)
          AND datetime(published_at) <= datetime(?)
          AND NOT EXISTS (
              SELECT 1
              FROM x_browser_post_audit AS audit
              WHERE audit.article_id = articles.id
                AND audit.status = 'FAILED'
                AND datetime(audit.attempted_at) >= datetime(?)
          )
        ORDER BY COALESCE(importance_score, 0) DESC, datetime(published_at) DESC, id DESC
        """,
        (cutoff.isoformat(), now.isoformat(), failed_retry_cutoff.isoformat()),
    ).fetchall()
    if not rows:
        return None

    columns = [
        "id",
        "slug",
        "title",
        "category",
        "why_it_matters",
        "importance_score",
        "published_at",
    ]
    candidates = [_as_dict(row, columns) for row in rows]
    for candidate in candidates:
        if not candidate.get("category") or candidate["category"] not in recent_categories:
            return candidate
    return candidates[0]


def mark_posted(
    conn: sqlite3.Connection,
    *,
    article_id: int,
    x_status_url: str,
    posted_at: datetime | None = None,
) -> None:
    """Atomically mark an article shared and record its confirmed X status URL."""
    if not x_status_url.startswith("https://x.com/"):
        raise ValueError("A confirmed x.com status URL is required")

    ensure_schema(conn)
    posted_at = posted_at or datetime.now(timezone.utc)
    timestamp = posted_at.isoformat()
    try:
        conn.execute("BEGIN IMMEDIATE")
        article = conn.execute(
            "SELECT slug, category, COALESCE(shared_on_x, 0) AS shared_on_x FROM articles WHERE id = ?",
            (article_id,),
        ).fetchone()
        if article is None:
            raise ValueError(f"Article {article_id} does not exist")

        article_data = _as_dict(article, ["slug", "category", "shared_on_x"])
        if article_data["shared_on_x"]:
            raise ValueError(f"Article {article_id} is already marked as shared on X")

        conn.execute(
            """
            INSERT INTO x_browser_post_audit (
                article_id, article_slug, category, status,
                x_status_url, attempted_at, posted_at
            ) VALUES (?, ?, ?, 'POSTED', ?, ?, ?)
            """,
            (
                article_id,
                article_data["slug"],
                article_data["category"],
                x_status_url,
                timestamp,
                timestamp,
            ),
        )
        conn.execute(
            "UPDATE articles SET shared_on_x = 1, shared_at = ? WHERE id = ?",
            (timestamp, article_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def mark_failed(
    conn: sqlite3.Connection,
    *,
    article_id: int,
    reason: str,
    attempted_at: datetime | None = None,
) -> None:
    """Record a browser posting failure without changing article share state."""
    ensure_schema(conn)
    attempted_at = attempted_at or datetime.now(timezone.utc)
    article = conn.execute(
        "SELECT slug, category FROM articles WHERE id = ?",
        (article_id,),
    ).fetchone()
    if article is None:
        raise ValueError(f"Article {article_id} does not exist")

    article_data = _as_dict(article, ["slug", "category"])
    conn.execute(
        """
        INSERT INTO x_browser_post_audit (
            article_id, article_slug, category, status,
            failure_reason, attempted_at
        ) VALUES (?, ?, ?, 'FAILED', ?, ?)
        """,
        (
            article_id,
            article_data["slug"],
            article_data["category"],
            reason[:500],
            attempted_at.isoformat(),
        ),
    )
    conn.commit()
