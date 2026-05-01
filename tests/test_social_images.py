import sqlite3


def test_article_social_meta_prefers_social_image(auth_client):
    import db as db_module

    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        """
        INSERT OR REPLACE INTO articles (
            slug, title, image, social_image, category, gist, why_it_matters,
            bull_case, bear_case, key_details, eli5, deep_analysis, source,
            source_url, full_json, published_at, importance_score, is_published,
            design_tokens
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "social-image-meta-test",
            "Social Image Meta Test",
            "/static/fallbacks/tools_0.jpg",
            "/static/img/social/social-image-meta-test.png",
            "Tools",
            "A concise social image test gist.",
            "This matters because social previews need stable thumbnails.",
            "Upside.",
            "Risk.",
            '["Fact"]',
            "Simple explanation.",
            "Deep analysis with enough context.",
            "Test Source",
            "https://example.com/social-image-meta-test",
            "{}",
            "2026-05-01T12:00:00",
            80,
            1,
            "{}",
        ),
    )
    conn.commit()
    conn.close()

    resp = auth_client.get("/article/social-image-meta-test")
    html = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'property="og:image"' in html
    assert "https://dailyaiwire.news/static/img/social/social-image-meta-test.png" in html
    assert 'name="twitter:image"' in html
    assert 'src="/static/fallbacks/tools_0.jpg"' in html


def test_nginx_static_images_do_not_send_x_robots_noindex():
    with open("nginx_optimized.conf", encoding="utf-8") as fh:
        conf = fh.read()

    assert 'X-Robots-Tag "noindex"' not in conf
