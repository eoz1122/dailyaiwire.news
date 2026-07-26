import sqlite3

from bs4 import BeautifulSoup

import db as db_module


def _seed_newsletter(newsletter_id=9901):
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS newsletters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT,
            intro_text TEXT,
            article_ids TEXT,
            article_metadata TEXT,
            scheduled_date TEXT,
            status TEXT DEFAULT 'DRAFT',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("DELETE FROM newsletters WHERE id = ?", (newsletter_id,))
    conn.execute(
        """
        INSERT INTO newsletters (
            id, subject, intro_text, article_ids, article_metadata,
            scheduled_date, status, created_at
        ) VALUES (?, ?, ?, '[]', '{}', ?, 'SENT', ?)
        """,
        (
            newsletter_id,
            "Visual regression issue",
            "A concise weekly briefing.",
            "2026-07-26T18:00:00",
            "2026-07-26T12:00:00",
        ),
    )
    conn.commit()
    conn.close()
    return newsletter_id


def test_newsletter_editor_heading_has_contrast_on_light_admin_background(auth_client):
    newsletter_id = _seed_newsletter()

    response = auth_client.get(f"/admin/newsletter/edit/{newsletter_id}")
    soup = BeautifulSoup(response.get_data(as_text=True), "html.parser")
    heading = soup.find("h1", string=lambda value: value and "Edit Intelligence Report" in value)
    newsletters_navigation = soup.find("a", href="/admin/newsletters")

    assert response.status_code == 200
    assert heading is not None
    assert "text-gray-900" in heading.get("class", [])
    assert "text-white" not in heading.get("class", [])
    assert "bg-pink-600" in newsletters_navigation.get("class", [])


def test_subscriber_page_highlights_audience_instead_of_target_acquisition(auth_client):
    response = auth_client.get("/admin/subscribers")
    soup = BeautifulSoup(response.get_data(as_text=True), "html.parser")
    audience = soup.find("a", href="/admin/subscribers")
    target_acquisition = soup.find("a", href="/admin/leads")

    assert response.status_code == 200
    assert audience is not None
    assert target_acquisition is not None
    assert "bg-purple-600" in audience.get("class", [])
    assert "bg-gray-50" in target_acquisition.get("class", [])
    assert "bg-emerald-50" not in target_acquisition.get("class", [])


def test_admin_newsletter_dates_are_human_readable_and_machine_parseable(auth_client):
    newsletter_id = _seed_newsletter()

    list_response = auth_client.get("/admin/newsletters")
    editor_response = auth_client.get(f"/admin/newsletter/edit/{newsletter_id}")

    assert list_response.status_code == 200
    assert editor_response.status_code == 200
    for response in (list_response, editor_response):
        soup = BeautifulSoup(response.get_data(as_text=True), "html.parser")
        date_node = soup.find("time", attrs={"datetime": "2026-07-26T18:00:00"})
        assert date_node is not None
        assert date_node.get_text(" ", strip=True) == "26 Jul 2026, 18:00"
        assert "2026-07-26T18:00:00" not in date_node.get_text(" ", strip=True)
