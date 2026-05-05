import sqlite3
from types import SimpleNamespace

import pytest

import ai_config
import db
from fetcher import ai_processor
import remove_duplicates
import services.lead_extractor as lead_extractor_module
from services.ai_gateway import AIGateway
from services.ai_schemas import DuplicatePair, DuplicateReviewPayload, LeadExtractionResult, ProposalDraft


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.usage_metadata = SimpleNamespace(
            prompt_token_count=10,
            candidates_token_count=5,
            thoughts_token_count=20,
            total_token_count=35,
        )


def _patch_fake_genai_client(monkeypatch, response_text: str):
    calls = []

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            calls.append(
                {
                    "model": model,
                    "contents": contents,
                    "config": config,
                }
            )
            return _FakeResponse(response_text)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.models = FakeModels()

    from services import ai_gateway as gateway_module

    monkeypatch.setattr(gateway_module.genai, "Client", FakeClient)
    return calls


def test_ai_gateway_validates_structured_json(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    calls = _patch_fake_genai_client(
        monkeypatch,
        '```json\n{"company_name":"Acme AI","email":"team@acme.ai","confidence":88,"product_value":"HIGH_VALUE","reason":"Clear enterprise fit"}\n```',
    )

    gateway = AIGateway(
        "gemini-test",
        system_instruction="system",
        generation_config={"response_mime_type": "application/json"},
        thinking_budget=0,
    )
    result, _response = gateway.generate_structured(
        "extract",
        LeadExtractionResult,
        prompt_type="test_lead_extraction",
        request_options={"timeout": 600},
    )

    assert result.company_name == "Acme AI"
    assert result.email == "team@acme.ai"
    assert calls[0]["model"] == "gemini-test"
    assert calls[0]["contents"] == "extract"
    assert calls[0]["config"].system_instruction == "system"
    assert calls[0]["config"].response_mime_type == "application/json"
    assert calls[0]["config"].thinking_config.thinking_budget == 0
    assert calls[0]["config"].http_options.timeout == 600000

    conn = sqlite3.connect(db.DB_PATH)
    row = conn.execute(
        "SELECT prompt_type, model FROM ai_logs WHERE prompt_type = 'test_lead_extraction' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row == ("test_lead_extraction", "gemini-test")


def test_ai_gateway_logs_total_tokens_including_thoughts(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _patch_fake_genai_client(
        monkeypatch,
        '{"company_name":"Acme AI","email":"team@acme.ai","confidence":88,"product_value":"HIGH_VALUE","reason":"Clear enterprise fit"}',
    )

    gateway = AIGateway("gemini-test")
    gateway.generate_structured(
        "extract",
        LeadExtractionResult,
        prompt_type="test_total_token_logging",
    )

    conn = sqlite3.connect(db.DB_PATH)
    row = conn.execute(
        "SELECT cost_estimate FROM ai_logs WHERE prompt_type = 'test_total_token_logging' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()

    assert row == (35.0,)


def _ensure_proposal_lead_columns():
    conn = sqlite3.connect(db.DB_PATH)
    existing = {row[1] for row in conn.execute("PRAGMA table_info(leads)").fetchall()}
    wanted = {
        "detected_email": "ALTER TABLE leads ADD COLUMN detected_email TEXT",
        "draft_proposal": "ALTER TABLE leads ADD COLUMN draft_proposal TEXT",
        "product_value": "ALTER TABLE leads ADD COLUMN product_value TEXT",
    }
    for column, ddl in wanted.items():
        if column not in existing:
            conn.execute(ddl)
    conn.commit()
    conn.close()


def test_proposal_agent_uses_gateway_with_routine_settings(monkeypatch):
    import services.proposal_agent as proposal_agent_module

    _ensure_proposal_lead_columns()
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute("DELETE FROM leads")
    conn.execute(
        """
        INSERT INTO leads (
            domain, source_url, title, status, confidence_score, opportunity_reason,
            detected_email, draft_proposal, product_value
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "example.com",
            "https://example.com/post",
            "Example Lead",
            "NEW",
            90,
            "Gateway migration test",
            "lead@example.com",
            None,
            "MID_VALUE",
        ),
    )
    lead_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()

    calls = {}
    budget_logs = []

    class FakeGateway:
        def __init__(self, model_name, *, system_instruction=None, generation_config=None, thinking_budget=None, logger_name=None):
            calls["init"] = {
                "model_name": model_name,
                "system_instruction": system_instruction,
                "generation_config": generation_config,
                "thinking_budget": thinking_budget,
                "logger_name": logger_name,
            }

        def generate_structured(self, prompt, schema, *, prompt_type, request_options=None, generation_config=None):
            calls["generate"] = {
                "prompt": prompt,
                "schema": schema,
                "prompt_type": prompt_type,
                "request_options": request_options,
                "generation_config": generation_config,
            }
            return (
                ProposalDraft(subject="Sharp Subject", body_html="<p>Body</p>"),
                SimpleNamespace(
                    usage_metadata=SimpleNamespace(
                        prompt_token_count=12,
                        candidates_token_count=8,
                    )
                ),
            )

    monkeypatch.setattr(proposal_agent_module, "AIGateway", FakeGateway)
    monkeypatch.setattr(proposal_agent_module, "DB_PATH", db.DB_PATH)
    monkeypatch.setattr(proposal_agent_module.budget, "can_make_request", lambda estimated_tokens=0: True)
    monkeypatch.setattr(
        proposal_agent_module.budget,
        "log_request",
        lambda input_tokens, output_tokens, category="": budget_logs.append(
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "category": category,
            }
        ),
    )

    agent = proposal_agent_module.ProposalAgent()
    draft_json = agent.generate_pitch(lead_id)

    assert calls["init"]["model_name"] == ai_config.ROUTINE_MODEL
    assert calls["init"]["thinking_budget"] == ai_config.ROUTINE_THINKING_BUDGET
    assert calls["init"]["generation_config"] == {"response_mime_type": "application/json"}
    assert calls["init"]["logger_name"] == "proposal_agent"
    assert calls["generate"]["schema"] is ProposalDraft
    assert calls["generate"]["prompt_type"] == "proposal_generation"
    assert "Example Lead" in calls["generate"]["prompt"]
    assert draft_json == '{"subject": "Sharp Subject", "body_html": "<p>Body</p>"}'
    assert budget_logs == [
        {"input_tokens": 12, "output_tokens": 8, "category": "Proposal Gen"}
    ]


def test_insufficient_data_article_allows_empty_fields():
    from services.ai_schemas import ArticleAnalysis

    result = ArticleAnalysis(
        status="INSUFFICIENT_DATA",
        batch_id=0,
        headline=None,
        seo_slug=None,
        category=None,
        gist="",
        key_details=[],
        why_it_matters=None,
        optimistic_outlook=None,
        pessimistic_outlook=None,
        thought_provoking_question=None,
        eli5=None,
        importance_score=None,
        deep_analysis=None,
        narration_script=None,
    )

    assert result.status == "INSUFFICIENT_DATA"
    assert result.importance_score == 0


def test_success_article_still_requires_content():
    from services.ai_schemas import ArticleAnalysis

    with pytest.raises(ValueError, match="SUCCESS article missing required fields"):
        ArticleAnalysis(
            status="SUCCESS",
            batch_id=0,
            headline="",
            seo_slug="",
            category="Tools",
            gist="",
        )


def test_process_batch_does_not_mark_sent_to_api_before_validation(monkeypatch):
    recorded_statuses = []

    calls = []

    class FakeGateway:
        def __init__(self, *args, **kwargs):
            calls.append(kwargs.get("model_name") or args[0])

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

    calls = []

    class FakeGateway:
        def __init__(self, *args, **kwargs):
            calls.append(kwargs.get("model_name") or args[0])

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
    monkeypatch.setattr(remove_duplicates.ai_config, "ROUTINE_MODEL", "gemini-routine-test")

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
    assert calls == ["gemini-routine-test"]


def test_recent_ai_dedup_skips_repeated_headline_signature(monkeypatch):
    conn = sqlite3.connect(db.DB_PATH)
    cur = conn.cursor()
    for slug, title in (
        ("dedup-repeat-1", "OpenAI launches repeated cost guard"),
        ("dedup-repeat-2", "OpenAI repeated cost guard ships"),
    ):
        cur.execute(
            """
            INSERT INTO articles (slug, title, image, category, gist, why_it_matters, bull_case, bear_case, key_details, eli5, deep_analysis, source, source_url, full_json, published_at, importance_score, is_published, design_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, ?)
            """,
            (
                slug,
                title,
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
                f"https://example.com/{slug}",
                "{}",
                80,
                1,
                "{}",
            ),
        )
    conn.commit()
    conn.close()

    calls = []

    class FakeGateway:
        def __init__(self, *args, **kwargs):
            calls.append("init")

        def generate_structured(self, *args, **kwargs):
            return DuplicateReviewPayload(duplicate_pairs=[]), _FakeResponse("{}")

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(remove_duplicates, "AIGateway", FakeGateway)

    remove_duplicates.ai_deduplicate(recent_only=True)
    remove_duplicates.ai_deduplicate(recent_only=True)

    assert calls == ["init"]
