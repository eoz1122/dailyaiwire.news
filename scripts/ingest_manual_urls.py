
import sqlite3
import trafilatura
import google.generativeai as genai
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from slugify import slugify

# Load environment variables
load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

DB_PATH = "news.db"

def analyze_article(content, url):
    """Uses Gemini to generate title, summary, key details, bull/bear cases etc."""
    model = genai.GenerativeModel("gemini-2.0-flash")
    
    prompt = f"""
    You are an elite Tech Investment Analyst. Analyze the following article and extract deep intelligence.
    
    URL: {url}
    CONTENT:
    {content[:20000]} 
    
    Return a JSON object with the following fields:
    - title: A catchy, news-style headline (max 80 chars).
    - category: Choose one [AI Agents, Hardware, Blockchain, Video, Industry].
    - gist: A 2-sentence summary of what this is (Executive Brief).
    - why_it_matters: Why is this significant for the future of AI/Tech? (1 sentence).
    - key_details: A list of 3-4 bullet points extracted from the text (Technical Specs/Facts).
    - deep_analysis: A 2-paragraph coherent analysis of the technology and its ecosystem impact.
    - bull_case: A paragraph explaining the optimistic outlook: Why could this be huge? What problem does it solve effectively? (Be specific).
    - bear_case: A paragraph explaining the risks/challenges: What could go wrong? Is it scalable? Is there competition?
    - thought_provoking_question: A question to engage readers/investors on social media.
    - hashtags: A list of 3-5 relevant hashtags (e.g. #AI, #RustChain, #DePIN).
    
    JSON Output:
    """
    
    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        return json.loads(response.text)
    except Exception as e:
        print(f"Error analyzing with AI: {e}")
        return None

def ingest_url(url, publish_date):
    print(f"\\nProcessing: {url}")
    
    # 1. DELETE if exists (Force Re-ingest to update content/date)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM articles WHERE source_url = ?", (url,))
    if cursor.rowcount > 0:
        print("  -> Removed existing entry to force update.")
    conn.commit()

    # 2. Scrape Content
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        print("  -> Failed to download URL.")
        conn.close()
        return
        
    text_content = trafilatura.extract(downloaded)
    if not text_content:
        print("  -> Failed to extract text content.")
        conn.close()
        return
        
    print(f"  -> Extracted {len(text_content)} characters. Analyzing...")
    
    # 3. Analyze with AI
    data = analyze_article(text_content, url)
    if not data:
        print("  -> AI analysis failed.")
        conn.close()
        return
        
    # 4. Insert into DB
    slug = slugify(data['title']) + "-" + datetime.now().strftime("%H%M")
    
    try:
        cursor.execute('''
            INSERT INTO articles (
                slug, title, image, category, gist, why_it_matters, key_details, 
                deep_analysis, bull_case, bear_case, source, source_url, full_json, published_at, 
                thought_provoking_question, hashtags, importance_score, is_published, shared_on_x
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        ''', (
            slug,
            data['title'],
            "https://bottube.ai/assets/images/logo.png", # Fallback
            data['category'],
            data['gist'],
            data['why_it_matters'],
            json.dumps(data['key_details']),
            data['deep_analysis'],
            data.get('bull_case', 'Analysis pending...'),
            data.get('bear_case', 'Analysis pending...'),
            "Bottube Intelligence",
            url,
            json.dumps(data),
            publish_date.isoformat(),
            data['thought_provoking_question'],
            json.dumps(data['hashtags']),
            90, # Very High Importance
            1   # Auto-Publish so bots pick it up
        ))
        conn.commit()
        print(f"  -> SUCCESS! Saved as '{data['title']}'")
        print(f"  -> Scheduled for: {publish_date.strftime('%Y-%m-%d %H:%M')}")
    except Exception as e:
        print(f"  -> Database insertion failed: {e}")
    finally:
        conn.close()

def main():
    urls = [
        "https://bottube.ai/blog/what-is-bottube",
        "https://bottube.ai/blog/rustchain-proof-of-antiquity",
        "https://bottube.ai/blog/elyan-labs-ecosystem"
    ]
    
    # DRIP SCHEDULE LOGIC
    # Start: Now (or Tomorrow morning)
    # Interval: 2 days
    
    start_date = datetime.now() + timedelta(minutes=5) # Start almost immediately for the first one
    
    print(f"Starting Intelligent Ingestion of {len(urls)} URLs with Drip Schedule...")
    
    for i, url in enumerate(urls):
        # Schedule: 0 -> Now, 1 -> +2 days, 2 -> +4 days
        schedule_time = start_date + timedelta(days=i*2)
        ingest_url(url, schedule_time)
        
    print("\\nDone. Feeds updated.")

if __name__ == "__main__":
    main()
