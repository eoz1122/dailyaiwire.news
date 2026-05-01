import sqlite3


def test_backfill_moves_social_cards_out_of_onsite_image(tmp_path):
    db_path = tmp_path / "news.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT,
            image TEXT,
            social_image TEXT,
            category TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO articles (slug, image, category) VALUES (?, ?, ?)",
        (
            "social-card-row",
            "/static/img/social/social-card-row.png",
            "AI Agents",
        ),
    )
    conn.execute(
        "INSERT INTO articles (slug, image, social_image, category) VALUES (?, ?, ?, ?)",
        (
            "source-image-row",
            "https://cdn.example.com/source.jpg",
            None,
            "Business",
        ),
    )
    conn.commit()
    conn.close()

    from scripts.backfill_social_images import backfill_social_images

    changed = backfill_social_images(str(db_path))

    conn = sqlite3.connect(db_path)
    rows = {
        row[0]: row
        for row in conn.execute(
            "SELECT slug, image, social_image FROM articles ORDER BY id"
        ).fetchall()
    }
    conn.close()

    assert changed == 1
    assert rows["social-card-row"][1].startswith("/static/fallbacks/")
    assert rows["social-card-row"][2] == "/static/img/social/social-card-row.png"
    assert rows["source-image-row"][1] == "https://cdn.example.com/source.jpg"
    assert rows["source-image-row"][2] is None
