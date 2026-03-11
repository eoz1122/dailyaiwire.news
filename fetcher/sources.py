"""
Fetcher — Source Aggregation & Headline Filtering
RSS fetching, source discovery, fuzzy dedup, and AI headline filter.
"""
import os
import time
import sqlite3
import difflib
import feedparser
import requests
from datetime import datetime, timedelta
from typing import List, Dict

import google.generativeai as genai
from dotenv import load_dotenv

from db import DB_PATH
from fetcher.db_init import get_last_scan_timestamp, get_recent_published_titles, log_processing_attempt
from fetcher.spam import is_spam, is_ignored_source

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Budget Tracker
from budget_tracker import BudgetTracker
MONTHLY_BUDGET_USD = float(os.getenv("MONTHLY_BUDGET_USD", "10.0"))
budget = BudgetTracker(monthly_cap_usd=MONTHLY_BUDGET_USD)


def filter_high_signal_headlines(articles: List[Dict], recent_titles: List[str] = []) -> List[Dict]:
    """Uses Gemini to filter for high-value AI news headlines and exclude duplicates/similar stories."""
    if not articles:
        return []

    print(f"AI Pre-Filtering {len(articles)} headlines for signal quality and deduplication...")

    # OPTIMIZATION: If we have very few articles, don't waste an AI call filtering them.
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
    1. EXCLUDE any article that is the same story as one in the RECENTLY PUBLISHED list.
    2. EXCLUDE "Sponsored", "Advertisement", "Promoted", "Affiliate", or "Partner Content".
    3. PRIORITIZE major breakthroughs, strategic corporate shifts, and research milestones.
    4. ALLOW "Product Launches" ONLY IF they are:
       - Open Source / MIT Licensed / Hugging Face releases.
       - A major infrastructure update (e.g. AWS, NVIDIA, OpenAI).
    5. BLOCK generic B2B SaaS launches, "All-in-one" marketing tools, and paid wrapper apps.
    6. BLOCK stories about SUICIDE, MURDER, or VIOLENCE unless they are critical geopolitical events (e.g. involving a head of state).
    
    Return EXACTLY 8 indices of the most important articles.
    
    Example Input:
    - OpenAI releases Sora API [Keep]
    - Local coffee shop uses AI for menu [Block]
    - Invoce: AI Invoicing for Freelancers [Block - SaaS]
    - Llama-3-70b release on Hugging Face [Keep - Open Source]
    - Google announces Gemini 2.5 [Keep]
    - [Sponsored] Best AI SEO Tools 2026 [Block]
    Example Output: 0, 3, 4
    
    HEADLINES:
    {headline_list}
    """

    try:
        from ai_config import DEFAULT_MODEL
        model_name = DEFAULT_MODEL
        print(f"⚡ using AI Model (Filter): {model_name}")

        # Budget Check
        estimated_tokens = len(prompt) // 4 + 500
        if not budget.can_make_request(estimated_tokens):
             print("Skipping filter due to budget.")
             return articles[:8]  # Fallback

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
    # 1. Fetch Active Sources from DB
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name, url FROM sources WHERE is_active = 1")
        sources = cursor.fetchall()
    except sqlite3.OperationalError:
        print("⚠️ 'sources' table not found. Using fallback list.")
        sources = [
            ("The Verge", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
            ("OpenAI", "https://openai.com/news/rss.xml")
        ]
    finally:
        conn.close()

    if not sources:
        print("⚠️ No active sources found in DB.")
        return []

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
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            try:
                if source_name == "Hacker News (AI)":
                    resp = requests.get(url, headers=headers, timeout=15)
                else:
                    resp = requests.get(url, headers=headers, timeout=10)

                resp.raise_for_status()
                feed = feedparser.parse(resp.content)
            except Exception as req_err:
                print(f"   ⚠️ Connection error for {source_name}: {req_err}")
                continue

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
                    time.sleep(4)  # Rate Limit Safety
                    # SMART SOURCE DISCOVERY
                    real_source = source_name

                    if source_name in ["Google News", "Hacker News (AI)", "Papers with Code"]:
                        if hasattr(entry, 'source') and 'title' in entry.source:
                            real_source = entry.source.title

                        if not real_source or real_source == source_name:
                            try:
                                from urllib.parse import urlparse
                                domain = urlparse(link).netloc
                                domain = domain.replace('www.', '')
                                if domain:
                                    real_source = domain.split('.')[0].title()

                                    overrides = {
                                        'Bbc': 'BBC News', 'Ycombinator': 'Hacker News', 'Github': 'GitHub',
                                        'Arxiv': 'ArXiv Research', 'Youtube': 'YouTube', 'Nytimes': 'NY Times',
                                        'Wsj': 'Wall Street Journal', 'Cnbc': 'CNBC', 'Techcrunch': 'TechCrunch'
                                    }
                                    real_source = overrides.get(real_source, real_source)
                            except (ValueError, AttributeError):
                                pass

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

    # FILTER: Remove any URLs we have already ATTEMPTED to process in the last 24h
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    cur.execute("DELETE FROM processing_attempts WHERE attempted_at < ?", (cutoff,))
    conn.commit()

    cur.execute("SELECT url FROM processing_attempts")
    attempted_urls = {row[0] for row in cur.fetchall()}
    conn.close()

    # Filter candidates with Local Fuzzy Deduplication (Cost: $0)
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
        is_duplicate = False
        clean_title = art['title'].lower().strip()

        for recent in recent_titles:
            if clean_title in recent.lower() or recent.lower() in clean_title:
                is_duplicate = True
                break

            ratio = difflib.SequenceMatcher(None, clean_title, recent.lower()).ratio()
            if ratio > 0.85:
                is_duplicate = True
                break

        if is_duplicate:
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
