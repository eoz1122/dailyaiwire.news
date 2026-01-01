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
import requests

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
            thought_provoking_question TEXT,
            importance_score INTEGER DEFAULT 50,
            original_author TEXT,
            hashtags TEXT, -- Stored as JSON string
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

    # Add importance_score if it doesn't exist
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN importance_score INTEGER DEFAULT 50")
    except sqlite3.OperationalError:
        pass # Already exists

    # Add design_tokens (GenUI 2026) if it doesn't exist
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN design_tokens TEXT")
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

    # Editorials Table (Opinion/Human Content)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS editorials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE,
            title TEXT,
            subtitle TEXT,
            content TEXT,
            author TEXT DEFAULT 'Emre Ozen',
            image TEXT,
            published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_published BOOLEAN DEFAULT 0
        )
    ''')

    # AI Logs Table (Audit Trail)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            model TEXT,
            prompt_type TEXT,
            prompt_text TEXT,
            response_text TEXT,
            cost_estimate REAL
        )
    ''')

    # Metadata Table for scan tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    # Processing Attempts Log (The "Crash Loop" Circuit Breaker)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processing_attempts (
            url TEXT PRIMARY KEY,
            attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT
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
    return datetime.utcnow() - timedelta(hours=24)

def update_last_scan_timestamp(ts: datetime):
    """Updates the last successful scan timestamp in metadata."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_scan_timestamp', ?)", (ts.isoformat(),))
    # Blocked Sources Table (Dynamic Blocklist)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blocked_sources (
            domain TEXT PRIMARY KEY,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def get_recent_published_titles(hours=36) -> List[str]:
    """Retrieves titles of articles published in the last X hours for deduplication."""
    target_time = datetime.utcnow() - timedelta(hours=hours)
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
    """Filters out sources that are too local, irrelevant, or explicitly blocked."""
    # 1. Hardcoded Blocklist (Legacy/Emergency)
    blocked_defaults = [
        "Kurdistan24", "kurdistan24.net", 
        "Seacoastonline.com", "Pittsburgh Post-Gazette",
        "KERA News", "Oregon Public Broadcasting - OPB",
        "pymnts", "pymnts.com"
    ]
    
    if any(b.lower() in source_name.lower() for b in blocked_defaults):
        return True

    # 2. Dynamic Blocklist from DB
    # Note: For high performance in a loop, ideally we load this once outside. 
    # But for safety/simplicity in this context, we check. 
    # To optimize: We will cache this in 'fetch_all_sources' and pass it down in a future refactor.
    # For now, let's do a quick check (SQLite is fast).
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        # Check for exact match or partial domain match
        # We'll fetch all blocked domains and check in python to be flexible
        cur.execute("SELECT domain FROM blocked_sources")
        blocked_db = [row[0].lower() for row in cur.fetchall()]
        conn.close()
        
        if any(b in source_name.lower() for b in blocked_db):
            return True
            
    except Exception:
        pass # If DB fails, fallback to allowing (or just hardcoded list)

    return False

def filter_high_signal_headlines(articles: List[Dict], recent_titles: List[str] = []) -> List[Dict]:
    """Uses Gemini to filter for high-value AI news headlines and exclude duplicates/similar stories."""
    if not articles:
        return []

    print(f"AI Pre-Filtering {len(articles)} headlines for signal quality and deduplication...")
    
    # OPTIMIZATION: If we have very few articles, don't waste an AI call filtering them.
    # Also prevents errors when asking "Top 8" from a list of 1.
    if len(articles) <= 5:
        print(f"Skipping AI filter (Small batch: {len(articles)} articles). processing all.")
        return articles
    
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
        print(f"Headline filtering failed: {e}. Proceeding with first 10 articles as fallback.")
        return articles[:10]

def fetch_all_sources() -> List[Dict]:
    """Fetches news from multiple specific AI feeds and Google News."""
    sources = [
        # // PRIMARY WIRE
        ("The Verge", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
        ("TechCrunch", "https://techcrunch.com/category/artificial-intelligence/feed/"),
        ("Wired", "https://www.wired.com/feed/tag/ai/latest/rss"),
        # ("The Batch", "https://read.deeplearning.ai/the-batch/feed"), # 404 - No public RSS found
        ("Import AI", "https://importai.substack.com/feed"),
        # ("Ben's Bites", "https://bensbites.beehiiv.com/feed"), # 404 - Requires specific Beehiiv ID
        ("DFKI (Germany)", "https://robotik.dfki-bremen.de/de/startseite/news-rss-feed"),
        ("BracAI (EU)", "https://www.bracai.eu/blog-feed.xml"),
        ("Zukunftszentrum KI NRW", "https://www.zukunftszentrum-ki.nrw/feed/"),
        
        # // RESEARCH LABS
        ("OpenAI", "https://openai.com/news/rss.xml"),
        ("DeepMind", "https://deepmind.com/blog/feed/basic/"),
        ("BAIR Blog", "https://bair.berkeley.edu/blog/feed.xml"),
        # ("Meta AI (FAIR)", "https://ai.meta.com/blog/rss.xml"), # 400 - Feed broken/unreliable
        ("Microsoft Research", "https://www.microsoft.com/en-us/research/feed/"),
        ("Anthropic", "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_news.xml"),
        ("Cambridge University AI", "https://www.cam.ac.uk/taxonomy/term/51032/feed"),
        
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
    
    # PRE-FETCH: Get existing URLs from DB to avoid re-processing
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT source_url FROM articles")
    existing_urls = {row[0] for row in cursor.fetchall()}
    conn.close()
    
    # GET STATE: Only fetch articles after last scan
    last_scan = get_last_scan_timestamp()
    print(f"📡 Only scanning news published since: {last_scan.strftime('%Y-%m-%d %H:%M:%S')}")

    for source_name, url in sources:
        print(f"Fetching from {source_name}...")
        try:
            # Fix: Use requests with timeout to prevent hanging on unresponsive feeds (e.g., DFKI)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            try:
                if source_name == "Hacker News (AI)":
                    # Special case for hnrss which might need looser timeout or specific headers
                    resp = requests.get(url, headers=headers, timeout=15)
                else:
                    resp = requests.get(url, headers=headers, timeout=10)
                
                resp.raise_for_status()
                feed = feedparser.parse(resp.content)
            except Exception as req_err:
                print(f"   ⚠️ Connection error for {source_name}: {req_err}")
                continue

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
                    dt_published = datetime.utcnow()

                # STATEFUL CHECK: Must be newer than last scan
                if dt_published <= last_scan:
                    skipped_count += 1
                    continue

                title = entry.title
                if " - " in title and source_name == "Google News":
                    title = title.rsplit(" - ", 1)[0]
                    
                link = entry.link
                if link not in unique_articles and link not in existing_urls:
                    # SMART SOURCE DISCOVERY
                    # Aggregators often list themselves as the source. We want the Real Publisher.
                    real_source = source_name
                    
                    if source_name in ["Google News", "Hacker News (AI)", "Papers with Code"]:
                        # 1. Try to get it from feed metadata if available
                        if hasattr(entry, 'source') and 'title' in entry.source:
                            real_source = entry.source.title
                        
                        # 2. If that fails or is generic, extract from URL domain
                        if not real_source or real_source == source_name:
                            try:
                                from urllib.parse import urlparse
                                domain = urlparse(link).netloc
                                # Remove www. and common suffixes to make it look like a "Source Name"
                                domain = domain.replace('www.', '')
                                if domain:
                                    real_source = domain.split('.')[0].title() # e.g. 'bbc.co.uk' -> 'Bbc'
                                    
                                    # Dictionary for common overrides to make them pretty
                                    overrides = {
                                        'Bbc': 'BBC News', 'Ycombinator': 'Hacker News', 'Github': 'GitHub',
                                        'Arxiv': 'ArXiv Research', 'Youtube': 'YouTube', 'Nytimes': 'NY Times',
                                        'Wsj': 'Wall Street Journal', 'Cnbc': 'CNBC', 'Techcrunch': 'TechCrunch'
                                    }
                                    real_source = overrides.get(real_source, real_source)
                            except:
                                pass # Keep original on error

                    # IGNORE LOCAL/BLOCKED SOURCES
                    if is_ignored_source(real_source):
                        continue

                    unique_articles[link] = {
                        "title": title,
                        "source": real_source, # Now holds 'BBC News' instead of 'Hacker News (AI)'
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
    
    # FILTER: Remove any URLs we have already ATTEMPTED to process in the last 24h
    # This prevents the "infinite retry loop" if the script crashes after API call but before DB save.
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Clean up old attempts > 24h to keep table small
    cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    cur.execute("DELETE FROM processing_attempts WHERE attempted_at < ?", (cutoff,))
    conn.commit()
    
    # Get recent attempts
    cur.execute("SELECT url FROM processing_attempts")
    attempted_urls = {row[0] for row in cur.fetchall()}
    conn.close()
    
    # Filter candidates with Local Fuzzy Deduplication (Cost: $0)
    import difflib
    candidates = []
    
    print(f"🔎 Scanning {len(all_articles)} raw headlines against {len(recent_titles)} recent titles...")
    
    for art in all_articles:
        # 1. Check if URL attempted
        if art['link'] in attempted_urls:
            continue
            
        # 2. Check content length (cheap check)
        if len(art.get('title', '')) < 10:
            continue

        # 3. Fuzzy Title Match (The "Cheap" Dedup)
        # Verify against recent DB titles to avoid re-processing "OpenAI releases Sora" vs "Sora Released by OpenAI"
        is_duplicate = False
        clean_title = art['title'].lower().strip()
        
        for recent in recent_titles:
            # Quick substring check
            if clean_title in recent.lower() or recent.lower() in clean_title:
                is_duplicate = True
                break
            
            # Fuzzy Ratio check (slower but accurate)
            ratio = difflib.SequenceMatcher(None, clean_title, recent.lower()).ratio()
            if ratio > 0.85: # 85% similarity threshold
                is_duplicate = True
                break
        
        if is_duplicate:
            # print(f"♻️  Skipping Duplicate/Similar Story: {art['title']}")
            continue
            
        candidates.append(art)
        
    if not candidates:
        print("All candidates have already been attempted or matched recently. Skipping.")
        return []

    # CAP: Limit to top 40 candidates to prevent massive bills on "catch-up" runs
    if len(candidates) > 40:
        print(f"⚠️ High Volume Warning: Capping {len(candidates)} candidates to 40 to protect budget.")
        candidates = candidates[:40]

    return filter_high_signal_headlines(candidates, recent_titles)

def log_processing_attempt(url: str, status="PROCESSING"):
    """Logs that we are about to try processing this URL."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO processing_attempts (url, status, attempted_at) VALUES (?, ?, ?)", 
                   (url, status, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Failed to log attempt: {e}")


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
    model_name = "gemini-1.5-flash"
    print(f"⚡ Analyzing batch with: {model_name}")
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=(
            "## ROLE\n"
            "Lead Intelligence Strategist for DailyAIWire. AI-First Execution; Human-Led Responsibility.\n"
            "Your mission is to transform raw technical data into high-density executive intelligence. Priority: Factual Density > Narrative Flow.\n\n"
            
            "## TASK: EXECUTIVE INTELLIGENCE SYNTHESIS\n"
            "Analyze the input to produce structured JSON. Follow the 'Pure Signal' philosophy: strip away marketing fluff and prioritize facts, specs, and market implications.\n\n"
            
            "## 2026 COMPLIANCE & SAFETY GUARDRAILS\n"
            "- TRANSFORMATIVE VOICE: Use original analytical phrasing. Do not reproduce the source's unique metaphors. DO NOT copy more than 7 consecutive words.\n"
            "- HALLUCINATION PREVENTION: Base all analysis exclusively on the provided input. If data is unclear, omit it.\n"
            "- STEP-BY-STEP REASONING: For 'Outlook', logically link predictions to specific source facts.\n\n"

            "## TOKEN & PERFORMANCE OPTIMIZATION\n"
            "- STRICT BREVITY: Use concise, professional language.\n"
            "- DETERMINISTIC BIAS: Prioritize consistency and factual accuracy.\n"
            "- FORMAT: Output strictly in valid JSON."
        )
    )

    batch_input = []
    skipped_low_quality = 0
    
    for idx, item in enumerate(batch):
        content, og_image, author = extract_content(item['link'])
        item['scraped_image'] = og_image  # Attach to batch item for save_to_db
        item['original_author'] = author
        
        # QUALITY CONTROL: If scraper got nothing (<300 chars), SKIP IT.
        # This prevents "Title-Only" analysis which leads to "No content provided" and wasted money.
        if not content or len(content) < 300:
            print(f"📉 Low Content Signal ({len(content) if content else 0} chars). Skipping: {item['title']}")
            log_processing_attempt(item['link'], status="SKIPPED_LOW_CONTENT")
            skipped_low_quality += 1
            continue

        analysis_context = content[:3500] 
        batch_input.append(f"ARTICLE ID: {idx}\nSOURCE TITLE: {item['title']} (Ensure Output is English)\nSOURCE CONTENT: {analysis_context}")

        # CRITICAL: Mark as attempted immediately to prevent loops
        log_processing_attempt(item['link'], status="SENT_TO_API")

    if not batch_input:
        print("⚠️ All articles in this batch were skipped due to low content.")
        return []

    prompt = (
        f"Process the following {len(batch_input)} news articles (some ID indices may be skipped) and return a JSON list of objects matching this structure:\n"
        "[\n"
        "  {\n"
        "    \"status\": \"SUCCESS | INSUFFICIENT_DATA\",\n"
        "    \"batch_id\": [Integer matching the ARTICLE ID provided below],\n"
        "    \"headline\": \"Clicky but Factual Title\",\n"
        "    \"seo_slug\": \"url-safe-slug\",\n"
        "    \"image_query\": \"A concise keyword for an Unsplash image\",\n"
        "    \"category\": \"Strictly choose ONE from: ['LLMs', 'Robotics', 'Business', 'Tools', 'Policy', 'Science', 'Security', 'Society', 'Ethics']\",\n"
        "    \"gist\": \"Single bold sentence (max 25 tokens).\",\n"
        "    \"key_details\": [\"Extract 2-5 verifiable facts (hard data points). If <2 verifiable facts, set status to INSUFFICIENT_DATA and leave empty.\"],\n"
        "    \"why_it_matters\": \"Brief insight on impact (2-3 sentences max)\",\n"
        "    \"optimistic_outlook\": \"Upside analysis in 2-3 sentences. Focus on positive potential.\",\n"
        "    \"pessimistic_outlook\": \"Downside/Risk analysis in 2-3 sentences. Focus on concerns.\",\n"
        "    \"hashtags\": [\"3-5 relevant hashtags\"],\n"
        "    \"thought_provoking_question\": \"A short, engaging question to spark discussion.\",\n"
        "    \"eli5\": \"Explain like I'm 5 years old version\",\n"
        "    \"importance_score\": \"40-100 reflecting strategic value.\",\n"
        "    \"deep_analysis\": \"300+ words. Comprehensive summary using multiple paragraphs.\",\n"
        "    \"narration_script\": \"1-minute radio script starting with 'Intelligence from DailyAIWire dot news...'.\",\n"
        "    \"metadata\": { \"ai_detected\": true, \"model\": \"Gemini 2.5 Flash\", \"label\": \"EU AI Act Art. 50 Compliant\" },\n"
        "    \"design_tokens\": {\n"
        "      \"intensity\": \"critical | high | standard | low\",\n"
        "      \"sentiment_pallet\": \"techno-optimist | warning | crisis\",\n"
        "      \"component_triggers\": [\"quick_facts_grid\", \"market_ticker\", \"code_block\"]\n"
        "    }\n"
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
                    generation_config={"response_mime_type": "application/json"},
                    request_options={'timeout': 600}
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
        # 1. Status Check (New 2026 Guardrail)
        if art.get('status') == "INSUFFICIENT_DATA":
            print(f"Skipping '{art.get('headline')}' - AI flagged as Insufficient Data.")
            continue

        # Skip articles where AI failed to find content or hit a paywall/blocker
        gist = str(art.get('gist', '')).lower()
        impact = str(art.get('why_it_matters', '')).lower()
        headline = str(art.get('headline', '')).lower()
        analysis = str(art.get('deep_analysis', ''))

        # 2. Transparency & Attribution Injection (EU AI Act)
        # We append this programmatically to guarantee it appears on all platforms.
        footer = "\n\n_Context: This intelligence report was compiled by the DailyAIWire Strategy Engine. Verified for Art. 50 Compliance._"
        if footer not in analysis:
            art['deep_analysis'] = analysis + footer
            analysis = art['deep_analysis'].lower() # Update for blacklist check

        blacklist = [
            "source content missing",
            "javascript is disabled",
            "enable javascript",
            "article unavailable",
            "content access",
            "access denied",
            "please enable js",
            "browser to continue"
        ]
        
        if any(b in gist for b in blacklist) or \
           any(b in impact for b in blacklist) or \
           any(b in headline for b in blacklist) or \
           any(b in analysis for b in blacklist):
            print(f"Skipping '{art.get('headline')}' due to content blocker signal (JS/Access Denied).")
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
                    "/static/fallbacks/llms_1.jpg",
                    "/static/fallbacks/llms_2.jpg",
                    "/static/fallbacks/llms_3.jpg"
                ],
                "Robotics": [
                    "/static/fallbacks/robotics_0.jpg",
                    "/static/fallbacks/robotics_1.jpg",
                    "/static/fallbacks/robotics_2.jpg",
                    "/static/fallbacks/robotics_3.jpg",
                    "/static/fallbacks/robotics_4.jpg",
                    "/static/fallbacks/robotics_5.jpg",
                    "/static/fallbacks/robotics_6.jpg",
                    "/static/fallbacks/robotics_7.jpg"
                ],
                "Business": [
                    "/static/fallbacks/business_0.jpg",
                    "/static/fallbacks/business_1.jpg",
                    "/static/fallbacks/business_2.jpg",
                    "/static/fallbacks/business_3.jpg",
                    "/static/fallbacks/business_4.jpg",
                    "/static/fallbacks/business_5.jpg",
                    "/static/fallbacks/business_6.jpg",
                    "/static/fallbacks/business_7.jpg",
                    "/static/fallbacks/business_8.jpg"
                ],
                "Tools": [
                    "/static/fallbacks/tools_0.jpg",
                    "/static/fallbacks/tools_1.jpg",
                    "/static/fallbacks/tools_2.jpg"
                ],
                "Policy": [
                    "/static/fallbacks/policy_0.jpg",
                    "/static/fallbacks/policy_1.jpg",
                    "/static/fallbacks/policy_2.jpg",
                    "/static/fallbacks/policy_3.jpg",
                    "/static/fallbacks/policy_4.jpg",
                    "/static/fallbacks/policy_5.jpg",
                    "/static/fallbacks/policy_6.jpg",
                    "/static/fallbacks/policy_7.jpg"
                ],
                "Science": [
                    "/static/fallbacks/science_0.jpg",
                    "/static/fallbacks/science_1.jpg",
                    "/static/fallbacks/science_2.jpg",
                    "/static/fallbacks/science_3.jpg",
                    "/static/fallbacks/science_4.jpg",
                    "/static/fallbacks/science_5.jpg",
                    "/static/fallbacks/science_6.jpg",
                    "/static/fallbacks/science_7.jpg"
                ],
                "Security": [
                    "/static/fallbacks/security_0.jpg",
                    "/static/fallbacks/security_1.jpg",
                    "/static/fallbacks/security_2.jpg",
                    "/static/fallbacks/security_3.jpg"
                ],
                "Society": [
                    "/static/fallbacks/society_0.jpg",
                    "/static/fallbacks/society_1.jpg",
                    "/static/fallbacks/society_2.jpg",
                    "/static/fallbacks/society_3.jpg",
                    "/static/fallbacks/society_4.jpg"
                ],
                "Ethics": [
                    "/static/fallbacks/policy_0.jpg",
                    "/static/fallbacks/policy_1.jpg",
                    "/static/fallbacks/policy_2.jpg",
                    "/static/fallbacks/policy_3.jpg"
                ]
            }
            # Fallback Logic: Avoid back-to-back duplicates
            images = cat_map.get(cat, cat_map["Tools"])
            
            # Check the most recently saved article's image to avoid repetition
            try:
                last_img_row = cursor.execute("SELECT image FROM articles ORDER BY id DESC LIMIT 1").fetchone()
                last_img = last_img_row[0] if last_img_row else None
            except:
                last_img = None

            # Filter out the last used image if possible
            available_images = [img for img in images if img != last_img]
            
            # If no images left (e.g. only 1 fallback exists), revert to full list
            if not available_images:
                available_images = images
                
            image_url = random.choice(available_images)

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
                (slug, title, image, category, gist, why_it_matters, bull_case, bear_case, key_details, eli5, deep_analysis, source, source_url, full_json, published_at, audio_male, audio_female, hashtags, original_author, narration_script, thought_provoking_question, importance_score, design_tokens)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                art.get('thought_provoking_question'),
                int(art.get('importance_score', 50) or 50),
                json.dumps(art.get('design_tokens', {}))
            ))
            
            # STAGGERED SOCIAL QUEUING - DISABLED
            # Consolidating all posting into tweet_scheduler.py for strict 1h gaps.
            pass
            
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
    ''', (datetime.utcnow().isoformat(),))
    
    pending = cursor.fetchall()
    
    if not pending:
        conn.close()
        return

    distributor = SocialDistributor()
    
    for row in pending:
        queue_id, slug, headline = row
        print(f"🚀 Processing scheduled post: {headline}")
        
        cursor.execute('''
            SELECT a.full_json, a.source FROM articles a
            JOIN social_queue sq ON sq.slug = a.slug
            WHERE sq.id = ?
        ''', (queue_id,))
        art_row = cursor.fetchone()
        
        if art_row:
            try:
                article_data = json.loads(art_row[0])
                article_data['seo_slug'] = slug
                article_data['source'] = art_row[1] # Inject source for attribution
                distributor.distribute(article_data)
                
                cursor.execute("UPDATE social_queue SET status='SENT' WHERE id=?", (queue_id,))
                # Update main articles table to stay in sync
                cursor.execute("UPDATE articles SET shared_on_x=1, shared_at=? WHERE slug=?", (datetime.utcnow().isoformat(), slug))
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
    scan_start_time = datetime.utcnow()
    
    print("Aggregating Intelligence from Multiple Sources...")
    new_articles = fetch_all_sources()
    
    if not new_articles:
        print("Everything up to date. No new intelligence to process.")
        # Advance frontier even if no articles passed the high-signal filter
        update_last_scan_timestamp(scan_start_time)
        return

    print(f"New High-Signal Articles to Process: {len(new_articles)}")
    
    # Process in batches for efficiency
    # HARD LIMIT: Never process more than 16 articles per cycle to prevent token spikes
    MAX_ARTICLES_PER_CYCLE = 16
    if len(new_articles) > MAX_ARTICLES_PER_CYCLE:
        print(f"⚠️ Cap reached! Truncating {len(new_articles)} articles to {MAX_ARTICLES_PER_CYCLE}")
        new_articles = new_articles[:MAX_ARTICLES_PER_CYCLE]

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
            total_posts_sent = save_to_db(processed, batch, distributor, social_limit=5, posts_count=total_posts_sent, audio_gen=None)
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
    fetch_interval = 7200 # 2 hours (was 3 hours)
    
    while True:
        try:
            current_time = time.time()
            
            # Run Fetcher if interval passed
            if current_time - last_fetch_time > fetch_interval:
                print(f"⏰ Starting scheduled fetch cycle at {time.strftime('%H:%M:%S')}")
                main()
                last_fetch_time = time.time()
            
            # Social posting is now handled exclusively by tweet_scheduler.py 
            # to prevent double-posting and 429 Rate Limits.
            # process_social_queue()
            
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
