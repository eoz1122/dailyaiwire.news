import sqlite3
import time

import db as db_module
from services.subscribers import (
    ensure_subscriber_events_schema,
    ensure_subscribers_schema,
    record_subscriber_event,
)


def _reset_funnel_data():
    conn = sqlite3.connect(db_module.DB_PATH)
    ensure_subscribers_schema(conn)
    ensure_subscriber_events_schema(conn)
    conn.execute("DELETE FROM subscriber_events")
    conn.execute("DELETE FROM subscribers")
    conn.execute("DROP TABLE IF EXISTS confirmation_deliveries")
    conn.commit()
    conn.close()


def test_subscribe_form_view_is_deduplicated(client):
    _reset_funnel_data()
    headers = {
        "User-Agent": "Mozilla/5.0 Legit Browser",
        "X-Forwarded-For": "203.0.113.40",
    }

    first = client.post(
        "/api/track-subscribe-view",
        data={"placement": "homepage_inline", "source_path": "/"},
        headers=headers,
    )
    second = client.post(
        "/api/track-subscribe-view",
        data={"placement": "homepage_inline", "source_path": "/"},
        headers={**headers, "User-Agent": "Mozilla/5.0 Rotated Browser"},
    )

    assert first.status_code == 200
    assert first.get_json()["counted"] is True
    assert second.status_code == 200
    assert second.get_json()["counted"] is False
    assert first.headers["Cache-Control"] == "no-store"

    conn = sqlite3.connect(db_module.DB_PATH)
    count = conn.execute(
        "SELECT COUNT(*) FROM subscriber_events WHERE event_type = 'form_view'"
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_subscribe_form_view_rejects_unknown_placement_and_ignores_bots(client):
    _reset_funnel_data()

    invalid = client.post(
        "/api/track-subscribe-view",
        data={"placement": "invented-placement", "source_path": "/"},
        headers={"User-Agent": "Mozilla/5.0 Legit Browser"},
    )
    bot = client.post(
        "/api/track-subscribe-view",
        data={"placement": "article_inline", "source_path": "/article/test"},
        headers={"User-Agent": "Googlebot/2.1"},
    )

    assert invalid.status_code == 400
    assert bot.status_code == 200
    assert bot.get_json()["counted"] is False

    conn = sqlite3.connect(db_module.DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM subscriber_events").fetchone()[0]
    conn.close()
    assert count == 0


def test_subscriber_funnel_uses_signup_cohorts_and_placement_views():
    from services.subscribers import get_subscriber_funnel

    _reset_funnel_data()
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_subscribers_schema(conn)
    ensure_subscriber_events_schema(conn)
    conn.executemany(
        """
        INSERT INTO subscribers (
            email, status, signup_placement, confirmed_at, created_at
        ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        [
            ("confirmed@example.com", "ACTIVE", "homepage_inline", "2026-07-22 08:00:00"),
            ("pending@example.com", "PENDING", "homepage_inline", None),
            ("article@example.com", "ACTIVE", "article_sidebar", "2026-07-22 08:00:00"),
        ],
    )
    for index in range(4):
        record_subscriber_event(
            conn,
            email="",
            event_type="form_view",
            reason="visible_1s",
            ip_hash=f"hash-{index}",
            user_agent="browser",
            referrer="",
            source_path="/",
            placement="homepage_inline" if index < 3 else "article_sidebar",
        )
    record_subscriber_event(
        conn,
        email="blocked@example.com",
        event_type="blocked",
        reason="honeypot",
        ip_hash="blocked-hash",
        user_agent="bot",
        referrer="",
        source_path="/",
        placement="homepage_inline",
    )
    for index, placement in enumerate(
        ("homepage_inline", "homepage_inline", "article_sidebar")
    ):
        record_subscriber_event(
            conn,
            email="",
            event_type="qualified_submit",
            reason="passed_abuse_checks",
            ip_hash=f"qualified-{index}",
            user_agent="browser",
            referrer="",
            source_path="/",
            placement=placement,
        )
    for event_type, placement in (
        ("confirmation_sent", "homepage_inline"),
        ("confirmation_failed", "homepage_inline"),
        ("confirmation_sent", "article_sidebar"),
    ):
        record_subscriber_event(
            conn,
            email=f"{event_type}-{placement}@example.com",
            event_type=event_type,
            reason="provider_accepted" if event_type == "confirmation_sent" else "provider_request_failed",
            ip_hash="provider-event",
            user_agent="browser",
            referrer="",
            source_path="/",
            placement=placement,
        )
    conn.execute(
        """
        CREATE TABLE confirmation_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscriber_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            placement TEXT,
            accepted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            delivered_at TIMESTAMP
        )
        """
    )
    subscriber_ids = {
        row["email"]: row["id"]
        for row in conn.execute("SELECT id, email FROM subscribers").fetchall()
    }
    conn.executemany(
        """
        INSERT INTO confirmation_deliveries (
            subscriber_id, status, placement, delivered_at
        ) VALUES (?, ?, ?, ?)
        """,
        [
            (
                subscriber_ids["confirmed@example.com"],
                "DELIVERED",
                "homepage_inline",
                "2026-07-24 08:00:00",
            ),
            (
                subscriber_ids["pending@example.com"],
                "FAILED",
                "homepage_inline",
                None,
            ),
            (
                subscriber_ids["article@example.com"],
                "ACCEPTED",
                "article_sidebar",
                None,
            ),
            (
                subscriber_ids["article@example.com"],
                "SUPPRESSED",
                "article_sidebar",
                None,
            ),
        ],
    )
    conn.commit()

    funnel = get_subscriber_funnel(conn, 30)
    conn.close()

    assert funnel["summary"] == {
        "views": 4,
        "qualified_submissions": 3,
        "signups": 3,
        "confirmed": 2,
        "explicit_confirmed": 2,
        "legacy_activated": 0,
        "confirmation_sent": 2,
        "confirmation_failed": 1,
        "provider_acceptance_rate": 66.7,
        "pending": 1,
        "confirmation_tracked": 4,
        "confirmation_delivered": 1,
        "confirmation_webhook_pending": 1,
        "confirmation_delayed": 0,
        "confirmation_delivery_issues": 2,
        "confirmation_delivery_rate": 25.0,
        "blocked": 1,
        "view_to_submit_rate": 75.0,
        "submission_to_signup_rate": 100.0,
        "view_to_confirm_rate": 50.0,
        "signup_to_confirm_rate": 66.7,
    }
    placements = {row["placement"]: row for row in funnel["placements"]}
    assert placements["homepage_inline"]["views"] == 3
    assert placements["homepage_inline"]["qualified_submissions"] == 2
    assert placements["homepage_inline"]["view_to_submit_rate"] == 66.7
    assert placements["homepage_inline"]["signups"] == 2
    assert placements["homepage_inline"]["confirmed"] == 1
    assert placements["homepage_inline"]["explicit_confirmed"] == 1
    assert placements["homepage_inline"]["legacy_activated"] == 0
    assert placements["homepage_inline"]["confirmation_sent"] == 1
    assert placements["homepage_inline"]["confirmation_failed"] == 1
    assert placements["homepage_inline"]["provider_acceptance_rate"] == 50.0
    assert placements["homepage_inline"]["pending"] == 1
    assert placements["article_sidebar"]["provider_acceptance_rate"] == 100.0
    assert placements["article_sidebar"]["view_to_confirm_rate"] == 100.0


def test_subscriber_funnel_splits_legacy_active_from_explicit_confirmation():
    from services.subscribers import get_subscriber_funnel

    _reset_funnel_data()
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_subscribers_schema(conn)
    conn.execute(
        """
        INSERT INTO subscribers (
            email, status, signup_placement, confirmed_at, created_at
        ) VALUES (?, 'ACTIVE', 'subscribe_page', NULL, CURRENT_TIMESTAMP)
        """,
        ("legacy-active@example.com",),
    )
    conn.commit()

    funnel = get_subscriber_funnel(conn, 30)
    conn.close()

    assert funnel["summary"]["signups"] == 1
    assert funnel["summary"]["confirmed"] == 1
    assert funnel["summary"]["explicit_confirmed"] == 0
    assert funnel["summary"]["legacy_activated"] == 1


def test_view_conversion_excludes_signups_before_view_tracking_started():
    from services.subscribers import get_subscriber_funnel

    _reset_funnel_data()
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_subscribers_schema(conn)
    ensure_subscriber_events_schema(conn)
    conn.execute(
        """
        INSERT INTO subscribers (
            email, status, signup_placement, confirmed_at, created_at
        ) VALUES (
            ?, 'ACTIVE', 'homepage_inline', datetime('now', '-1 day'),
            datetime('now', '-1 day')
        )
        """,
        ("historical@example.com",),
    )
    record_subscriber_event(
        conn,
        email="",
        event_type="form_view",
        reason="visible_1s",
        ip_hash="current-view",
        user_agent="browser",
        referrer="",
        source_path="/",
        placement="homepage_inline",
    )
    conn.commit()

    funnel = get_subscriber_funnel(conn, 30)
    conn.close()

    assert funnel["summary"]["views"] == 1
    assert funnel["summary"]["confirmed"] == 1
    assert funnel["summary"]["view_to_confirm_rate"] == 0.0


def test_admin_subscribers_shows_funnel_and_email_stats_link(auth_client):
    _reset_funnel_data()

    response = auth_client.get("/admin/subscribers?days=30")

    assert response.status_code == 200
    assert b"Subscriber Conversion" in response.data
    assert b"Form Views" in response.data
    assert b"Qualified Submissions" in response.data
    assert b"View to Submit" in response.data
    assert b"Submit to Signup" in response.data
    assert b"Explicit Confirmed" in response.data
    assert b"Legacy Activated" in response.data
    assert b"Provider Accepted" in response.data
    assert b"Provider Failed" in response.data
    assert b"Acceptance Rate" in response.data
    assert b"Current Pending" in response.data
    assert b"Confirmation Delivery" in response.data
    assert b"Tracked Messages" in response.data
    assert b"Actually Delivered" in response.data
    assert b"Webhook Pending" in response.data
    assert b"Delivery Issues" in response.data
    assert b"Tracked Delivery Rate" in response.data
    assert b"Signup to Activated" in response.data
    assert b"Email Delivery Stats" in response.data
    assert b'href="/admin/newsletters"' in response.data
    assert b"View tracking starts from this deployment" in response.data


def test_subscriber_channel_classification_prefers_utm_then_referrer():
    from services.subscribers import classify_subscriber_channel

    assert classify_subscriber_channel(
        "/article/one?utm_source=linkedin&utm_medium=social",
        "https://www.google.com/search?q=ai",
    ) == ("linkedin", "LinkedIn")
    assert classify_subscriber_channel(
        "/article/two",
        "https://www.google.co.uk/search?q=ai",
    ) == ("google_search", "Google Search")
    assert classify_subscriber_channel(
        "/article/three",
        "https://www.linkedin.com/feed/",
    ) == ("linkedin", "LinkedIn")
    assert classify_subscriber_channel(
        "/?utm_source=weekly_signal&utm_medium=email",
        "",
    ) == ("newsletter_email", "Newsletter / Email")
    assert classify_subscriber_channel(
        "/article/four",
        "https://dailyaiwire.news/",
    ) == ("internal", "Internal navigation")
    assert classify_subscriber_channel(
        "/article/five",
        "https://mail.google.com/mail/u/0/",
    ) == ("newsletter_email", "Newsletter / Email")
    assert classify_subscriber_channel("/", "") == (
        "direct_unattributed",
        "Direct / Unattributed",
    )


def test_subscriber_acquisition_groups_channels_landings_and_weeks():
    from services.subscribers import get_subscriber_acquisition

    _reset_funnel_data()
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_subscribers_schema(conn)
    conn.executemany(
        """
        INSERT INTO subscribers (
            email, status, signup_source_path, signup_referrer,
            signup_placement, confirmed_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, datetime('now', ?))
        """,
        [
            (
                "linkedin@example.com",
                "ACTIVE",
                "/article/one?utm_source=linkedin&utm_medium=social",
                "",
                "article_inline",
                "2026-07-24 08:00:00",
                "-1 day",
            ),
            (
                "google@example.com",
                "ACTIVE",
                "/article/two",
                "https://www.google.com/search?q=ai",
                "article_sidebar",
                "2026-07-24 08:00:00",
                "-2 days",
            ),
            (
                "newsletter@example.com",
                "PENDING",
                "/subscribe?utm_source=weekly_signal&utm_medium=email",
                "",
                "subscribe_page",
                None,
                "-3 days",
            ),
            (
                "direct@example.com",
                "ACTIVE",
                "/",
                "",
                "homepage_inline",
                "2026-07-24 08:00:00",
                "-4 days",
            ),
        ],
    )
    conn.commit()

    acquisition = get_subscriber_acquisition(conn, 30)
    conn.close()

    channels = {row["channel"]: row for row in acquisition["channels"]}
    assert channels["linkedin"]["signups"] == 1
    assert channels["linkedin"]["confirmed"] == 1
    assert channels["google_search"]["confirmed"] == 1
    assert channels["newsletter_email"]["confirmed"] == 0
    assert channels["direct_unattributed"]["confirmed"] == 1

    landings = {row["path"]: row for row in acquisition["landing_pages"]}
    assert landings["/article/one"]["signups"] == 1
    assert landings["/article/one"]["confirmed"] == 1
    assert landings["/"]["label"] == "Homepage"
    assert sum(row["signups"] for row in acquisition["weeks"]) == 4
    assert sum(row["confirmed"] for row in acquisition["weeks"]) == 3
    assert acquisition["summary"]["explicit_confirmed"] == 3
    assert acquisition["summary"]["legacy_activated"] == 0


def test_homepage_forms_capture_page_load_referrer(client):
    response = client.get(
        "/",
        headers={"Referer": "https://www.linkedin.com/feed/"},
    )

    assert response.status_code == 200
    assert (
        b'name="subscribe_referrer" value="https://www.linkedin.com/feed/"'
        in response.data
    )


def test_article_sidebar_states_the_weekly_reader_value(client):
    response = client.get("/article/test-article-slug")

    assert response.status_code == 200
    assert b'data-article-sidebar-newsletter="true"' in response.data
    assert b"What changed, why it matters, and the original sources" in response.data
    assert b"Get the weekly briefing" in response.data
    assert b'value="article_sidebar"' in response.data


def test_subscribe_persists_page_load_referrer_over_internal_post_referrer(
    client,
    monkeypatch,
):
    import newsletter_sender

    _reset_funnel_data()
    monkeypatch.setattr(
        newsletter_sender,
        "send_confirmation_email",
        lambda *_args, **_kwargs: True,
    )

    response = client.post(
        "/subscribe",
        data={
            "email": "attributed@example.com",
            "form_loaded_at": str(time.time() - 10),
            "newsletter_website": "",
            "subscribe_source_path": "/article/test",
            "subscribe_placement": "article_inline",
            "subscribe_referrer": "https://www.linkedin.com/feed/",
        },
        headers={
            "Referer": "https://dailyaiwire.news/article/test",
            "User-Agent": "Mozilla/5.0 Legit Browser",
            "X-Forwarded-For": "203.0.113.91",
        },
    )

    conn = sqlite3.connect(db_module.DB_PATH)
    referrer = conn.execute(
        "SELECT signup_referrer FROM subscribers WHERE email = ?",
        ("attributed@example.com",),
    ).fetchone()[0]
    conn.close()

    assert response.status_code == 302
    assert referrer == "https://www.linkedin.com/feed/"


def test_admin_subscribers_renders_acquisition_source_report(auth_client):
    _reset_funnel_data()
    conn = sqlite3.connect(db_module.DB_PATH)
    ensure_subscribers_schema(conn)
    conn.execute(
        """
        INSERT INTO subscribers (
            email, status, signup_source_path, signup_referrer,
            signup_placement, confirmed_at, created_at
        ) VALUES (
            ?, 'ACTIVE', ?, '', 'article_inline',
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        """,
        (
            "source-report@example.com",
            "/article/report?utm_source=linkedin&utm_medium=social",
        ),
    )
    conn.commit()
    conn.close()

    response = auth_client.get("/admin/subscribers?days=30")

    assert response.status_code == 200
    assert b"Acquisition sources" in response.data
    assert b"LinkedIn" in response.data
    assert b"Landing page" in response.data
    assert b"Weekly trend" in response.data
    assert b"Historical unknowns remain unattributed" in response.data
