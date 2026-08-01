"""Selection, caption, and audit helpers for browser-based Instagram posting."""
from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlparse


DEFAULT_BASE_URL = "https://dailyaiwire.news"
CAPTION_LIMIT = 2200


def ensure_schema(conn: sqlite3.Connection) -> None:
    article_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(articles)").fetchall()
    }
    if article_columns and "shared_on_ig" not in article_columns:
        conn.execute("ALTER TABLE articles ADD COLUMN shared_on_ig INTEGER DEFAULT 0")
    if article_columns and "shared_on_ig_at" not in article_columns:
        conn.execute("ALTER TABLE articles ADD COLUMN shared_on_ig_at TEXT")
    if article_columns and "source_published_at" not in article_columns:
        conn.execute("ALTER TABLE articles ADD COLUMN source_published_at TEXT")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS instagram_browser_post_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL,
            article_slug TEXT NOT NULL,
            category TEXT,
            status TEXT NOT NULL CHECK(status IN ('POSTED', 'FAILED')),
            instagram_post_url TEXT,
            failure_reason TEXT,
            attempted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            posted_at TEXT,
            FOREIGN KEY(article_id) REFERENCES articles(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_instagram_browser_audit_attempted
        ON instagram_browser_post_audit(attempted_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_instagram_browser_audit_category
        ON instagram_browser_post_audit(status, category, attempted_at)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_instagram_browser_audit_post_url
        ON instagram_browser_post_audit(instagram_post_url)
        WHERE instagram_post_url IS NOT NULL
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
    max_source_age_hours: int = 72,
) -> dict[str, Any] | None:
    """Select one fresh, important, unshared article with category diversity."""
    ensure_schema(conn)
    now = now or datetime.now(timezone.utc)
    publish_cutoff = now - timedelta(hours=lookback_hours)
    source_cutoff = now - timedelta(hours=max_source_age_hours)
    retry_cutoff = now - timedelta(hours=failed_retry_cooldown_hours)

    recent_rows = conn.execute(
        """
        SELECT category
        FROM instagram_browser_post_audit
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
            id, slug, title, category, why_it_matters, hashtags,
            importance_score, published_at, source_published_at
        FROM articles
        WHERE is_published = 1
          AND COALESCE(shared_on_ig, 0) = 0
          AND datetime(published_at) >= datetime(?)
          AND datetime(published_at) <= datetime(?)
          AND source_published_at IS NOT NULL
          AND source_published_at != ''
          AND datetime(source_published_at) >= datetime(?)
          AND datetime(source_published_at) <= datetime(?)
          AND NOT EXISTS (
              SELECT 1
              FROM instagram_browser_post_audit AS audit
              WHERE audit.article_id = articles.id
                AND audit.status = 'FAILED'
                AND datetime(audit.attempted_at) >= datetime(?)
          )
        ORDER BY COALESCE(importance_score, 0) DESC, datetime(published_at) DESC, id DESC
        """,
        (
            publish_cutoff.isoformat(),
            now.isoformat(),
            source_cutoff.isoformat(),
            now.isoformat(),
            retry_cutoff.isoformat(),
        ),
    ).fetchall()
    if not rows:
        return None

    columns = [
        "id",
        "slug",
        "title",
        "category",
        "why_it_matters",
        "hashtags",
        "importance_score",
        "published_at",
        "source_published_at",
    ]
    candidates = [_as_dict(row, columns) for row in rows]
    for candidate in candidates:
        if not candidate.get("category") or candidate["category"] not in recent_categories:
            return candidate
    return candidates[0]


def _clean_text(value: Any) -> str:
    text = str(value or "").replace("**", "").replace("__", "")
    return re.sub(r"\s+", " ", text).strip()


def _hashtags(raw: Any, category: str | None) -> list[str]:
    values: list[Any]
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, str):
        try:
            decoded = json.loads(raw)
            values = decoded if isinstance(decoded, list) else raw.split()
        except json.JSONDecodeError:
            values = raw.replace(",", " ").split()
    else:
        values = []

    values.extend([category or "", "AI", "DailyAIWire"])
    result: list[str] = []
    for value in values:
        tag = re.sub(r"[^A-Za-z0-9_]", "", str(value).lstrip("#"))
        if not tag:
            continue
        formatted = f"#{tag}"
        if formatted.lower() not in {item.lower() for item in result}:
            result.append(formatted)
        if len(result) == 5:
            break
    return result


def build_caption(article: dict[str, Any], *, base_url: str = DEFAULT_BASE_URL) -> str:
    title = _clean_text(article.get("title"))
    why_it_matters = _clean_text(article.get("why_it_matters"))
    slug = str(article.get("slug") or "").strip()
    tracked_url = (
        f"{base_url.rstrip('/')}/article/{slug}"
        "?utm_source=instagram&utm_medium=social&utm_campaign=dailyaiwire_browser"
    )
    tags = " ".join(_hashtags(article.get("hashtags"), article.get("category")))

    fixed_tail = f"Read: {tracked_url}\n\n{tags}"
    available_why = CAPTION_LIMIT - len(title) - len(fixed_tail) - 4
    if available_why < 0:
        title = title[: max(0, CAPTION_LIMIT - len(fixed_tail) - 4)].rstrip()
        available_why = 0
    if len(why_it_matters) > available_why:
        why_it_matters = why_it_matters[: max(0, available_why - 1)].rstrip() + "…"

    parts = [title]
    if why_it_matters:
        parts.append(why_it_matters)
    parts.append(fixed_tail)
    return "\n\n".join(parts)[:CAPTION_LIMIT]


def prepare_candidate(
    conn: sqlite3.Connection,
    *,
    now: datetime | None = None,
    lookback_hours: int = 48,
    max_source_age_hours: int = 72,
    base_url: str = DEFAULT_BASE_URL,
    card_generator: Callable[[str, str, str], str] | None = None,
) -> dict[str, Any] | None:
    candidate = select_next_candidate(
        conn,
        now=now,
        lookback_hours=lookback_hours,
        max_source_age_hours=max_source_age_hours,
    )
    if candidate is None:
        return None

    if card_generator is None:
        from instagram_card_generator import generate_card

        card_generator = generate_card
    card_path = card_generator(
        candidate["title"],
        candidate["slug"],
        candidate.get("why_it_matters") or "",
    )
    filename = os.path.basename(card_path)
    candidate["image_url"] = f"{base_url.rstrip('/')}/social-image/{filename}"
    candidate["caption"] = build_caption(candidate, base_url=base_url)
    return candidate


def _valid_instagram_post_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname in {"instagram.com", "www.instagram.com"}
        and (parsed.path.startswith("/p/") or parsed.path.startswith("/reel/"))
    )


def mark_posted(
    conn: sqlite3.Connection,
    *,
    article_id: int,
    instagram_post_url: str,
    posted_at: datetime | None = None,
) -> None:
    """Atomically record a visibly confirmed Instagram publication."""
    if not _valid_instagram_post_url(instagram_post_url):
        raise ValueError("A confirmed instagram.com post URL is required")

    ensure_schema(conn)
    posted_at = posted_at or datetime.now(timezone.utc)
    timestamp = posted_at.isoformat()
    try:
        conn.execute("BEGIN IMMEDIATE")
        article = conn.execute(
            """
            SELECT slug, category, COALESCE(shared_on_ig, 0) AS shared_on_ig
            FROM articles WHERE id = ?
            """,
            (article_id,),
        ).fetchone()
        if article is None:
            raise ValueError(f"Article {article_id} does not exist")
        article_data = _as_dict(article, ["slug", "category", "shared_on_ig"])
        if article_data["shared_on_ig"]:
            raise ValueError(f"Article {article_id} is already marked as shared on Instagram")

        conn.execute(
            """
            INSERT INTO instagram_browser_post_audit (
                article_id, article_slug, category, status,
                instagram_post_url, attempted_at, posted_at
            ) VALUES (?, ?, ?, 'POSTED', ?, ?, ?)
            """,
            (
                article_id,
                article_data["slug"],
                article_data["category"],
                instagram_post_url,
                timestamp,
                timestamp,
            ),
        )
        conn.execute(
            "UPDATE articles SET shared_on_ig = 1, shared_on_ig_at = ? WHERE id = ?",
            (timestamp, article_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def replace_post_url(
    conn: sqlite3.Connection,
    *,
    article_id: int,
    instagram_post_url: str,
    replaced_at: datetime | None = None,
) -> None:
    """Replace a confirmed repost URL without creating a second audit event."""
    if not _valid_instagram_post_url(instagram_post_url):
        raise ValueError("A confirmed instagram.com post URL is required")

    ensure_schema(conn)
    replaced_at = replaced_at or datetime.now(timezone.utc)
    timestamp = replaced_at.isoformat()
    try:
        conn.execute("BEGIN IMMEDIATE")
        article = conn.execute(
            "SELECT COALESCE(shared_on_ig, 0) AS shared_on_ig FROM articles WHERE id = ?",
            (article_id,),
        ).fetchone()
        if article is None:
            raise ValueError(f"Article {article_id} does not exist")
        article_data = _as_dict(article, ["shared_on_ig"])
        audit = conn.execute(
            """
            SELECT id
            FROM instagram_browser_post_audit
            WHERE article_id = ? AND status = 'POSTED'
            ORDER BY COALESCE(posted_at, attempted_at) DESC, id DESC
            LIMIT 1
            """,
            (article_id,),
        ).fetchone()
        if not article_data["shared_on_ig"] or audit is None:
            raise ValueError(f"Article {article_id} has no confirmed Instagram post")
        audit_data = _as_dict(audit, ["id"])

        conn.execute(
            """
            UPDATE instagram_browser_post_audit
            SET instagram_post_url = ?, attempted_at = ?, posted_at = ?
            WHERE id = ?
            """,
            (instagram_post_url, timestamp, timestamp, audit_data["id"]),
        )
        conn.execute(
            "UPDATE articles SET shared_on_ig_at = ? WHERE id = ?",
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
    """Record a failure without changing the article's share state."""
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
        INSERT INTO instagram_browser_post_audit (
            article_id, article_slug, category, status,
            failure_reason, attempted_at
        ) VALUES (?, ?, ?, 'FAILED', ?, ?)
        """,
        (
            article_id,
            article_data["slug"],
            article_data["category"],
            _clean_text(reason)[:500],
            attempted_at.isoformat(),
        ),
    )
    conn.commit()
