"""
Shared editorial loaders for DailyAIWire.news.
Handles schema drift and filters out incomplete or unpublished blog posts.
"""

from pathlib import Path
from typing import Optional

from db import get_db_connection
from lab_posts import get_lab_posts

EDITORIAL_FALLBACK_IMAGE = "/static/fallbacks/editorial_0.jpg"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _table_columns(conn, table_name: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    except Exception:
        return set()

    columns = set()
    for row in rows:
        if isinstance(row, tuple):
            columns.add(row[1])
        else:
            columns.add(row["name"])
    return columns


def _normalize_editorial_image(image_path: Optional[str]) -> str:
    candidate = (image_path or "").strip()
    if not candidate:
        return EDITORIAL_FALLBACK_IMAGE

    if candidate.startswith("/static/"):
        local_path = PROJECT_ROOT / candidate.lstrip("/")
        if not local_path.exists():
            return EDITORIAL_FALLBACK_IMAGE

    return candidate


def normalize_editorial_post(post: dict) -> dict:
    normalized = dict(post)
    normalized["slug"] = (normalized.get("slug") or "").strip()
    normalized["title"] = (normalized.get("title") or "").strip()
    normalized["subtitle"] = (
        normalized.get("subtitle")
        or normalized.get("meta_description")
        or ""
    ).strip()
    normalized["author_name"] = normalized.get("author_name") or ""
    normalized["author_title"] = normalized.get("author_title") or ""
    normalized["published_at"] = normalized.get("published_at") or ""
    normalized["image"] = _normalize_editorial_image(normalized.get("image"))
    return normalized


def get_db_blog_posts(*, published_only: bool = True) -> list[dict]:
    conn = get_db_connection()
    try:
        columns = _table_columns(conn, "blog_posts")
        if not columns:
            return []

        wanted_columns = [
            "id",
            "slug",
            "title",
            "subtitle",
            "content",
            "image",
            "author_name",
            "author_title",
            "author_image",
            "author_linkedin",
            "meta_description",
            "published_at",
            "is_published",
        ]
        select_columns = [col for col in wanted_columns if col in columns]
        if not select_columns:
            return []

        where_clauses = [
            "slug IS NOT NULL",
            "TRIM(slug) != ''",
            "title IS NOT NULL",
            "TRIM(title) != ''",
            "published_at IS NOT NULL",
        ]
        if published_only and "is_published" in columns:
            where_clauses.append("COALESCE(is_published, 0) = 1")

        query = (
            f"SELECT {', '.join(select_columns)} FROM blog_posts "
            f"WHERE {' AND '.join(where_clauses)} "
            "ORDER BY published_at DESC, id DESC"
        )
        rows = conn.execute(query).fetchall()
        return [normalize_editorial_post(dict(row)) for row in rows]
    except Exception:
        return []
    finally:
        conn.close()


def get_combined_lab_posts(*, published_only: bool = True) -> list[dict]:
    posts = [normalize_editorial_post(dict(post)) for post in get_lab_posts()]
    posts.extend(get_db_blog_posts(published_only=published_only))
    posts.sort(key=lambda post: post.get("published_at") or "", reverse=True)
    return posts
