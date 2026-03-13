"""
Unit tests for Facebook Page distribution — DailyAIWire.news
Tests message formatting, credential handling, and API interaction.
"""
from unittest.mock import patch, MagicMock
import os


class TestFacebookDistributor:
    """Facebook Graph API Page posting logic."""

    def _make_distributor(self, with_creds=False):
        """Create a SocialDistributor with optional FB credentials."""
        env_vars = {}
        if with_creds:
            env_vars = {
                "FB_PAGE_ID": "123456789012345",
                "FB_PAGE_ACCESS_TOKEN": "FAKE_FB_TOKEN_FOR_TESTING",
            }
        with patch.dict(os.environ, env_vars, clear=False):
            from social_distributor import SocialDistributor
            return SocialDistributor()

    def _dummy_article(self):
        return {
            "headline": "AI Breakthrough: GPT-5 Released",
            "gist": "OpenAI has released **GPT-5** with significant improvements.",
            "seo_slug": "gpt-5-released",
            "hashtags": ["#AI", "#GPT5", "#OpenAI"],
            "thought_provoking_question": "Will this change coding forever?",
            "image": "/static/images/test.jpg",
        }

    def test_skips_when_no_credentials(self, capsys):
        """Should gracefully skip when FB credentials are missing."""
        dist = self._make_distributor(with_creds=False)
        result = dist.post_to_facebook(self._dummy_article())
        assert result is False
        captured = capsys.readouterr()
        assert "credentials missing" in captured.out.lower()

    def test_correct_api_endpoint_called(self):
        """Should POST to the correct Graph API endpoint."""
        dist = self._make_distributor(with_creds=True)

        with patch("social_distributor.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"id": "123456789012345_987654321"}
            mock_post.return_value = mock_resp

            dist.post_to_facebook(self._dummy_article())

            call_args = mock_post.call_args
            assert "graph.facebook.com/v22.0/123456789012345/feed" in call_args[0][0]

    def test_message_contains_required_fields(self):
        """Message should include headline, gist (cleaned), and link."""
        dist = self._make_distributor(with_creds=True)

        with patch("social_distributor.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"id": "123_456"}
            mock_post.return_value = mock_resp

            dist.post_to_facebook(self._dummy_article())

            call_data = mock_post.call_args.kwargs.get("data", {})
            message = call_data.get("message", "")
            link = call_data.get("link", "")

            assert "GPT-5 Released" in message
            assert "**" not in message  # Markdown should be cleaned
            assert "gpt-5-released" in link
            assert "#DailyAIWire" in message

    def test_link_param_sent_separately(self):
        """Facebook link should be passed as a separate 'link' param for rich preview."""
        dist = self._make_distributor(with_creds=True)

        with patch("social_distributor.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"id": "123_456"}
            mock_post.return_value = mock_resp

            dist.post_to_facebook(self._dummy_article())

            call_data = mock_post.call_args.kwargs.get("data", {})
            assert call_data.get("link") == "https://dailyaiwire.news/article/gpt-5-released"

    def test_error_response_returns_false(self):
        """Should return False when API returns an error."""
        dist = self._make_distributor(with_creds=True)

        with patch("social_distributor.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "error": {"message": "Invalid token", "code": 190}
            }
            mock_post.return_value = mock_resp

            result = dist.post_to_facebook(self._dummy_article())
            assert result is False

    def test_rate_limit_error_is_reraised(self):
        """Rate limit errors (code 4, 32, 368) should be re-raised for scheduler backoff."""
        dist = self._make_distributor(with_creds=True)
        import pytest

        with patch("social_distributor.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "error": {"message": "Rate limit hit", "code": 4}
            }
            mock_post.return_value = mock_resp

            with pytest.raises(Exception, match="Facebook Rate Limit"):
                dist.post_to_facebook(self._dummy_article())

    def test_successful_post_returns_true(self):
        """Should return True when post succeeds."""
        dist = self._make_distributor(with_creds=True)

        with patch("social_distributor.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"id": "123456789012345_987654321"}
            mock_post.return_value = mock_resp

            result = dist.post_to_facebook(self._dummy_article())
            assert result is True
