import sqlite3


def _long_text(seed, words=520):
    return " ".join([seed] * words)


def _insert_article(conn, slug, *, title, source, image, deep_analysis, why_it_matters,
                    bull_case, bear_case, key_details, importance_score=90,
                    compass_score=0.85):
    conn.execute(
        """
        INSERT OR REPLACE INTO articles (
            slug, title, image, category, gist, why_it_matters, bull_case,
            bear_case, key_details, eli5, deep_analysis, source, source_url,
            full_json, published_at, importance_score, is_published,
            design_tokens, compass_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            slug,
            title,
            image,
            "Policy",
            "A detailed summary that gives readers direct context and concrete implications.",
            why_it_matters,
            bull_case,
            bear_case,
            key_details,
            "Plain English explanation.",
            deep_analysis,
            source,
            f"https://example.com/{slug}",
            "{}",
            "2026-04-29T10:00:00",
            importance_score,
            1,
            "{}",
            compass_score,
        ),
    )


def _seed_seo_articles():
    import db as db_module

    conn = sqlite3.connect(db_module.DB_PATH)
    _insert_article(
        conn,
        "admin-seo-eligible",
        title="High Signal Governance Article With Original Analysis",
        source="MIT Technology Review",
        image="/static/uploads/admin-seo-eligible.jpg",
        why_it_matters=(
            "This matters because it explains practical governance consequences "
            "for public institutions and enterprise AI buyers."
        ),
        bull_case="The upside is a clearer compliance path for high-risk AI systems.",
        bear_case="The downside is that smaller teams may face a larger compliance burden.",
        key_details='["Original context", "Concrete implication", "Clear tradeoff"]',
        deep_analysis=_long_text("indexable"),
    )
    _insert_article(
        conn,
        "admin-seo-thin",
        title="Thin GitHub Repo",
        source="GitHub",
        image="/static/fallbacks/tools_0.jpg",
        why_it_matters="",
        bull_case="",
        bear_case="",
        key_details="[]",
        deep_analysis="short summary only",
        importance_score=45,
        compass_score=0.6,
    )
    conn.commit()
    conn.close()


def test_admin_seo_requires_login(client):
    resp = client.get("/admin/seo", follow_redirects=False)

    assert resp.status_code in (302, 308)
    assert "/login" in resp.headers.get("Location", "")


def test_admin_seo_panel_shows_scores_and_blockers(auth_client):
    _seed_seo_articles()

    resp = auth_client.get("/admin/seo")
    html = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "Indexability Control" in html
    assert "Sitemap Eligible" in html
    assert "admin-seo-eligible" in html
    assert "admin-seo-thin" in html
    assert "low_context_source" in html
    assert "fallback_image" in html


def test_admin_seo_status_and_blocker_filters(auth_client):
    _seed_seo_articles()

    eligible_resp = auth_client.get("/admin/seo?status=eligible")
    eligible_html = eligible_resp.get_data(as_text=True)
    assert eligible_resp.status_code == 200
    assert "admin-seo-eligible" in eligible_html
    assert "admin-seo-thin" not in eligible_html

    blocker_resp = auth_client.get("/admin/seo?blocker=low_context_source")
    blocker_html = blocker_resp.get_data(as_text=True)
    assert blocker_resp.status_code == 200
    assert "admin-seo-thin" in blocker_html
    assert "admin-seo-eligible" not in blocker_html


def test_admin_seo_csv_export(auth_client):
    _seed_seo_articles()

    resp = auth_client.get("/admin/seo.csv?blocker=low_context_source")
    csv_body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert "slug,title,source,indexability_score,sitemap_eligible,blockers" in csv_body
    assert "admin-seo-thin" in csv_body
    assert "low_context_source" in csv_body
