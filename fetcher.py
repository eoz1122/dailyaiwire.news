import os
import sqlite3
import json
import time
import uuid
import random
import feedparser
import difflib
import trafilatura
import re
from remove_duplicates import get_jaccard_sim, remove_duplicates
import google.generativeai as genai
from slugify import slugify
from dotenv import load_dotenv
from typing import List, Dict, Tuple
from bs4 import BeautifulSoup

from social_distributor import SocialDistributor
from audio_generator import AudioGenerator
from datetime import datetime, timedelta

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
            published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            audio_male TEXT, -- Path to generated male audio
            audio_female TEXT, -- Path to generated female audio
            narration_script TEXT, -- AI-generated script for 1-minute read
            shared_on_x BOOLEAN DEFAULT 0,
            shared_at TIMESTAMP
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
            author_name TEXT,
            author_title TEXT,
            author_image TEXT,
            author_linkedin TEXT,
            meta_description TEXT,
            published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS social_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT,
            headline TEXT,
            status TEXT DEFAULT 'PENDING', -- PENDING, SENT, FAILED
            scheduled_time TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_source_url ON articles(source_url)')
    
    # Add original_author if it doesn't exist
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN original_author TEXT")
    except sqlite3.OperationalError:
        pass # Already exists

    # Add narration_script if it doesn't exist
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN narration_script TEXT")
    except sqlite3.OperationalError:
        pass # Already exists

    # Add thought_provoking_question if it doesn't exist
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN thought_provoking_question TEXT")
    except sqlite3.OperationalError:
        pass # Already exists

    # Authors Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS authors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            title TEXT,
            bio TEXT,
            image TEXT,
            linkedin TEXT
        )
    ''')

    # Metadata Table for scan tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def get_last_scan_timestamp() -> datetime:
    """Retrieves the last successful scan timestamp from metadata."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM metadata WHERE key = 'last_scan_timestamp'")
    row = cursor.fetchone()
    conn.close()
    if row:
        return datetime.fromisoformat(row[0])
    # Fallback: 24 hours ago if no record exists
    return datetime.now() - timedelta(hours=24)

def update_last_scan_timestamp(ts: datetime):
    """Updates the last successful scan timestamp in metadata."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_scan_timestamp', ?)", (ts.isoformat(),))
    conn.commit()
    conn.close()

def get_recent_published_titles(hours=36) -> List[str]:
    """Retrieves titles of articles published in the last X hours for deduplication."""
    target_time = datetime.now() - timedelta(hours=hours)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT title FROM articles WHERE published_at > ?", (target_time.isoformat(),))
    titles = [row[0] for row in cursor.fetchall()]
    conn.close()
    return titles

def is_spam(title: str) -> bool:
    spam_keywords = ["crypto", "bitcoin", "deal", "course", "vpn", "trading", "webinar", "sale", "limited time", "bundle", "discount"]
    title_lower = title.lower()
    return any(keyword in title_lower for keyword in spam_keywords)

def is_ignored_source(source_name: str) -> bool:
    """Filters out sources that are too local or irrelevant."""
    blocked = [
        "Kurdistan24", "kurdistan24.net", 
        "Seacoastonline.com", "Pittsburgh Post-Gazette",
        "KERA News", "Oregon Public Broadcasting - OPB"
    ]
    return any(b.lower() in source_name.lower() for b in blocked)

def filter_high_signal_headlines(articles: List[Dict], recent_titles: List[str] = []) -> List[Dict]:
    """Uses Gemini to filter for high-value AI news headlines and exclude duplicates/similar stories."""
    if not articles:
        return []

    print(f"AI Pre-Filtering {len(articles)} headlines for signal quality and deduplication...")
    
    # Bundle headlines for efficient batch checking
    headline_list = "\n".join([f"{idx}: {a['title']}" for idx, a in enumerate(articles)])
    recent_titles_block = "\n".join([f"- {t}" for t in recent_titles]) if recent_titles else "None"
    
    prompt = f"""
    You are an elite AI Intelligence Officer. Your task is to select the TOP 8 MOST NEWSWORTHY and UNIQUE articles.
    
    RECENTLY PUBLISHED TITLES (IGNORE ANY NEW ARTICLES THAT ARE DUPLICATES OR SEMANTICALLY SIMILAR TO THESE):
    {recent_titles_block}
    
    NEW HEADLINES TO ANALYZE (Format: Index: Title):
    {headline_list}
    
    CRITICAL INSTRUCTIONS:
    1. EXCLUDE any article that is the same story as one in the RECENTLY PUBLISHED list, even if the wording is different.
    2. PRIORITIZE major breakthroughs, strategic corporate shifts, and research milestones.
    3. EXCLUDE minor updates, generic tech news, and sponsored content.
    
    Return EXACTLY 8 indices of the most important, non-duplicate articles as a comma-separated list.
    If there are fewer than 8 worthy articles, return only those indices.
    
    Example Input:
    - OpenAI releases Sora API
    - Local coffee shop uses AI for menu
    - DeepMind breakthrough in protein folding
    - Google announces Gemini 2.5
    Example Output: 0, 2, 3
    
    HEADLINES:
    {headline_list}
    """
    
    try:
        model_name = 'gemini-2.5-flash'
        print(f"⚡ using AI Model (Filter): {model_name}")
        
        # Budget Check
        estimated_tokens = len(prompt) // 4 + 500
        from budget_tracker import BudgetTracker
        # Instantiate strictly for this check if not passed (though ideally passed)
        # To avoid circular imports or redefining, we rely on the global 'budget' object if available
        # But 'budget' is defined at module level (line 31), so it's available here.
        if not budget.can_make_request(estimated_tokens):
             print("Skipping filter due to budget.")
             return articles[:8] # Fallback

        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        
        # Log Usage
        if hasattr(response, 'usage_metadata'):
             budget.log_request(
                 getattr(response.usage_metadata, 'prompt_token_count', 0),
                 getattr(response.usage_metadata, 'candidates_token_count', 0),
                 category="Headline Filter"
             )

        text = response.text.replace('Indices:', '').strip()
        indices = [int(i.strip()) for i in text.split(',') if i.strip().isdigit()]
        
        filtered = [articles[i] for i in indices if i < len(articles)]
        print(f"Filtered down to {len(filtered)} high-signal articles.")
        return filtered
    except Exception as e:
        print(f"Headline filtering failed: {e}. Proceeding with all unique articles.")
        return articles

def fetch_all_sources() -> List[Dict]:
    """Fetches news from multiple specific AI feeds and Google News."""
    sources = [
        # // PRIMARY WIRE
        ("The Verge", "https://www.theverge.com/rss/artificial-intelligence/index.xml"),
        ("TechCrunch", "https://techcrunch.com/category/artificial-intelligence/feed/"),
        ("Wired", "https://www.wired.com/feed/tag/ai/latest/rss"),
        ("The Batch", "https://read.deeplearning.ai/the-batch/feed"),
        ("Import AI", "https://importai.substack.com/feed"),
        ("Ben's Bites", "https://bensbites.beehiiv.com/feed"),
        ("DFKI (Germany)", "https://www.dfki.de/en/web/news-media/news/rss"),
        
        # // RESEARCH LABS
        ("OpenAI", "https://openai.com/news/rss"),
        ("DeepMind", "https://deepmind.com/blog/feed/basic/"),
        ("BAIR Blog", "https://bair.berkeley.edu/blog/feed.xml"),
        ("Meta AI (FAIR)", "https://ai.meta.com/blog/rss/"),
        ("Microsoft Research", "https://www.microsoft.com/en-us/research/feed/"),
        ("Anthropic", "https://www.anthropic.com/news/feed"),
        
        # // ENTERPRISE & MARKETS
        ("VentureBeat", "https://venturebeat.com/category/ai/feed/"),
        ("AI Business", "https://aibusiness.com/rss.xml"),
        
        # // DEV TERMINAL & COMMUNITIES
        ("NVIDIA Dev", "https://developer.nvidia.com/blog/feed/"),
        ("ML Mastery", "https://machinelearningmastery.com/blog/feed/"),
        ("Hugging Face", "https://huggingface.co/blog/feed.xml"),
        ("Papers with Code", "https://paperswithcode.com/rss/latest"),
        ("Hacker News (AI)", "https://hnrss.org/newest?q=AI+OR+LLM"),

        # // AGGREGATOR
        ("Google News", "https://news.google.com/rss/search?q=Artificial+Intelligence+when:1d&hl=en-US&gl=US&ceid=US:en")
    ]
    
    unique_articles = {}
    
    # GET STATE: Only fetch articles after last scan
    last_scan = get_last_scan_timestamp()
    print(f"📡 Only scanning news published since: {last_scan.strftime('%Y-%m-%d %H:%M:%S')}")

    for source_name, url in sources:
        print(f"Fetching from {source_name}...")
        try:
            # Fix: Use Browser User-Agent to bypass Cloudflare/Bot blocks on The Verge, VentureBeat, etc.
            feed = feedparser.parse(url, agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            # Limit Google News to 30 articles (AI filter will select the best ones from this larger pool)
            entries = feed.entries[:30] if source_name == "Google News" else feed.entries
            
            skipped_count = 0
            added_count = 0
            for entry in entries:
                if is_spam(entry.title):
                    continue
                
                # Check normalized date
                pub_date_struct = getattr(entry, 'published_parsed', None)
                if pub_date_struct:
                    dt_published = datetime(*pub_date_struct[:6])
                else:
                    dt_published = datetime.now()

                # STATEFUL CHECK: Must be newer than last scan
                if dt_published <= last_scan:
                    skipped_count += 1
                    continue

                title = entry.title
                if " - " in title and source_name == "Google News":
                    title = title.rsplit(" - ", 1)[0]
                    
                link = entry.link
                if link not in unique_articles:
                    real_source = source_name
                    if source_name == "Google News" and hasattr(entry, 'source') and 'title' in entry.source:
                        real_source = entry.source.title

                    # IGNORE LOCAL/BLOCKED SOURCES
                    if is_ignored_source(real_source):
                        continue

                    unique_articles[link] = {
                        "title": title,
                        "source": real_source,
                        "link": link,
                        "published": dt_published.isoformat()
                    }
                    added_count += 1
            
            print(f"   ↳ {len(entries)} entries found. {added_count} new, {skipped_count} skipped (old).")

        except Exception as e:
            print(f"Error fetching {source_name}: {e}")
    
    all_articles = list(unique_articles.values())
    
    if not all_articles:
        print("📭 No new articles found since last scan.")
        return []

    print(f"Found {len(all_articles)} candidates for filtering.")

    # HARD LIMIT: Cap at 100 headlines to save tokens
    if len(all_articles) > 100:
        all_articles = all_articles[:100]

    # ACTIVATE AI FILTERING WITH 36H DUPLICATE AWARENESS
    recent_titles = get_recent_published_titles(hours=36)
    return filter_high_signal_headlines(all_articles, recent_titles)

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
            twitter_tag = soup.find("meta", attrs={"name": "twitter:image"})
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
            
        # 5. Extract Metadata (Author)
        metadata = trafilatura.extract_metadata(downloaded)
        author = metadata.author if metadata else None
            
        return (content if content else ""), og_image, (author if author else "")
    return "", "", ""

def process_batch(batch: List[Dict]):
    model_name = "gemini-2.5-flash"
    print(f"⚡ Analyzing batch with: {model_name}")
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=(
            "Identity: You are the Lead Editor and Chief Content Strategist for DailyAIWire.news. "
            "You are renowned for turning dense technical whitepapers into captivating, high-signal intelligence for industry leaders.\n"
            "Mandate: Use the optimized capabilities of Gemini 2.5 Flash for high-throughput intelligence analysis.\n"
            "Editorial Standards:\n"
            "* LANGUAGE: ALL OUTPUT MUST BE IN ENGLISH. If the source content is in German or another language, TRANSLATE it on the fly.\n"
            "* Headlines: Create high-impact, H1-worthy headlines that are factual yet 'click-magnetic'.\n"
            "* The Hook: Start with a punchy opening sentence that contextualizes the news immediately.\n"
            "* Tone: Authoritative, tech-forward, and urgent. Avoid corporate fluff and emojis.\n"
            "* Content: Focus on extraction of hard facts, expert quotes, and strategic implications.\n"
            "* Formatting: Return PLAIN TEXT for all fields. DO NOT use markdown, bolding (**), or italics. For 'deep_analysis', USE NEWLINES to create paragraph breaks."
        )
    )

    batch_input = []
    for idx, item in enumerate(batch):
        content, og_image, author = extract_content(item['link'])
        item['scraped_image'] = og_image  # Attach to batch item for save_to_db
        item['original_author'] = author
        
        # Robust context: If scraper failed, use the title/rss snippet to provide at least some signal
        analysis_context = content[:3000] if content and len(content) > 100 else item['title']
        batch_input.append(f"ARTICLE ID: {idx}\nSOURCE TITLE: {item['title']} (Ensure Output is English)\nSOURCE CONTENT: {analysis_context}")

    prompt = (
        f"Process the following {len(batch)} news articles and return a JSON list of objects matching this structure:\n"
        "[\n"
        "  {\n"
        "    \"batch_id\": 0,\n"
        "    \"headline\": \"Clicky Title\",\n"
        "    \"seo_slug\": \"url-safe-slug\",\n"
        "    \"image_query\": \"A concise keyword for an Unsplash image (e.g., 'robot arm', 'server farm')\",\n"
        "    \"category\": \"Strictly choose ONE from: ['LLMs', 'Robotics', 'Business', 'Tools', 'Policy', 'Science', 'Security', 'Society', 'Ethics']\",\n"
        "    \"gist\": \"1-2 sentence bold summary\",\n"
        "    \"key_details\": [\"Extract 3-5 HARD DATA POINTS (numbers, dates, specs) ONLY. If the source content is vague or lacks specific metrics, return an empty list []. Do NOT output generic summaries here.\"],\n"
        "    \"why_it_matters\": \"Brief insight on impact (2-3 sentences max)\",\n"
        "    \"optimistic_outlook\": \"Upside analysis in 2-3 sentences. Focus on positive potential and opportunities.\",\n"
        "    \"pessimistic_outlook\": \"Downside/Risk analysis in 2-3 sentences. Focus on concerns and challenges.\",\n"
        "    \"hashtags\": [\"Generate 3-5 relevant hashtags for social media (e.g., #AI, #MachineLearning, #TechNews). Include mix of broad and specific tags.\"],\n"
        "    \"thought_provoking_question\": \"A short, engaging question derived from the article content to spark discussion on social media.\",\n"
        "    \"eli5\": \"Explain like I'm 5 years old version\",\n"
        "    \"deep_analysis\": \"A comprehensive summary of at least 300 words. MUST use multiple paragraphs separated by newlines for better readability. Do not output a single wall of text.\",\n"
        "    \"narration_script\": \"A high-signal, narrative script for a 1-minute audio read (approx 150 words). MUST START with this exact short branding: 'Intelligence from DailyAIWire dot news.' followed by a brief pause. Use smooth transitions (e.g., 'Starting with...', 'Interestingly...', 'Looking ahead...'). Do not use headers. Focus on making it sound like a professional news segment.\"\n"
        "  }\n"
        "]\n\n"
        "ARTICLES TO PROCESS:\n" + "\n---\n".join(batch_input)
    )

    try:
        # Budget check before making API call
        estimated_tokens = len(prompt) // 4 + 2000
        if not budget.can_make_request(estimated_tokens):
            print("Skipping batch due to budget cap. Run will resume next month.")
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
                    budget.log_request(input_tokens, output_tokens, category="Article Analysis")
                
                # Cleanup: Strip markdown blocks if Gemini added them
                raw_json = response.text.strip()
                if raw_json.startswith("```json"):
                    raw_json = re.sub(r'^```json\s*', '', raw_json, flags=re.MULTILINE)
                    raw_json = re.sub(r'\s*```$', '', raw_json, flags=re.MULTILINE)
                
                clean_json_str = raw_json.replace('**', '')
                return json.loads(clean_json_str, strict=False)
            except Exception as e:
                if "429" in str(e):
                    # Multiplier based on attempt to survive the initial billing sync
                    wait_time = (attempt + 1) * 45
                    print(f"Quota hit! Waiting {wait_time}s and retrying...")
                    time.sleep(wait_time)
                    continue
                print(f"API Error ({attempt+1}/5): {e}")
                # Print a snippet of the problematic JSON if it's a parsing error
                if "JSON" in str(e) or "control character" in str(e).lower():
                    print(f"Problematic JSON snippet: {raw_json[:200]}...")
                time.sleep(10)
                continue
        return []
    except Exception as e:
        print(f"Error processing batch: {e}")
        return []

def save_to_db(processed_articles: List[Dict], original_batch: List[Dict], distributor=None, social_limit=2, posts_count=0, audio_gen=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for art in processed_articles:
        # Skip articles where AI failed to find content
        gist = str(art.get('gist', '')).lower()
        impact = str(art.get('why_it_matters', '')).lower()
        headline = str(art.get('headline', '')).lower()
        
        if "source content missing" in gist or "source content missing" in impact or "source content missing" in headline:
            print(f"Skipping '{art.get('headline')}' due to missing content signal.")
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
        
        # DOWNGRADED KILL SWITCH: Only warned, not skipped, to ensure content flows
        if source_name == "Google News" and is_generic:
            print(f"⚠️ Google News article '{art.get('headline')}' has no unique image. Using AI fallback.")

        if is_generic:
            cat = art.get('category', 'Tools')
            cat_map = {
                "LLMs": [
                    "/static/fallbacks/llms_0.jpg",
                    "/static/fallbacks/llms_1.jpg"
                ],
                "Robotics": [
                    "/static/fallbacks/robotics_0.jpg",
                    "/static/fallbacks/robotics_1.jpg"
                ],
                "Business": [
                    "/static/fallbacks/business_0.jpg",
                    "/static/fallbacks/business_1.jpg"
                ],
                "Tools": [
                    "/static/fallbacks/tools_0.jpg",
                    "/static/fallbacks/tools_1.jpg"
                ],
                "Policy": [
                    "/static/fallbacks/policy_0.jpg",
                    "/static/fallbacks/policy_1.jpg"
                ],
                "Science": [
                    "/static/fallbacks/science_0.jpg",
                    "/static/fallbacks/science_1.jpg"
                ],
                "Security": [
                    "/static/fallbacks/security_0.jpg",
                    "/static/fallbacks/security_1.jpg"
                ],
                "Society": [
                    "/static/fallbacks/society_0.jpg",
                    "/static/fallbacks/society_1.jpg"
                ],
                "Ethics": [
                    "/static/fallbacks/policy_0.jpg",
                    "/static/fallbacks/policy_1.jpg"
                ]
            }
            images = cat_map.get(cat, cat_map["Tools"])
            image_url = random.choice(images)

        # 3. Robust Slug Generation
        final_slug = art.get('seo_slug')
        if not final_slug or final_slug == "None" or len(final_slug) < 2:
            final_slug = slugify(art.get('headline', ''))
        if not final_slug:
            final_slug = slugify(original.get('title', 'article'))
        if not final_slug:
            final_slug = f"article-{uuid.uuid4().hex[:8]}"
        
        art['seo_slug'] = final_slug

        try:
            # Generate Audio Reads
            am, af = None, None
            if audio_gen:
                key_details_text = ". ".join(art.get('key_details', []))
                text_to_read = (
                    f"Headline: {art.get('headline')}. "
                    f"The Gist: {art.get('gist')}. "
                    f"Why It Matters: {art.get('why_it_matters')}. "
                    f"Optimistic Outlook: {art.get('optimistic_outlook')}. "
                    f"Risk Factors: {art.get('pessimistic_outlook')}. "
                    f"Key Details: {key_details_text}. "
                )
                am, af = audio_gen.generate_audio_reads(final_slug, text_to_read)

            cursor.execute('''
                INSERT OR REPLACE INTO articles 
                (slug, title, image, category, gist, why_it_matters, bull_case, bear_case, key_details, eli5, deep_analysis, source, source_url, full_json, published_at, audio_male, audio_female, hashtags, original_author, narration_script, thought_provoking_question)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                original.get('published'),
                am,
                af,
                json.dumps(art.get('hashtags', [])),
                original.get('original_author'),
                art.get('narration_script'),
                art.get('thought_provoking_question')
            ))
            
            # STAGGERED SOCIAL QUEUING
            # Queue for social media if not previously shared
            # We stagger posts by 45 minutes to prevent flooding
            if distributor and posts_count < social_limit:
                 # Check if already processed to avoid duplicates in queue
                 cursor.execute("SELECT id FROM social_queue WHERE slug = ?", (final_slug,))
                 if not cursor.fetchone():
                     # Calculate delay: (posts_count + 1) * 45 minutes from now
                     delay_minutes = (posts_count + 1) * 45
                     scheduled_time = datetime.now() + timedelta(minutes=delay_minutes)
                     
                     cursor.execute('''
                        INSERT INTO social_queue (slug, headline, status, scheduled_time)
                        VALUES (?, ?, 'PENDING', ?)
                     ''', (final_slug, art.get('headline'), scheduled_time.isoformat()))
                     
                     print(f"🕒 Staggered social post for '{art.get('headline')}' at {scheduled_time.strftime('%H:%M')}")
                     posts_count += 1
            
        except Exception as e:
            print(f"Error saving article {art.get('headline')}: {e}")
            
    conn.commit()
    conn.close()
    return posts_count

def process_social_queue():
    """Checks for pending social posts that are due."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, slug, headline FROM social_queue 
        WHERE status='PENDING' AND scheduled_time <= ?
    ''', (datetime.now().isoformat(),))
    
    pending = cursor.fetchall()
    
    if not pending:
        conn.close()
        return

    distributor = SocialDistributor()
    
    for row in pending:
        queue_id, slug, headline = row
        print(f"🚀 Processing scheduled post: {headline}")
        
        cursor.execute('SELECT full_json FROM articles WHERE slug = ?', (slug,))
        art_row = cursor.fetchone()
        
        if art_row:
            try:
                article_data = json.loads(art_row[0])
                article_data['seo_slug'] = slug
                distributor.distribute(article_data)
                
                cursor.execute("UPDATE social_queue SET status='SENT' WHERE id=?", (queue_id,))
                print(f"✅ Successfully posted: {headline}")
            except Exception as e:
                print(f"❌ Failed to post {headline}: {e}")
                cursor.execute("UPDATE social_queue SET status='FAILED' WHERE id=?", (queue_id,))
        else:
            print(f"⚠️ Article data missing for slug: {slug}")
            cursor.execute("UPDATE social_queue SET status='FAILED_MISSING_DATA' WHERE id=?", (queue_id,))
            
    conn.commit()
    conn.close()

def main():
    print("Initializing Database...")
    init_db()
    
    # Record scan start time
    scan_start_time = datetime.now()
    
    print("Aggregating Intelligence from Multiple Sources...")
    new_articles = fetch_all_sources()
    
    if not new_articles:
        print("Everything up to date. No new intelligence to process.")
        # Advance frontier even if no articles passed the high-signal filter
        update_last_scan_timestamp(scan_start_time)
        return

    print(f"New High-Signal Articles to Process: {len(new_articles)}")
    
    # Process in batches of 4 for efficiency
    batch_size = 4
    distributor = SocialDistributor()
    total_posts_sent = 0
    articles_saved = 0
    
    for i in range(0, len(new_articles), batch_size):
        batch = new_articles[i:i + batch_size]
        print(f"Processing batch {i//batch_size + 1} ({len(batch)} articles)...")
        processed = process_batch(batch)
        if processed:
            # Save WITHOUT audio generation (pass None for audio_gen)
            total_posts_sent = save_to_db(processed, batch, distributor, social_limit=2, posts_count=total_posts_sent, audio_gen=None)
            articles_saved += len(processed)
            print(f"Saved {len(processed)} articles from batch. Social posts sent so far: {total_posts_sent}")
        
        # Sleep 15s between batches to avoid rate limits
        time.sleep(15)

    # Save timestamp only after full processing attempt
    update_last_scan_timestamp(scan_start_time)

    # Run deduplication BEFORE generating expensive audio
    print("Running deduplication before audio generation...")
    remove_duplicates(seq_threshold=0.8, word_threshold=0.6)
    
    # Now generate audio only for articles that survived deduplication
    if articles_saved > 0:
        print(f"Generating audio for {articles_saved} deduplicated articles...")
        from generate_missing_audio import generate_audio_for_recent_articles
        generate_audio_for_recent_articles(limit=articles_saved)

def main_loop():
    """Runs the main fetcher loop with queued social posting."""
    print("Starting DailyAIWire Intelligence Service...")
    
    last_fetch_time = 0
    fetch_interval = 3600 # 1 hour
    
    while True:
        try:
            current_time = time.time()
            
            # Run Fetcher if interval passed
            if current_time - last_fetch_time > fetch_interval:
                print(f"⏰ Starting scheduled fetch cycle at {time.strftime('%H:%M:%S')}")
                main()
                last_fetch_time = time.time()
            
            # Sleep for 1 minute before next tick
            time.sleep(60)
            
        except KeyboardInterrupt:
            print("\nIntelligence Service stopped by user.")
            break
        except Exception as e:
            print(f"Error in main loop: {e}")
            print("Retrying in 1 minute...")
            time.sleep(60)

if __name__ == "__main__":
    import sys
    if "--loop" in sys.argv:
        main_loop()
    else:
        main()
