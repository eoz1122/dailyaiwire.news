import sqlite3
import json
import os
from google import genai
from google.genai import types
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Gemini
# client = genai.Client(api_key=os.getenv("GEMINI_API_KEY")) 
# We initialize client inside function or global. Global is fine.
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

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
        WHERE published_at >= ? AND is_published = 1
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
        f"ID: {a['id']}\nTITLE: {a['title']}\nGIST: {a['gist']}\nIMPORTANCE: {a['importance_score']}" 
        for a in top_articles
    ])
    
    week_ending = datetime.now().strftime('%B %d, %Y')
    
    prompt = f"""
    You are the Editor-in-Chief of 'Daily AI Wire'. 
    Your task is to write a high-end weekly intelligence briefing for subscribers.
    This is the AI Weekly Wrap for the week ending {week_ending}.
    
    TOP ARTICLES THIS WEEK:
    {articles_context}
    
    TASK:
    1. Write a compelling, curiosity-driven SUBJECT LINE for this week's newsletter.
       - The subject should reference specific themes from THIS week's stories.
       - Format: "AI Weekly Wrap: [Specific Theme from Articles]"
       - Do NOT use generic/abstract words like "Orbital", "Trajectory", "Nexus", "Paradigm", "Quantum Leap".
       - Be direct and descriptive about what happened this week.
    2. Write an 'EDITOR'S NOTE' (2-3 paragraphs) that synthesizes the meta-trend behind these stories. 
       Why was this week significant for AI? Don't just list news; provide a perspective.
    3. For EACH article, write a one-sentence 'WHY IT MATTERS' blurb that is different from its daily gist.
       Return these in a dictionary mapped by their ID.
    
    FORMAT: Return a JSON object with:
    {{
      "subject": "AI Weekly Wrap: [Your Specific Theme]",
      "intro_text": "The full editor's note content with paragraph breaks",
      "article_blurbs": {{
          "ID_FROM_CONTEXT": "The Why It Matters blurb...",
          "Another_ID": "..."
      }}
    }}
    
    TONE: Professional, insightful, tech-forward.
    """
    
    try:
        from budget_tracker import BudgetTracker
        from ai_config import DEFAULT_MODEL
        budget = BudgetTracker()
        
        # New Client API Call
        response = client.models.generate_content(
            model=DEFAULT_MODEL, 
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        # Log Usage
        if hasattr(response, 'usage_metadata'):
            budget.log_request(
                response.usage_metadata.prompt_token_count or 0,
                response.usage_metadata.candidates_token_count or 0,
                category="Weekly Digest"
            )

        data = json.loads(response.text)
        
        # Save to DB
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Serialize article IDs for reference
        article_ids = json.dumps([a['id'] for a in top_articles])
        
        # Serialize Metadata (Why It Matters)
        # Ensure keys are strings for JSON
        article_metadata = json.dumps(data.get('article_blurbs', {}))
        
        # Schedule for TODAY at 18:00 — newsletter covers last 7 days and should
        # be ready for immediate review and sending, not queued for next Sunday.
        scheduled_date = datetime.now().replace(hour=18, minute=0, second=0, microsecond=0)

        cursor.execute('''
            INSERT INTO newsletters (subject, intro_text, article_ids, article_metadata, status, scheduled_date)
            VALUES (?, ?, ?, ?, 'DRAFT', ?)
        ''', (data['subject'], data['intro_text'], article_ids, article_metadata, scheduled_date.isoformat()))
        
        conn.commit()
        conn.close()
        
        print(f"✅ Newsletter Draft Created: '{data['subject']}'")
        print(f"📅 Status: DRAFT | Scheduled for: {scheduled_date.strftime('%Y-%m-%d %H:%M')}")
        
    except Exception as e:
        print(f"❌ Failed to generate weekly wrap: {e}")

if __name__ == "__main__":
    generate_newsletter_draft()
