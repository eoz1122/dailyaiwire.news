from flask import render_template


def test_confirmation_template_renders_confirm_link(client):
    from app import app

    with app.app_context():
        html = render_template(
            "email/confirmation.html",
            confirmation_url="https://dailyaiwire.news/confirm-subscription/test-token",
        )

    assert "Confirm your subscription" in html
    assert "DailyAIWire" in html
    assert "https://dailyaiwire.news/confirm-subscription/test-token" in html
    assert "If you did not request this" in html


def test_send_confirmation_email_uses_confirmation_template(client, monkeypatch):
    import newsletter_sender

    captured = {}

    class FakeResponse:
        status_code = 200
        text = "ok"

    def fake_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(newsletter_sender, "RESEND_API_KEY", "test-key")
    monkeypatch.setattr(newsletter_sender.requests, "post", fake_post)

    sent = newsletter_sender.send_confirmation_email(
        "reader@example.com",
        "https://dailyaiwire.news/confirm-subscription/test-token",
    )

    assert sent is True
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["timeout"] == 10
    assert captured["payload"]["to"] == ["reader@example.com"]
    assert captured["payload"]["subject"] == "Confirm your DailyAIWire subscription"
    assert "Confirm your subscription" in captured["payload"]["html"]
    assert "https://dailyaiwire.news/confirm-subscription/test-token" in captured["payload"]["html"]
