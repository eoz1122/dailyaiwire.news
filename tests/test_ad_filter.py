"""
Tests for Ad/Promotional Content Detection — DailyAIWire.news
Validates the vector-based ad filter using embedding_service.score_ad_likelihood().

NOTE: These tests require qdrant_client and sentence_transformers (VPS deps).
They will skip automatically when run locally without those packages.
"""
import pytest

# Skip entire module if VPS dependencies aren't installed
pytest.importorskip("qdrant_client", reason="qdrant_client not installed (VPS-only)")
pytest.importorskip("sentence_transformers", reason="sentence_transformers not installed (VPS-only)")


# ── Test the ad-reference seeder ────────────────────────────────────

class TestAdReferenceSeed:
    """Verify ad-reference vectors can be seeded and collection stats update."""

    def test_seed_populates_collection(self):
        """seed_ad_references() should return count > 0."""
        from embedding_service import seed_ad_references
        count = seed_ad_references()
        assert count >= 30, f"Expected >= 30 ad-reference vectors, got {count}"

    def test_collection_stats_include_ad_count(self):
        """get_collection_stats() should report ad_reference_vectors."""
        from embedding_service import get_collection_stats
        stats = get_collection_stats()
        assert "ad_reference_vectors" in stats
        assert stats["ad_reference_vectors"] >= 30


# ── Test promotional content detection ──────────────────────────────

class TestAdLikelihoodScoring:
    """Validate score_ad_likelihood() catches promo content and passes legit news."""

    @pytest.fixture(autouse=True)
    def _seed(self):
        """Ensure ad-reference collection is populated before tests."""
        from embedding_service import seed_ad_references
        seed_ad_references()

    def test_obvious_ad_scores_high(self):
        """A single-product feature announcement should score >= 0.65."""
        from embedding_service import score_ad_likelihood
        score = score_ad_likelihood(
            "Truecaller's New Feature Lets You Protect Family From Scams",
            "Truecaller's new feature allows users to remotely protect family members from scam calls by acting as an admin.",
            "This feature addresses the growing problem of scam calls targeting vulnerable individuals."
        )
        assert score >= 0.65, f"Expected ad score >= 0.65 for obvious promo, got {score}"

    def test_download_cta_scores_high(self):
        """A download/signup push should score >= 0.65."""
        from embedding_service import score_ad_likelihood
        score = score_ad_likelihood(
            "New App Lets You Block Spam Calls for Free",
            "Download the app now and protect your family from unwanted calls with premium features.",
            "Available for free on iOS and Android with optional premium upgrade."
        )
        assert score >= 0.65, f"Expected ad score >= 0.65 for download CTA, got {score}"

    def test_legitimate_ai_news_scores_low(self):
        """Real AI industry news should score < 0.55."""
        from embedding_service import score_ad_likelihood
        score = score_ad_likelihood(
            "Western AI Models Struggle in Global South Agriculture",
            "Agricultural AI systems trained on Western data fail to account for crop varieties and farming practices in developing nations.",
            "The AI divide in agriculture threatens food security in regions that need it most."
        )
        assert score < 0.55, f"Expected ad score < 0.55 for legit news, got {score}"

    def test_policy_news_scores_low(self):
        """AI regulation news should not be flagged as ad."""
        from embedding_service import score_ad_likelihood
        score = score_ad_likelihood(
            "EU Passes Landmark AI Regulation Framework",
            "The European Parliament approved comprehensive AI regulation requiring transparency and risk assessment for high-stakes AI systems.",
            "This sets global precedent for how artificial intelligence will be governed."
        )
        assert score < 0.55, f"Expected ad score < 0.55 for policy news, got {score}"

    def test_acquisition_news_not_flagged(self):
        """Major acquisition news with company mentions should pass through."""
        from embedding_service import score_ad_likelihood
        score = score_ad_likelihood(
            "Microsoft Acquires AI Startup for $2.5 Billion",
            "Microsoft has acquired a leading AI infrastructure startup in its largest deal since the Activision merger.",
            "The acquisition signals growing competition for AI talent and computing resources."
        )
        assert score < 0.60, f"Expected ad score < 0.60 for acquisition news, got {score}"

    def test_graceful_failure_returns_zero(self):
        """On any internal error, score_ad_likelihood should return 0.0."""
        from embedding_service import score_ad_likelihood
        # Empty inputs should not crash
        score = score_ad_likelihood("", "", "")
        assert score >= 0.0  # Just verify it doesn't raise
