import sqlite3


def _article(**overrides):
    article = {
        "title": "High-Signal AI Governance Breakthrough",
        "slug": "high-signal-ai-governance-breakthrough",
        "source": "MIT Technology Review",
        "source_url": "https://www.technologyreview.com/example",
        "image": "/static/uploads/high-signal.jpg",
        "category": "Policy",
        "gist": "A concise summary of the policy breakthrough and its near-term consequences.",
        "why_it_matters": "This matters because it changes how public institutions evaluate high-risk AI systems before deployment.",
        "bull_case": "The policy could create safer adoption paths for enterprise and public-sector AI systems.",
        "bear_case": "The compliance burden could slow smaller builders and concentrate power among incumbents.",
        "key_details": '["Policy deadline moved forward", "Compliance tooling demand is rising", "Audits become more important"]',
        "deep_analysis": " ".join(["original context"] * 520),
        "importance_score": 90,
        "compass_score": 0.82,
    }
    article.update(overrides)
    return article


def test_indexability_score_accepts_original_high_signal_article():
    from services.indexability import score_article

    result = score_article(_article())

    assert result.score >= 75
    assert result.sitemap_eligible is True
    assert "deep_analysis" not in result.blockers


def test_indexability_score_rejects_thin_low_signal_article():
    from services.indexability import score_article

    result = score_article(
        _article(
            source="GitHub",
            image="/static/fallbacks/tools_0.jpg",
            why_it_matters="",
            bull_case="",
            bear_case="",
            key_details="[]",
            deep_analysis="short summary only",
            importance_score=45,
            compass_score=0.65,
        )
    )

    assert result.score < 65
    assert result.sitemap_eligible is False
    assert "deep_analysis" in result.blockers
    assert "why_it_matters" in result.blockers


def test_sitemap_core_uses_indexability_gate(client):
    import db as db_module

    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        """
        INSERT INTO articles (
            slug, title, image, category, gist, why_it_matters, bull_case,
            bear_case, key_details, eli5, deep_analysis, source, source_url,
            full_json, published_at, importance_score, is_published,
            design_tokens, compass_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "thin-low-signal-sitemap-test",
            "Thin Low Signal Sitemap Test",
            "/static/fallbacks/tools_0.jpg",
            "Tools",
            "Short gist.",
            "",
            "",
            "",
            "[]",
            "",
            "short summary only",
            "GitHub",
            "https://github.com/example/unproven",
            "{}",
            "2026-04-28T12:00:00",
            100,
            1,
            "{}",
            0.95,
        ),
    )
    conn.execute(
        """
        INSERT INTO articles (
            slug, title, image, category, gist, why_it_matters, bull_case,
            bear_case, key_details, eli5, deep_analysis, source, source_url,
            full_json, published_at, importance_score, is_published,
            design_tokens, compass_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "strong-indexable-sitemap-test",
            "Strong Indexable Sitemap Test",
            "/static/uploads/strong-indexable.jpg",
            "Policy",
            "A strong, original summary.",
            "This matters because it gives readers a clear strategic implication beyond the original source.",
            "The upside is faster adoption of safer systems.",
            "The downside is a larger compliance moat.",
            '["Original context", "Concrete implication", "Clear tradeoff"]',
            "Simple explanation.",
            " ".join(["substantive analysis"] * 520),
            "MIT Technology Review",
            "https://www.technologyreview.com/example-strong",
            "{}",
            "2026-04-28T13:00:00",
            100,
            1,
            "{}",
            0.95,
        ),
    )
    conn.commit()
    conn.close()

    resp = client.get("/sitemap-core.xml")
    xml = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "strong-indexable-sitemap-test" in xml
    assert "thin-low-signal-sitemap-test" not in xml


def test_sitemap_append_helper_can_skip_first_eligible_page():
    from routes.seo import _append_article_sitemap_pages

    strong_one = _article(slug="strong-one")
    strong_two = _article(slug="strong-two")
    weak = _article(
        slug="weak-one",
        deep_analysis="short",
        why_it_matters="",
        key_details="[]",
        bull_case="",
        bear_case="",
        source="GitHub",
        image="/static/fallbacks/tools_0.jpg",
        importance_score=30,
        compass_score=0.7,
    )
    rows = [strong_one, weak, strong_two]
    pages = []

    _append_article_sitemap_pages(
        pages,
        rows,
        "https://dailyaiwire.news",
        0.4,
        "monthly",
        "2026-04-29",
        limit=1,
        skip_eligible=1,
    )

    assert len(pages) == 1
    assert pages[0][0] == "https://dailyaiwire.news/article/strong-two"
