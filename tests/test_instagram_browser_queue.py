import json
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
            hashtags TEXT,
            importance_score INTEGER DEFAULT 50,
            published_at TEXT NOT NULL,
            source_published_at TEXT,
            is_published INTEGER DEFAULT 1,
            shared_on_ig INTEGER DEFAULT 0,
            shared_on_ig_at TEXT
        )
        """
    )


def _insert_article(conn, slug, category, score, published_at, source_published_at=None):
    source_published_at = source_published_at or published_at
    conn.execute(
        """
        INSERT INTO articles (
            slug, title, category, why_it_matters, hashtags,
            importance_score, published_at, source_published_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            slug,
            slug.replace("-", " ").title(),
            category,
            f"{slug} matters now.",
            json.dumps(["AI", category]),
            score,
            published_at,
            source_published_at,
        ),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def test_ensure_schema_adds_instagram_tracking_columns(tmp_path):
    from services.instagram_browser_queue import ensure_schema

    conn = sqlite3.connect(tmp_path / "news.db")
    conn.execute("CREATE TABLE articles (id INTEGER PRIMARY KEY, slug TEXT NOT NULL)")

    ensure_schema(conn)

    columns = {row[1] for row in conn.execute("PRAGMA table_info(articles)")}
    assert {"shared_on_ig", "shared_on_ig_at"}.issubset(columns)


def test_next_candidate_applies_freshness_and_category_diversity(tmp_path):
    from services.instagram_browser_queue import ensure_schema, select_next_candidate

    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    conn = sqlite3.connect(tmp_path / "news.db")
    conn.row_factory = sqlite3.Row
    _create_articles_table(conn)
    ensure_schema(conn)

    stale_id = _insert_article(
        conn,
        "stale-source",
        "Security",
        100,
        (now - timedelta(hours=1)).isoformat(),
        (now - timedelta(days=10)).isoformat(),
    )
    repeated_id = _insert_article(
        conn,
        "repeated-security",
        "Security",
        99,
        (now - timedelta(hours=2)).isoformat(),
    )
    diverse_id = _insert_article(
        conn,
        "diverse-robotics",
        "Robotics",
        90,
        (now - timedelta(hours=3)).isoformat(),
    )
    conn.execute(
        """
        INSERT INTO instagram_browser_post_audit (
            article_id, article_slug, category, status, instagram_post_url, posted_at
        ) VALUES (?, ?, ?, 'POSTED', ?, ?)
        """,
        (9001, "previous-security", "Security", "https://www.instagram.com/p/abc/", now.isoformat()),
    )
    conn.commit()

    candidate = select_next_candidate(conn, now=now, lookback_hours=48, max_source_age_hours=72)

    assert candidate["id"] == diverse_id
    assert candidate["id"] not in {stale_id, repeated_id}


def test_candidate_contains_deterministic_caption_and_image_url(tmp_path):
    from services.instagram_browser_queue import ensure_schema, prepare_candidate

    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    conn = sqlite3.connect(tmp_path / "news.db")
    conn.row_factory = sqlite3.Row
    _create_articles_table(conn)
    ensure_schema(conn)
    _insert_article(conn, "browser-instagram", "Security", 91, now.isoformat())
    conn.commit()

    candidate = prepare_candidate(
        conn,
        now=now,
        card_generator=lambda title, slug, gist: f"/srv/social/{slug}-instagram-v1.png",
    )

    assert candidate["image_url"] == (
        "https://dailyaiwire.news/social-image/browser-instagram-instagram-v1.png"
    )
    assert "Browser Instagram" in candidate["caption"]
    assert "browser-instagram?utm_source=instagram" in candidate["caption"]
    assert "#DailyAIWire" in candidate["caption"]
    assert len(candidate["caption"]) <= 2200


def test_mark_posted_is_transactional_and_validates_permalink(tmp_path):
    from services.instagram_browser_queue import ensure_schema, mark_posted

    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    conn = sqlite3.connect(tmp_path / "news.db")
    conn.row_factory = sqlite3.Row
    _create_articles_table(conn)
    ensure_schema(conn)
    article_id = _insert_article(conn, "confirmed-instagram", "Models", 92, now.isoformat())
    conn.commit()

    mark_posted(
        conn,
        article_id=article_id,
        instagram_post_url="https://www.instagram.com/p/confirmed123/",
        posted_at=now,
    )

    article = conn.execute(
        "SELECT shared_on_ig, shared_on_ig_at FROM articles WHERE id = ?", (article_id,)
    ).fetchone()
    audit = conn.execute(
        "SELECT status, instagram_post_url FROM instagram_browser_post_audit WHERE article_id = ?",
        (article_id,),
    ).fetchone()
    assert article["shared_on_ig"] == 1
    assert article["shared_on_ig_at"] == now.isoformat()
    assert dict(audit) == {
        "status": "POSTED",
        "instagram_post_url": "https://www.instagram.com/p/confirmed123/",
    }


def test_mark_failed_does_not_mark_article_shared(tmp_path):
    from services.instagram_browser_queue import ensure_schema, mark_failed

    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    conn = sqlite3.connect(tmp_path / "news.db")
    conn.row_factory = sqlite3.Row
    _create_articles_table(conn)
    ensure_schema(conn)
    article_id = _insert_article(conn, "failed-instagram", "Business", 90, now.isoformat())
    conn.commit()

    mark_failed(conn, article_id=article_id, reason="missing publication confirmation", attempted_at=now)

    article = conn.execute(
        "SELECT shared_on_ig FROM articles WHERE id = ?", (article_id,)
    ).fetchone()
    audit = conn.execute(
        "SELECT status, failure_reason FROM instagram_browser_post_audit WHERE article_id = ?",
        (article_id,),
    ).fetchone()
    assert article["shared_on_ig"] == 0
    assert dict(audit) == {
        "status": "FAILED",
        "failure_reason": "missing publication confirmation",
    }


def test_replace_post_url_updates_existing_audit_without_duplicate(tmp_path):
    from services.instagram_browser_queue import ensure_schema, mark_posted, replace_post_url

    posted_at = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    replaced_at = posted_at + timedelta(hours=1)
    conn = sqlite3.connect(tmp_path / "news.db")
    conn.row_factory = sqlite3.Row
    _create_articles_table(conn)
    ensure_schema(conn)
    article_id = _insert_article(conn, "replacement-instagram", "Models", 92, posted_at.isoformat())
    conn.commit()
    mark_posted(
        conn,
        article_id=article_id,
        instagram_post_url="https://www.instagram.com/p/old123/",
        posted_at=posted_at,
    )

    replace_post_url(
        conn,
        article_id=article_id,
        instagram_post_url="https://www.instagram.com/p/new456/",
        replaced_at=replaced_at,
    )

    audits = conn.execute(
        "SELECT instagram_post_url, attempted_at, posted_at "
        "FROM instagram_browser_post_audit WHERE article_id = ?",
        (article_id,),
    ).fetchall()
    article = conn.execute(
        "SELECT shared_on_ig, shared_on_ig_at FROM articles WHERE id = ?",
        (article_id,),
    ).fetchone()
    assert [dict(row) for row in audits] == [
        {
            "instagram_post_url": "https://www.instagram.com/p/new456/",
            "attempted_at": replaced_at.isoformat(),
            "posted_at": replaced_at.isoformat(),
        }
    ]
    assert dict(article) == {
        "shared_on_ig": 1,
        "shared_on_ig_at": replaced_at.isoformat(),
    }


def test_replace_post_url_requires_confirmed_existing_post(tmp_path):
    import pytest

    from services.instagram_browser_queue import ensure_schema, replace_post_url

    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    conn = sqlite3.connect(tmp_path / "news.db")
    conn.row_factory = sqlite3.Row
    _create_articles_table(conn)
    ensure_schema(conn)
    article_id = _insert_article(conn, "unconfirmed-instagram", "Models", 92, now.isoformat())
    conn.commit()

    with pytest.raises(ValueError, match="confirmed Instagram post"):
        replace_post_url(
            conn,
            article_id=article_id,
            instagram_post_url="https://www.instagram.com/p/new456/",
            replaced_at=now,
        )
