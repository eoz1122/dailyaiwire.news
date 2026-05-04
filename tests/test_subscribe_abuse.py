import sqlite3
import time

import db as db_module


def _reset_subscribers():
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            status TEXT DEFAULT 'ACTIVE',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("DELETE FROM subscribers")
    conn.execute("DROP TABLE IF EXISTS subscriber_events")
    conn.commit()
    conn.close()


def _subscriber_rows():
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM subscribers ORDER BY id").fetchall()
    conn.close()
    return rows


def _event_rows():
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM subscriber_events ORDER BY id").fetchall()
    conn.close()
    return rows


def _post_subscribe(client, email, **extra):
    payload = {
        "email": email,
        "form_loaded_at": str(int(time.time()) - 10),
        "newsletter_website": "",
        "subscribe_source_path": "/",
    }
    payload.update(extra)
    return client.post(
        "/subscribe",
        data=payload,
        headers={
            "User-Agent": "Mozilla/5.0 Legit Browser",
            "Referer": "https://dailyaiwire.news/",
            "X-Forwarded-For": "203.0.113.10",
        },
    )


def test_subscribe_normalizes_case_and_dedupes_case_variants(client):
    _reset_subscribers()

    first = _post_subscribe(client, "MixedCase.User@Example.com")
    second = _post_subscribe(client, "mixedcase.user@example.com")

    assert first.status_code == 302
    assert second.status_code == 302
    rows = _subscriber_rows()
    assert len(rows) == 1
    assert rows[0]["email"] == "mixedcase.user@example.com"
    assert rows[0]["status"] == "PENDING"


def test_subscribe_rejects_honeypot_without_inserting(client):
    _reset_subscribers()

    response = _post_subscribe(
        client,
        "bot@example.com",
        newsletter_website="https://spam.example",
    )

    assert response.status_code == 302
    assert _subscriber_rows() == []
    assert _event_rows()[0]["event_type"] == "blocked"
    assert _event_rows()[0]["reason"] == "honeypot"


def test_subscribe_rejects_too_fast_submission_without_inserting(client):
    _reset_subscribers()

    response = _post_subscribe(
        client,
        "fast@example.com",
        form_loaded_at=str(int(time.time())),
    )

    assert response.status_code == 302
    assert _subscriber_rows() == []
    assert _event_rows()[0]["event_type"] == "blocked"
    assert _event_rows()[0]["reason"] == "submitted_too_fast"


def test_subscribe_records_signup_audit_metadata(client):
    _reset_subscribers()

    response = _post_subscribe(client, "audit@example.com")

    assert response.status_code == 302
    rows = _subscriber_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["signup_ip_hash"]
    assert row["signup_user_agent"] == "Mozilla/5.0 Legit Browser"
    assert row["signup_referrer"] == "https://dailyaiwire.news/"
    assert row["signup_source_path"] == "/"
    assert row["confirmation_token_hash"]


def test_confirm_subscription_activates_pending_address(client, monkeypatch):
    _reset_subscribers()
    monkeypatch.setattr("services.subscribers.secrets.token_urlsafe", lambda _: "fixed-confirm-token")

    _post_subscribe(client, "confirm@example.com")
    row = _subscriber_rows()[0]
    assert row["status"] == "PENDING"

    response = client.get("/confirm-subscription/fixed-confirm-token")

    assert response.status_code == 302
    confirmed = _subscriber_rows()[0]
    assert confirmed["status"] == "ACTIVE"
    assert confirmed["confirmed_at"]
    assert confirmed["confirmation_token_hash"] is None
