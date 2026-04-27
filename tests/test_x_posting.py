from datetime import datetime, timedelta, timezone
import os
from unittest.mock import patch

import pytest


def _make_distributor(with_creds=False):
    env_vars = {
        "X_API_KEY": "",
        "X_API_SECRET": "",
        "X_ACCESS_TOKEN": "",
        "X_ACCESS_SECRET": "",
        "X_BEARER_TOKEN": "",
    }
    if with_creds:
        env_vars = {
            "X_API_KEY": "test-key",
            "X_API_SECRET": "test-secret",
            "X_ACCESS_TOKEN": "test-access-token",
            "X_ACCESS_SECRET": "test-access-secret",
            "X_BEARER_TOKEN": "test-bearer-token",
        }
    with patch.dict(os.environ, env_vars, clear=False):
        from social_distributor import SocialDistributor

        return SocialDistributor()


def _dummy_article():
    return {
        "headline": "AI Policy Update",
        "gist": "A concise summary of the article.",
        "seo_slug": "ai-policy-update",
        "hashtags": ["#AI", "#Policy"],
        "thought_provoking_question": "What changes next?",
        "source": "Test Source",
    }


def test_classify_x_exception_maps_payment_required_to_billing_pause():
    from social_distributor import XPostingPause, classify_x_exception

    with patch.dict(os.environ, {"X_BILLING_BACKOFF_SECONDS": "21600"}, clear=False):
        pause = classify_x_exception(
            Exception("402 Payment Required\nYour enrolled account does not have any credits to fulfill this request.")
        )

    assert isinstance(pause, XPostingPause)
    assert pause.reason == "billing"
    assert pause.retry_after_seconds == 21600


def test_classify_x_exception_maps_rate_limit_to_retry_pause():
    from social_distributor import XPostingPause, classify_x_exception

    with patch.dict(os.environ, {"X_RATE_LIMIT_BACKOFF_SECONDS": "1800"}, clear=False):
        pause = classify_x_exception(Exception("429 Too Many Requests"))

    assert isinstance(pause, XPostingPause)
    assert pause.reason == "rate_limit"
    assert pause.retry_after_seconds == 1800


def test_post_to_x_raises_billing_pause_signal():
    from social_distributor import XPostingPause

    distributor = _make_distributor(with_creds=True)

    with patch("social_distributor.shorten", return_value="https://s.dailyaiwire.news/test"), \
         patch("social_distributor.notify_google_index"), \
         patch("social_distributor.tweepy.Client") as mock_client:
        mock_client.return_value.create_tweet.side_effect = Exception(
            "402 Payment Required\nYour enrolled account does not have any credits to fulfill this request."
        )

        with pytest.raises(XPostingPause) as exc_info:
            distributor.post_to_x(_dummy_article())

    assert exc_info.value.reason == "billing"


def test_build_x_backoff_window_is_deterministic():
    from tweet_scheduler import _build_x_backoff_window

    now_utc = datetime(2026, 4, 27, 21, 0, tzinfo=timezone.utc)
    until, label = _build_x_backoff_window("billing", 21600, now_utc=now_utc)

    assert until == now_utc + timedelta(hours=6)
    assert label == "billing/credits"
