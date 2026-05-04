import sqlite3

import db as db_module
from services.subscribers import ensure_subscribers_schema


def _reset_subscribers():
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_subscribers_schema(conn)
    conn.execute("DELETE FROM subscribers")
    conn.execute("DROP TABLE IF EXISTS subscriber_events")
    conn.commit()
    conn.close()


def _row(email):
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM subscribers WHERE email = ?", (email,)).fetchone()
    conn.close()
    return row


def _events():
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM subscriber_events ORDER BY id").fetchall()
    conn.close()
    return rows


def _insert_subscriber(email, status, created_at="2026-05-04 10:00:00"):
    conn = sqlite3.connect(db_module.DB_PATH)
    ensure_subscribers_schema(conn)
    conn.execute(
        "INSERT INTO subscribers (email, status, created_at) VALUES (?, ?, ?)",
        (email, status, created_at),
    )
    conn.commit()
    conn.close()


def test_admin_reconfirmation_sends_only_to_suspicious(auth_client, monkeypatch):
    _reset_subscribers()
    sent = []

    def fake_send_confirmation_email(recipient, confirmation_url):
        sent.append((recipient, confirmation_url))
        return True

    monkeypatch.setattr("services.subscribers.secrets.token_urlsafe", lambda _: "fixed-reconfirm-token")
    monkeypatch.setattr("newsletter_sender.send_confirmation_email", fake_send_confirmation_email)

    conn = sqlite3.connect(db_module.DB_PATH)
    ensure_subscribers_schema(conn)
    conn.execute(
        "INSERT INTO subscribers (email, status) VALUES (?, ?)",
        ("needs-check@example.com", "SUSPICIOUS"),
    )
    conn.execute(
        "INSERT INTO subscribers (email, status) VALUES (?, ?)",
        ("already-active@example.com", "ACTIVE"),
    )
    conn.commit()
    conn.close()

    response = auth_client.post("/admin/subscribers/reconfirm-suspicious")

    assert response.status_code == 302
    assert sent == [
        (
            "needs-check@example.com",
            "https://localhost/confirm-subscription/fixed-reconfirm-token",
        )
    ]
    suspicious = _row("needs-check@example.com")
    active = _row("already-active@example.com")
    assert suspicious["status"] == "PENDING"
    assert suspicious["confirmation_token_hash"]
    assert active["status"] == "ACTIVE"
    assert _events()[0]["event_type"] == "reconfirmation_sent"


def test_admin_reconfirmation_keeps_suspicious_when_email_fails(auth_client, monkeypatch):
    _reset_subscribers()

    monkeypatch.setattr("services.subscribers.secrets.token_urlsafe", lambda _: "fixed-reconfirm-token")
    monkeypatch.setattr("newsletter_sender.send_confirmation_email", lambda *_: False)

    conn = sqlite3.connect(db_module.DB_PATH)
    ensure_subscribers_schema(conn)
    conn.execute(
        "INSERT INTO subscribers (email, status) VALUES (?, ?)",
        ("failed-send@example.com", "SUSPICIOUS"),
    )
    conn.commit()
    conn.close()

    response = auth_client.post("/admin/subscribers/reconfirm-suspicious")

    assert response.status_code == 302
    row = _row("failed-send@example.com")
    assert row["status"] == "SUSPICIOUS"
    assert row["confirmation_token_hash"] is None
    assert _events()[0]["event_type"] == "reconfirmation_failed"


def test_admin_subscribers_can_filter_by_status(auth_client):
    _reset_subscribers()
    _insert_subscriber("active@example.com", "ACTIVE")
    _insert_subscriber("pending@example.com", "PENDING")
    _insert_subscriber("expired@example.com", "EXPIRED")

    response = auth_client.get("/admin/subscribers?status=PENDING")

    assert response.status_code == 200
    assert b"pending@example.com" in response.data
    assert b"active@example.com" not in response.data
    assert b"expired@example.com" not in response.data
    assert b"Expire Stale Pending" in response.data


def test_admin_expire_pending_marks_only_stale_pending(auth_client):
    _reset_subscribers()
    _insert_subscriber("old-pending@example.com", "PENDING", "2026-04-01 00:00:00")
    _insert_subscriber("fresh-pending@example.com", "PENDING", "2999-01-01 00:00:00")
    _insert_subscriber("active@example.com", "ACTIVE", "2026-04-01 00:00:00")

    response = auth_client.post("/admin/subscribers/expire-pending")

    assert response.status_code == 302
    assert _row("old-pending@example.com")["status"] == "EXPIRED"
    assert _row("fresh-pending@example.com")["status"] == "PENDING"
    assert _row("active@example.com")["status"] == "ACTIVE"
    assert _events()[0]["event_type"] == "pending_expired"
