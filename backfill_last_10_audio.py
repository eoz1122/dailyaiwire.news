import sqlite3
import os
import json
from audio_generator import AudioGenerator
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "news.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def backfill():
    print("🚀 Starting Audio Backfill for last 10 articles...")
    
    # Initialize Audio Generator
    try:
        audio_gen = AudioGenerator()
    except Exception as e:
        print(f"❌ Failed to init audio generator: {e}")
        return

    conn = get_db_connection()
    articles = conn.execute('SELECT * FROM articles ORDER BY published_at DESC LIMIT 10').fetchall()
    
    for art in articles:
        print(f"Processing: {art['title']}")
        slug = art['slug']
        
        # Construct Expanded Text
        try:
            key_details = json.loads(art['key_details']) if art['key_details'] else []
        except:
            key_details = []
            
        key_details_text = ". ".join(key_details)
        
        text_to_read = (
            f"Headline: {art['title']}. "  # Fallback to title if headline missing in dict (row has title)
            f"The Gist: {art['gist']}. "
            f"Why It Matters: {art['why_it_matters']}. "
            f"Optimistic Outlook: {art['bull_case']}. " # DB col is bull_case, fetcher dict uses optimistic_outlook map?
            f"Risk Factors: {art['bear_case']}. "       # DB col bear_case
            f"Key Details: {key_details_text}. "
            f"Deep Analysis: {art['deep_analysis']}"
        )
        
        # DB schema uses 'bull_case' / 'bear_case', check fetcher logic
        # fetcher logic: text_to_read used art.get('optimistic_outlook') but art was a DICT from scraping.
        # DB columns: bull_case, bear_case.
        
        try:
            am, af = audio_gen.generate_audio_reads(slug, text_to_read)
            
            # Update DB
            conn.execute('UPDATE articles SET audio_male = ?, audio_female = ? WHERE slug = ?', (am, af, slug))
            conn.commit()
            print(f"✅ Updated audio for {slug}")
        except Exception as e:
            print(f"❌ Failed to generate audio for {slug}: {e}")
            
    conn.close()
    print("🏁 Backfill complete.")

if __name__ == "__main__":
    backfill()
