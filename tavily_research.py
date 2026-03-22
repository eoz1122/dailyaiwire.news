"""
Deep Research Layer — DailyAIWire.news
Web research enrichment for high-signal articles using DuckDuckGo Search.

Completely free — no API key, no credit limits.
Triggered only for articles with importance_score >= 80 to avoid
slowing down the pipeline with unnecessary network calls.

Per AIRULES.md §1: 100% free solution.
"""
import logging
import time
from typing import Dict, Optional

logger = logging.getLogger('tavily_research')


def deep_research(title: str, gist: str, source_url: str = "") -> Optional[Dict]:
    """
    Perform deep web research for a high-signal article using DuckDuckGo.

    Returns:
        {
            "query": str,
            "sources": [{"title": str, "url": str, "snippet": str}],
            "context": str,         # Concatenated research context for AI prompt
            "source_count": int
        }
        Returns None on failure (never blocks pipeline).
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        logger.warning("⚠️ duckduckgo-search not installed. Run: pip install duckduckgo-search")
        return None

    # Build a targeted search query
    query = f"{title} official announcement documentation"

    try:
        ddgs = DDGS()

        # Rate limit politeness
        time.sleep(1)

        results = ddgs.text(
            query,
            max_results=5,
            safesearch="moderate"
        )

        if not results:
            logger.debug("🔍 Deep Research: No results for '%s...'", title[:50])
            return None

        # Filter out self-references and low-value sources
        exclude_domains = [
            "dailyaiwire.news", "reddit.com", "twitter.com",
            "x.com", "facebook.com", "instagram.com", "tiktok.com"
        ]

        sources = []
        for r in results:
            url = r.get('href', r.get('link', ''))
            if any(d in url.lower() for d in exclude_domains):
                continue

            sources.append({
                "title": r.get('title', ''),
                "url": url,
                "snippet": r.get('body', r.get('snippet', ''))[:500]
            })

        if not sources:
            return None

        # Build context block for the AI prompt
        context_parts = []
        for i, src in enumerate(sources[:3], 1):
            context_parts.append(
                f"SOURCE {i}: [{src['title']}]({src['url']})\n{src['snippet']}"
            )

        context = "\n\n".join(context_parts)

        logger.info("🔬 Deep Research: Found %d sources for '%s...'", len(sources), title[:50])

        return {
            "query": query,
            "sources": sources,
            "context": context,
            "source_count": len(sources)
        }

    except Exception as e:
        logger.warning("⚠️ Deep research failed (non-blocking): %s", e)
        return None
