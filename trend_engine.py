"""
Trend Intelligence Engine for DailyAIWire.

SQL-driven trend detection using rolling time-window comparisons.
No external dependencies — works with SQLite only.

Analyzes: category velocity, hashtag frequency, emerging keywords.
"""

import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional


# Common English stopwords for keyword extraction
STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'is', 'it', 'its', 'that', 'this', 'was',
    'are', 'be', 'has', 'have', 'had', 'not', 'will', 'can', 'do', 'does',
    'how', 'what', 'when', 'where', 'who', 'why', 'all', 'each', 'every',
    'as', 'if', 'than', 'up', 'out', 'so', 'no', 'just', 'about', 'into',
    'over', 'after', 'new', 'more', 'could', 'say', 'says', 'said',
    'also', 'may', 'would', 'should', 'now', 'like', 'get', 'make',
    'first', 'been', 'only', 'some', 'them', 'their', 'then', 'being',
    'most', 'our', 'you', 'your', 'we', 'they', 'he', 'she', 'his', 'her',
    'i', 'me', 'my', 'us', 'while', 'between', 'through', 'before',
    'use', 'used', 'using', 'here', 'there', 'these', 'those', 'own',
    'other', 'well', 'very', 'still', 'even', 'much', 'many', 'such',
    'way', 'part', 'set', 'big', 'take', 'top', 'per', 'go', 'look',
    'see', 'come', 'want', 'give', 'one', 'two', 'three', 'year', 'years',
    'report', 'reports', 'according', 'across'
}


def _velocity(current: int, previous: int) -> Dict:
    """Calculate velocity percentage and direction label."""
    if previous == 0:
        pct = 100.0 if current > 0 else 0.0
    else:
        pct = round(((current - previous) / previous) * 100, 1)

    if pct > 50:
        direction = "surging"
        emoji = "🚀"
    elif pct > 10:
        direction = "rising"
        emoji = "📈"
    elif pct > -10:
        direction = "stable"
        emoji = "➡️"
    else:
        direction = "declining"
        emoji = "📉"

    return {
        "velocity_pct": pct,
        "direction": direction,
        "emoji": emoji
    }


def get_trending_categories(conn, days: int = 7) -> List[Dict]:
    """
    Compare article counts per category: last N days vs previous N days.
    Returns categories sorted by velocity (highest surge first).
    """
    now = datetime.utcnow()
    current_start = (now - timedelta(days=days)).strftime('%Y-%m-%d')
    previous_start = (now - timedelta(days=days * 2)).strftime('%Y-%m-%d')
    current_end = now.strftime('%Y-%m-%d %H:%M:%S')

    # Current window
    current_counts = {}
    rows = conn.execute("""
        SELECT category, COUNT(*) as cnt
        FROM articles
        WHERE is_published = 1
          AND category IS NOT NULL
          AND DATE(published_at) >= ?
        GROUP BY category
    """, (current_start,)).fetchall()
    for r in rows:
        current_counts[r['category']] = r['cnt']

    # Previous window
    previous_counts = {}
    rows = conn.execute("""
        SELECT category, COUNT(*) as cnt
        FROM articles
        WHERE is_published = 1
          AND category IS NOT NULL
          AND DATE(published_at) >= ?
          AND DATE(published_at) < ?
        GROUP BY category
    """, (previous_start, current_start)).fetchall()
    for r in rows:
        previous_counts[r['category']] = r['cnt']

    # Combine
    all_cats = set(list(current_counts.keys()) + list(previous_counts.keys()))
    trends = []
    for cat in all_cats:
        curr = current_counts.get(cat, 0)
        prev = previous_counts.get(cat, 0)
        vel = _velocity(curr, prev)
        trends.append({
            "category": cat,
            "count_current": curr,
            "count_previous": prev,
            **vel
        })

    # Sort by velocity descending, then by current count
    trends.sort(key=lambda t: (t['velocity_pct'], t['count_current']), reverse=True)
    return trends


def get_trending_hashtags(conn, days: int = 7, top_n: int = 10) -> List[Dict]:
    """
    Extract and count individual hashtags, compare windows.
    Returns top N by velocity.
    """
    now = datetime.utcnow()
    current_start = (now - timedelta(days=days)).strftime('%Y-%m-%d')
    previous_start = (now - timedelta(days=days * 2)).strftime('%Y-%m-%d')

    def _extract_hashtags(start_date, end_date=None):
        """Count hashtag frequency in a date window."""
        if end_date:
            rows = conn.execute("""
                SELECT hashtags FROM articles
                WHERE is_published = 1
                  AND hashtags IS NOT NULL AND hashtags != '[]'
                  AND DATE(published_at) >= ? AND DATE(published_at) < ?
            """, (start_date, end_date)).fetchall()
        else:
            rows = conn.execute("""
                SELECT hashtags FROM articles
                WHERE is_published = 1
                  AND hashtags IS NOT NULL AND hashtags != '[]'
                  AND DATE(published_at) >= ?
            """, (start_date,)).fetchall()

        counts = {}
        for r in rows:
            try:
                tags = json.loads(r['hashtags']) if isinstance(r['hashtags'], str) else r['hashtags']
                for tag in tags:
                    clean = tag.strip().lstrip('#').lower()
                    if clean and len(clean) > 2:
                        counts[clean] = counts.get(clean, 0) + 1
            except (json.JSONDecodeError, TypeError):
                continue
        return counts

    current_tags = _extract_hashtags(current_start)
    previous_tags = _extract_hashtags(previous_start, current_start)

    all_tags = set(list(current_tags.keys()) + list(previous_tags.keys()))
    trends = []
    for tag in all_tags:
        curr = current_tags.get(tag, 0)
        prev = previous_tags.get(tag, 0)
        if curr == 0 and prev == 0:
            continue
        vel = _velocity(curr, prev)
        trends.append({
            "hashtag": f"#{tag}",
            "count_current": curr,
            "count_previous": prev,
            **vel
        })

    trends.sort(key=lambda t: (t['velocity_pct'], t['count_current']), reverse=True)
    return trends[:top_n]


def get_trending_keywords(conn, days: int = 7, top_n: int = 8) -> List[Dict]:
    """
    Extract frequent title words from recent articles vs previous window.
    Returns emerging keywords with velocity.
    """
    now = datetime.utcnow()
    current_start = (now - timedelta(days=days)).strftime('%Y-%m-%d')
    previous_start = (now - timedelta(days=days * 2)).strftime('%Y-%m-%d')

    def _extract_keywords(start_date, end_date=None):
        """Count word frequency from titles in a date window."""
        if end_date:
            rows = conn.execute("""
                SELECT title FROM articles
                WHERE is_published = 1 AND title IS NOT NULL
                  AND DATE(published_at) >= ? AND DATE(published_at) < ?
            """, (start_date, end_date)).fetchall()
        else:
            rows = conn.execute("""
                SELECT title FROM articles
                WHERE is_published = 1 AND title IS NOT NULL
                  AND DATE(published_at) >= ?
            """, (start_date,)).fetchall()

        counts = {}
        for r in rows:
            words = re.findall(r'[a-zA-Z]{3,}', r['title'].lower())
            for word in words:
                if word not in STOPWORDS and len(word) > 3:
                    counts[word] = counts.get(word, 0) + 1
        return counts

    current_kw = _extract_keywords(current_start)
    previous_kw = _extract_keywords(previous_start, current_start)

    all_kw = set(list(current_kw.keys()) + list(previous_kw.keys()))
    trends = []
    for kw in all_kw:
        curr = current_kw.get(kw, 0)
        prev = previous_kw.get(kw, 0)
        if curr < 2:  # Minimum frequency to be "trending"
            continue
        vel = _velocity(curr, prev)
        trends.append({
            "keyword": kw.title(),
            "count_current": curr,
            "count_previous": prev,
            **vel
        })

    trends.sort(key=lambda t: (t['velocity_pct'], t['count_current']), reverse=True)
    return trends[:top_n]


def get_trend_snapshot(conn) -> Dict:
    """
    Full trend snapshot combining categories, hashtags, and keywords.
    Designed for single pass to template.
    """
    categories = get_trending_categories(conn)
    hashtags = get_trending_hashtags(conn)
    keywords = get_trending_keywords(conn)

    # Filter to only interesting trends (surging or rising)
    hot_categories = [c for c in categories if c['direction'] in ('surging', 'rising')]
    hot_hashtags = [h for h in hashtags if h['direction'] in ('surging', 'rising')]
    hot_keywords = [k for k in keywords if k['direction'] in ('surging', 'rising')]

    # Total article count for context
    total = conn.execute("SELECT COUNT(*) FROM articles WHERE is_published = 1").fetchone()[0]

    return {
        "categories": categories,
        "hashtags": hashtags,
        "keywords": keywords,
        "hot_categories": hot_categories,
        "hot_hashtags": hot_hashtags,
        "hot_keywords": hot_keywords,
        "total_articles": total,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "has_trends": len(hot_categories) + len(hot_hashtags) + len(hot_keywords) > 2
    }
