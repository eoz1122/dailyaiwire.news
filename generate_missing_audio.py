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
               bull_case, bear_case, key_details, narration_script, audio_female
        FROM articles 
        WHERE is_published = 1
          AND audio_male IS NULL
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
        slug, title, gist, matters, bull, bear, details_json, script, existing_female = art
        
        # Build audio script: Prioritize AI Narrative Script, fallback to multi-field
        if script and len(script) > 50:
            print(f"   🎙️ Using Narrative AI Script for: {title[:50]}...")
            text_to_read = script
        else:
            print(f"   📜 Using Field Fallback for: {title[:50]}...")
            try:
                key_details = json.loads(details_json) if details_json else []
            except (json.JSONDecodeError, ValueError, TypeError):
                key_details = []
            key_details_text = ". ".join(key_details)
            text_to_read = (
                f"Intelligence from DailyAIWire dot news. "
                f"Headline: {title}. "
                f"The Gist: {gist}. "
                f"Why It Matters: {matters}. "
                f"Optimistic Outlook: {bull}. "
                f"Risk Factors: {bear}. "
                f"Key Details: {key_details_text}. "
            )
        
        male, female = audio_gen.generate_audio_reads(slug, text_to_read)
        
        if male:
            cursor.execute(
                'UPDATE articles SET audio_male = ?, audio_female = ? WHERE slug = ?',
                (male, female or existing_female, slug)
            )
            conn.commit()
            print(f"✅ Generated and committed audio for: {art[1][:50]}...")
    
    conn.close()
    print(f"Audio generation complete for {len(articles)} articles.")

if __name__ == "__main__":
    # Can be run standalone to backfill audio for articles missing it
    generate_audio_for_recent_articles(limit=20)
