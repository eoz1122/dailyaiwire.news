import sqlite3

import pytest

import db as db_module


class FakeCredentials:
    token = "test-token"

    def refresh(self, _request):
        return None


class FakeResponse:
    def __init__(self, status_code=200, text='{"ok": true}'):
        self.status_code = status_code
        self.text = text


def _fetch_audit_rows():
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT url, action, status, status_code, response_body, error "
        "FROM indexing_notifications ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return rows


@pytest.fixture(autouse=True)
def _clear_indexing_audit(_patch_db):
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute("DELETE FROM indexing_notifications")
    conn.commit()
    conn.close()


def test_notify_google_index_records_success(monkeypatch, _patch_db):
    import google_indexer

    posted = {}

    def fake_post(endpoint, headers, json, timeout):
        posted.update({
            "endpoint": endpoint,
            "headers": headers,
            "json": json,
            "timeout": timeout,
        })
        return FakeResponse(200, '{"urlNotificationMetadata": {"latestUpdate": {}}}')

    monkeypatch.setattr(google_indexer, "get_credentials", lambda: FakeCredentials())
    monkeypatch.setattr(google_indexer.requests, "post", fake_post)

    google_indexer.notify_google_index("https://dailyaiwire.news/article/new-signal")

    rows = _fetch_audit_rows()
    assert len(rows) == 1
    assert rows[0]["url"] == "https://dailyaiwire.news/article/new-signal"
    assert rows[0]["action"] == "URL_UPDATED"
    assert rows[0]["status"] == "success"
    assert rows[0]["status_code"] == 200
    assert "urlNotificationMetadata" in rows[0]["response_body"]
    assert rows[0]["error"] is None
    assert posted["json"] == {
        "url": "https://dailyaiwire.news/article/new-signal",
        "type": "URL_UPDATED",
    }


def test_notify_google_index_records_quota_and_request_failure(monkeypatch, _patch_db):
    import google_indexer

    monkeypatch.setattr(google_indexer, "get_credentials", lambda: FakeCredentials())
    monkeypatch.setattr(
        google_indexer.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(429, "quota exceeded"),
    )

    google_indexer.notify_google_index("https://dailyaiwire.news/article/quota")

    def raise_timeout(*_args, **_kwargs):
        raise google_indexer.requests.Timeout("timed out")

    monkeypatch.setattr(google_indexer.requests, "post", raise_timeout)

    google_indexer.notify_google_index("https://dailyaiwire.news/article/timeout")

    rows = _fetch_audit_rows()
    assert [row["status"] for row in rows] == ["quota_exceeded", "failed"]
    assert rows[0]["status_code"] == 429
    assert "quota exceeded" in rows[0]["response_body"]
    assert rows[1]["status_code"] is None
    assert "timed out" in rows[1]["error"]


def test_notify_google_index_records_skipped_when_credentials_missing(monkeypatch, _patch_db):
    import google_indexer

    monkeypatch.setattr(google_indexer, "get_credentials", lambda: None)

    google_indexer.notify_google_index("https://dailyaiwire.news/article/no-creds")

    rows = _fetch_audit_rows()
    assert len(rows) == 1
    assert rows[0]["status"] == "skipped"
    assert "credentials unavailable" in rows[0]["error"]


def test_admin_indexing_requires_login(client):
    resp = client.get("/admin/indexing", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_admin_indexing_page_and_csv(auth_client, _patch_db):
    from services.indexing_audit import record_indexing_notification

    record_indexing_notification(
        url="https://dailyaiwire.news/article/admin-visible",
        action="URL_UPDATED",
        status="success",
        status_code=200,
        response_body='{"ok": true}',
    )
    record_indexing_notification(
        url="https://dailyaiwire.news/article/admin-failed",
        action="URL_UPDATED",
        status="failed",
        error="network failed",
    )

    resp = auth_client.get("/admin/indexing")
    html = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "Indexing Notifications" in html
    assert "admin-visible" in html
    assert "admin-failed" in html
    assert "network failed" in html

    filtered = auth_client.get("/admin/indexing?status=failed")
    filtered_html = filtered.get_data(as_text=True)

    assert "admin-failed" in filtered_html
    assert "admin-visible" not in filtered_html

    csv_resp = auth_client.get("/admin/indexing.csv?status=failed")
    csv_body = csv_resp.get_data(as_text=True)

    assert csv_resp.status_code == 200
    assert csv_resp.mimetype == "text/csv"
    assert "url,action,status,status_code,error,attempted_at" in csv_body
    assert "admin-failed" in csv_body
    assert "admin-visible" not in csv_body


def test_retry_candidates_ignore_urls_that_later_succeeded(_patch_db):
    from services.indexing_audit import (
        fetch_retry_candidates,
        record_indexing_notification,
    )

    record_indexing_notification(
        url="https://dailyaiwire.news/article/recovered",
        action="URL_UPDATED",
        status="failed",
        error="temporary network failure",
    )
    record_indexing_notification(
        url="https://dailyaiwire.news/article/recovered",
        action="URL_UPDATED",
        status="success",
        status_code=200,
    )
    record_indexing_notification(
        url="https://dailyaiwire.news/article/still-failed",
        action="URL_UPDATED",
        status="failed",
        error="network failed",
    )
    record_indexing_notification(
        url="https://dailyaiwire.news/article/quota",
        action="URL_UPDATED",
        status="quota_exceeded",
        status_code=429,
    )

    candidates = fetch_retry_candidates(limit=10)

    assert [row["url"] for row in candidates] == [
        "https://dailyaiwire.news/article/still-failed",
        "https://dailyaiwire.news/article/quota",
    ]
