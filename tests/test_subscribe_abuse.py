import sqlite3
import time

import db as db_module
from services.subscribers import confirmation_token_hash


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
    conn.execute("DROP TABLE IF EXISTS confirmation_deliveries")
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


def test_subscribe_suppresses_repeat_blocked_source_without_extra_event(client):
    _reset_subscribers()

    first = _post_subscribe(
        client,
        "bot@example.com",
        newsletter_website="https://spam.example",
    )
    second = _post_subscribe(client, "legit-looking@example.com")

    assert first.status_code == 302
    assert second.status_code == 302
    assert _subscriber_rows() == []
    rows = _event_rows()
    assert len(rows) == 1
    assert rows[0]["reason"] == "honeypot"


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


def test_subscribe_records_deduplicated_qualified_submissions_without_email_hash(client):
    _reset_subscribers()

    first = _post_subscribe(
        client,
        "first-qualified@example.com",
        subscribe_placement="article_sidebar",
    )
    second = _post_subscribe(
        client,
        "second-qualified@example.com",
        subscribe_placement="article_sidebar",
    )

    assert first.status_code == 302
    assert second.status_code == 302
    qualified = [
        row for row in _event_rows()
        if row["event_type"] == "qualified_submit"
    ]
    assert len(qualified) == 1
    assert qualified[0]["email_hash"] is None
    assert qualified[0]["placement"] == "article_sidebar"


def test_subscribe_records_confirmation_provider_acceptance(client, monkeypatch):
    import newsletter_sender

    _reset_subscribers()
    monkeypatch.setattr(
        newsletter_sender,
        "send_confirmation_email",
        lambda *_args, **_kwargs: True,
    )

    response = _post_subscribe(client, "accepted-confirmation@example.com")

    assert response.status_code == 302
    assert "status=pending" in response.headers["Location"]
    event_types = [row["event_type"] for row in _event_rows()]
    assert "confirmation_sent" in event_types
    assert "confirmation_failed" not in event_types


def test_subscribe_persists_confirmation_provider_message_id(client, monkeypatch):
    import newsletter_sender

    _reset_subscribers()
    monkeypatch.setattr(
        newsletter_sender,
        "send_confirmation_email",
        lambda *_args, **_kwargs: {
            "accepted": True,
            "message_id": "confirmation_message_456",
        },
    )

    response = _post_subscribe(client, "tracked-confirmation@example.com")

    assert "status=pending" in response.headers["Location"]
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    delivery = conn.execute(
        """
        SELECT c.resend_message_id, c.status, s.email
        FROM confirmation_deliveries c
        JOIN subscribers s ON s.id = c.subscriber_id
        """
    ).fetchone()
    conn.close()
    assert dict(delivery) == {
        "resend_message_id": "confirmation_message_456",
        "status": "ACCEPTED",
        "email": "tracked-confirmation@example.com",
    }


def test_confirmation_tracking_failure_does_not_hide_accepted_send(client, monkeypatch):
    import newsletter_sender
    import services.resend_webhooks

    _reset_subscribers()
    monkeypatch.setattr(
        newsletter_sender,
        "send_confirmation_email",
        lambda *_args, **_kwargs: {
            "accepted": True,
            "message_id": "confirmation_message_untracked",
        },
    )
    monkeypatch.setattr(
        services.resend_webhooks,
        "record_confirmation_delivery",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            sqlite3.OperationalError("audit insert unavailable")
        ),
    )

    response = _post_subscribe(client, "accepted-untracked@example.com")

    assert response.status_code == 302
    assert "status=pending" in response.headers["Location"]
    assert _subscriber_rows()[0]["status"] == "PENDING"


def test_subscribe_reports_confirmation_provider_failure(client, monkeypatch):
    import newsletter_sender

    _reset_subscribers()
    monkeypatch.setattr(
        newsletter_sender,
        "send_confirmation_email",
        lambda *_args, **_kwargs: False,
    )

    response = _post_subscribe(client, "failed-confirmation@example.com")

    assert response.status_code == 302
    assert "status=delivery_issue" in response.headers["Location"]
    assert _subscriber_rows()[0]["status"] == "PENDING"
    event_types = [row["event_type"] for row in _event_rows()]
    assert "confirmation_failed" in event_types
    assert "confirmation_sent" not in event_types


def test_pending_subscriber_can_retry_a_failed_confirmation_send(client, monkeypatch):
    import newsletter_sender
    import routes.public

    _reset_subscribers()
    send_results = iter((False, True))
    tokens = iter(("failed-token", "accepted-token"))
    monkeypatch.setattr(
        newsletter_sender,
        "send_confirmation_email",
        lambda *_args, **_kwargs: next(send_results),
    )
    monkeypatch.setattr(
        routes.public,
        "create_confirmation_token",
        lambda: (
            (token := next(tokens)),
            confirmation_token_hash(token),
        ),
    )

    first = _post_subscribe(client, "retry-confirmation@example.com")
    second = _post_subscribe(client, "retry-confirmation@example.com")

    assert "status=delivery_issue" in first.headers["Location"]
    assert "status=pending" in second.headers["Location"]
    subscribers = _subscriber_rows()
    assert len(subscribers) == 1
    assert subscribers[0]["confirmation_token_hash"] == confirmation_token_hash(
        "accepted-token"
    )
    event_types = [row["event_type"] for row in _event_rows()]
    assert event_types.count("confirmation_failed") == 1
    assert event_types.count("confirmation_sent") == 1


def test_confirmation_delivery_issue_page_prompts_a_retry(client):
    response = client.get("/thank-you?status=delivery_issue")

    assert response.status_code == 200
    assert b"We could not send the confirmation email" in response.data
    assert b'href="/subscribe"' in response.data


def test_subscribe_records_allowlisted_signup_placement(client):
    _reset_subscribers()

    response = _post_subscribe(
        client,
        "placement@example.com",
        subscribe_placement="article_sidebar",
    )

    assert response.status_code == 302
    subscriber = _subscriber_rows()[0]
    event = _event_rows()[0]
    assert subscriber["signup_placement"] == "article_sidebar"
    assert event["placement"] == "article_sidebar"


def test_subscribe_normalizes_unknown_signup_placement(client):
    _reset_subscribers()

    _post_subscribe(
        client,
        "unknown-placement@example.com",
        subscribe_placement="<script>invented-placement</script>",
    )

    assert _subscriber_rows()[0]["signup_placement"] == "unknown"
    assert _event_rows()[0]["placement"] == "unknown"


def test_confirm_subscription_activates_pending_address(client, monkeypatch):
    _reset_subscribers()
    monkeypatch.setattr("services.subscribers.secrets.token_urlsafe", lambda _: "fixed-confirm-token")

    _post_subscribe(
        client,
        "confirm@example.com",
        subscribe_placement="homepage_inline",
    )
    row = _subscriber_rows()[0]
    assert row["status"] == "PENDING"

    response = client.get("/confirm-subscription/fixed-confirm-token")

    assert response.status_code == 302
    confirmed = _subscriber_rows()[0]
    assert confirmed["status"] == "ACTIVE"
    assert confirmed["confirmed_at"]
    assert confirmed["confirmation_token_hash"] is None
    assert _event_rows()[-1]["placement"] == "homepage_inline"
