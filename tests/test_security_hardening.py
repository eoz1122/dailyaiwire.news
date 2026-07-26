import ast
import io
import os
import re
import sqlite3
from pathlib import Path

import db as db_module
import pytest


def _ensure_newsletter_tables():
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
            status TEXT,
            created_at TEXT
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
    conn.commit()
    conn.close()


def _ensure_subscribers_table():
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            status TEXT,
            created_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def _ensure_lead_columns():
    conn = sqlite3.connect(db_module.DB_PATH)
    existing = {row[1] for row in conn.execute("PRAGMA table_info(leads)").fetchall()}
    wanted = {
        "detected_email": "ALTER TABLE leads ADD COLUMN detected_email TEXT",
        "draft_proposal": "ALTER TABLE leads ADD COLUMN draft_proposal TEXT",
        "product_value": "ALTER TABLE leads ADD COLUMN product_value TEXT",
    }
    for column, ddl in wanted.items():
        if column not in existing:
            conn.execute(ddl)
    conn.commit()
    conn.close()


def test_signal_detail_escapes_newsletter_intro_html(client):
    _ensure_newsletter_tables()
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        """
        INSERT INTO newsletters (
            subject, intro_text, article_ids, article_metadata, scheduled_date, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "Security Test",
            "Hello<script>alert(1)</script>\nNext line",
            "[]",
            "{}",
            "2026-05-04 10:00:00",
            "SENT",
            "2026-05-04 10:00:00",
        ),
    )
    newsletter_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()

    resp = client.get(f"/signal/{newsletter_id}")

    assert resp.status_code == 200
    assert b"Hello&lt;script&gt;alert(1)&lt;/script&gt;" in resp.data
    assert b"Hello<script>alert(1)</script>" not in resp.data
    assert b"Next line" in resp.data


def test_admin_leads_preview_sanitizes_generated_html(auth_client):
    _ensure_lead_columns()
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        """
        INSERT INTO leads (
            domain, source_url, title, status, confidence_score, opportunity_reason,
            detected_email, draft_proposal, product_value
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "example.com",
            "https://example.com/post",
            "Example Lead",
            "DRAFT_READY",
            90,
            "Security test",
            "lead@example.com",
            '{"subject":"Hi","body_html":"<strong>Safe</strong><script>alert(1)</script><a href=\\"javascript:alert(2)\\">click</a><br>Done"}',
            "HIGH_VALUE",
        ),
    )
    conn.commit()
    conn.close()

    resp = auth_client.get("/admin/leads")

    assert resp.status_code == 200
    assert b"<strong>Safe</strong>" in resp.data
    assert b"javascript:alert(2)" not in resp.data
    assert b"<script>alert(1)</script>" not in resp.data
    assert b"raw-json-" not in resp.data


def test_admin_create_rejects_disallowed_upload_extension(auth_client):
    resp = auth_client.post(
        "/admin/create",
        data={
            "title": "Upload Reject Test",
            "slug": "upload-reject-test",
            "category": "Tools",
            "published_at": "2026-05-05 10:00:00",
            "source": "Test Source",
            "source_url": "https://example.com/upload-reject-test",
            "gist": "Gist",
            "why_it_matters": "Why",
            "bull_case": "Bull",
            "bear_case": "Bear",
            "deep_analysis": "Deep",
            "image_file": (io.BytesIO(b"<html>bad</html>"), "bad.html"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"not allowed" in resp.data

    conn = sqlite3.connect(db_module.DB_PATH)
    row = conn.execute(
        "SELECT id FROM articles WHERE slug = ?",
        ("upload-reject-test",),
    ).fetchone()
    conn.close()
    assert row is None


def test_stock_manager_rejects_disallowed_upload_extension(auth_client):
    bad_path = os.path.join(
        "/Users/aliemreozen/Documents/Gemini/static/stock/Business",
        "bad.html",
    )
    if os.path.exists(bad_path):
        os.remove(bad_path)

    resp = auth_client.post(
        "/admin/stock-manager",
        data={
            "category": "Business",
            "file": (io.BytesIO(b"<html>bad</html>"), "bad.html"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"not allowed" in resp.data
    assert not os.path.exists(bad_path)


def test_author_upload_rejects_disallowed_upload_extension(auth_client):
    resp = auth_client.post(
        "/admin/author",
        data={
            "name": "Ali",
            "title": "Editor",
            "bio": "Bio",
            "linkedin": "https://linkedin.com/in/test",
            "image_file": (io.BytesIO(b"<html>bad</html>"), "profile.html"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"not allowed" in resp.data

    conn = sqlite3.connect(db_module.DB_PATH)
    row = conn.execute("SELECT image FROM author_config LIMIT 1").fetchone()
    conn.close()
    if row:
        assert not str(row[0] or "").endswith(".html")


def test_welcome_email_uses_request_timeout(monkeypatch):
    import newsletter_sender

    captured = {}

    class DummyResponse:
        status_code = 200
        text = "ok"

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr(newsletter_sender, "RESEND_API_KEY", "test-key")
    monkeypatch.setattr(newsletter_sender.requests, "post", fake_post)

    assert newsletter_sender.send_welcome_email("reader@example.com") is True
    assert captured["timeout"] == newsletter_sender.RESEND_TIMEOUT_SECONDS


def test_tracking_token_requires_secret_key(monkeypatch):
    import newsletter_sender

    monkeypatch.delenv("SECRET_KEY", raising=False)

    try:
        newsletter_sender._tracking_token(1, "reader@example.com")
        assert False, "Expected RuntimeError when SECRET_KEY is missing"
    except RuntimeError as exc:
        assert "SECRET_KEY" in str(exc)


def test_send_newsletter_uses_request_timeout(monkeypatch):
    import newsletter_sender

    _ensure_newsletter_tables()
    _ensure_subscribers_table()
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute("DELETE FROM newsletters")
    conn.execute("DELETE FROM newsletter_deliveries")
    conn.execute("DELETE FROM subscribers")
    conn.execute(
        """
        INSERT INTO newsletters (
            subject, intro_text, article_ids, article_metadata, scheduled_date, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "Weekly Briefing",
            "Intro",
            "[]",
            "{}",
            "2026-05-05 09:00:00",
            "DRAFT",
            "2026-05-05 09:00:00",
        ),
    )
    newsletter_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO subscribers (email, status, created_at) VALUES (?, ?, ?)",
        ("reader@example.com", "ACTIVE", "2026-05-05 09:01:00"),
    )
    conn.commit()
    conn.close()

    captured = {}

    class DummyResponse:
        status_code = 200
        text = "ok"

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr(newsletter_sender, "DB_PATH", db_module.DB_PATH)
    monkeypatch.setattr(newsletter_sender, "RESEND_API_KEY", "test-key")
    monkeypatch.setenv("SECRET_KEY", "ci-test-newsletter-secret")
    monkeypatch.setattr(newsletter_sender.requests, "post", fake_post)
    monkeypatch.setattr(newsletter_sender.time, "sleep", lambda *_args, **_kwargs: None)

    assert newsletter_sender.send_newsletter(newsletter_id) is True
    assert captured["timeout"] == newsletter_sender.RESEND_TIMEOUT_SECONDS


@pytest.mark.parametrize(
    "payload",
    [
        {"to": ["reader@example.com"], "cc": ["other@example.com"]},
        {"to": ["reader@example.com"], "bcc": ["other@example.com"]},
        {"to": ["reader@example.com", "other@example.com"]},
        {"to": "reader@example.com"},
        {"to": ["other@example.com"]},
    ],
)
def test_newsletter_recipient_isolation_rejects_non_private_payloads(payload):
    import newsletter_sender

    with pytest.raises(ValueError, match="CRITICAL PRIVACY ERROR"):
        newsletter_sender._assert_recipient_isolation(payload, "reader@example.com")


def test_newsletter_recipient_isolation_accepts_one_matching_recipient():
    import newsletter_sender

    newsletter_sender._assert_recipient_isolation(
        {"to": ["reader@example.com"]},
        "reader@example.com",
    )


def test_subscriber_email_module_has_one_guarded_network_gateway():
    import newsletter_sender

    tree = ast.parse(Path(newsletter_sender.__file__).read_text(encoding="utf-8"))
    functions_with_direct_posts = []

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "post"
                and isinstance(func.value, ast.Name)
                and func.value.id == "requests"
            ):
                functions_with_direct_posts.append(node.name)

    assert functions_with_direct_posts == ["_post_private_email"]


def test_private_email_gateway_rejects_before_network(monkeypatch):
    import newsletter_sender

    network_called = False

    def fake_post(*_args, **_kwargs):
        nonlocal network_called
        network_called = True

    monkeypatch.setattr(newsletter_sender.requests, "post", fake_post)

    with pytest.raises(ValueError, match="CRITICAL PRIVACY ERROR"):
        newsletter_sender._post_private_email(
            {
                "to": ["reader@example.com", "other@example.com"],
                "subject": "Unsafe",
            },
            "reader@example.com",
        )

    assert network_called is False


def test_send_newsletter_adds_unsubscribe_headers_and_provider_id(monkeypatch):
    import newsletter_sender

    _ensure_newsletter_tables()
    _ensure_subscribers_table()
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute("DELETE FROM newsletters")
    conn.execute("DELETE FROM newsletter_deliveries")
    conn.execute("DELETE FROM subscribers")
    conn.execute(
        """
        INSERT INTO newsletters (
            subject, intro_text, article_ids, article_metadata, scheduled_date, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "Weekly Briefing",
            "Intro",
            "[]",
            "{}",
            "2026-05-05 09:00:00",
            "DRAFT",
            "2026-05-05 09:00:00",
        ),
    )
    newsletter_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO subscribers (email, status, created_at) VALUES (?, ?, ?)",
        ("reader@example.com", "ACTIVE", "2026-05-05 09:01:00"),
    )
    conn.commit()
    conn.close()

    captured = {}

    class DummyResponse:
        status_code = 200
        text = '{"id":"email_123"}'

        def json(self):
            return {"id": "email_123"}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return DummyResponse()

    monkeypatch.setattr(newsletter_sender, "DB_PATH", db_module.DB_PATH)
    monkeypatch.setattr(newsletter_sender, "RESEND_API_KEY", "test-key")
    monkeypatch.setenv("SECRET_KEY", "ci-test-newsletter-secret")
    monkeypatch.setattr(newsletter_sender.requests, "post", fake_post)
    monkeypatch.setattr(newsletter_sender.time, "sleep", lambda *_args, **_kwargs: None)

    assert newsletter_sender.send_newsletter(newsletter_id) is True

    payload_headers = captured["json"]["headers"]
    assert "List-Unsubscribe" in payload_headers
    assert "List-Unsubscribe-Post" in payload_headers
    assert payload_headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert f"/unsubscribe/{newsletter_id}/" in payload_headers["List-Unsubscribe"]
    assert f"/unsubscribe/{newsletter_id}/" in captured["json"]["html"]

    conn = sqlite3.connect(db_module.DB_PATH)
    row = conn.execute(
        """
        SELECT resend_message_id, provider_response
        FROM newsletter_deliveries
        WHERE newsletter_id = ? AND recipient_email = ?
        """,
        (newsletter_id, "reader@example.com"),
    ).fetchone()
    conn.close()
    assert row == ("email_123", '{"id":"email_123"}')


def test_newsletter_unsubscribe_token_marks_subscriber_inactive(client):
    _ensure_newsletter_tables()
    _ensure_subscribers_table()
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute("DELETE FROM newsletter_deliveries")
    conn.execute("DELETE FROM subscribers")
    conn.execute("DROP TABLE IF EXISTS subscriber_events")
    conn.execute(
        "INSERT INTO subscribers (email, status, created_at) VALUES (?, ?, ?)",
        ("reader@example.com", "ACTIVE", "2026-05-05 09:01:00"),
    )
    conn.execute(
        """
        INSERT INTO newsletter_deliveries (
            newsletter_id, recipient_email, status, tracking_token
        ) VALUES (?, ?, ?, ?)
        """,
        (42, "reader@example.com", "DELIVERED", "abcdef1234567890"),
    )
    conn.commit()
    conn.close()

    resp = client.post("/unsubscribe/42/abcdef1234567890")

    assert resp.status_code == 200
    assert b"unsubscribed" in resp.data.lower()
    assert "no-store" in resp.headers["Cache-Control"]

    conn = sqlite3.connect(db_module.DB_PATH)
    status = conn.execute(
        "SELECT status FROM subscribers WHERE email = ?",
        ("reader@example.com",),
    ).fetchone()[0]
    event = conn.execute(
        "SELECT event_type, reason FROM subscriber_events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert status == "UNSUBSCRIBED"
    assert event == ("unsubscribed", "newsletter_unsubscribe")


def test_proposal_send_uses_request_timeout(monkeypatch):
    import requests
    import services.proposal_agent as proposal_agent

    _ensure_lead_columns()
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute("DELETE FROM leads")
    conn.execute(
        """
        INSERT INTO leads (
            domain, source_url, title, status, confidence_score, opportunity_reason,
            detected_email, draft_proposal, product_value
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "example.com",
            "https://example.com/post",
            "Example Lead",
            "DRAFT_READY",
            88,
            "Timeout test",
            "lead@example.com",
            '{"subject":"Hi","body_html":"<p>Test</p>"}',
            "MID_VALUE",
        ),
    )
    lead_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()

    captured = {}

    class DummyResponse:
        status_code = 200
        text = "ok"

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr(proposal_agent, "DB_PATH", db_module.DB_PATH)
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setenv("RESEND_API_KEY", "test-key")

    agent = proposal_agent.ProposalAgent.__new__(proposal_agent.ProposalAgent)
    ok, _message = agent.send_active_proposal(lead_id)

    assert ok is True
    assert captured["timeout"] == proposal_agent.RESEND_TIMEOUT_SECONDS


def test_track_audio_dedupes_same_visitor(client):
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute("UPDATE articles SET audio_plays = 0 WHERE id = 1")
    conn.execute("DELETE FROM audio_play_events WHERE article_id = 1")
    conn.commit()
    conn.close()

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)",
        "Accept-Language": "en-US,en;q=0.9",
    }

    first = client.post("/api/track-audio/1", headers=headers)
    second = client.post("/api/track-audio/1", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.get_json()["counted"] is True
    assert second.get_json()["deduped"] is True

    conn = sqlite3.connect(db_module.DB_PATH)
    audio_plays = conn.execute(
        "SELECT audio_plays FROM articles WHERE id = 1"
    ).fetchone()[0]
    event_count = conn.execute(
        "SELECT COUNT(*) FROM audio_play_events WHERE article_id = 1"
    ).fetchone()[0]
    conn.close()

    assert audio_plays == 1
    assert event_count == 2


def test_homepage_uses_nonce_based_csp(client):
    resp = client.get("/")

    assert resp.status_code == 200
    csp = resp.headers["Content-Security-Policy"]
    match = re.search(r"script-src-elem 'self' 'nonce-([^']+)'", csp)

    assert match is not None
    assert "script-src-attr 'unsafe-inline'" in csp
    assert b"http-equiv=\"Content-Security-Policy\"" not in resp.data
    nonce = match.group(1)
    assert f'nonce="{nonce}"'.encode() in resp.data
