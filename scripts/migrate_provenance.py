"""
Migration: Add Content Provenance Chain columns to articles table.

Adds:
  - source_content_hash TEXT  — SHA-256 of the raw scraped content
  - ai_model_used TEXT        — Model identifier (e.g., 'gemini-2.5-flash')

Usage:
    python scripts/migrate_provenance.py

Idempotent: safe to run multiple times.
"""
import os
import sys
import sqlite3

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from db import DB_PATH


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Add source_content_hash if missing
    try:
        cursor.execute("SELECT source_content_hash FROM articles LIMIT 1")
        print("✅ source_content_hash column already exists.")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE articles ADD COLUMN source_content_hash TEXT")
        print("🔗 Added source_content_hash column to articles table.")

    # Add ai_model_used if missing
    try:
        cursor.execute("SELECT ai_model_used FROM articles LIMIT 1")
        print("✅ ai_model_used column already exists.")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE articles ADD COLUMN ai_model_used TEXT")
        print("🤖 Added ai_model_used column to articles table.")

    conn.commit()
    conn.close()
    print("✅ Provenance migration complete.")


if __name__ == "__main__":
    migrate()
