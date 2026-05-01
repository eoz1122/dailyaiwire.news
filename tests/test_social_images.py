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
    assert "https://dailyaiwire.news/social-image/social-image-meta-test.png" in html
    assert 'name="twitter:image"' in html
    assert 'src="/static/fallbacks/tools_0.jpg"' in html


def test_social_image_route_serves_generated_cards_without_x_robots(client):
    from pathlib import Path

    image_dir = Path("static/img/social")
    image_dir.mkdir(parents=True, exist_ok=True)
    image_path = image_dir / "route-test.png"
    image_path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
        b"\x90wS\xde"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    try:
        resp = client.get("/social-image/route-test.png")
    finally:
        image_path.unlink(missing_ok=True)

    assert resp.status_code == 200
    assert resp.mimetype == "image/png"
    assert "X-Robots-Tag" not in resp.headers


def test_social_image_route_rejects_path_traversal(client):
    resp = client.get("/social-image/../favicon.png")

    assert resp.status_code == 404


def test_nginx_static_images_do_not_send_x_robots_noindex():
    with open("nginx_optimized.conf", encoding="utf-8") as fh:
        conf = fh.read()

    assert 'X-Robots-Tag "noindex"' not in conf
