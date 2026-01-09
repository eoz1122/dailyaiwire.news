import sqlite3
import os
import sys
from dotenv import load_dotenv

# Load Environment Variables from .env file explicitly
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

# Add current dict to path to allow imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.lead_extractor import LeadExtractor
from urllib.parse import urlparse

def process_killed_articles():
    print("🚀 Starting Killed Article Processing Sequence...")
    
    conn = sqlite3.connect('news.db')
    cursor = conn.cursor()
    
    # Check articles table columns to find the right URL column
    cursor.execute("PRAGMA table_info(articles)")
    columns = [info[1] for info in cursor.fetchall()]
    
    url_col = 'url'
    if 'source_url' in columns:
        url_col = 'source_url'
    elif 'link' in columns:
        url_col = 'link'
    elif 'original_url' in columns:
        url_col = 'original_url'
        
    print(f"ℹ️ Using '{url_col}' as source URL column.")
    
    # Fetch Manually Killed Articles (is_published = 0)
    try:
        if 'is_published' in columns:
            cursor.execute(f"SELECT {url_col}, title FROM articles WHERE is_published = 0")
            killed_articles = cursor.fetchall()
        else:
            print("❌ 'is_published' column not found! Cannot identify manually killed articles.")
            return
    except Exception as e:
        print(f"❌ Error fetching articles: {e}")
        return

    conn.close()
    
    if not killed_articles:
        print("⚠️ No manually killed articles found.")
        return
        
    print(f"🎯 Found {len(killed_articles)} manually killed articles. Initializing Iron Judo...")
    
    extractor = LeadExtractor()
    
    processed_count = 0
    
    for url, title in killed_articles:
        if not url:
            continue
            
        print(f"\n⚡ Processing: {title[:50]}...")
        print(f"   URL: {url}")
        
        try:
            # Check if lead already exists to avoid redundant processing/cost
            check_conn = sqlite3.connect('news.db')
            check_cur = check_conn.cursor()
            domain = urlparse(url).netloc
            check_cur.execute("SELECT id FROM leads WHERE domain = ?", (domain,))
            exists = check_cur.fetchone()
            check_conn.close()
            
            if exists:
                print("   ⏩ Lead already exists for this domain. Skipping.")
                continue
                
            # Extract!
            extractor.extract_and_log(url, title)
            processed_count += 1
            
        except Exception as e:
            print(f"   ❌ Failed to process: {e}")
            
    print("\n✅ Processing Complete.")

if __name__ == "__main__":
    process_killed_articles()
