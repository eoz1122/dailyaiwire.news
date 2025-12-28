import sqlite3
import json
import os
import google.generativeai as genai
from audio_generator import AudioGenerator
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def generate_sample():
    conn = sqlite3.connect('news.db')
    cursor = conn.cursor()
    
    # Get the latest article
    cursor.execute('SELECT slug, title, deep_analysis FROM articles ORDER BY id DESC LIMIT 1')
    art = cursor.fetchone()
    if not art:
        print("No articles found.")
        return
    
    slug, title, analysis = art
    print(f"Generating sample for: {title}")
    
    # 1. Generate Narrative Script
    model = genai.GenerativeModel('gemini-2.5-flash')
    prompt = f"Create a 1-minute professional news narrative script (approx 150 words). MUST START with: 'Intelligence from DailyAIWire dot news.' based on this analysis: {analysis[:3000]}. Use smooth transitions, look authoritative, and conclude with a forward-looking statement."
    
    response = model.generate_content(prompt)
    script = response.text.strip()
    print(f"\n--- SCRIPT ---\n{script}\n--------------\n")
    
    # 2. Update DB
    cursor.execute('UPDATE articles SET narration_script = ?, audio_male = NULL, audio_female = NULL WHERE slug = ?', (script, slug))
    conn.commit()
    conn.close()
    
    # 3. Generate Audio
    audio_gen = AudioGenerator()
    
    # Force delete old files to avoid cache issues
    m_old = f"static/audio/{slug}_male.mp3"
    f_old = f"static/audio/{slug}_female.mp3"
    if os.path.exists(m_old): os.remove(m_old)
    if os.path.exists(f_old): os.remove(f_old)

    male, female = audio_gen.generate_audio_reads(slug, script)
    
    print(f"\n✅ Sample Generated!")
    print(f"Male: {male}")
    print(f"Female: {female}")

if __name__ == "__main__":
    generate_sample()
