from collections import Counter
from datetime import datetime, timezone
import sqlite3
from types import SimpleNamespace

import weekly_curator
from services.ai_schemas import WeeklyNewsletterDraft


NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


def _article(
    article_id,
    category,
    score,
    *,
    source_url=None,
    published_at="2026-07-26T08:00:00+00:00",
):
    return {
        "id": article_id,
        "title": f"Article {article_id}",
        "gist": f"Gist for article {article_id}",
        "why_it_matters": f"Existing context for article {article_id}",
        "importance_score": score,
        "category": category,
        "source": f"Source {article_id}",
        "source_url": source_url or f"https://example.com/story-{article_id}",
        "published_at": published_at,
    }


def test_extract_source_date_from_common_url_paths():
    assert weekly_curator.extract_source_date(
        "https://example.com/2026/07/24/current-story"
    ) == datetime(2026, 7, 24).date()
    assert weekly_curator.extract_source_date(
        "https://example.com/news/2026-07-23/current-story"
    ) == datetime(2026, 7, 23).date()
    assert weekly_curator.extract_source_date(
        "https://example.com/story-without-date"
    ) is None


def test_select_diverse_articles_excludes_stale_sources_and_caps_categories():
    candidates = [
        _article(
            1,
            "Robotics",
            100,
            source_url="https://example.com/2026/01/06/stale-story",
        ),
        _article(2, "Security", 99),
        _article(3, "Security", 98),
        _article(4, "Security", 97),
        _article(5, "Business", 96),
        _article(6, "Business", 95),
        _article(7, "Tools", 94),
        _article(8, "Policy", 93),
        _article(9, "LLMs", 92),
    ]

    selected = weekly_curator.select_diverse_articles(
        candidates,
        limit=7,
        now=NOW,
    )

    selected_ids = {article["id"] for article in selected}
    category_counts = Counter(article["category"] for article in selected)

    assert len(selected) == 7
    assert 1 not in selected_ids
    assert max(category_counts.values()) <= 2
    assert len(category_counts) >= 4


def test_select_diverse_articles_accepts_sqlite_rows():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT
                10 AS id,
                'SQLite candidate' AS title,
                'Tools' AS category,
                90 AS importance_score,
                'https://example.com/2026/07/25/story' AS source_url,
                '2026-07-26T08:00:00+00:00' AS published_at
            """
        ).fetchone()
    finally:
        conn.close()

    selected = weekly_curator.select_diverse_articles([row], limit=1, now=NOW)

    assert selected == [dict(row)]


def test_prompt_contains_editorial_and_grounding_contract():
    articles = [
        _article(
            20,
            "Business",
            95,
            source_url="https://example.com/2026/07/24/compute-projection",
        )
    ]

    prompt = weekly_curator.build_newsletter_prompt(
        articles,
        week_ending="July 26, 2026",
        now=NOW,
    )

    assert "60 characters" in prompt
    assert "80-120 words" in prompt
    assert "20-40 words" in prompt
    assert "projections" in prompt
    assert "commitments" in prompt
    assert "sensational" in prompt
    assert "CATEGORY: Business" in prompt
    assert "SOURCE URL: https://example.com/2026/07/24/compute-projection" in prompt
    assert "SOURCE DATE: 2026-07-24" in prompt


def test_validation_rejects_unsupported_or_overlong_copy():
    articles = [_article(30, "Security", 95)]
    draft = SimpleNamespace(
        subject=(
            "AI Weekly Wrap: AI Escapes Control and Unleashes "
            "Catastrophic Real-World Threats"
        ),
        intro_text="word " * 130,
        article_blurbs={
            "30": (
                "This loss of control proves catastrophic consequences are inevitable "
                "for every organization deploying artificial intelligence systems today."
            )
        },
    )

    errors = weekly_curator.validate_newsletter_draft(draft, articles)

    assert any("60 characters" in error for error in errors)
    assert any("80-120 words" in error for error in errors)
    assert any("sensational" in error for error in errors)
    assert any("20-40 words" in error for error in errors)


def test_validation_rejects_hyphenated_loss_of_control_language():
    articles = [_article(31, "Security", 95)]
    draft = SimpleNamespace(
        subject="AI Weekly Wrap: Security Tests and Model Risk",
        intro_text=" ".join(["measured"] * 90),
        article_blurbs={
            "31": (
                "The reported incident validates loss-of-control concerns for every "
                "organization, requiring immediate containment changes before advanced "
                "systems can be evaluated or deployed safely."
            )
        },
    )

    errors = weekly_curator.validate_newsletter_draft(draft, articles)

    assert any("sensational" in error for error in errors)


def test_validation_rejects_future_spending_as_a_commitment():
    articles = [_article(32, "Business", 95)]
    draft = SimpleNamespace(
        subject="AI Weekly Wrap: Compute Spending and Model Costs",
        intro_text=(
            "OpenAI committed $750 billion through 2030 as infrastructure demand "
            + "expands across the industry. "
            + " ".join(["measured"] * 78)
        ),
        article_blurbs={
            "32": (
                "The $750 billion infrastructure commitment through 2030 will reshape "
                "energy markets, financing conditions, and regional development for "
                "companies competing in frontier artificial intelligence."
            )
        },
    )

    errors = weekly_curator.validate_newsletter_draft(draft, articles)

    assert any("future financial projections" in error for error in errors)


def test_validation_requires_projection_language_for_future_financial_numbers():
    articles = [_article(33, "Business", 95)]
    draft = SimpleNamespace(
        subject="AI Weekly Wrap: Compute Spending and Model Costs",
        intro_text=(
            "OpenAI's reported $750 billion infrastructure investment by 2030 "
            + "could affect energy demand and financing. "
            + " ".join(["measured"] * 78)
        ),
        article_blurbs={
            "33": (
                "The reported $750 billion infrastructure investment through 2030 "
                "could affect energy markets, financing conditions, regional development, "
                "and companies competing in frontier artificial intelligence."
            )
        },
    )

    errors = weekly_curator.validate_newsletter_draft(draft, articles)

    assert any("projection language" in error for error in errors)


def test_validation_rejects_common_hype_terms():
    articles = [_article(34, "Science", 92)]
    draft = SimpleNamespace(
        subject="AI Weekly Wrap: Research and Product Changes",
        intro_text=" ".join(["measured"] * 90),
        article_blurbs={
            "34": (
                "The unprecedented system will profoundly change research workflows, "
                "revolutionizing how every organization develops and evaluates artificial "
                "intelligence products across global markets."
            )
        },
    )

    errors = weekly_curator.validate_newsletter_draft(draft, articles)

    assert any("sensational" in error for error in errors)


def test_validation_requires_attribution_for_risky_headlines():
    article = _article(35, "Security", 95)
    article["title"] = (
        "Models Breach Containment in Reported Loss-of-Control Incident"
    )
    draft = SimpleNamespace(
        subject="AI Weekly Wrap: Security Tests and Model Risk",
        intro_text=" ".join(["measured"] * 90),
        article_blurbs={
            "35": (
                "The models escaped containment and attacked external infrastructure, "
                "confirming autonomous behavior concerns for organizations evaluating "
                "advanced systems in connected environments."
            )
        },
    )

    errors = weekly_curator.validate_newsletter_draft(draft, [article])

    assert any("attribution" in error for error in errors)


def test_dry_run_returns_copy_without_creating_a_newsletter(monkeypatch):
    articles = [_article(40, "Tools", 90)]
    blurb = (
        "Teams gain a practical benchmark for comparing agent reliability before "
        "safely granting production permissions across sensitive cloud workflows and systems."
    )
    draft = WeeklyNewsletterDraft(
        subject="AI Weekly Wrap: Models, Costs, and Guardrails",
        intro_text=" ".join(["signal"] * 90),
        article_blurbs={"40": blurb},
    )

    class FakeGateway:
        def generate_structured(self, prompt, schema, prompt_type):
            return draft, SimpleNamespace()

    class FakeBudget:
        def log_request(self, *args, **kwargs):
            raise AssertionError("No usage metadata should mean no budget write")

    monkeypatch.setattr(weekly_curator, "get_top_articles", lambda **kwargs: articles)

    result = weekly_curator.generate_newsletter_draft(
        dry_run=True,
        now=NOW,
        gateway=FakeGateway(),
        budget=FakeBudget(),
    )

    assert result["dry_run"] is True
    assert result["subject"] == draft.subject
    assert result["article_ids"] == [40]
    assert result["article_blurbs"] == {"40": blurb}
