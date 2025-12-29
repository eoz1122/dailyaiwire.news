import sqlite3
import json
import os
import google.generativeai as genai
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

DB_PATH = "news.db"

def get_top_articles(days=7, limit=7):
    """Retrieves the highest importance articles from the last X days."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    threshold_date = (datetime.now() - timedelta(days=days)).isoformat()
    
    cursor.execute('''
        SELECT id, title, gist, importance_score 
        FROM articles 
        WHERE published_at >= ? 
        ORDER BY importance_score DESC, published_at DESC 
        LIMIT ?
    ''', (threshold_date, limit))
    
    articles = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return articles

def generate_newsletter_draft():
    """Synthesizes top articles into a newsletter draft using Gemini."""
    top_articles = get_top_articles()
    
    if not top_articles:
        print("📭 No high-signal articles found this week. Skipping draft generation.")
        return

    print(f"🔬 Synthesizing {len(top_articles)} landmark stories into a weekly wrap...")
    
    articles_context = "\n---\n".join([
        f"TITLE: {a['title']}\nGIST: {a['gist']}\nIMPORTANCE: {a['importance_score']}" 
        for a in top_articles
    ])
    
    prompt = f"""
    You are the Editor-in-Chief of 'Daily AI Wire'. 
    Your task is to write a high-end weekly intelligence briefing for subscribers.
    
    TOP ARTICLES THIS WEEK:
    {articles_context}
    
    TASK:
    1. Write a compelling, curiosity-driven SUBJECT LINE.
    2. Write an 'EDITOR'S NOTE' (2-3 paragraphs) that synthesizes the meta-trend behind these stories. 
       Why was this week significant for AI? Don't just list news; provide a perspective.
    3. For EACH article, write a one-sentence 'WHY IT MATTERS' blurb that is different from its daily gist.
    
    FORMAT: Return a JSON object with:
    {{
      "subject": "The Hooky Subject Line",
      "intro_text": "The full editor's note content with paragraph breaks",
      "article_blurbs": ["Blurb 1", "Blurb 2", ...]
    }}
    
    TONE: Professional, insightful, tech-forward.
    """
    
    try:
        from budget_tracker import BudgetTracker
        budget = BudgetTracker()
        
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(
            prompt, 
            generation_config={"response_mime_type": "application/json"}
        )
        
        # Log Usage
        if hasattr(response, 'usage_metadata'):
            budget.log_request(
                getattr(response.usage_metadata, 'prompt_token_count', 0),
                getattr(response.usage_metadata, 'candidates_token_count', 0),
                category="Weekly Digest"
            )

        data = json.loads(response.text)
        
        # Save to DB
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Serialize article IDs for reference
        article_ids = json.dumps([a['id'] for a in top_articles])
        
        # Build a raw HTML preview (Optional, can be refined in template)
        html_content = f"<h1>{data['subject']}</h1><p>{data['intro_text'].replace('\\n', '<br>')}</p>"
        
        # Default scheduled date: Next Sunday at 18:00
        # If today is Sunday, we might want to schedule for today or next.
        # Simple logic: ensure it is in the future.
        scheduled_date = datetime.now().replace(hour=18, minute=0, second=0, microsecond=0)
        if scheduled_date < datetime.now():
            scheduled_date += timedelta(days=7)

        cursor.execute('''
            INSERT INTO newsletters (subject, intro_text, article_ids, status, scheduled_date)
            VALUES (?, ?, ?, 'DRAFT', ?)
        ''', (data['subject'], data['intro_text'], article_ids, scheduled_date.isoformat()))
        
        conn.commit()
        conn.close()
        
        print(f"✅ Newsletter Draft Created: '{data['subject']}'")
        print(f"📅 Status: DRAFT | Scheduled for: {scheduled_date.strftime('%Y-%m-%d %H:%M')}")
        
    except Exception as e:
        print(f"❌ Failed to generate weekly wrap: {e}")

if __name__ == "__main__":
    generate_newsletter_draft()
