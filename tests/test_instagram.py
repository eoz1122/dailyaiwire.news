"""
Unit tests for Instagram distribution — DailyAIWire.news
Tests caption formatting, image URL construction, and credential handling.
"""
from unittest.mock import patch, MagicMock
import os


class TestInstagramDistributor:
    """Instagram Graph API distribution logic."""

    def _make_distributor(self, with_creds=False):
        """Create a SocialDistributor with optional IG credentials."""
        env_vars = {}
        if with_creds:
            env_vars = {
                "IG_USER_ID": "17841400000000000",
                "IG_ACCESS_TOKEN": "FAKE_TOKEN_FOR_TESTING",
            }
        with patch.dict(os.environ, env_vars, clear=False):
            from social_distributor import SocialDistributor
            return SocialDistributor()

    def _dummy_article(self, image="/static/images/test.jpg"):
        return {
            "headline": "AI Breakthrough: GPT-5 Released",
            "gist": "OpenAI has released **GPT-5** with significant improvements.",
            "seo_slug": "gpt-5-released",
            "hashtags": ["#AI", "#GPT5", "#OpenAI"],
            "thought_provoking_question": "Will this change coding forever?",
            "image": image,
        }

    def test_skips_when_no_credentials(self, capsys):
        """Should gracefully skip when IG credentials are missing."""
        dist = self._make_distributor(with_creds=False)
        result = dist.post_to_instagram(self._dummy_article())
        assert result is False
        captured = capsys.readouterr()
        assert "credentials missing" in captured.out.lower()

    def test_skips_when_no_image(self, capsys):
        """Should skip when article has no image (Instagram requires one)."""
        dist = self._make_distributor(with_creds=True)
        result = dist.post_to_instagram(self._dummy_article(image=""))
        assert result is False
        captured = capsys.readouterr()
        assert "No image found" in captured.out

    def test_relative_image_url_becomes_absolute(self):
        """Relative image paths should be prepended with base URL."""
        dist = self._make_distributor(with_creds=True)
        article = self._dummy_article(image="/static/images/test.jpg")

        with patch("social_distributor.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"error": {"message": "test abort", "code": 999}}
            mock_post.return_value = mock_resp

            dist.post_to_instagram(article)

            call_args = mock_post.call_args
            assert "https://dailyaiwire.news/static/images/test.jpg" in str(call_args)

    def test_absolute_image_url_unchanged(self):
        """Full HTTP image URLs should pass through unchanged."""
        dist = self._make_distributor(with_creds=True)
        article = self._dummy_article(image="https://cdn.example.com/photo.jpg")

        with patch("social_distributor.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"error": {"message": "test abort", "code": 999}}
            mock_post.return_value = mock_resp

            dist.post_to_instagram(article)

            call_args = mock_post.call_args
            assert "https://cdn.example.com/photo.jpg" in str(call_args)

    def test_caption_contains_required_fields(self):
        """Caption should include headline, gist (cleaned), link, and hashtags."""
        dist = self._make_distributor(with_creds=True)
        article = self._dummy_article()

        with patch("social_distributor.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"error": {"message": "test abort", "code": 999}}
            mock_post.return_value = mock_resp

            dist.post_to_instagram(article)

            call_data = mock_post.call_args[1].get("data", mock_post.call_args[0][0] if mock_post.call_args[0] else {})
            # Fallback: check kwargs 'data' param
            if not call_data:
                call_data = mock_post.call_args.kwargs.get("data", {})
            caption = call_data.get("caption", "")

            assert "GPT-5 Released" in caption
            assert "**" not in caption  # Markdown should be cleaned
            assert "gpt-5-released" in caption  # Link slug
            assert "#DailyAIWire" in caption

    def test_caption_respects_2200_char_limit(self):
        """Caption must not exceed Instagram's 2,200 character limit."""
        dist = self._make_distributor(with_creds=True)
        article = self._dummy_article()
        article["gist"] = "A" * 3000  # Oversize gist

        with patch("social_distributor.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"error": {"message": "test abort", "code": 999}}
            mock_post.return_value = mock_resp

            dist.post_to_instagram(article)

            call_data = mock_post.call_args.kwargs.get("data", {})
            caption = call_data.get("caption", "")
            assert len(caption) <= 2200
