import sqlite3
import sys
from types import SimpleNamespace


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

    persistence.save_to_db([_processed_article(slug)], [_original_article(slug)])

    conn = sqlite3.connect(db_module.DB_PATH)
    row = conn.execute(
        "SELECT image, social_image FROM articles WHERE slug = ?",
        (slug,),
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0].startswith("/static/fallbacks/")
    assert row[1] == "/static/img/social/agent-benchmarks-visual-context.png"


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
