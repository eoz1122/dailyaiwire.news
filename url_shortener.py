"""
URL Shortener — DailyAIWire.news
Wraps the self-hosted Kutt API to shorten outgoing article URLs.
Falls back gracefully to the original URL on any failure.
"""
import os
import logging

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger('url_shortener')

KUTT_API_URL = os.getenv("KUTT_API_URL", "").rstrip("/")
KUTT_API_KEY = os.getenv("KUTT_API_KEY", "")

# Cache to avoid re-shortening the same URL in one process lifetime
_cache: dict[str, str] = {}


def shorten(long_url: str) -> str:
    """Shorten a URL via the Kutt API.

    Returns the shortened URL on success, or the original URL on any failure.
    This ensures social posts are never blocked by a shortener outage.
    """
    if not KUTT_API_URL or not KUTT_API_KEY:
        return long_url

    if long_url in _cache:
        return _cache[long_url]

    try:
        resp = requests.post(
            f"{KUTT_API_URL}/api/v2/links",
            json={"target": long_url},
            headers={
                "X-API-Key": KUTT_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=5,
        )

        if resp.status_code in (200, 201):
            data = resp.json()
            short = data.get("link", long_url)
            _cache[long_url] = short
            logger.info("🔗 Shortened: %s → %s", long_url[:60], short)
            return short

        logger.warning("⚠️ Kutt API returned %d: %s", resp.status_code, resp.text[:200])
        return long_url

    except requests.exceptions.Timeout:
        logger.warning("⚠️ Kutt API timeout — using original URL")
        return long_url
    except requests.exceptions.RequestException as e:
        logger.warning("⚠️ Kutt API error: %s — using original URL", e)
        return long_url
    except Exception as e:
        logger.warning("⚠️ URL shortener unexpected error: %s", e)
        return long_url
