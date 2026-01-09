import sqlite3
import os
from audio_generator import AudioGenerator
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "news.db"

def backfill_audio(limit=4):
    if not os.path.exists(DB_PATH):
        print("❌ Database not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get the latest articles that don't have audio yet
    articles = cursor.execute('''
        SELECT slug, title, gist, why_it_matters 
        FROM articles 
        WHERE audio_male IS NULL OR audio_female IS NULL
        ORDER BY published_at DESC 
        LIMIT ?
    ''', (limit,)).fetchall()
    
    if not articles:
        print("✅ No articles need audio backfilling.")
        return

    print(f"🎙️ Found {len(articles)} articles to backfill...")
    audio_gen = AudioGenerator()
    
    if not audio_gen.client:
        print("❌ Google TTS Client not initialized. Check credentials.")
        return

    for art in articles:
        print(f"📖 Processing: {art['title']}")
        text_to_read = f"{art['title']}. {art['gist']}. {art['why_it_matters']}"
        
        am, af = audio_gen.generate_audio_reads(art['slug'], text_to_read)
        
        if am and af:
            cursor.execute('''
                UPDATE articles 
                SET audio_male = ?, audio_female = ? 
                WHERE slug = ?
            ''', (am, af, art['slug']))
            print(f"✅ Audio generated for: {art['slug']}")
        else:
            print(f"⚠️ Failed to generate audio for: {art['slug']}")
            
    conn.commit()
    conn.close()
    print("✨ Backfill complete.")

if __name__ == "__main__":
    backfill_audio(limit=4)
