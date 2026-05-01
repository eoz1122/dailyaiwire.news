"""
Google Indexing API audit helpers.

Keeps publication indexing observable without blocking article publishing when
the audit write itself fails.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

import db


VALID_STATUSES = {"success", "failed", "quota_exceeded", "skipped"}
MAX_RESPONSE_BODY_LENGTH = 4000
MAX_ERROR_LENGTH = 1000


def ensure_indexing_notifications_table(conn: Optional[sqlite3.Connection] = None) -> None:
    owns_connection = conn is None
    active_conn = conn or sqlite3.connect(db.DB_PATH, timeout=10)
    try:
        active_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS indexing_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                status_code INTEGER,
                response_body TEXT,
                error TEXT,
                attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        active_conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_indexing_notifications_attempted_at
            ON indexing_notifications(attempted_at)
            """
        )
        active_conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_indexing_notifications_status
            ON indexing_notifications(status)
            """
        )
        active_conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_indexing_notifications_url
            ON indexing_notifications(url)
            """
        )
        if owns_connection:
            active_conn.commit()
    finally:
        if owns_connection:
            active_conn.close()


def _trim(value: Any, max_length: int) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    if len(text) <= max_length:
        return text
    return text[:max_length]


def record_indexing_notification(
    *,
    url: str,
    action: str,
    status: str,
    status_code: Optional[int] = None,
    response_body: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid indexing notification status: {status}")

    conn = sqlite3.connect(db.DB_PATH, timeout=10)
    try:
        ensure_indexing_notifications_table(conn)
        conn.execute(
            """
            INSERT INTO indexing_notifications (
                url, action, status, status_code, response_body, error
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                url,
                action,
                status,
                status_code,
                _trim(response_body, MAX_RESPONSE_BODY_LENGTH),
                _trim(error, MAX_ERROR_LENGTH),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def fetch_indexing_notifications(
    *,
    status: str = "",
    query: str = "",
    limit: int = 100,
) -> list[sqlite3.Row]:
    ensure_indexing_notifications_table()
    safe_limit = max(1, min(limit, 500))
    conditions = []
    params: list[Any] = []

    if status in VALID_STATUSES:
        conditions.append("status = ?")
        params.append(status)

    if query:
        conditions.append("(url LIKE ? OR action LIKE ? OR error LIKE ?)")
        like = f"%{query}%"
        params.extend([like, like, like])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(safe_limit)

    conn = sqlite3.connect(db.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"""
            SELECT id, url, action, status, status_code, response_body, error,
                   attempted_at
            FROM indexing_notifications
            {where_clause}
            ORDER BY datetime(attempted_at) DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    finally:
        conn.close()

    return rows


def fetch_retry_candidates(
    *,
    limit: int = 50,
    retry_statuses: tuple[str, ...] = ("failed", "quota_exceeded"),
) -> list[sqlite3.Row]:
    ensure_indexing_notifications_table()
    safe_limit = max(1, min(limit, 500))
    statuses = [status for status in retry_statuses if status in VALID_STATUSES]
    if not statuses:
        return []

    placeholders = ",".join("?" for _ in statuses)
    params: list[Any] = statuses + [safe_limit]

    conn = sqlite3.connect(db.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"""
            WITH latest AS (
                SELECT url, action, MAX(id) AS latest_id
                FROM indexing_notifications
                GROUP BY url, action
            )
            SELECT n.id, n.url, n.action, n.status, n.status_code,
                   n.response_body, n.error, n.attempted_at
            FROM indexing_notifications n
            INNER JOIN latest l ON n.id = l.latest_id
            WHERE n.status IN ({placeholders})
            ORDER BY n.id ASC
            LIMIT ?
            """,
            params,
        ).fetchall()
    finally:
        conn.close()

    return rows


def summarize_indexing_notifications() -> dict[str, int]:
    ensure_indexing_notifications_table()
    conn = sqlite3.connect(db.DB_PATH, timeout=10)
    try:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM indexing_notifications
            GROUP BY status
            """
        ).fetchall()
    finally:
        conn.close()

    summary = {status: 0 for status in VALID_STATUSES}
    summary["total"] = 0
    for status, count in rows:
        summary[str(status)] = int(count)
        summary["total"] += int(count)
    return summary
