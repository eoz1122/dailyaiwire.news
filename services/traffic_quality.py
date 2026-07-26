import re
import sqlite3
from collections import defaultdict


KNOWN_AUTOMATION_UA_FRAGMENTS = (
    "dailyaiwire-",
    "scrapy/",
)
BOT_UA_PATTERN = re.compile(
    r"(bot|spider|crawl|slurp|headless|facebookexternalhit|whatsapp|telegrambot|"
    r"linkedinbot|python-requests|curl|wget|uptimerobot|datadog|pingdom|"
    r"dailyaiwire-|scrapy/)",
    re.IGNORECASE,
)
TRAFFIC_ANOMALY_DAILY_ARTICLE_LIMIT = 20
TRAFFIC_ANOMALY_BURST_ARTICLES = 10
TRAFFIC_ANOMALY_BURST_MINUTES = 15


def is_likely_bot(
    user_agent: str,
    *,
    purpose: str = "",
    sec_purpose: str = "",
) -> bool:
    if not user_agent:
        return True
    if BOT_UA_PATTERN.search(user_agent):
        return True
    return "prefetch" in f"{purpose} {sec_purpose}".lower()


def reclassify_known_bot_views(conn, *, apply: bool = False) -> dict[str, int]:
    where = " OR ".join(
        "lower(COALESCE(user_agent, '')) LIKE ?"
        for _ in KNOWN_AUTOMATION_UA_FRAGMENTS
    )
    params = tuple(f"%{fragment}%" for fragment in KNOWN_AUTOMATION_UA_FRAGMENTS)
    rows = conn.execute(
        f"""
        SELECT id, article_id, counted_verified
        FROM article_view_events
        WHERE (COALESCE(is_bot, 0) = 0 OR COALESCE(counted_verified, 0) = 1)
          AND ({where})
        """,
        params,
    ).fetchall()

    removed_by_article = defaultdict(int)
    affected_articles = set()
    for row in rows:
        event_id, article_id, counted_verified = row
        affected_articles.add(article_id)
        if counted_verified:
            removed_by_article[article_id] += 1

    if apply and rows:
        conn.executemany(
            """
            UPDATE article_view_events
            SET is_bot = 1, counted_verified = 0
            WHERE id = ?
            """,
            [(row[0],) for row in rows],
        )
        conn.executemany(
            """
            UPDATE articles
            SET verified_views = MAX(
                0,
                COALESCE(verified_views, 0) - ?
            )
            WHERE id = ?
            """,
            [
                (removed_count, article_id)
                for article_id, removed_count in removed_by_article.items()
            ],
        )

    return {
        "events": len(rows),
        "verified_views_removed": sum(removed_by_article.values()),
        "articles": len(affected_articles),
    }


def get_traffic_anomaly_summary(
    conn,
    *,
    days: int = 7,
    row_limit: int = 10,
) -> dict:
    days = min(max(int(days), 1), 90)
    row_limit = min(max(int(row_limit), 1), 50)
    empty = {
        "days": days,
        "daily_article_limit": TRAFFIC_ANOMALY_DAILY_ARTICLE_LIMIT,
        "burst_articles": TRAFFIC_ANOMALY_BURST_ARTICLES,
        "burst_minutes": TRAFFIC_ANOMALY_BURST_MINUTES,
        "flagged_sessions": 0,
        "high_volume_sessions": 0,
        "fast_burst_sessions": 0,
        "observed_excess_views": 0,
        "rows": [],
    }

    try:
        rows = conn.execute(
            """
            WITH visitor_days AS (
                SELECT
                    visitor_hash,
                    date(viewed_at) AS viewed_on,
                    COUNT(DISTINCT article_id) AS article_count,
                    MIN(viewed_at) AS first_seen,
                    MAX(viewed_at) AS last_seen,
                    MIN(COALESCE(user_agent, 'Unknown')) AS user_agent
                FROM article_view_events
                WHERE counted_verified = 1
                  AND COALESCE(is_bot, 0) = 0
                  AND viewed_at >= datetime('now', ?)
                GROUP BY visitor_hash, date(viewed_at)
            ),
            scored AS (
                SELECT *,
                    ROUND(
                        (julianday(last_seen) - julianday(first_seen)) * 1440,
                        1
                    ) AS elapsed_minutes
                FROM visitor_days
            )
            SELECT
                visitor_hash,
                viewed_on,
                article_count,
                elapsed_minutes,
                user_agent
            FROM scored
            WHERE article_count > ?
               OR (
                    article_count >= ?
                    AND elapsed_minutes <= ?
               )
            ORDER BY article_count DESC, elapsed_minutes ASC
            """,
            (
                f"-{days} days",
                TRAFFIC_ANOMALY_DAILY_ARTICLE_LIMIT,
                TRAFFIC_ANOMALY_BURST_ARTICLES,
                TRAFFIC_ANOMALY_BURST_MINUTES,
            ),
        ).fetchall()
    except sqlite3.OperationalError:
        return empty

    normalized = []
    high_volume_sessions = 0
    fast_burst_sessions = 0
    observed_excess_views = 0
    for row in rows:
        visitor_hash, viewed_on, article_count, elapsed_minutes, user_agent = row
        article_count = int(article_count or 0)
        elapsed_minutes = float(elapsed_minutes or 0)
        is_high_volume = article_count > TRAFFIC_ANOMALY_DAILY_ARTICLE_LIMIT
        is_fast_burst = (
            article_count >= TRAFFIC_ANOMALY_BURST_ARTICLES
            and elapsed_minutes <= TRAFFIC_ANOMALY_BURST_MINUTES
        )
        high_volume_sessions += int(is_high_volume)
        fast_burst_sessions += int(is_fast_burst)
        observed_excess_views += max(
            0,
            article_count - TRAFFIC_ANOMALY_DAILY_ARTICLE_LIMIT,
        )
        normalized.append(
            {
                "visitor_id": str(visitor_hash or "")[:10],
                "viewed_on": viewed_on,
                "article_count": article_count,
                "elapsed_minutes": elapsed_minutes,
                "user_agent": str(user_agent or "Unknown")[:100],
                "high_volume": is_high_volume,
                "fast_burst": is_fast_burst,
            }
        )

    return {
        **empty,
        "flagged_sessions": len(rows),
        "high_volume_sessions": high_volume_sessions,
        "fast_burst_sessions": fast_burst_sessions,
        "observed_excess_views": observed_excess_views,
        "rows": normalized[:row_limit],
    }
