"""
Fetcher — Source Aggregation & Headline Filtering
RSS fetching, source discovery, fuzzy dedup, and AI headline filter.
"""
import os
import time
import sqlite3
import logging
import re
import html
import feedparser
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Tuple
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import ai_config
from services.story_dedup import canonical_research_paper_id, likely_same_story
from db import DB_PATH
from fetcher.db_init import get_last_scan_timestamp, get_recent_published_titles, log_processing_attempt
from fetcher.spam import is_spam, is_ignored_source
from services.ai_gateway import AIGateway

logger = logging.getLogger('fetcher.sources')

# Budget Tracker
from budget_tracker import BudgetTracker
MONTHLY_BUDGET_USD = float(os.getenv("MONTHLY_BUDGET_USD", "10.0"))
budget = BudgetTracker(monthly_cap_usd=MONTHLY_BUDGET_USD)

# Block very low-signal GitHub repos by default.
# Default is 10; can be raised (e.g. 15) via GITHUB_MIN_STARS.
GITHUB_MIN_STARS = int(os.getenv("GITHUB_MIN_STARS", "10"))
GITHUB_CACHE_HOURS = int(os.getenv("GITHUB_CACHE_HOURS", "24"))
GITHUB_API_TIMEOUT_SECONDS = int(os.getenv("GITHUB_API_TIMEOUT_SECONDS", "8"))
HF_PAPERS_LIMIT = int(os.getenv("HF_PAPERS_LIMIT", "4"))
HF_PAPERS_URL = os.getenv("HF_PAPERS_URL", "https://huggingface.co/papers")
META_BLOG_LIMIT = int(os.getenv("META_BLOG_LIMIT", "5"))
META_BLOG_URL = os.getenv("META_BLOG_URL", "https://ai.meta.com/blog/")
META_BLOG_RECENCY_DAYS = int(os.getenv("META_BLOG_RECENCY_DAYS", "7"))
HEADLINE_FILTER_RECENT_TITLES_LIMIT = int(os.getenv("HEADLINE_FILTER_RECENT_TITLES_LIMIT", "24"))
HEADLINE_FILTER_MAX_RESEARCH_SHARE = float(
    os.getenv("HEADLINE_FILTER_MAX_RESEARCH_SHARE", "0.4")
)

_GITHUB_RESERVED_PATHS = {
    "about", "blog", "collections", "contact", "events", "explore", "features",
    "login", "marketplace", "new", "notifications", "organizations", "orgs",
    "pricing", "pulls", "search", "settings", "showcases", "site", "sponsors",
    "topics", "trending", "users",
}
_HF_PAPER_PATH_RE = re.compile(r"^/papers/(\d{4}\.\d{4,5})$")
_META_BLOG_PATH_RE = re.compile(r"^/blog/[^/]+/$")
_META_BLOG_DATE_RE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{1,2},\s+\d{4}\b"
)

_HIGH_SIGNAL_HEADLINE_TERMS = (
    "benchmark", "breakthrough", "funding", "acquisition", "regulation", "regulatory",
    "policy", "safety", "security", "breach", "open source", "open-source",
    "research", "paper", "arxiv", "launches model", "releases model", "llm",
    "robot", "robotics", "agent", "nvidia", "openai", "anthropic", "google",
    "meta", "microsoft", "deepmind", "hugging face", "chip", "inference",
)
_LOW_SIGNAL_HEADLINE_TERMS = (
    "webinar", "workshop", "conference recap", "how to", "guide", "tips", "top ",
    "best ", "roundup", "review", "for marketers", "for sales", "for teams",
    "all-in-one", "productivity", "crm", "seo", "landing page", "template",
    "plugin", "chrome extension", "deal", "coupon", "discount", "affiliate",
    "sponsored", "partner content",
)
_LOW_SIGNAL_SOURCE_TERMS = ("pr newswire", "business wire", "globenewswire", "accesswire")
_RESEARCH_AGGREGATOR_SOURCE_TERMS = (
    "arxiv",
    "hugging face papers",
    "papers with code",
)

# Known feed repairs for sources that changed endpoint format.
_SOURCE_FEED_REPAIRS = {
    ("Cambridge University AI", "https://www.cam.ac.uk/topics/artificial-intelligence/feed"):
        "https://www.cam.ac.uk/taxonomy/term/51032/feed",
    ("DeepMind", "https://deepmind.com/blog/feed/basic/"):
        "https://deepmind.google/blog/rss.xml",
    ("Meta AI (FAIR)", "https://ai.meta.com/blog/rss.xml"):
        META_BLOG_URL,
    ("Meta AI (FAIR)", "https://research.facebook.com/feed/"):
        META_BLOG_URL,
    ("Microsoft Research", "https://azure.microsoft.com/en-us/blog/feed/"):
        "https://www.microsoft.com/en-us/research/feed/",
}

# Some sources are handled by dedicated extractors and should not be fetched as raw RSS feeds.
_SPECIAL_SOURCE_HANDLERS = {"Meta AI (FAIR)", "Papers with Code"}


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

    if stars is None:
        logger.warning(
            "Skipped GitHub repo %s because star count could not be verified",
            repo_key,
        )
        return False

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


def _extract_meta_blog_posts_from_html(
    html_text: str,
    max_items: int = META_BLOG_LIMIT,
) -> List[Dict]:
    if not html_text:
        return []

    soup = BeautifulSoup(html_text, "html.parser")
    grouped_links: Dict[str, List] = {}

    for anchor in soup.select("a[href]"):
        href = (anchor.get("href") or "").strip()
        parsed = urlparse(href)
        host = (parsed.netloc or "").lower().replace("www.", "")
        if host and host != "ai.meta.com":
            continue
        if not _META_BLOG_PATH_RE.match(parsed.path or ""):
            continue
        canonical = f"https://ai.meta.com{parsed.path}"
        grouped_links.setdefault(canonical, []).append(anchor)

    items = []
    ignored_labels = {"featured", "learn more", "mehr dazu"}
    for canonical, anchors in grouped_links.items():
        title_candidates = []
        published_at = None

        for anchor in anchors:
            aria_label = " ".join((anchor.get("aria-label") or "").split())
            if aria_label.lower().startswith("read "):
                title_candidates.append(aria_label[5:].strip())

            anchor_text = " ".join(anchor.get_text(" ", strip=True).split())
            if len(anchor_text) >= 12 and anchor_text.lower() not in ignored_labels:
                title_candidates.append(anchor_text)

            node = anchor
            for _ in range(4):
                match = _META_BLOG_DATE_RE.search(
                    " ".join(node.get_text(" ", strip=True).split())
                )
                if match:
                    date_format = "%B %d, %Y" if len(match.group(0).split()[0]) > 3 else "%b %d, %Y"
                    published_at = datetime.strptime(match.group(0), date_format)
                    break
                if node.parent is None:
                    break
                node = node.parent

        if not title_candidates or published_at is None:
            continue

        items.append(
            {
                "title": max(title_candidates, key=len),
                "source": "Meta AI",
                "link": canonical,
                "published": published_at.isoformat(),
            }
        )

    items.sort(key=lambda item: item["published"], reverse=True)
    return items[:max_items]


def _fetch_meta_blog_posts() -> List[Dict]:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; DailyAIWireBot/1.0; +https://dailyaiwire.news)"
    }
    try:
        response = requests.get(META_BLOG_URL, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as exc:
        logger.warning("Meta AI blog fetch failed: %s", exc)
        return []
    return _extract_meta_blog_posts_from_html(
        response.text,
        max_items=META_BLOG_LIMIT,
    )


def _extract_meta_article_context(
    html_text: str,
    title: str,
    max_chars: int,
) -> str:
    if not html_text or max_chars <= 0:
        return ""

    soup = BeautifulSoup(html_text, "html.parser")
    title_terms = {
        token
        for token in re.findall(r"[a-z0-9]+", (title or "").lower())
        if len(token) >= 4
    }
    signal_terms = (
        "ai", "benchmark", "deployed", "dino", "gpu", "improved",
        "launched", "meta", "minutes", "model", "month", "open-source",
        "reduced", "released", "required", "result", "sam", "takes", "trained",
    )
    candidates = []
    sentence_index = 0

    for paragraph in soup.select("p"):
        paragraph_text = " ".join(paragraph.get_text(" ", strip=True).split())
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph_text):
            sentence = sentence.strip()
            if len(sentence) < 40:
                continue
            lowered = sentence.lower()
            if "subscribe to our newsletter" in lowered:
                continue
            sentence_terms = set(re.findall(r"[a-z0-9]+", lowered))
            score = len(title_terms & sentence_terms)
            score += sum(3 for term in signal_terms if term in lowered)
            if re.search(r"\d", sentence):
                score += 2
            candidates.append((score, sentence_index, sentence))
            sentence_index += 1

    selected = []
    used_chars = len(title) + len("Source title: \n")
    for _score, index, sentence in sorted(
        candidates,
        key=lambda candidate: (-candidate[0], candidate[1]),
    ):
        separator_chars = 1 if selected else 0
        if used_chars + separator_chars + len(sentence) > max_chars:
            continue
        selected.append((index, sentence))
        used_chars += separator_chars + len(sentence)

    selected.sort(key=lambda item: item[0])
    context = f"Source title: {title}\n" + "\n".join(
        sentence for _index, sentence in selected
    )
    return context[:max_chars]


def _enrich_meta_blog_item(item: Dict) -> Dict:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; DailyAIWireBot/1.0; +https://dailyaiwire.news)"
    }
    try:
        response = requests.get(item["link"], headers=headers, timeout=15)
        response.raise_for_status()
        context = _extract_meta_article_context(
            response.text,
            item.get("title", ""),
            max_chars=ai_config.ARTICLE_SOURCE_CHAR_LIMIT,
        )
    except Exception as exc:
        logger.warning("Meta AI article enrichment failed for %s: %s", item.get("link"), exc)
        return item

    if len(context) < 300:
        return item

    enriched = dict(item)
    enriched["pre_extracted_content"] = context
    return enriched


def _recent_meta_blog_posts(
    items: List[Dict],
    now: datetime = None,
    recency_days: int = META_BLOG_RECENCY_DAYS,
) -> List[Dict]:
    cutoff = (now or datetime.utcnow()) - timedelta(days=max(1, recency_days))
    recent = []
    for item in items:
        try:
            published_at = datetime.fromisoformat(item.get("published", ""))
        except (TypeError, ValueError):
            continue
        if published_at >= cutoff:
            recent.append(item)
    return recent


def _normalize_source_url(source_name: str, url: str) -> str:
    if not url:
        return ""
    cleaned = url.strip()
    return _SOURCE_FEED_REPAIRS.get((source_name, cleaned), cleaned)


def _repair_source_urls(conn: sqlite3.Connection, sources: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Auto-repair known broken source URLs and persist the fixed URL in DB."""
    repaired = []
    normalized_sources: List[Tuple[str, str]] = []

    for source_name, url in sources:
        normalized = _normalize_source_url(source_name, url)
        normalized_sources.append((source_name, normalized))
        if normalized and normalized != (url or "").strip():
            repaired.append((source_name, url, normalized))

    if repaired:
        for source_name, old_url, new_url in repaired:
            conn.execute(
                "UPDATE sources SET url = ? WHERE name = ? AND url = ?",
                (new_url, source_name, old_url),
            )
        conn.commit()
        for source_name, old_url, new_url in repaired:
            logger.info("🔧 Repaired source URL for %s: %s -> %s", source_name, old_url, new_url)

    return normalized_sources


def _looks_like_feed_response(resp: requests.Response) -> bool:
    content_type = (resp.headers.get("content-type") or "").lower()
    if any(tag in content_type for tag in ("xml", "rss", "atom")):
        return True
    head = (resp.text or "")[:200].lstrip().lower()
    return head.startswith("<?xml") or head.startswith("<rss") or head.startswith("<feed")


def _fetch_feed_response(url: str, headers: Dict[str, str], source_name: str):
    timeout = 15 if source_name == "Hacker News (AI)" else 10
    attempts = 2 if source_name in {"Hacker News (AI)", "Google News"} else 1
    last_err = None

    for attempt in range(1, attempts + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout + (attempt - 1) * 5)
            resp.raise_for_status()
            return resp
        except Exception as req_err:
            last_err = req_err
            if attempt < attempts:
                logger.warning(
                    "   ⚠️ %s fetch attempt %d/%d failed: %s. Retrying...",
                    source_name, attempt, attempts, req_err
                )
                time.sleep(1.2)
            else:
                raise
    raise last_err  # pragma: no cover


def _build_google_news_context(entry, title: str, source_name: str) -> str:
    summary_html = getattr(entry, "summary", "") or ""
    text = BeautifulSoup(summary_html, "html.parser").get_text(" ", strip=True)
    text = html.unescape(" ".join(text.split()))

    published = getattr(entry, "published", "") or ""
    source_href = ""
    if hasattr(entry, "source") and isinstance(entry.source, dict):
        source_href = entry.source.get("href", "") or ""

    context_lines = [
        f"Headline: {title}",
        f"Publisher: {source_name or 'Unknown'}",
    ]
    if source_href:
        context_lines.append(f"Publisher URL: {source_href}")
    if published:
        context_lines.append(f"Published: {published}")
    if text:
        context_lines.append(f"Wire digest: {text}")
    context_lines.append(
        "Context: This came through Google News wire aggregation. Use headline-level facts and publisher attribution."
    )
    return "\n".join(context_lines)


def _headline_signal_score(article: Dict) -> int:
    title = (article.get("title") or "").lower()
    source = (article.get("source") or "").lower()
    score = 0

    for term in _HIGH_SIGNAL_HEADLINE_TERMS:
        if term in title:
            score += 2

    for term in _LOW_SIGNAL_HEADLINE_TERMS:
        if term in title:
            score -= 3

    if any(term in source for term in _LOW_SIGNAL_SOURCE_TERMS):
        score -= 2

    if re.search(r"\b(series a|series b|series c|raises \$|raises €|secures \$|secures €)\b", title):
        score += 2
    if re.search(r"\b(api|sdk|framework|model|dataset|benchmark|chip|gpu)\b", title):
        score += 1
    if re.search(r"\b(tool|assistant|copilot|platform|app)\b", title):
        score -= 1

    return score


def _is_research_aggregator(article: Dict) -> bool:
    source = (article.get("source") or "").lower()
    return any(term in source for term in _RESEARCH_AGGREGATOR_SOURCE_TERMS)


def _diversify_candidate_pool(
    ranked_articles: List[Dict],
    *,
    pool_size: int,
    max_research_share: float = HEADLINE_FILTER_MAX_RESEARCH_SHARE,
) -> List[Dict]:
    """Reserve candidate-pool space for non-research news without reducing volume."""
    if pool_size <= 0:
        return []

    pool_size = min(pool_size, len(ranked_articles))
    research_limit = max(0, min(pool_size, int(pool_size * max_research_share)))
    selected = []
    deferred_research = []
    research_count = 0

    for article in ranked_articles:
        if _is_research_aggregator(article) and research_count >= research_limit:
            deferred_research.append(article)
            continue

        selected.append(article)
        if _is_research_aggregator(article):
            research_count += 1
        if len(selected) >= pool_size:
            return selected

    selected.extend(deferred_research[:pool_size - len(selected)])
    return selected


def _build_headline_filter_prompt(
    candidate_articles: List[Dict],
    recent_titles: List[str],
    target_count: int,
) -> str:
    recent_titles = [title for title in recent_titles if title]
    recent_titles = recent_titles[:HEADLINE_FILTER_RECENT_TITLES_LIMIT]
    headline_list = "\n".join([f"{idx}: {a['title']}" for idx, a in enumerate(candidate_articles)])
    recent_titles_block = "\n".join([f"- {t}" for t in recent_titles]) if recent_titles else "None"

    return (
        f"Select up to {target_count} AI news headlines worth full analysis.\n\n"
        "Reject duplicates, spam, and low-signal product fluff.\n\n"
        "Recently published titles:\n"
        f"{recent_titles_block}\n\n"
        "Candidate headlines (index: title):\n"
        f"{headline_list}\n\n"
        "Rules:\n"
        "- Exclude stories that match or closely repeat a recently published title.\n"
        '- Exclude Sponsored, Advertisement, Promoted, Affiliate, or Partner Content.\n'
        "- Prioritize breakthroughs, strategic moves, security, policy, major research, and important infrastructure releases.\n"
        "- Keep a balanced mix of research, business, policy, security, products, and infrastructure when qualified options exist.\n"
        "- Allow product launches only for major infrastructure or meaningful open-source/model releases.\n"
        "- Block generic B2B SaaS launches, wrapper apps, marketing tools, SEO tools, CRM tools, and listicles.\n"
        "- Block suicide, murder, or violence stories unless they are critical geopolitical events.\n\n"
        f"Return only comma-separated indices, for example: 0, 3, 4"
    )


def filter_high_signal_headlines(articles: List[Dict], recent_titles=None) -> List[Dict]:
    """Uses Gemini to filter for high-value AI news headlines and exclude duplicates/similar stories."""
    if recent_titles is None:
        recent_titles = []
    if not articles:
        return []

    logger.info("AI Pre-Filtering %d headlines for signal quality and deduplication...", len(articles))

    # OPTIMIZATION: If we have very few articles, don't waste an AI call filtering them.
    if len(articles) <= 5:
        logger.info("Skipping AI filter (Small batch: %d articles). processing all.", len(articles))
        return articles

    # Keep a moderate candidate flow now that article prompts stay in the cheap short-input bucket.
    target_count = min(12, max(8, len(articles) // 4))

    scored_articles = sorted(
        [(_headline_signal_score(article), article) for article in articles],
        key=lambda item: item[0],
        reverse=True,
    )
    non_negative_articles = [article for score, article in scored_articles if score >= 0]
    ranked_articles = [article for _score, article in scored_articles]
    candidate_pool_size = min(len(ranked_articles), max(target_count * 2, 12))
    if non_negative_articles:
        candidate_articles = _diversify_candidate_pool(
            non_negative_articles,
            pool_size=candidate_pool_size,
        )
    else:
        candidate_articles = _diversify_candidate_pool(
            ranked_articles,
            pool_size=candidate_pool_size,
        )
    if len(candidate_articles) < len(articles):
        logger.info(
            "Heuristic pre-filter trimmed %d headlines to top %d candidates before AI ranking.",
            len(articles),
            len(candidate_articles),
        )

    prompt = _build_headline_filter_prompt(candidate_articles, recent_titles, target_count)

    try:
        model_name = ai_config.ROUTINE_MODEL
        logger.info("⚡ using AI Model (Filter): %s", model_name)

        # Budget Check
        estimated_tokens = len(prompt) // 4 + 500
        if not budget.can_make_request(estimated_tokens):
             logger.warning("Skipping filter due to budget.")
             return articles[:8]  # Fallback

        gateway = AIGateway(
            model_name=model_name,
            generation_config={"temperature": 0},
            thinking_budget=ai_config.ROUTINE_THINKING_BUDGET,
            logger_name='fetcher.sources',
        )
        text, response = gateway.generate_text(
            prompt,
            prompt_type="headline_filter",
            request_options={'timeout': 120},
        )

        # Log Usage
        if hasattr(response, 'usage_metadata'):
             budget.log_request(
                 getattr(response.usage_metadata, 'prompt_token_count', 0),
                 getattr(response.usage_metadata, 'candidates_token_count', 0),
                 category="Headline Filter"
             )

        text = text.replace('Indices:', '').strip()
        indices = [int(i.strip()) for i in text.split(',') if i.strip().isdigit()]

        filtered = [candidate_articles[i] for i in indices if i < len(candidate_articles)]
        if not filtered:
            logger.warning("AI filter returned no valid indices. Falling back to top %d.", target_count)
            return candidate_articles[:target_count]
        filtered = filtered[:target_count]
        logger.info("Filtered down to %d high-signal articles (target=%d).", len(filtered), target_count)
        return filtered
    except Exception as e:
        logger.error("Headline filtering failed: %s. Proceeding with first %d articles as fallback.", e, target_count)
        return candidate_articles[:target_count]


def _is_duplicate_of_recent_title(candidate_title: str, recent_title: str) -> bool:
    return likely_same_story(candidate_title, recent_title)


def _is_known_article_link(
    link: str,
    unique_articles: Dict[str, Dict],
    existing_urls: set[str],
    known_research_ids: set[str],
) -> bool:
    if link in unique_articles or link in existing_urls:
        return True
    paper_id = canonical_research_paper_id(link)
    return bool(paper_id and paper_id in known_research_ids)


def _remember_research_paper(link: str, known_research_ids: set[str]) -> None:
    paper_id = canonical_research_paper_id(link)
    if paper_id:
        known_research_ids.add(paper_id)


def fetch_all_sources() -> List[Dict]:
    """Fetches news from multiple specific AI feeds and Google News."""
    # 1. Fetch Active Sources from DB
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name, url FROM sources WHERE is_active = 1 AND url IS NOT NULL AND url != '' AND url != 'None'")
        sources = cursor.fetchall()
        sources = _repair_source_urls(conn, sources)
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
    active_source_names = {name for name, _url in sources}

    if not sources:
        logger.warning("⚠️ No active sources found in DB.")
        return []

    logger.info("📡 Scanning %d active sources...", len(sources))

    unique_articles = {}
    source_health = {
        "scanned": 0,
        "connection_errors": 0,
        "non_feed": 0,
        "empty_feed": 0,
        "added": 0,
    }

    # PRE-FETCH: Get existing URLs from DB to avoid re-processing
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT source_url FROM articles")
    existing_urls = {row[0] for row in cursor.fetchall()}
    conn.close()
    known_research_ids = {
        paper_id
        for source_url in existing_urls
        if (paper_id := canonical_research_paper_id(source_url))
    }

    quality_conn = sqlite3.connect(DB_PATH)
    _ensure_repo_quality_cache_schema(quality_conn)

    # GET STATE: Only fetch articles after last scan
    last_scan = get_last_scan_timestamp()
    logger.info("📡 Only scanning news published since: %s", last_scan.strftime('%Y-%m-%d %H:%M:%S'))

    for source_name, url in sources:
        source_health["scanned"] += 1

        if source_name in _SPECIAL_SOURCE_HANDLERS:
            logger.info("Skipping direct RSS fetch for %s (handled by dedicated extractor).", source_name)
            continue

        logger.info("Fetching from %s...", source_name)
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            try:
                resp = _fetch_feed_response(url, headers, source_name)
                if not _looks_like_feed_response(resp):
                    logger.warning(
                        "   ⚠️ %s returned non-feed content-type (%s). Skipping source URL: %s",
                        source_name,
                        resp.headers.get("content-type", "unknown"),
                        url,
                    )
                    source_health["non_feed"] += 1
                    continue
                feed = feedparser.parse(resp.content)
            except Exception as req_err:
                logger.warning("   ⚠️ Connection error for %s: %s", source_name, req_err)
                source_health["connection_errors"] += 1
                continue

            entries = feed.entries[:30] if source_name == "Google News" else feed.entries
            if not entries:
                source_health["empty_feed"] += 1

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
                if not _is_known_article_link(
                    link,
                    unique_articles,
                    existing_urls,
                    known_research_ids,
                ):
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

                    # GOOGLE NEWS: avoid scraping consent/redirect pages by using wire context directly.
                    if source_name == "Google News":
                        article_dict['pre_extracted_content'] = _build_google_news_context(
                            entry, title, real_source
                        )

                    unique_articles[link] = article_dict
                    _remember_research_paper(link, known_research_ids)
                    added_count += 1

            source_health["added"] += added_count
            logger.info("   ↳ %d entries found. %d new, %d skipped (old).", len(entries), added_count, skipped_count)

        except Exception as e:
            logger.error("Error fetching %s: %s", source_name, e)

    if "Meta AI (FAIR)" in active_source_names:
        meta_added = 0
        meta_items = _recent_meta_blog_posts(_fetch_meta_blog_posts())
        for item in meta_items:
            item = _enrich_meta_blog_item(item)
            link = item["link"]
            if _is_known_article_link(
                link,
                unique_articles,
                existing_urls,
                known_research_ids,
            ):
                continue
            unique_articles[link] = item
            _remember_research_paper(link, known_research_ids)
            meta_added += 1
        logger.info("Added %d candidates from the Meta AI blog.", meta_added)
        source_health["added"] += meta_added

    # Hugging Face papers ingestion improves coverage beyond blog posts only.
    hf_added = 0
    for item in _fetch_huggingface_papers():
        link = item["link"]
        if _is_known_article_link(
            link,
            unique_articles,
            existing_urls,
            known_research_ids,
        ):
            continue
        unique_articles[link] = item
        _remember_research_paper(link, known_research_ids)
        hf_added += 1
    if hf_added:
        logger.info("Added %d candidates from Hugging Face papers.", hf_added)
        source_health["added"] += hf_added

    logger.info(
        "📊 Source health: scanned=%d added=%d connection_errors=%d non_feed=%d empty_feed=%d",
        source_health["scanned"],
        source_health["added"],
        source_health["connection_errors"],
        source_health["non_feed"],
        source_health["empty_feed"],
    )

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

            if _is_duplicate_of_recent_title(clean_title, recent):
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
