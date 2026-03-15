"""
Fetcher — Spam Defense Layer
Keyword filtering, heuristic microsites detection, and dynamic blocklist checks.
"""
import re
import sqlite3
import logging

from db import get_db_connection, DB_PATH

logger = logging.getLogger('fetcher.spam')


def is_spam(title: str) -> bool:
    """Checks if a title contains spammy keywords."""
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
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT domain FROM blocked_sources")
        blocked_db = [row[0].lower() for row in cur.fetchall()]
        conn.close()

        if any(b in source_name.lower() for b in blocked_db):
            return True

    except Exception:
        pass  # If DB fails, fallback to allowing

    return False


def is_spam_source(url, title):
    """
    Multi-layered defense against SEO spam and parasitical microsites.
    """
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower()

    # Layer 1: Database Blacklist
    conn = get_db_connection()
    try:
        blocked = conn.execute("SELECT 1 FROM blocked_sources WHERE domain = ?", (domain,)).fetchone()
        if blocked:
            logger.info("🛡️ Blocked Source (DB): %s", domain)
            return True
    except Exception as e:
        logger.error("Error checking blocked sources DB: %s", e)
    finally:
        conn.close()

    # Layer 2: Heuristic Patterns (Microsites)
    spam_patterns = [
        r'[a-z]+-\d+(\.\w+)$',  # e.g., wan2-6.org
        r'gpt-\d',              # e.g., gpt-5-news
        r'gemini-\d',           # e.g., gemini-2-guide
    ]

    for pattern in spam_patterns:
        if re.search(pattern, domain):
            logger.info("🛡️ Blocked Source (Heuristic): %s matches spam pattern.", domain)
            return True

    return False
