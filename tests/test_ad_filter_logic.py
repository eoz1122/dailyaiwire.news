from types import SimpleNamespace

import embedding_service
import numpy as np


def test_ad_reference_seed_corpus_has_at_least_thirty_examples():
    assert len(embedding_service._AD_REFERENCE_TEXTS) >= 30


def test_policy_news_dampening_reduces_borderline_false_positive(monkeypatch):
    class FakeClient:
        def count(self, _collection):
            return SimpleNamespace(count=25)

        def search(self, **kwargs):
            return [SimpleNamespace(score=0.555)]

    monkeypatch.setattr(embedding_service, "get_qdrant", lambda: FakeClient())
    monkeypatch.setattr(embedding_service, "embed_texts", lambda texts: np.array([[0.1, 0.2, 0.3]]))

    score = embedding_service.score_ad_likelihood(
        "EU Passes Landmark AI Regulation Framework",
        "The European Parliament approved comprehensive AI regulation requiring transparency and risk assessment for high-stakes AI systems.",
        "This sets global precedent for how artificial intelligence will be governed.",
    )

    assert score < 0.55


def test_promotional_cta_does_not_get_policy_dampening(monkeypatch):
    class FakeClient:
        def count(self, _collection):
            return SimpleNamespace(count=25)

        def search(self, **kwargs):
            return [SimpleNamespace(score=0.7)]

    monkeypatch.setattr(embedding_service, "get_qdrant", lambda: FakeClient())
    monkeypatch.setattr(embedding_service, "embed_texts", lambda texts: np.array([[0.1, 0.2, 0.3]]))

    score = embedding_service.score_ad_likelihood(
        "New App Lets You Block Spam Calls for Free",
        "Download the app now and protect your family from unwanted calls with premium features.",
        "Available for free on iOS and Android with optional premium upgrade.",
    )

    assert score == 0.7
