import json
import sqlite3
import sys
from datetime import datetime, timedelta
from types import ModuleType
from types import SimpleNamespace

import pytest

import ai_config
import db
from fetcher import ai_processor
import remove_duplicates
import services.lead_extractor as lead_extractor_module
from services.ai_gateway import AIGateway
from services.ai_schemas import (
    ArticleTriageDecision,
    DuplicatePair,
    DuplicateReviewPayload,
    LeadExtractionResult,
    ProposalDraft,
)


@pytest.fixture(autouse=True)
def _cleanup_gateway_test_rows(_patch_db):
    def cleanup():
        conn = sqlite3.connect(db.DB_PATH)
        conn.execute(
            "DELETE FROM articles WHERE slug IN (?, ?)",
            ("gateway-weekly-test", "opinion-gateway-test"),
        )
        for statement, params in (
            ("DELETE FROM newsletters WHERE subject = ?", ("AI Weekly Wrap: Gateways",)),
            ("DELETE FROM blog_posts WHERE slug = ?", ("the-walls-are-thinning",)),
        ):
            try:
                conn.execute(statement, params)
            except sqlite3.OperationalError:
                pass
        conn.commit()
        conn.close()

    cleanup()
    yield
    cleanup()


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.usage_metadata = SimpleNamespace(
            prompt_token_count=10,
            candidates_token_count=5,
            thoughts_token_count=20,
            cached_content_token_count=4,
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


def test_ai_gateway_logs_detailed_usage_columns(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _patch_fake_genai_client(
        monkeypatch,
        '{"company_name":"Acme AI","email":"team@acme.ai","confidence":88,"product_value":"HIGH_VALUE","reason":"Clear enterprise fit"}',
    )

    gateway = AIGateway("gemini-test")
    gateway.generate_structured(
        "extract this lead",
        LeadExtractionResult,
        prompt_type="test_detailed_token_logging",
    )

    conn = sqlite3.connect(db.DB_PATH)
    row = conn.execute(
        """
        SELECT
            prompt_tokens,
            output_tokens,
            thoughts_tokens,
            total_tokens,
            cached_input_tokens,
            prompt_char_count,
            response_char_count,
            request_status
        FROM ai_logs
        WHERE prompt_type = 'test_detailed_token_logging'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    conn.close()

    assert row == (10, 5, 20, 35, 4, len("extract this lead"), 126, "SUCCESS")


def test_ai_gateway_writes_fallback_when_db_logging_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    fallback_path = tmp_path / "ai_logs_fallback.jsonl"
    monkeypatch.setenv("AI_LOG_FALLBACK_PATH", str(fallback_path))
    _patch_fake_genai_client(
        monkeypatch,
        '{"company_name":"Acme AI","email":"team@acme.ai","confidence":88,"product_value":"HIGH_VALUE","reason":"Clear enterprise fit"}',
    )

    from services import ai_gateway as gateway_module

    def fail_connection(*, timeout):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(gateway_module.db, "get_db_connection", fail_connection)

    gateway = AIGateway("gemini-test")
    gateway.generate_structured(
        "extract this lead",
        LeadExtractionResult,
        prompt_type="test_fallback_token_logging",
    )

    record = json.loads(fallback_path.read_text(encoding="utf-8").strip())
    assert record["model"] == "gemini-test"
    assert record["prompt_type"] == "test_fallback_token_logging"
    assert record["request_status"] == "SUCCESS"
    assert record["prompt_tokens"] == 10
    assert record["output_tokens"] == 5
    assert record["thoughts_tokens"] == 20
    assert record["cached_input_tokens"] == 4
    assert record["total_tokens"] == 35
    assert record["prompt_char_count"] == len("extract this lead")
    assert record["response_char_count"] == 126
    assert record["db_error"] == "database is locked"


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


def _ensure_newsletters_table():
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS newsletters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT,
            intro_text TEXT,
            article_ids TEXT,
            article_metadata TEXT,
            status TEXT,
            scheduled_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


def _ensure_blog_posts_table():
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS blog_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE,
            title TEXT,
            subtitle TEXT,
            gist TEXT,
            impact TEXT,
            optimistic_outlook TEXT,
            pessimistic_warning TEXT,
            content TEXT,
            image TEXT,
            author_name TEXT,
            author_title TEXT,
            author_image TEXT,
            author_linkedin TEXT,
            meta_description TEXT,
            is_published BOOLEAN DEFAULT 0,
            published_at TIMESTAMP DEFAULT NULL
        )
        """
    )
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


def test_weekly_curator_uses_gateway_and_absolute_db_path(monkeypatch):
    import weekly_curator
    from services.ai_schemas import WeeklyNewsletterDraft
    recent_published_at = (datetime.now() - timedelta(days=1)).isoformat()

    _ensure_newsletters_table()
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute("DELETE FROM newsletters")
    article_id = conn.execute(
        """
        INSERT INTO articles (
            title, slug, gist, why_it_matters, importance_score, is_published, published_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "Gateway Weekly Test",
            "gateway-weekly-test",
            "Important weekly summary",
            "Enterprise AI buyers must reassess vendor risk this quarter.",
            91,
            1,
            recent_published_at,
        ),
    ).lastrowid
    conn.commit()
    conn.close()

    calls = {}
    budget_logs = []

    class FakeGateway:
        def __init__(self, model_name, *, system_instruction=None, generation_config=None, thinking_budget=None, logger_name=None):
            calls["init"] = {
                "model_name": model_name,
                "generation_config": generation_config,
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
                WeeklyNewsletterDraft(
                    subject="AI Weekly Wrap: Gateways",
                    intro_text=(
                        "This week, enterprise AI teams focused on operational "
                        "discipline as gateway design became central to reliability, "
                        "cost control, and vendor accountability. The strongest lesson "
                        "was that model quality alone cannot guarantee safe delivery "
                        "when routing, observability, and fallback behavior remain "
                        "inconsistent.\n\n"
                        "For engineering leaders, the practical response is to measure "
                        "requests end to end, compare providers against the same "
                        "workloads, document failure modes, and keep human review around "
                        "consequential decisions. These controls make weekly AI progress "
                        "easier to evaluate without overstating what any single system "
                        "can deliver."
                    ),
                    article_blurbs={
                        str(article_id): (
                            "Enterprise AI buyers can use centralized gateway logs and "
                            "consistent routing controls to compare vendors, contain "
                            "failures, and understand real operating costs before "
                            "scaling deployments."
                        )
                    },
                ),
                SimpleNamespace(
                    usage_metadata=SimpleNamespace(
                        prompt_token_count=21,
                        candidates_token_count=9,
                    )
                ),
            )

    class FakeBudget:
        def log_request(self, input_tokens, output_tokens, category=""):
            budget_logs.append(
                {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "category": category,
                }
            )

    monkeypatch.setattr(weekly_curator, "AIGateway", FakeGateway)
    monkeypatch.setattr(weekly_curator, "DB_PATH", db.DB_PATH)
    monkeypatch.setattr("budget_tracker.BudgetTracker", lambda: FakeBudget())

    weekly_curator.generate_newsletter_draft()

    assert calls["generate"]["schema"] is WeeklyNewsletterDraft
    assert calls["generate"]["prompt_type"] == "weekly_digest"
    assert "Gateway Weekly Test" in calls["generate"]["prompt"]
    assert "Enterprise AI buyers must reassess vendor risk this quarter." in calls["generate"]["prompt"]
    assert "who is affected" in calls["generate"]["prompt"].lower()
    assert "what concretely changes" in calls["generate"]["prompt"].lower()
    assert "signifies" in calls["generate"]["prompt"].lower()
    assert "underscores" in calls["generate"]["prompt"].lower()
    assert calls["init"]["logger_name"] == "weekly_curator"
    assert calls["init"]["generation_config"] == {"response_mime_type": "application/json"}
    assert budget_logs == [
        {"input_tokens": 21, "output_tokens": 9, "category": "Weekly Digest"}
    ]
    conn = sqlite3.connect(db.DB_PATH)
    seeded_article = conn.execute(
        "SELECT id FROM articles WHERE slug = ?",
        ("test-article-slug",),
    ).fetchone()
    conn.close()
    assert seeded_article is not None


def test_opinion_generator_uses_gateway_and_absolute_db_path(monkeypatch):
    import opinion_generator
    from services.ai_schemas import OpinionPieceDraft
    recent_published_at = (datetime.now() - timedelta(days=1)).isoformat()

    _ensure_blog_posts_table()
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute("DELETE FROM blog_posts")
    conn.execute(
        """
        INSERT INTO articles (
            title, slug, gist, why_it_matters, importance_score, source, category,
            is_published, published_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "Opinion Gateway Test",
            "opinion-gateway-test",
            "Important industry turn.",
            "Builders need to adapt.",
            88,
            "Example Source",
            "Business",
            1,
            recent_published_at,
        ),
    )
    conn.commit()
    conn.close()

    calls = {}
    budget_logs = []

    class FakeGateway:
        def __init__(self, model_name, *, system_instruction=None, generation_config=None, thinking_budget=None, logger_name=None):
            calls["init"] = {
                "model_name": model_name,
                "generation_config": generation_config,
                "logger_name": logger_name,
                "thinking_budget": thinking_budget,
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
                OpinionPieceDraft(
                    title="The Walls Are Thinning",
                    subtitle="A week that changed the builder map.",
                    gist="Plain summary.",
                    impact="Plain impact.",
                    optimistic_outlook="Optimistic.",
                    pessimistic_warning="Pessimistic.",
                    content="<h2>Section</h2><p>Body</p>",
                    meta_description="Meta description",
                ),
                SimpleNamespace(
                    usage_metadata=SimpleNamespace(
                        prompt_token_count=34,
                        candidates_token_count=13,
                    )
                ),
            )

    class FakeBudget:
        def log_request(self, input_tokens, output_tokens, category=""):
            budget_logs.append(
                {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "category": category,
                }
            )

    monkeypatch.setattr(opinion_generator, "AIGateway", FakeGateway)
    monkeypatch.setattr(opinion_generator, "DB_PATH", db.DB_PATH)
    monkeypatch.setattr("budget_tracker.BudgetTracker", lambda: FakeBudget())

    opinion_generator.generate_opinion_piece()

    assert calls["generate"]["schema"] is OpinionPieceDraft
    assert calls["generate"]["prompt_type"] == "opinion_piece"
    assert calls["generate"]["generation_config"] == {"temperature": 0.7}
    assert "Opinion Gateway Test" in calls["generate"]["prompt"]
    assert calls["init"]["logger_name"] == "opinion_generator"
    assert budget_logs == [
        {"input_tokens": 34, "output_tokens": 13, "category": "Opinion Piece"}
    ]
    conn = sqlite3.connect(db.DB_PATH)
    seeded_article = conn.execute(
        "SELECT id FROM articles WHERE slug = ?",
        ("test-article-slug",),
    ).fetchone()
    conn.close()
    assert seeded_article is not None


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


def test_process_batch_truncates_article_source_context(monkeypatch):
    prompts = []

    class FakeGateway:
        def __init__(self, *args, **kwargs):
            return None

        def generate_structured(self, prompt, *args, **kwargs):
            prompts.append(prompt)
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
    monkeypatch.setattr(ai_processor, "extract_content", lambda url: ("A" * 1000, "", ""))
    monkeypatch.setattr(ai_processor, "is_spam_source", lambda link, title: False)
    monkeypatch.setattr(ai_processor.budget, "can_make_request", lambda estimated_tokens: True)
    monkeypatch.setattr(ai_processor.budget, "log_request", lambda *args, **kwargs: None)
    monkeypatch.setattr(lead_extractor_module, "LeadExtractor", FakeLeadExtractor)
    monkeypatch.setattr(ai_processor.ai_config, "ARTICLE_SOURCE_CHAR_LIMIT", 180)
    monkeypatch.setattr(ai_processor.ai_config, "ARTICLE_RESEARCH_ENABLED", False)

    ai_processor.process_batch([
        {"title": "Test Source Story", "link": "https://example.com/story", "rss_summary": "summary"}
    ])

    assert prompts
    assert "A" * 180 in prompts[0]
    assert "A" * 181 not in prompts[0]


def test_process_batch_skips_deep_research_by_default(monkeypatch):
    prompts = []
    calls = {"research": 0}

    class FakeGateway:
        def __init__(self, *args, **kwargs):
            return None

        def generate_structured(self, prompt, *args, **kwargs):
            prompts.append(prompt)
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

    fake_module = ModuleType("tavily_research")
    def fake_deep_research(*args, **kwargs):
        calls["research"] += 1
        return {"context": "expensive extra context", "source_count": 1}
    fake_module.deep_research = fake_deep_research

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(ai_processor, "AIGateway", FakeGateway)
    monkeypatch.setattr(ai_processor, "extract_content", lambda url: ("B" * 1000, "", ""))
    monkeypatch.setattr(ai_processor, "is_spam_source", lambda link, title: False)
    monkeypatch.setattr(ai_processor.budget, "can_make_request", lambda estimated_tokens: True)
    monkeypatch.setattr(ai_processor.budget, "log_request", lambda *args, **kwargs: None)
    monkeypatch.setattr(lead_extractor_module, "LeadExtractor", FakeLeadExtractor)
    monkeypatch.setattr(ai_processor.ai_config, "ARTICLE_RESEARCH_ENABLED", False)
    monkeypatch.setitem(sys.modules, "tavily_research", fake_module)

    ai_processor.process_batch([
        {"title": "Breakthrough story", "link": "https://example.com/story", "rss_summary": "summary"}
    ])

    assert prompts
    assert calls["research"] == 0
    assert "SUPPLEMENTARY RESEARCH" not in prompts[0]


def test_article_analysis_prompt_keeps_required_fields_but_omits_dead_ones():
    prompt = ai_processor.build_article_analysis_prompt([
        "ARTICLE ID: 0\nSOURCE TITLE: Test\nSOURCE CONTENT: sample"
    ])

    assert '"headline"' in prompt
    assert '"seo_slug"' in prompt
    assert '"category"' in prompt
    assert '"why_it_matters"' in prompt
    assert '"hashtags"' in prompt
    assert '"eli5"' in prompt
    assert '"design_tokens"' in prompt
    assert '"mermaid_diagram"' in prompt
    assert '"image_query"' not in prompt
    assert '"metadata"' not in prompt


def test_article_triage_prompt_stays_compact_and_english_only():
    prompt = ai_processor.build_article_triage_prompt([
        "ARTICLE ID: 0\nSOURCE TITLE: Test\nSOURCE CONTENT: sample"
    ])

    assert "KEEP or BLOCK" in prompt
    assert "Return valid JSON only." in prompt
    assert "Return exactly one object for every ARTICLE ID" in prompt
    assert "usually KEEP 0-1 per 3-article batch" in prompt
    assert "Default to BLOCK when uncertain" in prompt
    assert "generic AI adoption commentary" in prompt
    assert "SOURCE CONTENT" in prompt
    assert len(prompt) < 2500


def test_process_batch_triage_blocks_low_signal_articles_before_full_analysis(monkeypatch):
    structured_prompts = []
    calls = []
    processing_attempts = []

    class FakeGateway:
        def __init__(self, *args, **kwargs):
            calls.append(kwargs.get("model_name") or args[0])

        def generate_structured(self, prompt, schema, *, prompt_type, **kwargs):
            structured_prompts.append((prompt_type, prompt))
            if prompt_type == "article_triage":
                return ([
                    ArticleTriageDecision(batch_id=0, decision="KEEP", reason="Major infrastructure move"),
                    ArticleTriageDecision(batch_id=1, decision="BLOCK", reason="Thin product launch"),
                ], _FakeResponse("{}"))

            assert prompt_type == "article_analysis"
            assert "Strong infrastructure story" in prompt
            assert "Thin product launch" not in prompt
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

    budget_logs = []
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(ai_processor, "AIGateway", FakeGateway)
    monkeypatch.setattr(
        ai_processor,
        "extract_content",
        lambda url: ("x" * 1000, "", ""),
    )
    monkeypatch.setattr(ai_processor, "is_spam_source", lambda link, title: False)
    monkeypatch.setattr(
        ai_processor,
        "log_processing_attempt",
        lambda url, status="PROCESSING": processing_attempts.append((url, status)),
    )
    monkeypatch.setattr(ai_processor.budget, "can_make_request", lambda estimated_tokens: True)
    monkeypatch.setattr(
        ai_processor.budget,
        "log_request",
        lambda input_tokens, output_tokens, category="": budget_logs.append((category, input_tokens, output_tokens)),
    )
    monkeypatch.setattr(lead_extractor_module, "LeadExtractor", FakeLeadExtractor)
    monkeypatch.setattr(ai_processor.ai_config, "ARTICLE_TRIAGE_ENABLED", True)
    monkeypatch.setattr(ai_processor.ai_config, "ARTICLE_TRIAGE_CHAR_LIMIT", 400)

    result = ai_processor.process_batch([
        {"title": "Strong infrastructure story", "link": "https://example.com/1", "rss_summary": "summary"},
        {"title": "Thin product launch", "link": "https://example.com/2", "rss_summary": "summary"},
    ])

    assert len(result) == 1
    assert [prompt_type for prompt_type, _ in structured_prompts] == ["article_triage", "article_analysis"]
    assert calls[0] == ai_processor.ai_config.ROUTINE_MODEL
    assert calls[1] == ai_processor.ai_config.DEFAULT_MODEL
    assert any(category == "Article Triage" for category, *_ in budget_logs)
    assert any(category == "Article Analysis" for category, *_ in budget_logs)
    assert processing_attempts == [("https://example.com/2", "TRIAGE_BLOCKED")]


def test_triage_retries_omitted_decisions_before_filtering(monkeypatch):
    triage_prompts = []
    processing_attempts = []

    class FakeGateway:
        def __init__(self, *args, **kwargs):
            return None

        def generate_structured(self, prompt, schema, *, prompt_type, **kwargs):
            assert prompt_type == "article_triage"
            triage_prompts.append(prompt)
            if len(triage_prompts) == 1:
                return (
                    [
                        ArticleTriageDecision(
                            batch_id=0,
                            decision="BLOCK",
                            reason="Low signal",
                        )
                    ],
                    _FakeResponse("{}"),
                )
            return (
                [
                    ArticleTriageDecision(batch_id=0, decision="BLOCK", reason="Low signal"),
                    ArticleTriageDecision(batch_id=1, decision="BLOCK", reason="Routine update"),
                    ArticleTriageDecision(batch_id=2, decision="KEEP", reason="Major policy move"),
                ],
                _FakeResponse("{}"),
            )

    records = [
        {
            "batch_id": batch_id,
            "triage_input": f"ARTICLE ID: {batch_id}\nSOURCE CONTENT: candidate {batch_id}",
            "item": {"link": f"https://example.com/{batch_id}"},
        }
        for batch_id in range(3)
    ]

    monkeypatch.setattr(ai_processor, "AIGateway", FakeGateway)
    monkeypatch.setattr(ai_processor.ai_config, "ARTICLE_TRIAGE_ENABLED", True)
    monkeypatch.setattr(ai_processor.budget, "can_make_request", lambda estimated_tokens: True)
    monkeypatch.setattr(ai_processor.budget, "log_request", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        ai_processor,
        "log_processing_attempt",
        lambda url, status="PROCESSING": processing_attempts.append((url, status)),
    )

    result = ai_processor._triage_batch(records)

    assert len(triage_prompts) == 2
    assert "CRITICAL CORRECTION" in triage_prompts[1]
    assert [record["batch_id"] for record in result] == [2]
    assert processing_attempts == [
        ("https://example.com/0", "TRIAGE_BLOCKED"),
        ("https://example.com/1", "TRIAGE_BLOCKED"),
    ]


def test_triage_falls_back_after_two_invalid_decision_sets(monkeypatch):
    triage_prompts = []
    processing_attempts = []

    class FakeGateway:
        def __init__(self, *args, **kwargs):
            return None

        def generate_structured(self, prompt, schema, *, prompt_type, **kwargs):
            assert prompt_type == "article_triage"
            triage_prompts.append(prompt)
            return (
                [
                    ArticleTriageDecision(
                        batch_id=0,
                        decision="BLOCK",
                        reason="Low signal",
                    )
                ],
                _FakeResponse("{}"),
            )

    records = [
        {
            "batch_id": batch_id,
            "triage_input": f"ARTICLE ID: {batch_id}\nSOURCE CONTENT: candidate {batch_id}",
            "item": {"link": f"https://example.com/{batch_id}"},
        }
        for batch_id in range(3)
    ]

    monkeypatch.setattr(ai_processor, "AIGateway", FakeGateway)
    monkeypatch.setattr(ai_processor.ai_config, "ARTICLE_TRIAGE_ENABLED", True)
    monkeypatch.setattr(ai_processor.budget, "can_make_request", lambda estimated_tokens: True)
    monkeypatch.setattr(ai_processor.budget, "log_request", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        ai_processor,
        "log_processing_attempt",
        lambda url, status="PROCESSING": processing_attempts.append((url, status)),
    )

    result = ai_processor._triage_batch(records)

    assert len(triage_prompts) == 2
    assert result == records
    assert processing_attempts == []


def test_process_batch_retries_duplicate_analysis_ids_and_restores_source_batch_ids(monkeypatch):
    analysis_calls = []

    def analysis(batch_id, headline):
        return ai_processor.ArticleAnalysis(
            status="SUCCESS",
            batch_id=batch_id,
            headline=headline,
            seo_slug=headline.lower().replace(" ", "-"),
            image_query="",
            category="Security",
            gist=f"{headline} gist.",
            key_details=["Fact 1", "Fact 2"],
            why_it_matters="Because it matters.",
            optimistic_outlook="Upside view.",
            pessimistic_outlook="Risk view.",
            hashtags=["#AI"],
            thought_provoking_question="What changes next?",
            eli5="Simple explanation.",
            importance_score=80,
            deep_analysis="Three paragraph style analysis.",
            narration_script="Intelligence from DailyAIWire dot news...",
        )

    class FakeGateway:
        def __init__(self, *args, **kwargs):
            return None

        def generate_structured(self, prompt, schema, *, prompt_type, **kwargs):
            if prompt_type == "article_triage":
                return (
                    [
                        ArticleTriageDecision(batch_id=0, decision="BLOCK", reason="Low signal"),
                        ArticleTriageDecision(batch_id=1, decision="KEEP", reason="Major security issue"),
                        ArticleTriageDecision(batch_id=2, decision="KEEP", reason="Major policy issue"),
                    ],
                    _FakeResponse("{}"),
                )

            analysis_calls.append(prompt)
            if len(analysis_calls) == 1:
                return (
                    [
                        analysis(0, "Security Story"),
                        analysis(0, "Policy Story"),
                    ],
                    _FakeResponse("{}"),
                )
            return (
                [
                    analysis(0, "Security Story"),
                    analysis(1, "Policy Story"),
                ],
                _FakeResponse("{}"),
            )

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(ai_processor, "AIGateway", FakeGateway)
    monkeypatch.setattr(
        ai_processor,
        "extract_content",
        lambda url: (f"Source material for {url}. " * 30, "", ""),
    )
    monkeypatch.setattr(ai_processor, "is_spam_source", lambda link, title: False)
    monkeypatch.setattr(ai_processor.budget, "can_make_request", lambda estimated_tokens: True)
    monkeypatch.setattr(ai_processor.budget, "log_request", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        lead_extractor_module,
        "LeadExtractor",
        lambda: SimpleNamespace(extract_and_log=lambda *args, **kwargs: None),
    )
    monkeypatch.setattr(ai_processor.ai_config, "ARTICLE_TRIAGE_ENABLED", True)

    result = ai_processor.process_batch(
        [
            {"title": "Low Signal", "link": "https://example.com/0"},
            {"title": "Security Source", "link": "https://example.com/1"},
            {"title": "Policy Source", "link": "https://example.com/2"},
        ]
    )

    assert len(analysis_calls) == 2
    assert "ARTICLE ID: 0" in analysis_calls[0]
    assert "ARTICLE ID: 1" in analysis_calls[0]
    assert "ARTICLE ID: 2" not in analysis_calls[0]
    assert [article["batch_id"] for article in result] == [1, 2]
    assert result[0]["source_content_hash"] != result[1]["source_content_hash"]


def test_process_batch_records_insufficient_analysis_without_marking_success(monkeypatch):
    processing_attempts = []

    class FakeGateway:
        def __init__(self, *args, **kwargs):
            return None

        def generate_structured(self, prompt, schema, *, prompt_type, **kwargs):
            assert prompt_type == "article_analysis"
            return ([
                ai_processor.ArticleAnalysis(
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
    monkeypatch.setattr(
        ai_processor,
        "log_processing_attempt",
        lambda url, status="PROCESSING": processing_attempts.append((url, status)),
    )
    monkeypatch.setattr(lead_extractor_module, "LeadExtractor", FakeLeadExtractor)
    monkeypatch.setattr(ai_processor.ai_config, "ARTICLE_TRIAGE_ENABLED", False)

    result = ai_processor.process_batch([
        {"title": "Thin source story", "link": "https://example.com/thin", "rss_summary": "summary"}
    ])

    assert result[0]["status"] == "INSUFFICIENT_DATA"
    assert processing_attempts == [("https://example.com/thin", "INSUFFICIENT_DATA")]


def test_process_batch_triage_failure_falls_back_to_full_analysis(monkeypatch):
    structured_prompts = []

    class FakeGateway:
        def __init__(self, *args, **kwargs):
            self.model_name = kwargs.get("model_name") or args[0]

        def generate_structured(self, prompt, schema, *, prompt_type, **kwargs):
            structured_prompts.append(prompt_type)
            if prompt_type == "article_triage":
                raise RuntimeError("triage unavailable")
            return ([
                ai_processor.ArticleAnalysis(
                    status="SUCCESS",
                    batch_id=0,
                    headline="Validated Headline One",
                    seo_slug="validated-headline-one",
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
                ),
                ai_processor.ArticleAnalysis(
                    status="SUCCESS",
                    batch_id=1,
                    headline="Validated Headline Two",
                    seo_slug="validated-headline-two",
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
                ),
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
    monkeypatch.setattr(lead_extractor_module, "LeadExtractor", FakeLeadExtractor)
    monkeypatch.setattr(ai_processor.ai_config, "ARTICLE_TRIAGE_ENABLED", True)

    result = ai_processor.process_batch([
        {"title": "Fallback story one", "link": "https://example.com/story-1", "rss_summary": "summary"},
        {"title": "Fallback story two", "link": "https://example.com/story-2", "rss_summary": "summary"},
    ])

    assert len(result) == 2
    assert structured_prompts == ["article_triage", "article_analysis"]


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
