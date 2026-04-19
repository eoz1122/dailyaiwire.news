import sqlite3
from types import SimpleNamespace

import pytest

import db
from fetcher import ai_processor
import remove_duplicates
import services.lead_extractor as lead_extractor_module
from services.ai_gateway import AIGateway
from services.ai_schemas import DuplicatePair, DuplicateReviewPayload, LeadExtractionResult


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.usage_metadata = SimpleNamespace(prompt_token_count=10, candidates_token_count=5)


def test_ai_gateway_validates_structured_json(monkeypatch):
    class FakeModel:
        def __init__(self, *args, **kwargs):
            pass

        def generate_content(self, *args, **kwargs):
            return _FakeResponse(
                '```json\n{"company_name":"Acme AI","email":"team@acme.ai","confidence":88,"product_value":"HIGH_VALUE","reason":"Clear enterprise fit"}\n```'
            )

    from services import ai_gateway as gateway_module

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(gateway_module.genai, "configure", lambda **kwargs: None)
    monkeypatch.setattr(gateway_module.genai, "GenerativeModel", FakeModel)

    gateway = AIGateway("gemini-test")
    result, _response = gateway.generate_structured(
        "extract",
        LeadExtractionResult,
        prompt_type="test_lead_extraction",
    )

    assert result.company_name == "Acme AI"
    assert result.email == "team@acme.ai"

    conn = sqlite3.connect(db.DB_PATH)
    row = conn.execute(
        "SELECT prompt_type, model FROM ai_logs WHERE prompt_type = 'test_lead_extraction' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row == ("test_lead_extraction", "gemini-test")


def test_process_batch_does_not_mark_sent_to_api_before_validation(monkeypatch):
    recorded_statuses = []

    class FakeGateway:
        def __init__(self, *args, **kwargs):
            pass

        def generate_structured(self, *args, **kwargs):
            return ([
                ai_processor.ArticleAnalysis(
                    status="SUCCESS",
                    batch_id=0,
                    headline="Validated Headline",
                    seo_slug="validated-headline",
                    image_query="robotics",
                    category="Tools",
                    gist="Short gist.",
                    key_details=["Fact 1", "Fact 2"],
                    why_it_matters="Because it matters.",
                    optimistic_outlook="Upside view.",
                    pessimistic_outlook="Risk view.",
                    hashtags=["#AI"],
                    thought_provoking_question="What changes next?",
                    eli5="Simple explanation.",
                    importance_score=77,
                    deep_analysis="Three paragraph style analysis.",
                    narration_script="Intelligence from DailyAIWire dot news...",
                )
            ], _FakeResponse("{}"))

    class FakeLeadExtractor:
        def extract_and_log(self, *args, **kwargs):
            return None

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(ai_processor, "AIGateway", FakeGateway)
    monkeypatch.setattr(ai_processor, "extract_content", lambda url: ("x" * 1000, "", ""))
    monkeypatch.setattr(ai_processor, "is_spam_source", lambda link, title: False)
    monkeypatch.setattr(ai_processor.budget, "can_make_request", lambda estimated_tokens: True)
    monkeypatch.setattr(ai_processor.budget, "log_request", lambda *args, **kwargs: None)
    monkeypatch.setattr(ai_processor, "log_processing_attempt", lambda url, status="PROCESSING": recorded_statuses.append(status))
    monkeypatch.setattr(lead_extractor_module, "LeadExtractor", FakeLeadExtractor)

    result = ai_processor.process_batch([
        {"title": "Test Source Story", "link": "https://example.com/story", "rss_summary": "summary"}
    ])

    assert result
    assert "SENT_TO_API" not in recorded_statuses


def test_ai_dedup_flags_review_without_deleting_articles(monkeypatch):
    conn = sqlite3.connect(db.DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO articles (slug, title, image, category, gist, why_it_matters, bull_case, bear_case, key_details, eli5, deep_analysis, source, source_url, full_json, published_at, importance_score, is_published, design_tokens)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, ?)
        """,
        (
            "dup-1",
            "OpenAI launches Sora API",
            "/static/fallbacks/tools_0.jpg",
            "Tools",
            "gist",
            "impact",
            "up",
            "down",
            "[]",
            "eli5",
            "analysis",
            "Source",
            "https://example.com/dup-1",
            "{}",
            80,
            1,
            "{}",
        ),
    )
    keep_id = cur.lastrowid
    cur.execute(
        """
        INSERT INTO articles (slug, title, image, category, gist, why_it_matters, bull_case, bear_case, key_details, eli5, deep_analysis, source, source_url, full_json, published_at, importance_score, is_published, design_tokens)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, ?)
        """,
        (
            "dup-2",
            "Sora video generation comes to all users",
            "/static/fallbacks/tools_0.jpg",
            "Tools",
            "gist",
            "impact",
            "up",
            "down",
            "[]",
            "eli5",
            "analysis",
            "Source",
            "https://example.com/dup-2",
            "{}",
            79,
            1,
            "{}",
        ),
    )
    delete_id = cur.lastrowid
    before_count = cur.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    conn.commit()
    conn.close()

    class FakeGateway:
        def __init__(self, *args, **kwargs):
            pass

        def generate_structured(self, *args, **kwargs):
            return (
                DuplicateReviewPayload(
                    duplicate_pairs=[
                        DuplicatePair(
                            keep_id=keep_id,
                            delete_id=delete_id,
                            reason="same launch event",
                        )
                    ]
                ),
                _FakeResponse("{}"),
            )

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(remove_duplicates, "AIGateway", FakeGateway)

    remove_duplicates.ai_deduplicate(recent_only=False)

    conn = sqlite3.connect(db.DB_PATH)
    after_count = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    review_row = conn.execute(
        """
        SELECT keep_article_id, duplicate_article_id, detection_method, status
        FROM duplicate_review_queue
        WHERE keep_article_id = ? AND duplicate_article_id = ?
        """,
        (keep_id, delete_id),
    ).fetchone()
    conn.close()

    assert after_count == before_count
    assert review_row == (keep_id, delete_id, "AI_SEMANTIC", "PENDING_REVIEW")
