import sqlite3
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _cleanup_persistence_test_articles():
    yield

    import db as db_module

    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        """
        DELETE FROM articles
        WHERE slug LIKE 'agent-benchmarks-%'
           OR slug LIKE 'hugging-face-%-test'
           OR slug LIKE 'deepsearch-world-%-test'
           OR slug LIKE 'source-url-collision-%-test'
        """
    )
    conn.commit()
    conn.close()


def _processed_article(slug):
    return {
        "status": "SUCCESS",
        "batch_id": 0,
        "headline": "Research Agent Benchmarks Need Stronger Visual Context",
        "seo_slug": slug,
        "category": "AI Agents",
        "gist": "A research story about AI agents and benchmark quality.",
        "why_it_matters": "This matters because better benchmark context helps readers judge real progress.",
        "optimistic_outlook": "The upside is clearer evaluation of agent systems.",
        "pessimistic_outlook": "The risk is overfitting to narrow benchmark behavior.",
        "key_details": ["Benchmark gap", "Agent evaluation", "Research quality"],
        "eli5": "It is like testing robots with harder homework.",
        "deep_analysis": "Substantive analysis with context and implications.",
        "importance_score": 75,
        "hashtags": ["#AI"],
        "thought_provoking_question": "How should agent benchmarks improve?",
        "narration_script": "DailyAIWire analysis.",
    }


def _original_article(slug):
    return {
        "title": "Research Agent Benchmarks Need Stronger Visual Context",
        "source": "ArXiv cs.AI",
        "link": f"https://arxiv.org/abs/{slug}",
        "published": "2026-04-30T10:00:00+00:00",
        "scraped_image": "",
    }


def test_save_to_db_separates_onsite_image_from_social_card(monkeypatch):
    import db as db_module
    import fetcher.persistence as persistence
    import ig_card_generator

    slug = "agent-benchmarks-visual-context"
    generated_path = "/Users/test/project/static/img/social/agent-benchmarks-visual-context.png"

    fake_embedding = SimpleNamespace(
        score_ad_likelihood=lambda *args, **kwargs: 0.0,
        find_duplicates=lambda *args, **kwargs: None,
        score_article=lambda *args, **kwargs: (0.8, []),
        index_article=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(persistence, "DB_PATH", db_module.DB_PATH)
    monkeypatch.setitem(sys.modules, "embedding_service", fake_embedding)
    monkeypatch.setattr(persistence, "notify_google_index", lambda *args, **kwargs: None)
    monkeypatch.setattr(persistence, "run_post_publication_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(ig_card_generator, "generate_card", lambda *args, **kwargs: generated_path)

    result = persistence.save_to_db([_processed_article(slug)], [_original_article(slug)])

    conn = sqlite3.connect(db_module.DB_PATH)
    row = conn.execute(
        "SELECT image, social_image FROM articles WHERE slug = ?",
        (slug,),
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0].startswith("/static/fallbacks/")
    assert row[1] == "/static/img/social/agent-benchmarks-visual-context.png"
    assert result.articles_saved == 1


def test_save_to_db_keeps_stock_fallback_when_card_generation_fails(monkeypatch):
    import db as db_module
    import fetcher.persistence as persistence
    import ig_card_generator

    slug = "agent-benchmarks-card-failure"

    fake_embedding = SimpleNamespace(
        score_ad_likelihood=lambda *args, **kwargs: 0.0,
        find_duplicates=lambda *args, **kwargs: None,
        score_article=lambda *args, **kwargs: (0.8, []),
        index_article=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(persistence, "DB_PATH", db_module.DB_PATH)
    monkeypatch.setitem(sys.modules, "embedding_service", fake_embedding)
    monkeypatch.setattr(persistence, "notify_google_index", lambda *args, **kwargs: None)
    monkeypatch.setattr(persistence, "run_post_publication_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(ig_card_generator, "generate_card", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("card failed")))

    persistence.save_to_db([_processed_article(slug)], [_original_article(slug)])

    conn = sqlite3.connect(db_module.DB_PATH)
    row = conn.execute("SELECT image FROM articles WHERE slug = ?", (slug,)).fetchone()
    conn.close()

    assert row is not None
    assert row[0].startswith("/static/fallbacks/")


def test_save_to_db_keeps_scraped_image_and_stores_social_card(monkeypatch):
    import db as db_module
    import fetcher.persistence as persistence
    import ig_card_generator

    slug = "agent-benchmarks-with-source-image"
    generated_path = "/Users/test/project/static/img/social/agent-benchmarks-with-source-image.png"
    original = _original_article(slug)
    original["scraped_image"] = "https://cdn.example.com/research-photo.jpg"

    fake_embedding = SimpleNamespace(
        score_ad_likelihood=lambda *args, **kwargs: 0.0,
        find_duplicates=lambda *args, **kwargs: None,
        score_article=lambda *args, **kwargs: (0.8, []),
        index_article=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(persistence, "DB_PATH", db_module.DB_PATH)
    monkeypatch.setitem(sys.modules, "embedding_service", fake_embedding)
    monkeypatch.setattr(persistence, "notify_google_index", lambda *args, **kwargs: None)
    monkeypatch.setattr(persistence, "run_post_publication_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(ig_card_generator, "generate_card", lambda *args, **kwargs: generated_path)

    persistence.save_to_db([_processed_article(slug)], [original])

    conn = sqlite3.connect(db_module.DB_PATH)
    row = conn.execute(
        "SELECT image, social_image FROM articles WHERE slug = ?",
        (slug,),
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "https://cdn.example.com/research-photo.jpg"
    assert row[1] == "/static/img/social/agent-benchmarks-with-source-image.png"


def test_save_to_db_commits_article_before_indexing_side_effects(monkeypatch):
    import db as db_module
    import fetcher.persistence as persistence
    import ig_card_generator

    slug = "agent-benchmarks-commit-before-hooks"

    fake_embedding = SimpleNamespace(
        score_ad_likelihood=lambda *args, **kwargs: 0.0,
        find_duplicates=lambda *args, **kwargs: None,
        score_article=lambda *args, **kwargs: (0.8, []),
        index_article=lambda *args, **kwargs: None,
    )

    observed = {"visible_during_indexing": False}

    def _assert_article_visible(url):
        conn = sqlite3.connect(db_module.DB_PATH)
        try:
            row = conn.execute(
                "SELECT slug FROM articles WHERE slug = ?",
                (slug,),
            ).fetchone()
        finally:
            conn.close()
        observed["visible_during_indexing"] = row is not None

    monkeypatch.setattr(persistence, "DB_PATH", db_module.DB_PATH)
    monkeypatch.setitem(sys.modules, "embedding_service", fake_embedding)
    monkeypatch.setattr(persistence, "notify_google_index", _assert_article_visible)
    monkeypatch.setattr(persistence, "run_post_publication_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(ig_card_generator, "generate_card", lambda *args, **kwargs: None)

    persistence.save_to_db([_processed_article(slug)], [_original_article(slug)])

    assert observed["visible_during_indexing"] is True


def test_save_to_db_blocks_recent_cross_source_story_duplicate(monkeypatch):
    import db as db_module
    import fetcher.persistence as persistence

    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        """
        INSERT INTO articles (
            slug, title, category, gist, source, source_url, published_at,
            importance_score, is_published
        ) VALUES (?, ?, ?, ?, ?, ?, datetime('now', '-4 hours'), ?, 1)
        """,
        (
            "hugging-face-network-breached-autonomous-ai-agent-test",
            "Hugging Face Network Breached by Autonomous AI Agent",
            "Security",
            "Autonomous AI agent breached Hugging Face.",
            "BleepingComputer",
            "https://example.com/original-hugging-face-story",
            80,
        ),
    )
    conn.commit()
    conn.close()

    processed = _processed_article("hugging-face-ai-agent-breach-test")
    processed.update(
        {
            "headline": "Hugging Face Confirms AI Agent-Driven Security Breach",
            "gist": "AI agent breached Hugging Face infrastructure.",
            "category": "Security",
        }
    )
    original = _original_article("hugging-face-ai-agent-breach-test")
    original.update(
        {
            "title": processed["headline"],
            "source": "Mrkt30",
            "link": "https://example.net/reworded-hugging-face-story",
        }
    )

    fake_embedding = SimpleNamespace(
        score_ad_likelihood=lambda *args, **kwargs: 0.0,
        find_duplicates=lambda *args, **kwargs: None,
        score_article=lambda *args, **kwargs: (0.8, []),
        index_article=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(persistence, "DB_PATH", db_module.DB_PATH)
    monkeypatch.setitem(sys.modules, "embedding_service", fake_embedding)
    monkeypatch.setattr(persistence, "notify_google_index", lambda *args, **kwargs: None)
    monkeypatch.setattr(persistence, "run_post_publication_audit", lambda *args, **kwargs: None)
    persistence.save_to_db([processed], [original])

    conn = sqlite3.connect(db_module.DB_PATH)
    duplicate = conn.execute(
        "SELECT id FROM articles WHERE slug = ?",
        ("hugging-face-ai-agent-breach-test",),
    ).fetchone()
    conn.close()

    assert duplicate is None


def test_save_to_db_blocks_old_cross_source_copy_of_same_research_paper(monkeypatch):
    import db as db_module
    import fetcher.persistence as persistence

    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        """
        INSERT INTO articles (
            slug, title, category, gist, source, source_url, published_at,
            importance_score, is_published
        ) VALUES (?, ?, ?, ?, ?, ?, datetime('now', '-10 days'), ?, 1)
        """,
        (
            "deepsearch-world-arxiv-test",
            "DeepSearch-World Enables Self-Evolving Web Agents",
            "AI Agents",
            "A verifiable environment for training web agents.",
            "ArXiv cs.CL",
            "https://arxiv.org/abs/2607.07820",
            85,
        ),
    )
    conn.commit()
    conn.close()

    processed = _processed_article("deepsearch-world-hugging-face-test")
    processed.update(
        {
            "headline": "DeepSearch-World Enables Self-Distillation for Web Agents",
            "seo_slug": "deepsearch-world-hugging-face-test",
            "gist": "Self-distillation trains web agents in verifiable environments.",
            "category": "AI Agents",
        }
    )
    original = _original_article("deepsearch-world-hugging-face-test")
    original.update(
        {
            "title": processed["headline"],
            "source": "Hugging Face Papers",
            "link": "https://huggingface.co/papers/2607.07820",
        }
    )

    fake_embedding = SimpleNamespace(
        score_ad_likelihood=lambda *args, **kwargs: 0.0,
        find_duplicates=lambda *args, **kwargs: None,
        score_article=lambda *args, **kwargs: (0.8, []),
        index_article=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(persistence, "DB_PATH", db_module.DB_PATH)
    monkeypatch.setitem(sys.modules, "embedding_service", fake_embedding)
    monkeypatch.setattr(persistence, "notify_google_index", lambda *args, **kwargs: None)
    monkeypatch.setattr(persistence, "run_post_publication_audit", lambda *args, **kwargs: None)

    persistence.save_to_db([processed], [original])

    conn = sqlite3.connect(db_module.DB_PATH)
    duplicate = conn.execute(
        "SELECT id FROM articles WHERE slug = ?",
        ("deepsearch-world-hugging-face-test",),
    ).fetchone()
    conn.close()

    assert duplicate is None


def test_save_to_db_never_replaces_existing_article_on_source_url_collision(monkeypatch):
    import db as db_module
    import fetcher.persistence as persistence
    import ig_card_generator

    source_url = "https://example.com/source-url-collision"
    conn = sqlite3.connect(db_module.DB_PATH)
    existing_id = conn.execute(
        """
        INSERT INTO articles (
            slug, title, category, gist, source, source_url, published_at,
            importance_score, is_published
        ) VALUES (?, ?, ?, ?, ?, ?, datetime('now', '-10 days'), ?, 1)
        """,
        (
            "source-url-collision-existing-test",
            "Existing Canonical Source Story",
            "Business",
            "Existing source story.",
            "Existing Source",
            source_url,
            80,
        ),
    ).lastrowid
    conn.commit()
    conn.close()

    processed = _processed_article("source-url-collision-new-test")
    processed.update(
        {
            "headline": "Unrelated New Analysis Must Not Replace Existing Record",
            "seo_slug": "source-url-collision-new-test",
            "gist": "A distinct analysis that arrived with a reused source URL.",
        }
    )
    original = _original_article("source-url-collision-new-test")
    original.update(
        {
            "title": processed["headline"],
            "source": "New Source",
            "link": source_url,
        }
    )

    fake_embedding = SimpleNamespace(
        score_ad_likelihood=lambda *args, **kwargs: 0.0,
        find_duplicates=lambda *args, **kwargs: None,
        score_article=lambda *args, **kwargs: (0.8, []),
        index_article=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(persistence, "DB_PATH", db_module.DB_PATH)
    monkeypatch.setitem(sys.modules, "embedding_service", fake_embedding)
    monkeypatch.setattr(persistence, "notify_google_index", lambda *args, **kwargs: None)
    monkeypatch.setattr(persistence, "run_post_publication_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(ig_card_generator, "generate_card", lambda *args, **kwargs: None)

    persistence.save_to_db([processed], [original])

    conn = sqlite3.connect(db_module.DB_PATH)
    rows = conn.execute(
        "SELECT id, slug, title FROM articles WHERE source_url = ?",
        (source_url,),
    ).fetchall()
    conn.close()

    assert rows == [
        (
            existing_id,
            "source-url-collision-existing-test",
            "Existing Canonical Source Story",
        )
    ]


@pytest.mark.parametrize("invalid_batch_id", [None, -1, 99, [0], True])
def test_save_to_db_rejects_invalid_batch_id_without_source_fallback(
    monkeypatch,
    invalid_batch_id,
):
    import db as db_module
    import fetcher.persistence as persistence
    import ig_card_generator

    slug = "agent-benchmarks-invalid-source-map"
    processed = _processed_article(slug)
    processed["batch_id"] = invalid_batch_id

    fake_embedding = SimpleNamespace(
        score_ad_likelihood=lambda *args, **kwargs: 0.0,
        find_duplicates=lambda *args, **kwargs: None,
        score_article=lambda *args, **kwargs: (0.8, []),
        index_article=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(persistence, "DB_PATH", db_module.DB_PATH)
    monkeypatch.setitem(sys.modules, "embedding_service", fake_embedding)
    monkeypatch.setattr(persistence, "notify_google_index", lambda *args, **kwargs: None)
    monkeypatch.setattr(persistence, "run_post_publication_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(ig_card_generator, "generate_card", lambda *args, **kwargs: None)

    result = persistence.save_to_db([processed], [_original_article(slug)])

    conn = sqlite3.connect(db_module.DB_PATH)
    row = conn.execute(
        "SELECT id FROM articles WHERE slug = ?",
        (slug,),
    ).fetchone()
    conn.close()

    assert row is None
    assert result.articles_saved == 0
