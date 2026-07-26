import base64
import hashlib
import hmac
import json
import sqlite3
import time

import db as db_module


WEBHOOK_SECRET_BYTES = b"dailyaiwire-webhook-test-secret"
WEBHOOK_SECRET = "whsec_" + base64.b64encode(WEBHOOK_SECRET_BYTES).decode("ascii")


def _reset_delivery_data():
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS newsletter_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            newsletter_id INTEGER,
            recipient_email TEXT,
            status TEXT,
            tracking_token TEXT,
            opened_at TEXT,
            resend_message_id TEXT,
            provider_response TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            status TEXT DEFAULT 'ACTIVE',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("DROP TABLE IF EXISTS newsletter_provider_events")
    conn.execute("DROP TABLE IF EXISTS confirmation_deliveries")
    conn.execute("DELETE FROM newsletter_deliveries")
    conn.execute("DELETE FROM subscribers")
    conn.execute(
        "INSERT INTO subscribers (email, status) VALUES (?, 'ACTIVE')",
        ("reader@example.com",),
    )
    conn.execute(
        """
        INSERT INTO newsletter_deliveries (
            newsletter_id, recipient_email, status, tracking_token, resend_message_id
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (42, "reader@example.com", "ACCEPTED", "abcdef1234567890", "email_123"),
    )
    conn.commit()
    conn.close()


def _insert_confirmation_delivery(message_id="confirmation_email_123"):
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        """
        CREATE TABLE confirmation_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscriber_id INTEGER NOT NULL,
            resend_message_id TEXT,
            status TEXT NOT NULL DEFAULT 'ACCEPTED',
            placement TEXT,
            accepted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sent_at TIMESTAMP,
            delivered_at TIMESTAMP,
            delayed_at TIMESTAMP,
            opened_at TIMESTAMP,
            clicked_at TIMESTAMP,
            bounced_at TIMESTAMP,
            complained_at TIMESTAMP,
            failed_at TIMESTAMP,
            suppressed_at TIMESTAMP,
            last_event_at TIMESTAMP,
            last_event_type TEXT,
            bounce_type TEXT
        )
        """
    )
    subscriber_id = conn.execute(
        """
        INSERT INTO subscribers (email, status)
        VALUES (?, 'PENDING')
        """,
        ("pending-confirmation@example.com",),
    ).lastrowid
    delivery_id = conn.execute(
        """
        INSERT INTO confirmation_deliveries (
            subscriber_id, resend_message_id, status, placement
        ) VALUES (?, ?, 'ACCEPTED', 'article_sidebar')
        """,
        (subscriber_id, message_id),
    ).lastrowid
    conn.commit()
    conn.close()
    return subscriber_id, delivery_id


def _signed_headers(raw_body, message_id="msg_test_1"):
    timestamp = str(int(time.time()))
    signed = f"{message_id}.{timestamp}.".encode("utf-8") + raw_body
    digest = hmac.new(WEBHOOK_SECRET_BYTES, signed, hashlib.sha256).digest()
    signature = base64.b64encode(digest).decode("ascii")
    return {
        "Content-Type": "application/json",
        "svix-id": message_id,
        "svix-timestamp": timestamp,
        "svix-signature": f"v1,{signature}",
    }


def _event(event_type, **data_overrides):
    data = {
        "email_id": "email_123",
        "to": ["reader@example.com"],
        "subject": "Weekly briefing",
    }
    data.update(data_overrides)
    return {
        "type": event_type,
        "created_at": "2026-07-22T02:00:00.000Z",
        "data": data,
    }


def _post_event(client, monkeypatch, payload, message_id="msg_test_1"):
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", WEBHOOK_SECRET)
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return client.post(
        "/api/webhooks/resend",
        data=raw_body,
        headers=_signed_headers(raw_body, message_id),
    )


def test_resend_webhook_rejects_unsigned_requests(client, monkeypatch):
    _reset_delivery_data()
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", WEBHOOK_SECRET)

    response = client.post(
        "/api/webhooks/resend",
        data=json.dumps(_event("email.delivered")),
        content_type="application/json",
    )

    assert response.status_code == 400


def test_resend_webhook_marks_actual_delivery_and_is_replay_safe(client, monkeypatch):
    _reset_delivery_data()

    first = _post_event(client, monkeypatch, _event("email.delivered"))
    replay = _post_event(client, monkeypatch, _event("email.delivered"))

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.get_json()["duplicate"] is True

    conn = sqlite3.connect(db_module.DB_PATH)
    delivery = conn.execute(
        """
        SELECT status, delivered_at, last_event_type
        FROM newsletter_deliveries WHERE resend_message_id = ?
        """,
        ("email_123",),
    ).fetchone()
    event_count = conn.execute(
        "SELECT COUNT(*) FROM newsletter_provider_events WHERE event_id = ?",
        ("msg_test_1",),
    ).fetchone()[0]
    conn.close()

    assert delivery[0] == "DELIVERED"
    assert delivery[1]
    assert delivery[2] == "email.delivered"
    assert event_count == 1


def test_resend_webhook_matches_confirmation_delivery(client, monkeypatch):
    _reset_delivery_data()
    subscriber_id, delivery_id = _insert_confirmation_delivery()

    payload = _event(
        "email.delivered",
        email_id="confirmation_email_123",
        to=["pending-confirmation@example.com"],
        subject="Confirm your DailyAIWire subscription",
    )
    response = _post_event(
        client,
        monkeypatch,
        payload,
        message_id="msg_confirmation_delivered",
    )

    assert response.status_code == 200
    conn = sqlite3.connect(db_module.DB_PATH)
    confirmation = conn.execute(
        """
        SELECT status, delivered_at, last_event_type
        FROM confirmation_deliveries
        WHERE id = ?
        """,
        (delivery_id,),
    ).fetchone()
    subscriber_status = conn.execute(
        "SELECT status FROM subscribers WHERE id = ?",
        (subscriber_id,),
    ).fetchone()[0]
    matched_id = conn.execute(
        """
        SELECT matched_confirmation_delivery_id
        FROM newsletter_provider_events
        WHERE event_id = ?
        """,
        ("msg_confirmation_delivered",),
    ).fetchone()[0]
    conn.close()
    assert confirmation[0] == "DELIVERED"
    assert confirmation[1]
    assert confirmation[2] == "email.delivered"
    assert subscriber_status == "PENDING"
    assert matched_id == delivery_id


def test_permanent_confirmation_bounce_suppresses_pending_subscriber(client, monkeypatch):
    _reset_delivery_data()
    subscriber_id, delivery_id = _insert_confirmation_delivery(
        "confirmation_email_bounced"
    )

    payload = _event(
        "email.bounced",
        email_id="confirmation_email_bounced",
        to=["pending-confirmation@example.com"],
        subject="Confirm your DailyAIWire subscription",
        bounce={"type": "Permanent", "subType": "NoEmail"},
    )
    response = _post_event(
        client,
        monkeypatch,
        payload,
        message_id="msg_confirmation_bounced",
    )

    assert response.status_code == 200
    conn = sqlite3.connect(db_module.DB_PATH)
    confirmation = conn.execute(
        "SELECT status, bounce_type FROM confirmation_deliveries WHERE id = ?",
        (delivery_id,),
    ).fetchone()
    subscriber = conn.execute(
        """
        SELECT status, confirmation_token_hash
        FROM subscribers
        WHERE id = ?
        """,
        (subscriber_id,),
    ).fetchone()
    conn.close()
    assert confirmation == ("BOUNCED", "Permanent")
    assert subscriber == ("BOUNCED", None)


def test_resend_webhook_suppresses_complaining_subscriber(client, monkeypatch):
    _reset_delivery_data()

    response = _post_event(
        client,
        monkeypatch,
        _event("email.complained"),
        message_id="msg_complained",
    )

    assert response.status_code == 200
    conn = sqlite3.connect(db_module.DB_PATH)
    delivery_status = conn.execute(
        "SELECT status, delivered_at FROM newsletter_deliveries WHERE resend_message_id = ?",
        ("email_123",),
    ).fetchone()
    subscriber_status = conn.execute(
        "SELECT status FROM subscribers WHERE email = ?",
        ("reader@example.com",),
    ).fetchone()[0]
    conn.close()
    assert delivery_status[0] == "COMPLAINED"
    assert delivery_status[1]
    assert subscriber_status == "COMPLAINED"


def test_only_permanent_bounce_suppresses_subscriber(client, monkeypatch):
    _reset_delivery_data()
    temporary = _event(
        "email.bounced",
        bounce={"type": "Transient", "subType": "MailboxFull"},
    )

    response = _post_event(
        client,
        monkeypatch,
        temporary,
        message_id="msg_temporary_bounce",
    )

    assert response.status_code == 200
    conn = sqlite3.connect(db_module.DB_PATH)
    delivery_status = conn.execute(
        "SELECT status FROM newsletter_deliveries WHERE resend_message_id = ?",
        ("email_123",),
    ).fetchone()[0]
    subscriber_status = conn.execute(
        "SELECT status FROM subscribers WHERE email = ?",
        ("reader@example.com",),
    ).fetchone()[0]
    conn.close()
    assert delivery_status == "DELAYED"
    assert subscriber_status == "ACTIVE"

    _reset_delivery_data()
    permanent = _event(
        "email.bounced",
        bounce={"type": "Permanent", "subType": "NoEmail"},
    )
    response = _post_event(
        client,
        monkeypatch,
        permanent,
        message_id="msg_permanent_bounce",
    )

    assert response.status_code == 200
    conn = sqlite3.connect(db_module.DB_PATH)
    subscriber_status = conn.execute(
        "SELECT status FROM subscribers WHERE email = ?",
        ("reader@example.com",),
    ).fetchone()[0]
    conn.close()
    assert subscriber_status == "BOUNCED"


def test_failed_and_suppressed_events_have_distinct_effects(client, monkeypatch):
    _reset_delivery_data()
    response = _post_event(
        client,
        monkeypatch,
        _event("email.failed"),
        message_id="msg_failed",
    )
    assert response.status_code == 200

    conn = sqlite3.connect(db_module.DB_PATH)
    statuses = (
        conn.execute(
            "SELECT status FROM newsletter_deliveries WHERE resend_message_id = ?",
            ("email_123",),
        ).fetchone()[0],
        conn.execute(
            "SELECT status FROM subscribers WHERE email = ?",
            ("reader@example.com",),
        ).fetchone()[0],
    )
    conn.close()
    assert statuses == ("FAILED", "ACTIVE")

    _reset_delivery_data()
    response = _post_event(
        client,
        monkeypatch,
        _event("email.suppressed"),
        message_id="msg_suppressed",
    )
    assert response.status_code == 200

    conn = sqlite3.connect(db_module.DB_PATH)
    statuses = (
        conn.execute(
            "SELECT status FROM newsletter_deliveries WHERE resend_message_id = ?",
            ("email_123",),
        ).fetchone()[0],
        conn.execute(
            "SELECT status FROM subscribers WHERE email = ?",
            ("reader@example.com",),
        ).fetchone()[0],
    )
    conn.close()
    assert statuses == ("SUPPRESSED", "SUPPRESSED")


def test_tracking_pixel_preserves_provider_delivery_status(client):
    _reset_delivery_data()
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        "UPDATE newsletter_deliveries SET status = 'DELIVERED' WHERE resend_message_id = ?",
        ("email_123",),
    )
    conn.commit()
    conn.close()

    response = client.get("/t/nl/42/abcdef1234567890")

    assert response.status_code == 200
    conn = sqlite3.connect(db_module.DB_PATH)
    row = conn.execute(
        "SELECT status, opened_at FROM newsletter_deliveries WHERE resend_message_id = ?",
        ("email_123",),
    ).fetchone()
    conn.close()
    assert row[0] == "DELIVERED"
    assert row[1]


def test_successful_resend_api_response_is_recorded_as_accepted(monkeypatch):
    import newsletter_sender

    _reset_delivery_data()
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute("DELETE FROM newsletter_deliveries")
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
    conn.execute("DELETE FROM newsletters")
    conn.execute(
        """
        INSERT INTO newsletters (
            id, subject, intro_text, article_ids, article_metadata, status
        ) VALUES (42, 'Weekly briefing', 'Intro', '[]', '{}', 'DRAFT')
        """
    )
    conn.commit()
    conn.close()

    class DummyResponse:
        status_code = 200
        text = '{"id":"email_123"}'

        @staticmethod
        def json():
            return {"id": "email_123"}

    monkeypatch.setattr(newsletter_sender, "DB_PATH", db_module.DB_PATH)
    monkeypatch.setattr(newsletter_sender, "RESEND_API_KEY", "test-key")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setattr(newsletter_sender.requests, "post", lambda *_args, **_kwargs: DummyResponse())
    monkeypatch.setattr(newsletter_sender.time, "sleep", lambda *_args: None)

    assert newsletter_sender.send_newsletter(42) is True

    conn = sqlite3.connect(db_module.DB_PATH)
    status = conn.execute(
        "SELECT status FROM newsletter_deliveries WHERE resend_message_id = ?",
        ("email_123",),
    ).fetchone()[0]
    conn.close()
    assert status == "ACCEPTED"


def test_admin_newsletter_metrics_separate_provider_states(auth_client):
    from services.resend_webhooks import ensure_resend_webhook_schema

    _reset_delivery_data()
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
    conn.execute("DELETE FROM newsletters")
    conn.execute(
        """
        INSERT INTO newsletters (
            id, subject, intro_text, article_ids, article_metadata, status
        ) VALUES (42, 'Provider Metrics', 'Intro', '[]', '{}', 'SENT')
        """
    )
    ensure_resend_webhook_schema(conn)
    conn.execute("DELETE FROM newsletter_deliveries")
    conn.executemany(
        """
        INSERT INTO newsletter_deliveries (
            newsletter_id, recipient_email, status, sent_at, opened_at,
            clicked_at, unsubscribed_at, last_event_type
        ) VALUES (42, ?, ?, '2026-07-23 08:00:00', ?, ?, ?, ?)
        """,
        [
            ("accepted@example.com", "ACCEPTED", None, None, None, None),
            (
                "delivered@example.com",
                "DELIVERED",
                "2026-07-23 08:05:00",
                "2026-07-23 08:06:00",
                None,
                "email.clicked",
            ),
            ("failed@example.com", "FAILED", None, None, None, "email.failed"),
            (
                "bounced@example.com",
                "BOUNCED",
                None,
                None,
                "2026-07-23 08:10:00",
                "email.bounced",
            ),
        ],
    )
    conn.commit()
    conn.close()

    response = auth_client.get("/admin/newsletters")

    assert response.status_code == 200
    assert b"4 accepted" in response.data
    assert b"1 delivered" in response.data
    assert b"2 failed" in response.data
    assert b"1 opened/read (100.0%)" in response.data
    assert b"1 clicked" in response.data
    assert b"1 unsubscribed" in response.data
    assert b"Provider-confirmed" in response.data
    html = response.data.decode("utf-8")
    opened_position = html.index("1 opened/read (100.0%)")
    opened_class_position = html.rfind('class="', 0, opened_position)
    assert "text-blue-400" in html[opened_class_position:opened_position]


def test_admin_newsletter_metrics_label_legacy_delivery_as_untracked(auth_client):
    from services.resend_webhooks import ensure_resend_webhook_schema

    _reset_delivery_data()
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
    conn.execute("DELETE FROM newsletters")
    conn.execute(
        """
        INSERT INTO newsletters (
            id, subject, intro_text, article_ids, article_metadata, status
        ) VALUES (43, 'Legacy Metrics', 'Intro', '[]', '{}', 'SENT')
        """
    )
    ensure_resend_webhook_schema(conn)
    conn.execute("DELETE FROM newsletter_deliveries")
    conn.executemany(
        """
        INSERT INTO newsletter_deliveries (
            newsletter_id, recipient_email, status, sent_at, opened_at, delivered_at
        ) VALUES (43, ?, ?, '2026-07-19 08:00:00', ?, ?)
        """,
        [
            ("unopened@example.com", "ACCEPTED", None, None),
            (
                "opened@example.com",
                "DELIVERED",
                "2026-07-19 09:00:00",
                "2026-07-19 09:00:00",
            ),
        ],
    )
    conn.commit()
    conn.close()

    response = auth_client.get("/admin/newsletters")

    assert response.status_code == 200
    assert b"2 sent/accepted" in response.data
    assert b"Delivery was not tracked historically" in response.data
    assert b"1 opened/read (50.0%)" in response.data
    assert b"Legacy/inferred" in response.data
    html = response.data.decode("utf-8")
    opened_position = html.index("1 opened/read (50.0%)")
    opened_class_position = html.rfind('class="', 0, opened_position)
    assert "text-blue-400" in html[opened_class_position:opened_position]


def test_admin_newsletter_warns_when_provider_events_are_overdue(auth_client):
    from services.resend_webhooks import ensure_resend_webhook_schema

    _reset_delivery_data()
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
    conn.execute("DELETE FROM newsletters")
    conn.execute(
        """
        INSERT INTO newsletters (
            id, subject, intro_text, article_ids, article_metadata, status
        ) VALUES (44, 'Webhook Health', 'Intro', '[]', '{}', 'SENT')
        """
    )
    ensure_resend_webhook_schema(conn)
    conn.execute("DELETE FROM newsletter_deliveries")
    conn.execute(
        """
        INSERT INTO newsletter_deliveries (
            newsletter_id, recipient_email, status, sent_at, last_event_type
        ) VALUES (
            44, 'pending@example.com', 'ACCEPTED',
            datetime('now', '-20 minutes'), NULL
        )
        """
    )
    conn.commit()
    conn.close()

    response = auth_client.get("/admin/newsletters")

    assert response.status_code == 200
    assert b"1 accepted" in response.data
    assert b"Awaiting provider events" in response.data
    assert b"Provider tracking warning" in response.data


def test_unsubscribe_records_delivery_timestamp(client):
    from services.resend_webhooks import ensure_resend_webhook_schema

    _reset_delivery_data()
    conn = sqlite3.connect(db_module.DB_PATH)
    ensure_resend_webhook_schema(conn)
    conn.commit()
    conn.close()

    response = client.post("/unsubscribe/42/abcdef1234567890")

    assert response.status_code == 200
    conn = sqlite3.connect(db_module.DB_PATH)
    unsubscribed_at = conn.execute(
        "SELECT unsubscribed_at FROM newsletter_deliveries WHERE resend_message_id = ?",
        ("email_123",),
    ).fetchone()[0]
    conn.close()
    assert unsubscribed_at
