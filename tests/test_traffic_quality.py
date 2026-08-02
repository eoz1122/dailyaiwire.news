import sqlite3

import pytest

from services.traffic_quality import (
    get_traffic_anomaly_summary,
    is_likely_bot,
    reclassify_known_bot_views,
)


@pytest.mark.parametrize(
    "user_agent",
    [
        "DailyAIWire-Monitor/1.0",
        "DailyAIWire-LinkAudit/1.0",
        "DailyAIWire-DeployVerify/1.0",
        "Scrapy/2.16.0 (+https://scrapy.org)",
        "Googlebot/2.1 (+http://www.google.com/bot.html)",
    ],
)
def test_known_automation_user_agents_are_bots(user_agent):
    assert is_likely_bot(user_agent) is True


def test_normal_browser_user_agent_is_not_a_bot():
    assert is_likely_bot(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/146.0.0.0 Safari/537.36"
    ) is False


def test_prefetch_is_not_counted_as_human_traffic():
    assert is_likely_bot("Mozilla/5.0 Legit Browser", purpose="prefetch") is True


def test_reclassify_known_bot_views_is_idempotent():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            verified_views INTEGER DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE article_view_events (
            id INTEGER PRIMARY KEY,
            article_id INTEGER NOT NULL,
            user_agent TEXT,
            is_bot INTEGER DEFAULT 0,
            counted_verified INTEGER DEFAULT 0
        )
        """
    )
    conn.execute("INSERT INTO articles (id, verified_views) VALUES (1, 5)")
    conn.executemany(
        """
        INSERT INTO article_view_events (
            id, article_id, user_agent, is_bot, counted_verified
        ) VALUES (?, 1, ?, ?, ?)
        """,
        [
            (1, "DailyAIWire-Monitor/1.0", 0, 1),
            (2, "Scrapy/2.16.0 (+https://scrapy.org)", 0, 1),
            (3, "Mozilla/5.0 Legit Browser", 0, 1),
            (4, "Googlebot/2.1", 1, 0),
            (5, "DailyAIWire-LinkAudit/1.0", 0, 1),
        ],
    )

    preview = reclassify_known_bot_views(conn, apply=False)
    assert preview == {"events": 3, "verified_views_removed": 3, "articles": 1}
    assert conn.execute(
        "SELECT verified_views FROM articles WHERE id = 1"
    ).fetchone()[0] == 5

    applied = reclassify_known_bot_views(conn, apply=True)
    assert applied == preview
    assert conn.execute(
        "SELECT verified_views FROM articles WHERE id = 1"
    ).fetchone()[0] == 2
    assert conn.execute(
        "SELECT is_bot, counted_verified FROM article_view_events WHERE id = 1"
    ).fetchone() == (1, 0)

    repeated = reclassify_known_bot_views(conn, apply=True)
    assert repeated == {"events": 0, "verified_views_removed": 0, "articles": 0}
    assert conn.execute(
        "SELECT verified_views FROM articles WHERE id = 1"
    ).fetchone()[0] == 2
    conn.close()


def test_traffic_anomaly_summary_flags_volume_and_speed_without_identifiers():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE article_view_events (
            id INTEGER PRIMARY KEY,
            article_id INTEGER NOT NULL,
            visitor_hash TEXT NOT NULL,
            user_agent TEXT,
            is_bot INTEGER DEFAULT 0,
            counted_verified INTEGER DEFAULT 0,
            viewed_at TIMESTAMP
        )
        """
    )
    event_id = 0
    for visitor, count, minute_step in (
        ("volume-visitor-secret", 25, 2),
        ("burst-visitor-secret", 12, 0.25),
        ("normal-visitor-secret", 5, 30),
    ):
        for index in range(count):
            event_id += 1
            conn.execute(
                """
                INSERT INTO article_view_events (
                    id, article_id, visitor_hash, user_agent, is_bot,
                    counted_verified, viewed_at
                ) VALUES (
                    ?, ?, ?, ?, 0, 1,
                    datetime('now', 'start of day', '-1 day', '+12 hours', ?)
                )
                """,
                (
                    event_id,
                    event_id,
                    visitor,
                    "Mozilla/5.0 Test Browser",
                    f"-{120 - (index * minute_step)} minutes",
                ),
            )

    summary = get_traffic_anomaly_summary(conn, days=7)

    assert summary["flagged_sessions"] == 2
    assert summary["high_volume_sessions"] == 1
    assert summary["fast_burst_sessions"] == 1
    assert summary["observed_excess_views"] == 5
    assert {row["visitor_id"] for row in summary["rows"]} == {
        "volume-vis",
        "burst-visi",
    }
    assert "secret" not in repr(summary)
    conn.close()
