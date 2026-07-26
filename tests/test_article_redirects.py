import sqlite3

import pytest


TEST_SLUGS = (
    "canonical-redirect-test",
    "duplicate-redirect-test",
    "unpublished-no-redirect-test",
)


@pytest.fixture(autouse=True)
def _cleanup_article_redirect_rows(_patch_db):
    yield

    import db

    conn = sqlite3.connect(db.DB_PATH)
    try:
        conn.execute(
            "DELETE FROM article_redirects WHERE source_slug IN (?, ?, ?)",
            TEST_SLUGS,
        )
    except sqlite3.OperationalError:
        pass
    conn.executemany(
        "DELETE FROM articles WHERE slug = ?",
        [(slug,) for slug in TEST_SLUGS],
    )
    conn.commit()
    conn.close()


def _insert_article(conn, *, slug, published):
    cursor = conn.execute(
        """
        INSERT INTO articles (
            slug, title, category, gist, source, source_url, published_at,
            importance_score, is_published
        ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, ?)
        """,
        (
            slug,
            slug.replace("-", " ").title(),
            "Tools",
            "Redirect test article.",
            "Test Source",
            f"https://example.com/{slug}",
            80,
            int(published),
        ),
    )
    return cursor.lastrowid


def test_consolidated_duplicate_permanently_redirects_to_published_canonical(client):
    import db
    from services.article_redirects import consolidate_article_duplicate

    conn = sqlite3.connect(db.DB_PATH)
    canonical_id = _insert_article(
        conn,
        slug="canonical-redirect-test",
        published=True,
    )
    duplicate_id = _insert_article(
        conn,
        slug="duplicate-redirect-test",
        published=True,
    )
    conn.commit()

    result = consolidate_article_duplicate(
        duplicate_article_id=duplicate_id,
        canonical_article_id=canonical_id,
        reason="Confirmed test duplicate",
        conn=conn,
    )
    conn.close()

    response = client.get("/article/duplicate-redirect-test", follow_redirects=False)

    assert response.status_code == 301
    assert response.headers["Location"].endswith("/article/canonical-redirect-test")
    assert result["source_slug"] == "duplicate-redirect-test"
    assert result["target_slug"] == "canonical-redirect-test"

    conn = sqlite3.connect(db.DB_PATH)
    states = conn.execute(
        "SELECT slug, is_published FROM articles WHERE id IN (?, ?) ORDER BY id",
        (canonical_id, duplicate_id),
    ).fetchall()
    conn.close()
    assert states == [
        ("canonical-redirect-test", 1),
        ("duplicate-redirect-test", 0),
    ]


def test_unpublished_article_without_redirect_returns_410(client):
    import db

    conn = sqlite3.connect(db.DB_PATH)
    _insert_article(
        conn,
        slug="unpublished-no-redirect-test",
        published=False,
    )
    conn.commit()
    conn.close()

    response = client.get("/article/unpublished-no-redirect-test")

    assert response.status_code == 410


def test_consolidation_rejects_unpublished_canonical_article(_patch_db):
    import db
    from services.article_redirects import consolidate_article_duplicate

    conn = sqlite3.connect(db.DB_PATH)
    canonical_id = _insert_article(
        conn,
        slug="canonical-redirect-test",
        published=False,
    )
    duplicate_id = _insert_article(
        conn,
        slug="duplicate-redirect-test",
        published=True,
    )
    conn.commit()

    with pytest.raises(ValueError, match="published"):
        consolidate_article_duplicate(
            duplicate_article_id=duplicate_id,
            canonical_article_id=canonical_id,
            reason="Invalid test consolidation",
            conn=conn,
        )
    conn.close()
