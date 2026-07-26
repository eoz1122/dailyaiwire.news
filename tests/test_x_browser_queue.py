import sqlite3
from datetime import datetime, timedelta, timezone


def _create_articles_table(conn):
    conn.execute(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            category TEXT,
            why_it_matters TEXT,
            importance_score INTEGER DEFAULT 50,
            published_at TEXT NOT NULL,
            is_published INTEGER DEFAULT 1,
            shared_on_x INTEGER DEFAULT 0,
            shared_at TEXT
        )
        """
    )


def _insert_article(conn, slug, category, score, published_at):
    conn.execute(
        """
        INSERT INTO articles (
            slug, title, category, why_it_matters, importance_score, published_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            slug,
            slug.replace("-", " ").title(),
            category,
            f"{slug} matters now.",
            score,
            published_at,
        ),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def test_next_candidate_prefers_category_diversity(tmp_path):
    from services.x_browser_queue import ensure_schema, select_next_candidate

    now = datetime(2026, 7, 25, 18, 0, tzinfo=timezone.utc)
    db_path = tmp_path / "news.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _create_articles_table(conn)
    ensure_schema(conn)

    highest_id = _insert_article(
        conn, "highest-policy", "Policy", 99, (now - timedelta(hours=2)).isoformat()
    )
    diverse_id = _insert_article(
        conn, "diverse-enterprise", "Enterprise", 85, (now - timedelta(hours=3)).isoformat()
    )
    conn.execute(
        """
        INSERT INTO x_browser_post_audit (
            article_id, article_slug, category, status, x_status_url, posted_at
        ) VALUES (?, ?, ?, 'POSTED', ?, ?)
        """,
        (9001, "previous-policy", "Policy", "https://x.com/status/1", now.isoformat()),
    )
    conn.commit()

    candidate = select_next_candidate(conn, now=now, lookback_hours=48)

    assert candidate["id"] == diverse_id
    assert candidate["id"] != highest_id


def test_mark_posted_is_transactional_and_audited(tmp_path):
    from services.x_browser_queue import ensure_schema, mark_posted

    now = datetime(2026, 7, 25, 18, 0, tzinfo=timezone.utc)
    db_path = tmp_path / "news.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _create_articles_table(conn)
    ensure_schema(conn)
    article_id = _insert_article(
        conn, "confirmed-post", "Research", 90, (now - timedelta(hours=1)).isoformat()
    )
    conn.commit()

    mark_posted(
        conn,
        article_id=article_id,
        x_status_url="https://x.com/DailyAIWireNews/status/123",
        posted_at=now,
    )

    article = conn.execute(
        "SELECT shared_on_x, shared_at FROM articles WHERE id = ?", (article_id,)
    ).fetchone()
    audit = conn.execute(
        "SELECT status, x_status_url FROM x_browser_post_audit WHERE article_id = ?",
        (article_id,),
    ).fetchone()
    assert article["shared_on_x"] == 1
    assert article["shared_at"] == now.isoformat()
    assert dict(audit) == {
        "status": "POSTED",
        "x_status_url": "https://x.com/DailyAIWireNews/status/123",
    }


def test_mark_failed_does_not_mark_article_shared(tmp_path):
    from services.x_browser_queue import ensure_schema, mark_failed

    now = datetime(2026, 7, 25, 18, 0, tzinfo=timezone.utc)
    db_path = tmp_path / "news.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _create_articles_table(conn)
    ensure_schema(conn)
    article_id = _insert_article(
        conn, "failed-post", "Models", 90, (now - timedelta(hours=1)).isoformat()
    )
    conn.commit()

    mark_failed(conn, article_id=article_id, reason="Browser confirmation missing", attempted_at=now)

    article = conn.execute(
        "SELECT shared_on_x FROM articles WHERE id = ?", (article_id,)
    ).fetchone()
    audit = conn.execute(
        "SELECT status, failure_reason FROM x_browser_post_audit WHERE article_id = ?",
        (article_id,),
    ).fetchone()
    assert article["shared_on_x"] == 0
    assert dict(audit) == {
        "status": "FAILED",
        "failure_reason": "Browser confirmation missing",
    }


def test_next_candidate_skips_recent_failures_but_allows_old_retries(tmp_path):
    from services.x_browser_queue import ensure_schema, select_next_candidate

    now = datetime(2026, 7, 25, 18, 0, tzinfo=timezone.utc)
    db_path = tmp_path / "news.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _create_articles_table(conn)
    ensure_schema(conn)

    recent_failure_id = _insert_article(
        conn, "recent-failure", "Security", 99, (now - timedelta(hours=1)).isoformat()
    )
    old_failure_id = _insert_article(
        conn, "old-failure", "Enterprise", 95, (now - timedelta(hours=2)).isoformat()
    )
    fallback_id = _insert_article(
        conn, "eligible-fallback", "Models", 90, (now - timedelta(hours=3)).isoformat()
    )
    conn.executemany(
        """
        INSERT INTO x_browser_post_audit (
            article_id, article_slug, category, status, failure_reason, attempted_at
        ) VALUES (?, ?, ?, 'FAILED', ?, ?)
        """,
        (
            (
                recent_failure_id,
                "recent-failure",
                "Security",
                "Rejected as stale",
                (now - timedelta(hours=1)).isoformat(),
            ),
            (
                old_failure_id,
                "old-failure",
                "Enterprise",
                "Temporary browser failure",
                (now - timedelta(hours=25)).isoformat(),
            ),
        ),
    )
    conn.commit()

    candidate = select_next_candidate(conn, now=now, lookback_hours=48)

    assert candidate["id"] == old_failure_id
    assert candidate["id"] != recent_failure_id
    assert candidate["id"] != fallback_id
