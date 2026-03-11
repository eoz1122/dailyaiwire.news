"""
Fetcher — Database Initialization & Metadata Helpers
Schema creation, lazy migrations, and scan tracking.
"""
import os
import sqlite3
from datetime import datetime, timedelta
from typing import List

from db import DB_PATH


def init_db():
    """Create all required tables and run lazy column migrations."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE,
            title TEXT,
            image TEXT,
            category TEXT,
            gist TEXT,
            why_it_matters TEXT,
            bull_case TEXT,
            bear_case TEXT,
            key_details TEXT, -- Stored as JSON string
            eli5 TEXT,
            deep_analysis TEXT,
            source TEXT,
            source_url TEXT UNIQUE,
            full_json TEXT,
            published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            audio_male TEXT, -- Path to generated male audio
            audio_female TEXT, -- Path to generated female audio
            narration_script TEXT, -- AI-generated script for 1-minute read
            thought_provoking_question TEXT,
            importance_score INTEGER DEFAULT 50,
            original_author TEXT,
            hashtags TEXT, -- Stored as JSON string
            shared_on_x BOOLEAN DEFAULT 0,
            shared_at TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blog_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE,
            title TEXT,
            subtitle TEXT,
            content TEXT,
            image TEXT,
            author_name TEXT,
            author_title TEXT,
            author_image TEXT,
            author_linkedin TEXT,
            meta_description TEXT,
            published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS social_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT,
            headline TEXT,
            status TEXT DEFAULT 'PENDING', -- PENDING, SENT, FAILED
            scheduled_time TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_source_url ON articles(source_url)')

    # Add original_author if it doesn't exist
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN original_author TEXT")
    except sqlite3.OperationalError:
        pass  # Already exists

    # Add narration_script if it doesn't exist
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN narration_script TEXT")
    except sqlite3.OperationalError:
        pass  # Already exists

    # Add thought_provoking_question if it doesn't exist
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN thought_provoking_question TEXT")
    except sqlite3.OperationalError:
        pass  # Already exists

    # Add importance_score if it doesn't exist
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN importance_score INTEGER DEFAULT 50")
    except sqlite3.OperationalError:
        pass  # Already exists

    # Blocked Sources (Adversarial Defense)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blocked_sources (
            domain TEXT PRIMARY KEY,
            reason TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add design_tokens columns (GenUI)
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN design_tokens TEXT")
    except sqlite3.OperationalError:
        pass  # Already exists

    # Authors Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS authors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            title TEXT,
            bio TEXT,
            image TEXT,
            linkedin TEXT
        )
    ''')

    # Editorials Table (Opinion/Human Content)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS editorials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE,
            title TEXT,
            subtitle TEXT,
            content TEXT,
            author TEXT DEFAULT 'Emre Ozen',
            image TEXT,
            published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_published BOOLEAN DEFAULT 0
        )
    ''')

    # AI Logs Table (Audit Trail)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            model TEXT,
            prompt_type TEXT,
            prompt_text TEXT,
            response_text TEXT,
            cost_estimate REAL
        )
    ''')

    # Metadata Table for scan tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    # Processing Attempts Log (The "Crash Loop" Circuit Breaker)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processing_attempts (
            url TEXT PRIMARY KEY,
            attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT
        )
    ''')

    # Lazy migration: Add compass_score column if missing
    try:
        cursor.execute("SELECT compass_score FROM articles LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE articles ADD COLUMN compass_score REAL DEFAULT 0.7")
        print("📐 Added compass_score column to articles table.")

    conn.commit()
    conn.close()


def get_last_scan_timestamp() -> datetime:
    """Retrieves the last successful scan timestamp from metadata."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM metadata WHERE key = 'last_scan_timestamp'")
    row = cursor.fetchone()
    conn.close()
    if row:
        return datetime.fromisoformat(row[0])
    # Fallback: 24 hours ago if no record exists
    return datetime.utcnow() - timedelta(hours=24)


def update_last_scan_timestamp(ts: datetime):
    """Updates the last successful scan timestamp in metadata."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_scan_timestamp', ?)", (ts.isoformat(),))
    # Blocked Sources Table (Dynamic Blocklist)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blocked_sources (
            domain TEXT PRIMARY KEY,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()


def get_recent_published_titles(hours=36) -> List[str]:
    """Retrieves titles of articles published in the last X hours for deduplication."""
    target_time = datetime.utcnow() - timedelta(hours=hours)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT title FROM articles WHERE published_at > ?", (target_time.isoformat(),))
    titles = [row[0] for row in cursor.fetchall()]
    conn.close()
    return titles


def log_processing_attempt(url: str, status="PROCESSING"):
    """Logs that we are about to try processing this URL."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO processing_attempts (url, status, attempted_at) VALUES (?, ?, ?)",
                   (url, status, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Failed to log attempt: {e}")
