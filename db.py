"""
Shared Database Layer — DailyAIWire.news
Single source of truth for DB path and connection factory.
"""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "news.db")
DEFAULT_DB_TIMEOUT_SECONDS = 10.0


def get_db_connection(*, timeout: float = DEFAULT_DB_TIMEOUT_SECONDS):
    """Returns a sqlite3 connection with Row factory enabled."""
    conn = sqlite3.connect(DB_PATH, timeout=timeout)
    conn.execute(f"PRAGMA busy_timeout = {int(max(timeout, 0) * 1000)}")
    conn.row_factory = sqlite3.Row
    return conn
