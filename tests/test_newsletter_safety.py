import sqlite3

import db as db_module
import pytest


def _reset_newsletter_data():
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
    conn.execute("DELETE FROM newsletter_deliveries")
    conn.execute("DELETE FROM newsletters")
    conn.execute("DELETE FROM subscribers")
    conn.commit()
    conn.close()


def _insert_newsletter(status="DRAFT"):
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        """
        INSERT INTO newsletters (
            subject, intro_text, article_ids, article_metadata,
            scheduled_date, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "Weekly Safety Briefing",
            "The test briefing intro.",
            "[]",
            "{}",
            "2026-07-26T18:00:00",
            status,
            "2026-07-22T01:00:00",
        ),
    )
    newsletter_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return newsletter_id


def test_newsletter_reservation_is_atomic(monkeypatch):
    import newsletter_sender

    _reset_newsletter_data()
    newsletter_id = _insert_newsletter()
    monkeypatch.setattr(newsletter_sender, "DB_PATH", db_module.DB_PATH)

    assert newsletter_sender.reserve_newsletter_send(newsletter_id) is True
    assert newsletter_sender.reserve_newsletter_send(newsletter_id) is False

    conn = sqlite3.connect(db_module.DB_PATH)
    row = conn.execute(
        "SELECT status, broadcast_started_at FROM newsletters WHERE id = ?",
        (newsletter_id,),
    ).fetchone()
    conn.close()
    assert row[0] == "SENDING"
    assert row[1]


def test_delivery_safety_schema_rejects_duplicate_recipient(monkeypatch):
    import newsletter_sender

    _reset_newsletter_data()
    monkeypatch.setattr(newsletter_sender, "DB_PATH", db_module.DB_PATH)

    conn = sqlite3.connect(db_module.DB_PATH)
    newsletter_sender.ensure_newsletter_delivery_safety_schema(conn)
    conn.execute(
        """
        INSERT INTO newsletter_deliveries (newsletter_id, recipient_email, status)
        VALUES (?, ?, ?)
        """,
        (42, "Reader@Example.com", "DELIVERED"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO newsletter_deliveries (newsletter_id, recipient_email, status)
            VALUES (?, ?, ?)
            """,
            (42, "reader@example.com", "DELIVERED"),
        )
    conn.close()


def test_test_send_does_not_change_status_or_create_delivery(client, monkeypatch):
    import newsletter_sender

    _reset_newsletter_data()
    newsletter_id = _insert_newsletter()
    monkeypatch.setattr(newsletter_sender, "DB_PATH", db_module.DB_PATH)
    monkeypatch.setattr(newsletter_sender, "RESEND_API_KEY", "test-key")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    captured = {}

    class DummyResponse:
        status_code = 200
        text = '{"id":"test_message"}'

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["payload"] = json
        return DummyResponse()

    monkeypatch.setattr(newsletter_sender.requests, "post", fake_post)

    assert newsletter_sender.send_test_newsletter(
        newsletter_id,
        "owner@example.com",
    ) is True

    conn = sqlite3.connect(db_module.DB_PATH)
    status = conn.execute(
        "SELECT status FROM newsletters WHERE id = ?",
        (newsletter_id,),
    ).fetchone()[0]
    delivery_count = conn.execute(
        "SELECT COUNT(*) FROM newsletter_deliveries WHERE newsletter_id = ?",
        (newsletter_id,),
    ).fetchone()[0]
    conn.close()

    assert status == "DRAFT"
    assert delivery_count == 0
    assert captured["payload"]["to"] == ["owner@example.com"]
    assert captured["payload"]["subject"].startswith("[TEST]")
    assert "cc" not in captured["payload"]
    assert "bcc" not in captured["payload"]


def test_admin_send_confirmation_shows_exact_audience(auth_client, monkeypatch):
    import newsletter_sender

    _reset_newsletter_data()
    newsletter_id = _insert_newsletter()
    monkeypatch.setattr(newsletter_sender, "DB_PATH", db_module.DB_PATH)

    conn = sqlite3.connect(db_module.DB_PATH)
    conn.executemany(
        "INSERT INTO subscribers (email, status) VALUES (?, ?)",
        [
            ("one@example.com", "ACTIVE"),
            ("two@example.com", "ACTIVE"),
            ("old@example.com", "UNSUBSCRIBED"),
        ],
    )
    conn.execute(
        """
        INSERT INTO newsletter_deliveries (newsletter_id, recipient_email, status)
        VALUES (?, ?, ?)
        """,
        (newsletter_id, "one@example.com", "DELIVERED"),
    )
    conn.commit()
    conn.close()

    response = auth_client.get(f"/admin/newsletter/send/{newsletter_id}")

    assert response.status_code == 200
    assert b"2 active subscribers" in response.data
    assert b"1 already delivered" in response.data
    assert b"1 recipient remaining" in response.data
    assert b'name="expected_recipient_count" value="1"' in response.data


def test_admin_send_rejects_changed_audience_count(auth_client, monkeypatch):
    import newsletter_sender

    _reset_newsletter_data()
    newsletter_id = _insert_newsletter()
    monkeypatch.setattr(newsletter_sender, "DB_PATH", db_module.DB_PATH)
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        "INSERT INTO subscribers (email, status) VALUES (?, ?)",
        ("one@example.com", "ACTIVE"),
    )
    conn.commit()
    conn.close()

    response = auth_client.post(
        f"/admin/newsletter/send/{newsletter_id}",
        data={"expected_recipient_count": "2"},
        follow_redirects=True,
    )

    conn = sqlite3.connect(db_module.DB_PATH)
    status = conn.execute(
        "SELECT status FROM newsletters WHERE id = ?",
        (newsletter_id,),
    ).fetchone()[0]
    conn.close()

    assert response.status_code == 200
    assert b"audience changed" in response.data.lower()
    assert status == "DRAFT"


def test_reserved_worker_aborts_if_confirmed_audience_changes(monkeypatch):
    import newsletter_sender

    _reset_newsletter_data()
    newsletter_id = _insert_newsletter()
    monkeypatch.setattr(newsletter_sender, "DB_PATH", db_module.DB_PATH)
    monkeypatch.setattr(newsletter_sender, "RESEND_API_KEY", "test-key")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    network_calls = []
    monkeypatch.setattr(
        newsletter_sender.requests,
        "post",
        lambda *_args, **_kwargs: network_calls.append(_kwargs),
    )
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.executemany(
        "INSERT INTO subscribers (email, status) VALUES (?, 'ACTIVE')",
        [("one@example.com",), ("two@example.com",)],
    )
    conn.commit()
    conn.close()

    assert newsletter_sender.reserve_newsletter_send(newsletter_id) is True
    assert newsletter_sender.send_newsletter(
        newsletter_id,
        reservation_held=True,
        expected_recipient_count=1,
    ) is False

    conn = sqlite3.connect(db_module.DB_PATH)
    row = conn.execute(
        "SELECT status, last_send_error FROM newsletters WHERE id = ?",
        (newsletter_id,),
    ).fetchone()
    conn.close()
    assert network_calls == []
    assert row[0] == "PARTIAL"
    assert "audience changed" in row[1].lower()


def test_private_gateway_sends_provider_idempotency_key(monkeypatch):
    import newsletter_sender

    captured = {}

    class DummyResponse:
        status_code = 200

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["headers"] = headers
        return DummyResponse()

    monkeypatch.setattr(newsletter_sender.requests, "post", fake_post)

    newsletter_sender._post_private_email(
        {"to": ["reader@example.com"], "subject": "Safe"},
        "reader@example.com",
        idempotency_key="newsletter-42-reader-token",
    )

    assert captured["headers"]["Idempotency-Key"] == "newsletter-42-reader-token"


def test_confirmed_admin_send_starts_one_reserved_worker(auth_client, monkeypatch):
    import newsletter_sender
    import threading

    _reset_newsletter_data()
    newsletter_id = _insert_newsletter()
    monkeypatch.setattr(newsletter_sender, "DB_PATH", db_module.DB_PATH)
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        "INSERT INTO subscribers (email, status) VALUES (?, 'ACTIVE')",
        ("one@example.com",),
    )
    conn.commit()
    conn.close()

    reservations = []
    sends = []
    monkeypatch.setattr(
        newsletter_sender,
        "reserve_newsletter_send",
        lambda issue_id: reservations.append(issue_id) or True,
    )
    monkeypatch.setattr(
        newsletter_sender,
        "send_newsletter",
        lambda issue_id, **kwargs: sends.append((issue_id, kwargs)) or True,
    )

    class ImmediateThread:
        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon

        def start(self):
            self.target()

    monkeypatch.setattr(threading, "Thread", ImmediateThread)

    response = auth_client.post(
        f"/admin/newsletter/send/{newsletter_id}",
        data={"expected_recipient_count": "1"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert reservations == [newsletter_id]
    assert sends == [
        (
            newsletter_id,
            {"reservation_held": True, "expected_recipient_count": 1},
        )
    ]
