import os
import sqlite3
import json
import time
import uuid
import feedparser
import trafilatura
import google.generativeai as genai
from slugify import slugify
from dotenv import load_dotenv
from typing import List, Dict, Tuple
from bs4 import BeautifulSoup

from social_distributor import SocialDistributor

# Load environment variables
load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Initialize Budget Tracker
from budget_tracker import BudgetTracker
MONTHLY_BUDGET_USD = float(os.getenv("MONTHLY_BUDGET_USD", "10.0"))
budget = BudgetTracker(monthly_cap_usd=MONTHLY_BUDGET_USD)

# Database setup
DB_PATH = "news.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE,
            title TEXT,
            image TEXT,
            category TEXT,
            gist TEXT,
            why_it_matters TEXT,
            bull_case TEXT,
            bear_case TEXT,
            key_details TEXT, -- Stored as JSON string
            eli5 TEXT,
            deep_analysis TEXT,
            source TEXT,
            source_url TEXT UNIQUE,
            full_json TEXT,
            published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blog_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE,
            title TEXT,
            subtitle TEXT,
            content TEXT,
            image TEXT,
            published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_source_url ON articles(source_url)')
    conn.commit()
    conn.close()

def is_spam(title: str) -> bool:
    spam_keywords = ["crypto", "bitcoin", "deal", "course", "vpn", "trading"]
    title_lower = title.lower()
    return any(keyword in title_lower for keyword in spam_keywords)

def fetch_all_sources() -> List[Dict]:
    """Fetches news from multiple specific AI feeds and Google News."""
    sources = [
        ("The Verge", "https://www.theverge.com/rss/artificial-intelligence/index.xml"),
        ("TechCrunch", "https://techcrunch.com/category/artificial-intelligence/feed/"),
        ("Wired", "https://www.wired.com/feed/tag/ai/latest/rss"),
        ("Google News", "https://news.google.com/rss/search?q=Artificial+Intelligence+when:1d&hl=en-US&gl=US&ceid=US:en")
    ]
    
    unique_articles = {}
    
    for source_name, url in sources:
        print(f"Fetching from {source_name}...")
        feed = feedparser.parse(url)
        
        # Limit Google News to 5 articles to avoid noise and high token usage
        entries = feed.entries[:5] if source_name == "Google News" else feed.entries
        
        for entry in entries:
            if is_spam(entry.title):
                continue
            
            # Clean title
            title = entry.title
            if " - " in title and source_name == "Google News":
                title = title.rsplit(" - ", 1)[0]
                
            link = entry.link
            if link not in unique_articles:
                # Normalize date to ISO format for frontend comparison
                from datetime import datetime
                pub_date = getattr(entry, 'published_parsed', None)
                if pub_date:
                    iso_date = datetime(*pub_date[:6]).isoformat()
                else:
                    iso_date = datetime.now().isoformat()
                    
                unique_articles[link] = {
                    "title": title,
                    "source": source_name,
                    "link": link,
                    "published": iso_date
                }
    
    return list(unique_articles.values())

def extract_content(url: str) -> Tuple[str, str]:
    """Extracts text content and social image from a URL with multiple fallbacks."""
    downloaded = trafilatura.fetch_url(url)
    if downloaded:
        content = trafilatura.extract(downloaded)
        
        # Extract Image with multiple fallbacks
        soup = BeautifulSoup(downloaded, 'html.parser')
        og_image = ""
        
        # 1. Try OG:Image
        img_tag = soup.find("meta", property="og:image")
        if img_tag:
            og_image = img_tag.get("content", "")
            
        # 2. Try Twitter:Image
        if not og_image:
            twitter_tag = soup.find("meta", name="twitter:image")
            if twitter_tag:
                og_image = twitter_tag.get("content", "")

        # 3. Try broad image search if metadata failed
        if not og_image:
            for img in soup.find_all('img', src=True):
                src = img['src']
                if src.startswith('http') and not any(x in src.lower() for x in ['pixel', 'logo', 'icon', 'sprite', 'ad']):
                    og_image = src
                    break

        # 4. Defensive check: Avoid small icons or tracking pixels
        if og_image and any(x in og_image.lower() for x in ['pixel', 'logo', 'icon', 'sprite', '1x1', 'tracking']):
            og_image = ""

        # 4. Resolve relative URLs
        if og_image and not og_image.startswith('http'):
            from urllib.parse import urljoin
            og_image = urljoin(url, og_image)
            
        return (content if content else ""), og_image
    return "", ""

def process_batch(batch: List[Dict]):
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        system_instruction=(
            "Identity: You are the Lead Editor and Chief Content Strategist for DailyAIWire.news. "
            "You are renowned for turning dense technical whitepapers into captivating, high-signal intelligence for industry leaders.\n"
            "Mandate: Use the optimized capabilities of Gemini 1.5 Flash for high-throughput intelligence analysis.\n"
            "Editorial Standards:\n"
            "* Headlines: Create high-impact, H1-worthy headlines that are factual yet 'click-magnetic'.\n"
            "* The Hook: Start with a punchy opening sentence that contextualizes the news immediately.\n"
            "* Tone: Authoritative, tech-forward, and urgent. Avoid corporate fluff and emojis.\n"
            "* Content: Focus on extraction of hard facts, expert quotes, and strategic implications.\n"
            "* Formatting: Return PLAIN TEXT for all fields. DO NOT use markdown, bolding (**), or italics in the string values."
        )
    )

    batch_input = []
    for idx, item in enumerate(batch):
        content, og_image = extract_content(item['link'])
        item['scraped_image'] = og_image  # Attach to batch item for save_to_db
        
        # Robust context: If scraper failed, use the title/rss snippet to provide at least some signal
        analysis_context = content[:3000] if content and len(content) > 100 else item['title']
        batch_input.append(f"ARTICLE ID: {idx}\nSOURCE TITLE: {item['title']}\nSOURCE CONTENT: {analysis_context}")

    prompt = (
        f"Process the following {len(batch)} news articles and return a JSON list of objects matching this structure:\n"
        "[\n"
        "  {\n"
        "    \"batch_id\": 0,\n"
        "    \"headline\": \"Clicky Title\",\n"
        "    \"seo_slug\": \"url-safe-slug\",\n"
        "    \"image_query\": \"A concise keyword for an Unsplash image (e.g., 'robot arm', 'server farm')\",\n"
        "    \"category\": \"Strictly choose ONE from: ['LLMs', 'Robotics', 'Business', 'Tools', 'Policy', 'Science', 'Security', 'Society']\",\n"
        "    \"gist\": \"1-2 sentence bold summary\",\n"
        "    \"key_details\": [\"Bullet 1\", \"Bullet 2\", \"Bullet 3\"],\n"
        "    \"why_it_matters\": \"Brief insight on impact\",\n"
        "    \"optimistic_outlook\": \"Upside analysis and positive potential\",\n"
        "    \"pessimistic_outlook\": \"Downside/Risk analysis and critical concerns\",\n"
        "    \"eli5\": \"Explain like I'm 5 years old version\",\n"
        "    \"deep_analysis\": \"A comprehensive summary of at least 400 words covering the nuances, background, and expert opinions mentioned in the source.\"\n"
        "  }\n"
        "]\n\n"
        "ARTICLES TO PROCESS:\n" + "\n---\n".join(batch_input)
    )

    try:
        # Budget check before making API call
        estimated_tokens = len(prompt) // 4 + 2000
        if not budget.can_make_request(estimated_tokens):
            print("⛔ Skipping batch due to budget cap. Run will resume next month.")
            return []
        
        # Retry logic for quota issues (429)
        for attempt in range(5):
            try:
                response = model.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
                
                # Log token usage for budget tracking
                if hasattr(response, 'usage_metadata'):
                    input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0)
                    output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0)
                    budget.log_request(input_tokens, output_tokens)
                
                # Cleanup: Strip markdown bolding if Gemini ignored instructions
                raw_json = response.text
                clean_json_str = raw_json.replace('**', '')
                return json.loads(clean_json_str)
            except Exception as e:
                if "429" in str(e):
                    # Multiplier based on attempt to survive the initial billing sync
                    wait_time = (attempt + 1) * 45
                    print(f"Quota hit! Waiting {wait_time}s and retrying...")
                    time.sleep(wait_time)
                    continue
                print(f"API Error: {e}")
                time.sleep(10)
                continue
        return []
    except Exception as e:
        print(f"Error processing batch: {e}")
        return []

def save_to_db(processed_articles: List[Dict], original_batch: List[Dict]):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    distributor = SocialDistributor()
    
    for art in processed_articles:
        # Skip articles where AI failed to find content
        gist = str(art.get('gist', '')).lower()
        impact = str(art.get('why_it_matters', '')).lower()
        headline = str(art.get('headline', '')).lower()
        
        if "source content missing" in gist or "source content missing" in impact or "source content missing" in headline:
            print(f"⚠️ Skipping '{art.get('headline')}' due to missing content signal.")
            continue

        # Determine the article identifier (Gemini's provided slug or derived from title)
        lookup_slug = art.get('seo_slug') or slugify(art.get('headline', ''))
        
        # Find original source info (link, published date, scraped image)
        batch_id = art.get('batch_id')
        if batch_id is not None and 0 <= batch_id < len(original_batch):
            original = original_batch[batch_id]
        else:
            # Fallback to slug-based find
            source_map = {slugify(it['title']): it for it in original_batch}
            original = source_map.get(lookup_slug, original_batch[0])
        
        # 1. Prioritize scraped image (if it's a real external URL)
        image_url = original.get('scraped_image')
        
        # 2. Use image_query if scraped image is missing or is a generic placeholder/blocked tracker
        source_name = original.get('source', '')
        is_generic = not image_url or not image_url.startswith('http') or any(x in image_url.lower() for x in ["google", "placeholder", "logo", "icon", "pixel"])
        
        # KILL SWITCH: If it's Google News and has no real unique image, skip it entirely
        if source_name == "Google News" and is_generic:
            print(f"⚠️ Skipping Google News article '{art.get('headline')}' - No unique image found.")
            continue

        if is_generic:
            cat = art.get('category', 'Tools')
            cat_map = {
                "LLMs": "https://images.unsplash.com/photo-1677442136019-21780ecad995",
                "Robotics": "https://images.unsplash.com/photo-1485827404703-89b55fcc595e",
                "Business": "https://images.unsplash.com/photo-1507679799987-c73779587ccf",
                "Tools": "https://images.unsplash.com/photo-1518770660439-4636190af475",
                "Policy": "https://images.unsplash.com/photo-1450101499163-c8848c66ca85",
                "Science": "https://images.unsplash.com/photo-1532187863486-abf2ad613a00",
                "Security": "https://images.unsplash.com/photo-1550751827-4bd374c3f58b",
                "Society": "https://images.unsplash.com/photo-1529107386315-e1a2ed48a620"
            }
            base_url = cat_map.get(cat, cat_map["Tools"])
            image_url = f"{base_url}?auto=format&fit=crop&q=80&w=1200"

        # 3. Robust Slug Generation (Fixes 'None' slugs)
        final_slug = art.get('seo_slug')
        if not final_slug or final_slug == "None" or len(final_slug) < 2:
            final_slug = slugify(art.get('headline', ''))
        if not final_slug:
            final_slug = slugify(original.get('title', 'article'))
        if not final_slug:
            final_slug = f"article-{uuid.uuid4().hex[:8]}"
        
        # Important: Sync the slug so the social distributor uses the same one
        art['seo_slug'] = final_slug

        try:
            cursor.execute('''
                INSERT OR REPLACE INTO articles 
                (slug, title, image, category, gist, why_it_matters, bull_case, bear_case, key_details, eli5, deep_analysis, source, source_url, full_json, published_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                final_slug,
                art.get('headline'),
                image_url,
                art.get('category'),
                art.get('gist'),
                art.get('why_it_matters'),
                art.get('optimistic_outlook'),
                art.get('pessimistic_outlook'),
                json.dumps(art.get('key_details', [])),
                art.get('eli5'),
                art.get('deep_analysis'),
                original.get('source'),
                original.get('link'),
                json.dumps(art),
                original.get('published')
            ))
            
            # Post to Social Media Channels
            distributor.distribute(art)
            
        except Exception as e:
            print(f"Error saving article {art.get('headline')}: {e}")
            
    conn.commit()
    conn.close()

def main():
    print("Initializing Database...")
    init_db()
    
    print("Aggregating Intelligence from Multiple Sources...")
    raw_articles = fetch_all_sources()
    
    # Filter out articles we've already processed
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT source_url FROM articles')
    existing_urls = {row[0] for row in cursor.fetchall()}
    conn.close()
    
    new_articles = [art for art in raw_articles if art['link'] not in existing_urls]
    print(f"Total Unique Articles Found: {len(raw_articles)}")
    print(f"New Articles to Process: {len(new_articles)}")
    
    if not new_articles:
        print("Everything up to date. No new intelligence to process.")
        return

    # Process in batches of 2 for maximum stability during import
    batch_size = 2
    for i in range(0, len(new_articles), batch_size):
        batch = new_articles[i:i + batch_size]
        print(f"Processing batch {i//batch_size + 1} ({len(batch)} articles)...")
        processed = process_batch(batch)
        if processed:
            save_to_db(processed, batch)
            print(f"Saved {len(processed)} articles from batch.")
        
        # Sleep 15s between batches to avoid rate limits
        time.sleep(15)

def main_loop():
    """Runs the main fetcher in a continuous loop every 4 hours."""
    print("🚀 Starting DailyAIWire Intelligence Service...")
    while True:
        try:
            main()
            # 4 hours = 14400 seconds
            next_run = time.time() + 14400
            print(f"✅ Run complete. Sleeping for 4 hours. Next run at {time.strftime('%H:%M:%S', time.localtime(next_run))}")
            time.sleep(14400)
        except KeyboardInterrupt:
            print("\n👋 Intelligence Service stopped by user.")
            break
        except Exception as e:
            print(f"❌ Error in main loop: {e}")
            print("🔄 Retrying in 5 minutes...")
            time.sleep(300)

if __name__ == "__main__":
    import sys
    if "--loop" in sys.argv:
        main_loop()
    else:
        main()
