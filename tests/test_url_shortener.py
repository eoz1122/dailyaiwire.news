"""
Unit tests for url_shortener.py — DailyAIWire.news
Tests the Kutt API wrapper with mocked HTTP responses.
"""
from unittest.mock import patch, MagicMock

from url_shortener import shorten, _cache


class TestShorten:
    """URL shortener wrapper tests."""

    def setup_method(self):
        """Clear the in-memory cache before each test."""
        _cache.clear()

    @patch("url_shortener.KUTT_API_URL", "")
    @patch("url_shortener.KUTT_API_KEY", "")
    def test_returns_original_when_not_configured(self):
        url = "https://dailyaiwire.news/article/test"
        assert shorten(url) == url

    @patch("url_shortener.KUTT_API_URL", "https://s.dailyaiwire.news")
    @patch("url_shortener.KUTT_API_KEY", "test-key")
    @patch("url_shortener.requests.post")
    def test_returns_short_url_on_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"link": "https://s.dailyaiwire.news/abc123"}
        mock_post.return_value = mock_resp

        result = shorten("https://dailyaiwire.news/article/test")
        assert result == "https://s.dailyaiwire.news/abc123"

    @patch("url_shortener.KUTT_API_URL", "https://s.dailyaiwire.news")
    @patch("url_shortener.KUTT_API_KEY", "test-key")
    @patch("url_shortener.requests.post")
    def test_returns_original_on_api_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_post.return_value = mock_resp

        url = "https://dailyaiwire.news/article/test"
        assert shorten(url) == url

    @patch("url_shortener.KUTT_API_URL", "https://s.dailyaiwire.news")
    @patch("url_shortener.KUTT_API_KEY", "test-key")
    @patch("url_shortener.requests.post")
    def test_returns_original_on_timeout(self, mock_post):
        import requests as req
        mock_post.side_effect = req.exceptions.Timeout("timed out")

        url = "https://dailyaiwire.news/article/test"
        assert shorten(url) == url

    @patch("url_shortener.KUTT_API_URL", "https://s.dailyaiwire.news")
    @patch("url_shortener.KUTT_API_KEY", "test-key")
    @patch("url_shortener.requests.post")
    def test_cache_prevents_duplicate_calls(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"link": "https://s.dailyaiwire.news/cached"}
        mock_post.return_value = mock_resp

        url = "https://dailyaiwire.news/article/cache-test"
        shorten(url)
        shorten(url)  # second call should hit cache

        assert mock_post.call_count == 1
