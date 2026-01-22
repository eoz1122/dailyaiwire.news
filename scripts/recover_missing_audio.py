
import sqlite3
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audio_generator import AudioGenerator

DB_PATH = "news.db"
AUDIO_DIR = Path("static/audio")

def recover_audio():
    print("🚑 Starting Audio Recovery Protocol...")
    
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    import json

    # Get all articles (removing restrictive WHERE clause)
    try:
        articles = cursor.execute('''
            SELECT id, slug, title, narration_script, audio_male, audio_female,
                   gist, why_it_matters, bull_case, bear_case, key_details
            FROM articles 
            ORDER BY published_at DESC
        ''').fetchall()
    except Exception as e:
        print(f"❌ Error querying database: {e}")
        return

    print(f"📋 Found {len(articles)} total articles. Checking coverage...")
    
    generator = AudioGenerator()
    if not generator.client:
        print("❌ AudioGenerator failed to initialize (check credentials). Aborting.")
        return

    recovered_count = 0
    
    for art in articles:
        slug = art['slug']
        if not slug: continue

        # Determining Text Context
        script = art['narration_script']
        text_to_read = ""

        if script and len(script) > 50:
            text_to_read = script
        else:
            # Fallback logic mirroring app.py
            try:
                details = json.loads(art['key_details']) if art['key_details'] else []
            except:
                details = []
            details_text = ". ".join(details)
            
            # Simple check to ensure we have *some* content
            if art['title']:
                text_to_read = (
                    f"Intelligence from DailyAIWire dot news. "
                    f"Headline: {art['title']}. "
                    f"The Gist: {art['gist'] or ''}. "
                    f"Why It Matters: {art['why_it_matters'] or ''}. "
                    f"Optimistic Outlook: {art['bull_case'] or ''}. "
                    f"Risk Factors: {art['bear_case'] or ''}. "
                    f"Key Details: {details_text}. "
                )

        if not text_to_read or len(text_to_read) < 50:
            # print(f"   ⏩ Skipping {slug}: Insufficient content.")
            continue
        
        # Expected paths
        male_file = AUDIO_DIR / f"{slug}_male.mp3"
        female_file = AUDIO_DIR / f"{slug}_female.mp3"
        
        needs_regen = False
        
        if not male_file.exists():
            print(f"⚠️ Missing Male Audio for: {art['title']}")
            needs_regen = True
            
        if not female_file.exists():
            print(f"⚠️ Missing Female Audio for: {art['title']}")
            needs_regen = True
            
        if needs_regen:
            print(f"   🔄 Regenerating audio for: {slug}...")
            try:
                # Generate
                m_path, f_path = generator.generate_audio_reads(slug, text_to_read)
                
                if m_path and f_path:
                    # Update DB just in case paths were wrong or null
                    cursor.execute('''
                        UPDATE articles 
                        SET audio_male = ?, audio_female = ? 
                        WHERE id = ?
                    ''', (m_path, f_path, art['id']))
                    conn.commit()
                    print(f"   ✅ Recovered and Saved: {slug}")
                    recovered_count += 1
                else:
                    print(f"   ❌ Generation failed for {slug}")
            except Exception as e:
                print(f"   ❌ Exception during generation: {e}")
        else:
            # print(f"   OK: {slug}")
            pass

    conn.close()
    print(f"\n🎉 Recovery Complete. {recovered_count} articles restored.")

if __name__ == "__main__":
    recover_audio()
