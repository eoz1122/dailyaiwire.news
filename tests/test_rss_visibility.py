import sqlite3


def test_public_rss_excludes_unpublished_articles(client, _patch_db):
    import db as db_module

    slug = "unpublished-rss-visibility-test"
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        """
        INSERT INTO articles (
            slug, title, gist, source, source_url, published_at, is_published
        ) VALUES (?, ?, ?, ?, ?, datetime('now', '-1 minute'), 0)
        """,
        (
            slug,
            "Unpublished RSS Visibility Test",
            "This unpublished article must never appear in the public feed.",
            "Test Source",
            "https://example.com/unpublished-rss-visibility-test",
        ),
    )
    conn.commit()
    conn.close()

    try:
        response = client.get("/rss.xml")
        xml = response.get_data(as_text=True)

        assert response.status_code == 200
        assert slug not in xml
    finally:
        conn = sqlite3.connect(db_module.DB_PATH)
        conn.execute("DELETE FROM articles WHERE slug = ?", (slug,))
        conn.commit()
        conn.close()
