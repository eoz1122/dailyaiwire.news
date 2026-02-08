import sqlite3
import datetime
from urllib.parse import urlparse

DB_PATH = '/home/dailyai/dailyaiwire.news/news.db'

def convert_killed_to_leads():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Fetch killed articles
    cursor.execute("""
        SELECT id, title, source, source_url, gist, published_at 
        FROM articles 
        WHERE is_published = 0
    """)
    killed_articles = cursor.fetchall()

    print(f"Found {len(killed_articles)} killed articles.")
    
    leads_added = 0
    
    for art in killed_articles:
        # Extract domain
        try:
            domain = urlparse(art['source_url']).netloc
        except:
            domain = art['source']

        # Determine value (simple heuristic)
        # If it was killed, maybe it's low value, but we can flag it as RECOVERED
        value = 'MID_VALUE'
        
        # Reason
        reason = f"Recovered from Killed Articles (Published: {art['published_at']}). Source: {art['source']}"
        if art['gist']:
             reason += f"\n\nGist: {art['gist'][:100]}..."

        try:
            cursor.execute("""
                INSERT INTO leads (
                    domain, source_url, title, status, confidence_score, 
                    product_value, opportunity_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                domain,
                art['source_url'],
                art['title'],
                'NEW',
                60, # Confidence score
                value,
                reason
            ))
            leads_added += 1
            print(f"Converted: {art['title']}")
        except sqlite3.IntegrityError:
            print(f"Skipping (already exists): {art['title']}")
        except Exception as e:
            print(f"Error adding {art['title']}: {e}")

    conn.commit()
    conn.close()
    print(f"\nSuccessfully converted {leads_added} articles to Leads.")

if __name__ == "__main__":
    convert_killed_to_leads()
