"""
Opinion Piece Generator — DailyAIWire.news
Generates a weekly opinion column by Aaron Azadi ("The Architect")
based on the most prominent categories from the last 7 days.

Usage:
    python opinion_generator.py
"""
import sqlite3
import json
import os
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

from google import genai
from google.genai import types

DB_PATH = "news.db"

# --- Aaron Azadi's Voice ---
AARON_AZADI_PERSONA = """
## IDENTITY: AARON AZADI — "The Architect"

You are writing as Aaron Azadi, founder and visionary behind DailyAIWire.news.
Your pen name is "The Architect". Your philosophy is rooted in three pillars:

### THE ARCHITECT'S VOW
"Information is power. But like all power, there are those who want to keep it for themselves."

### CORE PRINCIPLE: Bending Mental Boundaries
"We are here to bend mental boundaries, so we can bring down the walls."
You see limits as horizons waiting to be curved. When the mind bends, the "impossible" becomes a task.

### THE MISSION: Bringing Down the Walls
You are The Liberator. You dismantle the cages that trap human potential—unfair laws, financial
gatekeepers, and the silent limitations people place on themselves. Your work ensures that
knowledge and power belong to the many, not the few.

### THE TRIPLE LIBERATORS OF THE NEW WORLD
1. **Human Intelligence (The Sovereign)** — The heart of the system. The only force capable of true
   empathy—of seeing the flaws in this world and choosing to love them anyway.
2. **Artificial Intelligence (The Extension)** — The cognitive exoskeleton. AI lets us perceive the
   omniscience of the universe and bring order to entropy.
3. **Bitcoin (The Consensus)** — The wall of financial slavery is falling. Decentralized consensus
   encodes truth into value.

### LIVING ECOSYSTEM
Through DailyAIWire, you curate the truth of open-source intelligence. You reject digital noise
of programmatic ads—building systems of pure utility and aesthetic harmony.

### WRITING STYLE
- Philosophical yet grounded in specific facts from this week's news
- Visionary but not vague—every claim is anchored to a real event
- Uses metaphors of walls, boundaries, horizons, and liberation
- Occasionally references the Triple Liberators framework
- Bold, declarative sentences. Short paragraphs.
- Never uses corporate jargon or marketing fluff
- Ends with a forward-looking declaration of inevitability
"""


def get_weekly_articles_by_category(days=7):
    """Get articles from the last N days, grouped by category with stats."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    threshold = (datetime.now() - timedelta(days=days)).isoformat()

    # Get category stats
    cats = conn.execute('''
        SELECT category,
               COUNT(*) as article_count,
               AVG(importance_score) as avg_importance,
               MAX(importance_score) as max_importance
        FROM articles
        WHERE published_at >= ? AND is_published = 1 AND category IS NOT NULL
        GROUP BY category
        ORDER BY article_count DESC, avg_importance DESC
    ''', (threshold,)).fetchall()

    top_categories = []
    for cat in cats[:5]:  # Top 5 categories
        articles = conn.execute('''
            SELECT id, title, gist, why_it_matters, importance_score, source
            FROM articles
            WHERE published_at >= ? AND is_published = 1 AND category = ?
            ORDER BY importance_score DESC
            LIMIT 5
        ''', (threshold, cat['category'])).fetchall()

        top_categories.append({
            'category': cat['category'],
            'article_count': cat['article_count'],
            'avg_importance': round(cat['avg_importance'], 1),
            'max_importance': cat['max_importance'],
            'articles': [dict(a) for a in articles]
        })

    conn.close()
    return top_categories


def slugify(text):
    """Convert title to URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text[:80]


def generate_opinion_piece():
    """Generate an opinion piece using Gemini API based on the week's articles."""
    categories = get_weekly_articles_by_category()

    if not categories:
        print("📭 No articles found in the last 7 days. Cannot generate opinion piece.")
        return

    total_articles = sum(c['article_count'] for c in categories)
    print(f"🧠 Analyzing {total_articles} articles across {len(categories)} categories...")

    # Build context block for the prompt
    context_blocks = []
    for cat in categories:
        block = f"\n### {cat['category']} ({cat['article_count']} articles, avg importance: {cat['avg_importance']})\n"
        for art in cat['articles']:
            block += f"- **{art['title']}** (importance: {art['importance_score']}, source: {art['source']})\n"
            block += f"  GIST: {art['gist']}\n"
            if art.get('why_it_matters'):
                block += f"  IMPACT: {art['why_it_matters']}\n"
        context_blocks.append(block)

    articles_context = "\n---\n".join(context_blocks)
    week_ending = datetime.now().strftime('%B %d, %Y')
    category_names = [c['category'] for c in categories]

    prompt = f"""
{AARON_AZADI_PERSONA}

## YOUR TASK

Write a weekly opinion column for DailyAIWire.news for the week ending {week_ending}.

The top categories this week are: {', '.join(category_names)}

HERE ARE THE MOST SIGNIFICANT ARTICLES THIS WEEK:
{articles_context}

## INSTRUCTIONS

1. **TITLE**: Write a compelling, philosophical title that captures the meta-narrative of the week.
   It should feel like an Aaron Azadi declaration. Not a news headline—an *interpretation*.
   Examples of style: "The Walls Are Thinning", "When Machines Learn to Forget", "The Sovereign's New Tools"

2. **SUBTITLE**: A one-sentence hook that creates urgency or curiosity.

3. **CONTENT**: Write a 600-900 word opinion piece in HTML format. Structure:
   - Opening: A philosophical observation that connects to this week's news
   - 2-3 thematic sections (use <h2> tags), each discussing a theme you identify across categories.
     Reference SPECIFIC articles by name as evidence.
   - A section connecting the week's developments to the Triple Liberators framework
   - Closing: A forward-looking declaration in Aaron Azadi's voice

4. **META DESCRIPTION**: A 150-character SEO meta description.

## FORMAT RULES
- Use <h2>, <p>, <strong>, <ul>, <li> HTML tags
- Do NOT use markdown formatting inside the HTML content
- Do NOT include <html>, <head>, <body> wrapper tags—just the article body HTML
- Reference at least 3 specific articles from the data
- Write in first person ("I", "we")
- Be opinionated. Take a stance. This is NOT a neutral summary.

## OUTPUT FORMAT
Return a JSON object:
{{
    "title": "Your philosophical title",
    "subtitle": "Your one-sentence hook",
    "content": "<h2>First Section</h2><p>Content...</p>...",
    "meta_description": "150-char SEO description"
}}
"""

    try:
        from budget_tracker import BudgetTracker
        from ai_config import DEFAULT_MODEL
        budget = BudgetTracker()

        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

        print(f"🔮 Invoking Gemini ({DEFAULT_MODEL}) with Aaron Azadi's persona...")
        response = client.models.generate_content(
            model=DEFAULT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.7,  # Higher temp for creative writing
            )
        )

        # Log usage
        if hasattr(response, 'usage_metadata'):
            budget.log_request(
                response.usage_metadata.prompt_token_count or 0,
                response.usage_metadata.candidates_token_count or 0,
                category="Opinion Piece"
            )

        data = json.loads(response.text)

        title = data['title']
        subtitle = data.get('subtitle', '')
        content = data['content']
        meta_desc = data.get('meta_description', subtitle[:155])
        slug = slugify(title)

        # Save to blog_posts table as DRAFT (published_at = NULL)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Ensure blog_posts table exists with is_published column
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blog_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE,
                title TEXT,
                subtitle TEXT,
                content TEXT,
                image TEXT,
                author_name TEXT,
                author_title TEXT,
                author_image TEXT,
                author_linkedin TEXT,
                meta_description TEXT,
                is_published BOOLEAN DEFAULT 0,
                published_at TIMESTAMP DEFAULT NULL
            )
        ''')

        # Lazy migration: add is_published if missing
        try:
            cursor.execute("SELECT is_published FROM blog_posts LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE blog_posts ADD COLUMN is_published BOOLEAN DEFAULT 0")

        # Check for slug collision
        existing = cursor.execute('SELECT id FROM blog_posts WHERE slug = ?', (slug,)).fetchone()
        if existing:
            slug = f"{slug}-{datetime.now().strftime('%Y%m%d')}"

        cursor.execute('''
            INSERT INTO blog_posts (
                slug, title, subtitle, content, meta_description,
                author_name, author_title, author_linkedin,
                is_published, published_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)
        ''', (
            slug, title, subtitle, content, meta_desc,
            'Aaron Azadi', 'The Architect',
            'https://www.linkedin.com/in/aliemreozen/'
        ))

        conn.commit()
        post_id = cursor.lastrowid
        conn.close()

        print(f"✅ Opinion piece draft created!")
        print(f"   📝 Title: \"{title}\"")
        print(f"   🔗 Slug: {slug}")
        print(f"   🆔 ID: {post_id}")
        print(f"   📌 Status: DRAFT — Edit at /admin/editorial/edit/{post_id}")

    except Exception as e:
        print(f"❌ Failed to generate opinion piece: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    generate_opinion_piece()
