import sqlite3

import db as db_module


def _render_briefing(client, *, article_metadata, article):
    template = client.application.jinja_env.get_template("email/briefing.html")
    return template.render(
        subject="Weekly test",
        intro_text="The week's important developments.",
        articles=[article],
        article_metadata=article_metadata,
        newsletter_date_display="22 JUL 2026",
        newsletter_issue_label="W30 - 2026",
        tracking_pixel_url="",
        unsubscribe_url="https://dailyaiwire.news/unsubscribe/test",
    )


def test_briefing_labels_article_impact_as_why_it_matters(client):
    html = _render_briefing(
        client,
        article_metadata={"101": "Procurement teams must update their model risk controls."},
        article={
            "id": 101,
            "category": "Enterprise AI",
            "title": "A material platform change",
            "slug": "material-platform-change",
            "gist": "A platform changed.",
            "why_it_matters": "Existing controls no longer cover the new behavior.",
        },
    )

    assert "Why it matters" in html
    assert "Strategic take" not in html
    assert "Procurement teams must update their model risk controls." in html


def test_briefing_falls_back_to_article_why_it_matters_before_gist(client):
    html = _render_briefing(
        client,
        article_metadata={},
        article={
            "id": 102,
            "category": "Policy",
            "title": "A policy change",
            "slug": "policy-change",
            "gist": "The policy was announced.",
            "why_it_matters": "Deployers now face a concrete compliance deadline.",
        },
    )

    assert "Deployers now face a concrete compliance deadline." in html
    assert "The policy was announced." not in html


def test_subscribe_page_links_to_latest_sent_issue(client):
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS newsletters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT,
            intro_text TEXT,
            article_ids TEXT,
            article_metadata TEXT,
            status TEXT,
            scheduled_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("DELETE FROM newsletters")
    conn.execute(
        "INSERT INTO newsletters (subject, status, scheduled_date) VALUES (?, ?, ?)",
        ("Visible sent issue", "SENT", "2026-07-20 18:00:00"),
    )
    sent_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO newsletters (subject, status, scheduled_date) VALUES (?, ?, ?)",
        ("Hidden draft issue", "DRAFT", "2026-07-21 18:00:00"),
    )
    conn.commit()
    conn.close()

    response = client.get("/subscribe")

    assert response.status_code == 200
    assert b"Visible sent issue" in response.data
    assert f'/signal/{sent_id}'.encode() in response.data
    assert b"Hidden draft issue" not in response.data
