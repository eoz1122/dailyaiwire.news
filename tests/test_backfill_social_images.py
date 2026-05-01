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
    conn.execute(
        "INSERT INTO articles (slug, image, social_image, category) VALUES (?, ?, ?, ?)",
        (
            "machine-collective-intelligence-explainable-science",
            "/static/fallbacks/science_1.jpg",
            "/static/img/social/machine-collective-intelligence-explainable-science.png",
            "Science",
        ),
    )
    conn.execute(
        "INSERT INTO articles (slug, image, social_image, category) VALUES (?, ?, ?, ?)",
        (
            "safe-bilevel-delegation-multi-agent-ai-safety",
            "/static/fallbacks/agents_2.jpg",
            "/static/img/social/safe-bilevel-delegation-multi-agent-ai-safety.png",
            "AI Agents",
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

    assert changed == 3
    assert rows["social-card-row"][1].startswith("/static/fallbacks/")
    assert rows["social-card-row"][2] == "/static/img/social/social-card-row.png"
    assert rows["source-image-row"][1] == "https://cdn.example.com/source.jpg"
    assert rows["source-image-row"][2] is None
    assert rows["machine-collective-intelligence-explainable-science"][1] != "/static/fallbacks/science_1.jpg"
    assert rows["machine-collective-intelligence-explainable-science"][2] == "/static/img/social/machine-collective-intelligence-explainable-science.png"
    assert rows["safe-bilevel-delegation-multi-agent-ai-safety"][1] != "/static/fallbacks/agents_2.jpg"
    assert rows["safe-bilevel-delegation-multi-agent-ai-safety"][1].startswith("/static/fallbacks/")
    assert rows["safe-bilevel-delegation-multi-agent-ai-safety"][2] == "/static/img/social/safe-bilevel-delegation-multi-agent-ai-safety.png"
