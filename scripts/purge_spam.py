import sqlite3
import sys
import os

# DB is in the parent directory (project root)
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "news.db")

def block_and_purge(domain_or_slug):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print(f"🛡️ Action: Purging spam source '{domain_or_slug}'")
    
    # 1. Add to Blocked Sources Table
    cursor.execute('CREATE TABLE IF NOT EXISTS blocked_sources (domain TEXT PRIMARY KEY, added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    try:
        # If input looks like a domain
        if '.' in domain_or_slug and not domain_or_slug.startswith('http'):
            cursor.execute('INSERT OR IGNORE INTO blocked_sources (domain) VALUES (?)', (domain_or_slug,))
            print(f"✅ Domain '{domain_or_slug}' added to permanent blocklist.")
            
            # Delete articles from this source
            count = cursor.execute("DELETE FROM articles WHERE source_url LIKE ?", (f'%{domain_or_slug}%',)).rowcount
            print(f"🗑️ Deleted {count} articles associated with this domain.")
            
    except Exception as e:
        print(f"⚠️ Error blocking domain: {e}")

    # 2. Delete specific article if slug provided
    if not '.' in domain_or_slug:
        count = cursor.execute("DELETE FROM articles WHERE slug = ?", (domain_or_slug,)).rowcount
        print(f"🗑️ Deleted article with slug '{domain_or_slug}': {count} removed.")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    target = "wan2-6.org" # Default target from user report
    if len(sys.argv) > 1:
        target = sys.argv[1]
    
    block_and_purge(target)
