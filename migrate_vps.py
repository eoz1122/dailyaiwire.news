import sqlite3
import os

DB_PATH = "news.db"

def run_migrations():
    print(f"📡 Connecting to {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Sources Governance
    print("--- Checking 'sources' table --")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            url TEXT UNIQUE,
            is_active BOOLEAN DEFAULT 1,
            last_scraped_at TIMESTAMP
        )
    ''')
    
    # 2. Blocked Sources
    print("--- Checking 'blocked_sources' table --")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blocked_sources (
            domain TEXT PRIMARY KEY,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 3. Leads (Iron Judo)
    print("--- Checking 'leads' table --")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT,
            source_url TEXT UNIQUE,
            title TEXT,
            detected_email TEXT,
            status TEXT DEFAULT 'NEW',  -- NEW, CONTACT_FOUND, PROPOSAL_SENT, CONVERTED, BLOCKED
            confidence_score INTEGER,
            found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 3b. Leads Columns Upgrade (Value & Drafts)
    columns_to_add = [
        ('product_value', 'TEXT'),
        ('opportunity_reason', 'TEXT'),
        ('draft_proposal', 'TEXT')
    ]
    
    for col_name, col_type in columns_to_add:
        try:
            cursor.execute(f'ALTER TABLE leads ADD COLUMN {col_name} {col_type}')
            print(f"   + Added column '{col_name}' to leads.")
        except sqlite3.OperationalError:
            pass # Exists

    # 4. Articles (Kill Switch)
    print("--- Checking 'articles' table updates --")
    try:
        cursor.execute('ALTER TABLE articles ADD COLUMN is_published INTEGER DEFAULT 1')
        print("   + Added 'is_published' column.")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()
    print("✅ MIGRATION COMPLETE. VPS Database is ready for Iron Judo.")

if __name__ == "__main__":
    run_migrations()
