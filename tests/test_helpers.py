"""
Unit tests for helpers.py — DailyAIWire.news
Tests template filters: time_ago, remove_emojis, slugify, add_utm_to_html.
"""
from datetime import datetime, timedelta, timezone

from helpers import time_ago, remove_emojis, slugify, add_utm_to_html


# ── slugify ──────────────────────────────────────────────────────────

class TestSlugify:
    def test_basic(self):
        assert slugify("Hello World") == "hello-world"

    def test_special_chars(self):
        assert slugify("AI & Machine Learning!") == "ai-machine-learning"

    def test_multiple_spaces(self):
        assert slugify("  too   many   spaces  ") == "too-many-spaces"

    def test_unicode(self):
        result = slugify("Gemini 2.5 — Pro Release")
        assert "gemini" in result
        assert "--" not in result

    def test_empty(self):
        assert slugify("") == ""


# ── remove_emojis ───────────────────────────────────────────────────

class TestRemoveEmojis:
    def test_removes_emoji(self):
        assert remove_emojis("Hello 🚀 World") == "Hello  World"

    def test_no_emoji(self):
        assert remove_emojis("No emoji here") == "No emoji here"

    def test_none_input(self):
        assert remove_emojis(None) == ""

    def test_empty_input(self):
        assert remove_emojis("") == ""

    def test_only_emoji(self):
        result = remove_emojis("🔥🚀💡")
        assert result.strip() == ""


# ── time_ago ─────────────────────────────────────────────────────────

class TestTimeAgo:
    def test_none_input(self):
        assert time_ago(None) == ""

    def test_empty_string(self):
        assert time_ago("") == ""

    def test_just_now(self):
        now = datetime.now(timezone.utc).isoformat()
        result = time_ago(now)
        assert result in ("Just now", "1m ago")

    def test_minutes_ago(self):
        dt = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        result = time_ago(dt)
        assert "m ago" in result

    def test_hours_ago(self):
        dt = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        result = time_ago(dt)
        assert "h ago" in result

    def test_days_ago(self):
        dt = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        result = time_ago(dt)
        assert "d ago" in result

    def test_weeks_ago(self):
        dt = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        result = time_ago(dt)
        assert "w ago" in result

    def test_months_ago(self):
        dt = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
        result = time_ago(dt)
        assert "mo ago" in result

    def test_one_day_plus_hours_rolls_to_days(self):
        dt = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
        result = time_ago(dt)
        assert "d ago" in result

    def test_utc_naive_timestamp_stays_hour_granular_before_24h(self):
        dt = (datetime.now(timezone.utc) - timedelta(hours=23)).strftime('%Y-%m-%d %H:%M:%S')
        result = time_ago(dt)
        assert "h ago" in result

    def test_old_date_returns_years_for_very_old_dates(self):
        dt = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
        result = time_ago(dt)
        assert "y ago" in result

    def test_future_date(self):
        dt = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        result = time_ago(dt)
        assert result == "Future"

    def test_space_separated_format(self):
        result = time_ago("2026-03-10 12:00:00")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_invalid_string(self):
        result = time_ago("not-a-date")
        assert result == "not-a-date"


# ── add_utm_to_html ─────────────────────────────────────────────────

class TestAddUtmToHtml:
    def test_adds_utm_params(self):
        html = '<a href="https://example.com">Link</a>'
        result = add_utm_to_html(html)
        assert "utm_source=dailyaiwire" in result
        assert "utm_medium=smart_referral" in result

    def test_skips_existing_utm(self):
        html = '<a href="https://example.com?utm_source=dailyaiwire">Link</a>'
        result = add_utm_to_html(html)
        # Should not double-add UTM
        assert result.count("utm_source=dailyaiwire") == 1

    def test_preserves_existing_params(self):
        html = '<a href="https://example.com?foo=bar">Link</a>'
        result = add_utm_to_html(html)
        assert "foo=bar" in result
        assert "&utm_source=dailyaiwire" in result

    def test_none_input(self):
        assert add_utm_to_html(None) == ""

    def test_empty_input(self):
        assert add_utm_to_html("") == ""

    def test_no_links(self):
        html = "<p>No links here</p>"
        assert add_utm_to_html(html) == html
