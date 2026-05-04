"""
Helpers for non-destructive duplicate review queueing.
"""
from __future__ import annotations

import logging
import sqlite3

import db


logger = logging.getLogger('duplicate_review')


def ensure_duplicate_review_table() -> None:
    conn = sqlite3.connect(db.DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS duplicate_review_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keep_article_id INTEGER NOT NULL,
            keep_title TEXT,
            duplicate_article_id INTEGER NOT NULL,
            duplicate_title TEXT,
            detection_method TEXT NOT NULL,
            confidence_score REAL,
            reason TEXT,
            status TEXT DEFAULT 'PENDING_REVIEW',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_duplicate_review_pair
        ON duplicate_review_queue (keep_article_id, duplicate_article_id, detection_method)
    ''')
    conn.commit()
    conn.close()


def flag_duplicate_pair(
    *,
    keep_article_id: int,
    keep_title: str,
    duplicate_article_id: int,
    duplicate_title: str,
    detection_method: str,
    confidence_score: float | None = None,
    reason: str = "",
) -> None:
    ensure_duplicate_review_table()
    conn = sqlite3.connect(db.DB_PATH)
    cur = conn.cursor()
    cur.execute(
        '''
        INSERT OR IGNORE INTO duplicate_review_queue
        (keep_article_id, keep_title, duplicate_article_id, duplicate_title, detection_method, confidence_score, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            keep_article_id,
            keep_title,
            duplicate_article_id,
            duplicate_title,
            detection_method,
            confidence_score,
            reason,
        ),
    )
    conn.commit()
    conn.close()
    logger.info(
        "Flagged duplicate review: keep=%s delete=%s method=%s",
        keep_article_id,
        duplicate_article_id,
        detection_method,
    )
