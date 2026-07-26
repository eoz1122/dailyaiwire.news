"""Idempotent weekly newsletter draft orchestration."""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta

import weekly_curator
from db import DB_PATH

logger = logging.getLogger("weekly_newsletter_runner")


def run_weekly_newsletter(
    *,
    db_path: str = DB_PATH,
    now: datetime | None = None,
    dedupe_hours: int = 24,
) -> str:
    """Generate one weekly draft unless a newsletter was created recently."""
    now = now or datetime.now()
    threshold = now - timedelta(hours=dedupe_hours)

    conn = sqlite3.connect(db_path)
    try:
        recent = conn.execute(
            """
            SELECT id
            FROM newsletters
            WHERE datetime(created_at) >= datetime(?)
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT 1
            """,
            (threshold.isoformat(),),
        ).fetchone()
    finally:
        conn.close()

    if recent:
        logger.info("Recent newsletter %s already exists; skipping weekly generation.", recent[0])
        return "skipped_recent"

    newsletter_id = weekly_curator.generate_newsletter_draft()
    if newsletter_id is None:
        logger.info("Weekly newsletter generation had no eligible content.")
        return "skipped_no_content"

    logger.info("Created weekly newsletter draft %s.", newsletter_id)
    return f"created:{newsletter_id}"
