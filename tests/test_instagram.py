"""
Unit tests for Instagram distribution — DailyAIWire.news
Tests caption formatting, branded card generation, and credential handling.
"""
from unittest.mock import patch, MagicMock
import os


class TestInstagramDistributor:
    """Instagram Graph API distribution logic."""

    def _make_distributor(self, with_creds=False):
        """Create a SocialDistributor with optional IG credentials."""
        env_vars = {
            "IG_USER_ID": "",
            "IG_ACCESS_TOKEN": "",
        }
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

    def test_skips_when_no_credentials(self, caplog):
        """Should gracefully skip when IG credentials are missing."""
        dist = self._make_distributor(with_creds=False)
        result = dist.post_to_instagram(self._dummy_article())
        assert result is False
        assert "credentials missing" in caplog.text.lower()

    @patch("social_distributor.requests.post")
    def test_uses_branded_card_by_default(self, mock_post):
        """Should generate a branded card image instead of using source image."""
        dist = self._make_distributor(with_creds=True)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": {"message": "test abort", "code": 999}}
        mock_post.return_value = mock_resp

        with patch("ig_card_generator.generate_card", return_value="/tmp/social/test.png") as mock_gen:
            dist.post_to_instagram(self._dummy_article())
            mock_gen.assert_called_once()

        call_data = mock_post.call_args.kwargs.get("data", {})
        image_url = call_data.get("image_url", "")
        assert "/static/img/social/" in image_url

    @patch("social_distributor.requests.post")
    def test_falls_back_to_source_image_on_card_error(self, mock_post):
        """Should fallback to source article image if card generation fails."""
        dist = self._make_distributor(with_creds=True)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": {"message": "test abort", "code": 999}}
        mock_post.return_value = mock_resp

        with patch("ig_card_generator.generate_card", side_effect=Exception("Pillow broken")):
            dist.post_to_instagram(self._dummy_article(image="https://cdn.example.com/photo.jpg"))

        call_data = mock_post.call_args.kwargs.get("data", {})
        image_url = call_data.get("image_url", "")
        assert "https://cdn.example.com/photo.jpg" in image_url

    @patch("social_distributor.requests.post")
    def test_caption_contains_required_fields(self, mock_post):
        """Caption should include headline, gist (cleaned), link, and hashtags."""
        dist = self._make_distributor(with_creds=True)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": {"message": "test abort", "code": 999}}
        mock_post.return_value = mock_resp

        with patch("ig_card_generator.generate_card", return_value="/tmp/test.png"):
            dist.post_to_instagram(self._dummy_article())

        call_data = mock_post.call_args.kwargs.get("data", {})
        caption = call_data.get("caption", "")

        assert "GPT-5 Released" in caption
        assert "**" not in caption  # Markdown should be cleaned
        assert "gpt-5-released" in caption  # Link slug
        assert "#DailyAIWire" in caption

    @patch("social_distributor.requests.post")
    def test_utm_params_in_link(self, mock_post):
        """Instagram links should include UTM tracking parameters."""
        dist = self._make_distributor(with_creds=True)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": {"message": "test abort", "code": 999}}
        mock_post.return_value = mock_resp

        with patch("ig_card_generator.generate_card", return_value="/tmp/test.png"):
            dist.post_to_instagram(self._dummy_article())

        call_data = mock_post.call_args.kwargs.get("data", {})
        caption = call_data.get("caption", "")
        assert "utm_source=instagram" in caption

    @patch("social_distributor.requests.post")
    def test_caption_respects_2200_char_limit(self, mock_post):
        """Caption must not exceed Instagram's 2,200 character limit."""
        dist = self._make_distributor(with_creds=True)
        article = self._dummy_article()
        article["gist"] = "A" * 3000  # Oversize gist

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": {"message": "test abort", "code": 999}}
        mock_post.return_value = mock_resp

        with patch("ig_card_generator.generate_card", return_value="/tmp/test.png"):
            dist.post_to_instagram(article)

        call_data = mock_post.call_args.kwargs.get("data", {})
        caption = call_data.get("caption", "")
        assert len(caption) <= 2200
