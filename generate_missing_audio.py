import os
import sqlite3
import json
from audio_generator import AudioGenerator
from pathlib import Path

DB_PATH = "news.db"

def generate_audio_for_recent_articles(limit=10):
    """Generate audio for recent articles that don't have it yet."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get recent articles without audio
    articles = cursor.execute('''
        SELECT slug, title, gist, why_it_matters, 
               bull_case, bear_case, key_details
        FROM articles 
        WHERE (audio_male IS NULL OR audio_female IS NULL)
        ORDER BY published_at DESC 
        LIMIT ?
    ''', (limit,)).fetchall()
    
    if not articles:
        print("No articles need audio generation.")
        conn.close()
        return
    
    print(f"Generating audio for {len(articles)} articles...")
    audio_gen = AudioGenerator()
    
    for art in articles:
        slug = art[0]
        # Build audio script
        try:
            key_details = json.loads(art[6]) if art[6] else []
        except:
            key_details = []
            
        key_details_text = ". ".join(key_details)
        text_to_read = (
            f"Headline: {art[1]}. "
            f"The Gist: {art[2]}. "
            f"Why It Matters: {art[3]}. "
            f"Optimistic Outlook: {art[4]}. "
            f"Risk Factors: {art[5]}. "
            f"Key Details: {key_details_text}. "
        )
        
        male, female = audio_gen.generate_audio_reads(slug, text_to_read)
        
        if male and female:
            cursor.execute(
                'UPDATE articles SET audio_male = ?, audio_female = ? WHERE slug = ?',
                (male, female, slug)
            )
            print(f"✅ Generated audio for: {art[1][:50]}...")
    
    conn.commit()
    conn.close()
    print(f"Audio generation complete for {len(articles)} articles.")

if __name__ == "__main__":
    # Can be run standalone to backfill audio for articles missing it
    generate_audio_for_recent_articles(limit=20)
