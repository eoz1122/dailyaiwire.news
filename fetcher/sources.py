"""
Fetcher — Source Aggregation & Headline Filtering
RSS fetching, source discovery, fuzzy dedup, and AI headline filter.
"""
import os
import time
import sqlite3
import difflib
import logging
import re
import feedparser
import requests
from datetime import datetime, timedelta
from typing import List, Dict
from urllib.parse import urlparse

import google.generativeai as genai
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from db import DB_PATH
from fetcher.db_init import get_last_scan_timestamp, get_recent_published_titles, log_processing_attempt
from fetcher.spam import is_spam, is_ignored_source

logger = logging.getLogger('fetcher.sources')

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Budget Tracker
from budget_tracker import BudgetTracker
MONTHLY_BUDGET_USD = float(os.getenv("MONTHLY_BUDGET_USD", "10.0"))
budget = BudgetTracker(monthly_cap_usd=MONTHLY_BUDGET_USD)

# Block only zero-star GitHub repos by default.
GITHUB_MIN_STARS = int(os.getenv("GITHUB_MIN_STARS", "1"))
GITHUB_CACHE_HOURS = int(os.getenv("GITHUB_CACHE_HOURS", "24"))
GITHUB_API_TIMEOUT_SECONDS = int(os.getenv("GITHUB_API_TIMEOUT_SECONDS", "8"))
HF_PAPERS_LIMIT = int(os.getenv("HF_PAPERS_LIMIT", "12"))
HF_PAPERS_URL = os.getenv("HF_PAPERS_URL", "https://huggingface.co/papers")

_GITHUB_RESERVED_PATHS = {
    "about", "blog", "collections", "contact", "events", "explore", "features",
    "login", "marketplace", "new", "notifications", "organizations", "orgs",
    "pricing", "pulls", "search", "settings", "showcases", "site", "sponsors",
    "topics", "trending", "users",
}
_HF_PAPER_PATH_RE = re.compile(r"^/papers/(\d{4}\.\d{4,5})$")


def _ensure_repo_quality_cache_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS repo_quality_cache (
            repo_key TEXT PRIMARY KEY,
            stars INTEGER NOT NULL,
            checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_repo_quality_cache_checked_at ON repo_quality_cache(checked_at)'
    )
    conn.commit()


def _extract_github_repo(link: str):
    """Returns (owner, repo) if the URL points to a GitHub repository."""
    try:
        parsed = urlparse(link)
    except Exception:
        return None

    host = (parsed.netloc or "").lower().replace("www.", "")
    if host != "github.com":
        return None

    parts = [p for p in (parsed.path or "").split("/") if p]
    if len(parts) < 2:
        return None

    owner, repo = parts[0], parts[1]
    if not owner or not repo:
        return None
    if owner.lower() in _GITHUB_RESERVED_PATHS:
        return None

    repo = repo[:-4] if repo.lower().endswith(".git") else repo
    return owner, repo


def _fetch_github_repo_stars_api(owner: str, repo: str):
    """Fetch stargazers_count from GitHub API. Returns int or None on transient errors."""
    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "DailyAIWire-Fetcher/1.0",
    }
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = requests.get(api_url, headers=headers, timeout=GITHUB_API_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.warning("GitHub stars lookup failed for %s/%s: %s", owner, repo, exc)
        return None

    if resp.status_code == 200:
        payload = resp.json() or {}
        stars = payload.get("stargazers_count")
        return int(stars) if isinstance(stars, int) else None
    if resp.status_code == 404:
        return -1
    if resp.status_code == 403:
        logger.warning("GitHub API rate-limited. Skipping quality gate for %s/%s", owner, repo)
        return None

    logger.warning(
        "GitHub stars lookup HTTP %s for %s/%s",
        resp.status_code, owner, repo
    )
    return None


def _get_cached_repo_stars(conn: sqlite3.Connection, repo_key: str):
    row = conn.execute(
        '''
        SELECT stars
        FROM repo_quality_cache
        WHERE repo_key = ?
          AND checked_at >= datetime('now', ?)
        ''',
        (repo_key, f"-{GITHUB_CACHE_HOURS} hours")
    ).fetchone()
    if not row:
        return None
    return int(row[0])


def _set_cached_repo_stars(conn: sqlite3.Connection, repo_key: str, stars: int) -> None:
    conn.execute(
        '''
        INSERT INTO repo_quality_cache (repo_key, stars, checked_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(repo_key) DO UPDATE SET
            stars = excluded.stars,
            checked_at = excluded.checked_at
        ''',
        (repo_key, int(stars))
    )
    conn.commit()


def _passes_github_quality_gate(link: str, conn: sqlite3.Connection) -> bool:
    repo = _extract_github_repo(link)
    if not repo:
        return True

    owner, repo_name = repo

    repo_key = f"{owner.lower()}/{repo_name.lower()}"
    stars = _get_cached_repo_stars(conn, repo_key)
    if stars is None:
        stars = _fetch_github_repo_stars_api(owner, repo_name)
        if stars is not None:
            _set_cached_repo_stars(conn, repo_key, stars)

    # Fail open if API is temporarily unavailable.
    if stars is None:
        return True

    if stars < GITHUB_MIN_STARS:
        logger.info(
            "Skipped GitHub repo %s (%d stars < %d)",
            repo_key, stars, GITHUB_MIN_STARS
        )
        return False
    return True


def _extract_huggingface_papers_from_html(html: str, max_items: int = HF_PAPERS_LIMIT) -> List[Dict]:
    items: List[Dict] = []
    if not html:
        return items

    soup = BeautifulSoup(html, "html.parser")
    seen_links = set()

    for tag in soup.select("a[href^='/papers/']"):
        href = (tag.get("href") or "").split("#", 1)[0]
        match = _HF_PAPER_PATH_RE.match(href)
        if not match:
            continue

        canonical = f"https://huggingface.co/papers/{match.group(1)}"
        if canonical in seen_links:
            continue

        title = " ".join(tag.get_text(" ", strip=True).split())
        if not title:
            continue
        if title.isdigit():
            continue
        if title.startswith("·"):
            continue

        seen_links.add(canonical)
        items.append(
            {
                "title": title,
                "source": "Hugging Face Papers",
                "link": canonical,
                "published": datetime.utcnow().isoformat(),
            }
        )
        if len(items) >= max_items:
            break

    return items


def _fetch_huggingface_papers() -> List[Dict]:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; DailyAIWireBot/1.0; +https://dailyaiwire.news)"
    }
    try:
        resp = requests.get(HF_PAPERS_URL, headers=headers, timeout=12)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("Hugging Face papers fetch failed: %s", exc)
        return []
    return _extract_huggingface_papers_from_html(resp.text, max_items=HF_PAPERS_LIMIT)


def filter_high_signal_headlines(articles: List[Dict], recent_titles: List[str] = []) -> List[Dict]:
    """Uses Gemini to filter for high-value AI news headlines and exclude duplicates/similar stories."""
    if not articles:
        return []

    logger.info("AI Pre-Filtering %d headlines for signal quality and deduplication...", len(articles))

    # OPTIMIZATION: If we have very few articles, don't waste an AI call filtering them.
    if len(articles) <= 5:
        logger.info("Skipping AI filter (Small batch: %d articles). processing all.", len(articles))
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
        logger.info("⚡ using AI Model (Filter): %s", model_name)

        # Budget Check
        estimated_tokens = len(prompt) // 4 + 500
        if not budget.can_make_request(estimated_tokens):
             logger.warning("Skipping filter due to budget.")
             return articles[:8]  # Fallback

        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt, request_options={'timeout': 120})

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
        logger.info("Filtered down to %d high-signal articles.", len(filtered))
        return filtered
    except Exception as e:
        logger.error("Headline filtering failed: %s. Proceeding with first 10 articles as fallback.", e)
        return articles[:10]


def fetch_all_sources() -> List[Dict]:
    """Fetches news from multiple specific AI feeds and Google News."""
    # 1. Fetch Active Sources from DB
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name, url FROM sources WHERE is_active = 1 AND url IS NOT NULL AND url != '' AND url != 'None'")
        sources = cursor.fetchall()
    except sqlite3.OperationalError:
        logger.warning("⚠️ 'sources' table not found. Using fallback list.")
        sources = [
            ("The Verge", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
            ("OpenAI", "https://openai.com/news/rss.xml")
        ]
    finally:
        conn.close()

    # Runtime safety: filter out any sources with missing URLs
    sources = [(name, url) for name, url in sources if url and url.strip() and url.strip().lower() != 'none']

    if not sources:
        logger.warning("⚠️ No active sources found in DB.")
        return []

    logger.info("📡 Scanning %d active sources...", len(sources))

    unique_articles = {}

    # PRE-FETCH: Get existing URLs from DB to avoid re-processing
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT source_url FROM articles")
    existing_urls = {row[0] for row in cursor.fetchall()}
    conn.close()

    quality_conn = sqlite3.connect(DB_PATH)
    _ensure_repo_quality_cache_schema(quality_conn)

    # GET STATE: Only fetch articles after last scan
    last_scan = get_last_scan_timestamp()
    logger.info("📡 Only scanning news published since: %s", last_scan.strftime('%Y-%m-%d %H:%M:%S'))

    for source_name, url in sources:
        logger.info("Fetching from %s...", source_name)
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
                logger.warning("   ⚠️ Connection error for %s: %s", source_name, req_err)
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

                    try:
                        if not _passes_github_quality_gate(link, quality_conn):
                            continue
                    except Exception as gate_exc:
                        logger.warning("GitHub quality gate error for %s: %s", link, gate_exc)

                    article_dict = {
                        "title": title,
                        "source": real_source,
                        "link": link,
                        "published": dt_published.isoformat()
                    }

                    # UNIVERSAL RSS CONTENT FALLBACK
                    # Capture the RSS body or summary to use if full-page scraping fails (paywalls/bot blocks)
                    rss_text = ''
                    if hasattr(entry, 'content') and entry.content:
                        rss_text = entry.content[0].get('value', '')
                    if not rss_text:
                        rss_text = getattr(entry, 'summary', '')
                    if rss_text:
                        import re as _re
                        rss_text = _re.sub(r'<[^>]+>', '', rss_text).strip()
                    if rss_text:
                        article_dict['rss_summary'] = rss_text

                    # TWITTER/NITTER: Capture tweet body directly from RSS entry
                    # to bypass content extraction (tweets are too short for scraping)
                    if 'nitter' in url or 'twitter.com' in url or 'x.com' in url or 'bridge=Twitter' in url:
                        if rss_text:
                            article_dict['pre_extracted_content'] = rss_text

                    unique_articles[link] = article_dict
                    added_count += 1

            logger.info("   ↳ %d entries found. %d new, %d skipped (old).", len(entries), added_count, skipped_count)

        except Exception as e:
            logger.error("Error fetching %s: %s", source_name, e)

    # Hugging Face papers ingestion improves coverage beyond blog posts only.
    hf_added = 0
    for item in _fetch_huggingface_papers():
        link = item["link"]
        if link in unique_articles or link in existing_urls:
            continue
        unique_articles[link] = item
        hf_added += 1
    if hf_added:
        logger.info("Added %d candidates from Hugging Face papers.", hf_added)

    all_articles = list(unique_articles.values())
    quality_conn.close()

    if not all_articles:
        logger.info("📭 No new articles found since last scan.")
        return []

    logger.info("Found %d candidates for filtering.", len(all_articles))

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

    logger.info("🔎 Scanning %d raw headlines against %d recent titles...", len(all_articles), len(recent_titles))

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
        logger.info("All candidates have already been attempted or matched recently. Skipping.")
        return []

    # CAP: Limit to top 40 candidates to prevent massive bills on "catch-up" runs
    if len(candidates) > 40:
        logger.warning("⚠️ High Volume Warning: Capping %d candidates to 40 to protect budget.", len(candidates))
        candidates = candidates[:40]

    return filter_high_signal_headlines(candidates, recent_titles)
