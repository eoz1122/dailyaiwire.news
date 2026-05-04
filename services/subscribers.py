"""
Newsletter subscriber persistence helpers.

Keeps signup confirmation, audit metadata, and abuse events consistent across
public and admin flows.
"""
import hashlib
import secrets
import sqlite3
from typing import Optional


def hash_value(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def ensure_subscribers_schema(conn: sqlite3.Connection) -> None:
    conn.execute('''
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            status TEXT DEFAULT 'ACTIVE',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    existing = set()
    for row in conn.execute("PRAGMA table_info(subscribers)").fetchall():
        existing.add(row["name"] if hasattr(row, "keys") else row[1])
    migrations = {
        "signup_ip_hash": "ALTER TABLE subscribers ADD COLUMN signup_ip_hash TEXT",
        "signup_user_agent": "ALTER TABLE subscribers ADD COLUMN signup_user_agent TEXT",
        "signup_referrer": "ALTER TABLE subscribers ADD COLUMN signup_referrer TEXT",
        "signup_source_path": "ALTER TABLE subscribers ADD COLUMN signup_source_path TEXT",
        "signup_accept_language": "ALTER TABLE subscribers ADD COLUMN signup_accept_language TEXT",
        "signup_fingerprint_hash": "ALTER TABLE subscribers ADD COLUMN signup_fingerprint_hash TEXT",
        "confirmation_token_hash": "ALTER TABLE subscribers ADD COLUMN confirmation_token_hash TEXT",
        "confirmed_at": "ALTER TABLE subscribers ADD COLUMN confirmed_at TIMESTAMP",
    }
    for column, sql in migrations.items():
        if column not in existing:
            conn.execute(sql)


def ensure_subscriber_events_schema(conn: sqlite3.Connection) -> None:
    conn.execute('''
        CREATE TABLE IF NOT EXISTS subscriber_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_hash TEXT,
            event_type TEXT NOT NULL,
            reason TEXT,
            ip_hash TEXT,
            user_agent TEXT,
            referrer TEXT,
            source_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')


def record_subscriber_event(
    conn: sqlite3.Connection,
    *,
    email: str,
    event_type: str,
    reason: str,
    ip_hash: Optional[str],
    user_agent: str,
    referrer: str,
    source_path: str,
) -> None:
    ensure_subscriber_events_schema(conn)
    conn.execute(
        '''
        INSERT INTO subscriber_events (
            email_hash, event_type, reason, ip_hash, user_agent, referrer, source_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            hash_value(normalize_email(email)) if email else None,
            event_type,
            reason,
            ip_hash,
            user_agent,
            referrer,
            source_path,
        ),
    )


def confirmation_token_hash(token: str) -> str:
    return hash_value(token)


def create_confirmation_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, confirmation_token_hash(token)
