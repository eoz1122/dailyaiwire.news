
import sqlite3
import os

DB_PATH = "news.db"

def migrate_leads():
    print(f"Connecting to {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create LEADS Table
    print("Creating 'leads' table for Adversarial Sales...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT,
            source_url TEXT UNIQUE,
            title TEXT,
            detected_email TEXT,
            status TEXT DEFAULT 'NEW', -- NEW, PROPOSAL_SENT, CONVERTED, IGNORED
            confidence_score INTEGER,
            found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create BLOCKED_SOURCES Table if not exists (for reference)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blocked_sources (
            domain TEXT PRIMARY KEY,
            reason TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Leads Table Created.")

if __name__ == "__main__":
    migrate_leads()
