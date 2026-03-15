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
        env_vars = {
            "FB_PAGE_ID": "",
            "FB_PAGE_ACCESS_TOKEN": "",
        }
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

    def test_skips_when_no_credentials(self, caplog):
        """Should gracefully skip when FB credentials are missing."""
        dist = self._make_distributor(with_creds=False)
        result = dist.post_to_facebook(self._dummy_article())
        assert result is False
        assert "credentials missing" in caplog.text.lower()

    @patch("social_distributor.requests.post")
    def test_correct_api_endpoint_called(self, mock_post):
        """Should POST to the Graph API photos or feed endpoint."""
        dist = self._make_distributor(with_creds=True)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "123456789012345_987654321"}
        mock_post.return_value = mock_resp

        with patch("ig_card_generator.generate_card", return_value="/tmp/test.png"):
            dist.post_to_facebook(self._dummy_article())

        call_url = mock_post.call_args[0][0]
        assert "graph.facebook.com/v22.0/123456789012345/" in call_url

    @patch("social_distributor.requests.post")
    def test_message_contains_required_fields(self, mock_post):
        """Message should include headline, gist (cleaned), and UTM link."""
        dist = self._make_distributor(with_creds=True)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "123_456"}
        mock_post.return_value = mock_resp

        with patch("ig_card_generator.generate_card", return_value="/tmp/test.png"):
            dist.post_to_facebook(self._dummy_article())

        call_data = mock_post.call_args.kwargs.get("data", {})
        # Check caption (photo post) or message (link post)
        text = call_data.get("caption", call_data.get("message", ""))

        assert "GPT-5 Released" in text
        assert "**" not in text  # Markdown should be cleaned
        assert "#DailyAIWire" in text

    @patch("social_distributor.requests.post")
    def test_utm_params_in_link(self, mock_post):
        """Facebook links should include UTM tracking parameters."""
        dist = self._make_distributor(with_creds=True)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "123_456"}
        mock_post.return_value = mock_resp

        with patch("ig_card_generator.generate_card", return_value="/tmp/test.png"):
            dist.post_to_facebook(self._dummy_article())

        call_data = mock_post.call_args.kwargs.get("data", {})
        text = call_data.get("caption", call_data.get("message", ""))
        link = call_data.get("link", text)
        assert "utm_source=facebook" in link

    def test_error_response_returns_false(self):
        """Should return False when API returns an error."""
        dist = self._make_distributor(with_creds=True)

        with patch("social_distributor.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "error": {"message": "Invalid token", "code": 190}
            }
            mock_post.return_value = mock_resp

            with patch("ig_card_generator.generate_card", return_value="/tmp/test.png"):
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

            with patch("ig_card_generator.generate_card", return_value="/tmp/test.png"):
                with pytest.raises(Exception, match="Facebook Rate Limit"):
                    dist.post_to_facebook(self._dummy_article())

    def test_successful_post_returns_true(self):
        """Should return True when post succeeds."""
        dist = self._make_distributor(with_creds=True)

        with patch("social_distributor.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"id": "123456789012345_987654321"}
            mock_post.return_value = mock_resp

            with patch("ig_card_generator.generate_card", return_value="/tmp/test.png"):
                result = dist.post_to_facebook(self._dummy_article())
            assert result is True
