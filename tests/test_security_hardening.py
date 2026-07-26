import io
import os
import re
import sqlite3

import db as db_module


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
            opened_at TEXT
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
