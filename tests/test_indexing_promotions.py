import sqlite3
from datetime import date, datetime, timedelta, timezone


def _insert_article(conn, *, slug, verified_views, views, strong=True, published_at="2026-07-14T12:00:00"):
    deep_analysis = " ".join(["substantive original analysis"] * (520 if strong else 20))
    conn.execute(
        """
        INSERT INTO articles (
            slug, title, image, social_image, category, gist, why_it_matters,
            bull_case, bear_case, key_details, eli5, deep_analysis, source,
            source_url, full_json, published_at, importance_score, is_published,
            views, verified_views, design_tokens, compass_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            slug,
            f"High-value indexing candidate {slug}",
            "/static/uploads/high-value.jpg",
            f"/static/img/social/{slug}.png",
            "Policy",
            "A detailed summary that explains the development and its practical implications for decision makers.",
            "This matters because it adds concrete context, identifies affected stakeholders, and explains the likely operational consequences.",
            "The upside is measurable adoption, stronger implementation evidence, and clearer outcomes for practitioners.",
            "The risk is that implementation complexity, weak oversight, and uncertain incentives could limit those outcomes.",
            '["Original evidence", "Operational consequence", "Clear tradeoff"]',
            "A simple explanation.",
            deep_analysis,
            "MIT Technology Review" if strong else "News",
            f"https://example.com/{slug}",
            "{}",
            published_at,
            100 if strong else 50,
            1,
            views,
            verified_views,
            "{}",
            0.95 if strong else 0.5,
        ),
    )
    return conn.execute("SELECT id FROM articles WHERE slug = ?", (slug,)).fetchone()[0]


def _cleanup(conn):
    conn.execute("DELETE FROM google_index_promotions")
    conn.execute("DELETE FROM articles WHERE slug LIKE 'promotion-test-%'")
    conn.commit()


def test_promote_next_article_uses_verified_views_and_skips_weak_content(_patch_db):
    from services.indexing_promotions import ensure_google_index_promotions_table, promote_next_article

    conn = sqlite3.connect(_patch_db)
    conn.row_factory = sqlite3.Row
    ensure_google_index_promotions_table(conn)
    _cleanup(conn)

    weak_id = _insert_article(
        conn,
        slug="promotion-test-weak-bot-traffic",
        verified_views=2,
        views=50000,
        strong=False,
    )
    verified_winner_id = _insert_article(
        conn,
        slug="promotion-test-verified-winner",
        verified_views=90,
        views=100,
    )
    _insert_article(
        conn,
        slug="promotion-test-raw-view-runner-up",
        verified_views=20,
        views=10000,
    )
    conn.commit()

    promoted = promote_next_article(target_day=date(2026, 7, 15), conn=conn)

    assert promoted["article_id"] == verified_winner_id
    assert promoted["article_id"] != weak_id
    assert promoted["verified_views_at_promotion"] == 90
    conn.close()


def test_promote_next_article_is_limited_to_one_new_article_per_day(_patch_db):
    from services.indexing_promotions import ensure_google_index_promotions_table, promote_next_article

    conn = sqlite3.connect(_patch_db)
    conn.row_factory = sqlite3.Row
    ensure_google_index_promotions_table(conn)
    _cleanup(conn)

    first_id = _insert_article(
        conn,
        slug="promotion-test-first-day",
        verified_views=50,
        views=60,
    )
    second_id = _insert_article(
        conn,
        slug="promotion-test-second-day",
        verified_views=40,
        views=55,
    )
    conn.commit()

    first = promote_next_article(target_day=date(2026, 7, 15), conn=conn)
    repeated = promote_next_article(target_day=date(2026, 7, 15), conn=conn)
    second = promote_next_article(target_day=date(2026, 7, 16), conn=conn)

    assert first["article_id"] == first_id
    assert repeated["article_id"] == first_id
    assert second["article_id"] == second_id
    assert conn.execute("SELECT COUNT(*) FROM google_index_promotions").fetchone()[0] == 2
    conn.close()


def test_promote_next_article_waits_until_article_is_24_hours_old(_patch_db):
    from services.indexing_promotions import ensure_google_index_promotions_table, promote_next_article

    conn = sqlite3.connect(_patch_db)
    conn.row_factory = sqlite3.Row
    ensure_google_index_promotions_table(conn)
    _cleanup(conn)

    as_of = datetime(2026, 7, 15, 15, 0, tzinfo=timezone.utc)
    too_new_id = _insert_article(
        conn,
        slug="promotion-test-too-new",
        verified_views=1000,
        views=1000,
        published_at="2026-07-14T15:00:01",
    )
    eligible_id = _insert_article(
        conn,
        slug="promotion-test-old-enough",
        verified_views=20,
        views=30,
        published_at="2026-07-14T15:00:00",
    )
    conn.commit()

    promoted = promote_next_article(
        target_day=date(2026, 7, 15),
        as_of=as_of,
        conn=conn,
    )

    assert promoted["article_id"] == eligible_id
    assert promoted["article_id"] != too_new_id
    conn.close()


def test_promote_next_article_prefers_recent_eligible_content(_patch_db):
    from services.indexing_promotions import ensure_google_index_promotions_table, promote_next_article

    conn = sqlite3.connect(_patch_db)
    conn.row_factory = sqlite3.Row
    ensure_google_index_promotions_table(conn)
    _cleanup(conn)

    as_of = datetime(2026, 7, 15, 15, 0, tzinfo=timezone.utc)
    stale_popular_id = _insert_article(
        conn,
        slug="promotion-test-stale-popular",
        verified_views=1000,
        views=1200,
        published_at="2026-04-01T12:00:00",
    )
    recent_id = _insert_article(
        conn,
        slug="promotion-test-recent-reader-pick",
        verified_views=20,
        views=30,
        published_at="2026-07-14T12:00:00",
    )
    conn.commit()

    promoted = promote_next_article(
        target_day=date(2026, 7, 15),
        as_of=as_of,
        conn=conn,
    )

    assert promoted["article_id"] == recent_id
    assert promoted["article_id"] != stale_popular_id
    conn.close()


def test_article_robots_and_sitemap_are_controlled_by_promotion(client, _patch_db):
    from services.indexing_promotions import ensure_google_index_promotions_table

    conn = sqlite3.connect(_patch_db)
    conn.row_factory = sqlite3.Row
    ensure_google_index_promotions_table(conn)
    _cleanup(conn)

    promoted_id = _insert_article(
        conn,
        slug="promotion-test-indexable",
        verified_views=60,
        views=70,
    )
    _insert_article(
        conn,
        slug="promotion-test-not-indexable-yet",
        verified_views=50,
        views=65,
    )
    conn.execute(
        """
        INSERT INTO google_index_promotions (
            article_id, promoted_on, verified_views_at_promotion, raw_views_at_promotion
        ) VALUES (?, ?, ?, ?)
        """,
        (promoted_id, "2026-07-15", 60, 70),
    )
    conn.commit()
    conn.close()

    promoted_page = client.get("/article/promotion-test-indexable")
    waiting_page = client.get("/article/promotion-test-not-indexable-yet")
    sitemap = client.get("/sitemap-core.xml")

    assert promoted_page.status_code == 200
    assert 'content="index, follow' in promoted_page.get_data(as_text=True)
    assert promoted_page.headers.get("X-Robots-Tag") is None

    assert waiting_page.status_code == 200
    assert 'content="noindex, follow"' in waiting_page.get_data(as_text=True)
    assert waiting_page.headers.get("X-Robots-Tag") == "noindex, follow"

    sitemap_xml = sitemap.get_data(as_text=True)
    assert "promotion-test-indexable" in sitemap_xml
    assert "promotion-test-not-indexable-yet" not in sitemap_xml


def test_homepage_and_related_section_link_to_reader_picks(client, _patch_db):
    from services.indexing_promotions import ensure_google_index_promotions_table

    conn = sqlite3.connect(_patch_db)
    conn.row_factory = sqlite3.Row
    ensure_google_index_promotions_table(conn)
    _cleanup(conn)

    promoted_id = _insert_article(
        conn,
        slug="promotion-test-reader-pick",
        verified_views=80,
        views=95,
        published_at="2026-07-14T12:00:00",
    )
    conn.execute(
        """
        INSERT INTO google_index_promotions (
            article_id, promoted_on, verified_views_at_promotion, raw_views_at_promotion
        ) VALUES (?, ?, ?, ?)
        """,
        (promoted_id, "2026-07-15", 80, 95),
    )
    conn.commit()
    conn.close()

    homepage_html = client.get("/").get_data(as_text=True)
    article_html = client.get("/article/test-article-slug").get_data(as_text=True)

    assert 'data-reader-picks="true"' in homepage_html
    assert 'grid grid-cols-1 md:grid-cols-3 gap-3' in homepage_html
    assert 'data-reader-pick-slug="promotion-test-reader-pick"' in homepage_html
    assert 'href="/article/promotion-test-reader-pick"' in article_html


def test_promotion_lookup_does_not_run_schema_ddl_after_migration(_patch_db, monkeypatch):
    import services.indexing_promotions as promotions

    conn = sqlite3.connect(_patch_db)
    promotions.ensure_google_index_promotions_table(conn)
    conn.commit()

    def fail_if_called(_conn=None):
        raise AssertionError("schema DDL must not run during a normal article request")

    monkeypatch.setattr(promotions, "ensure_google_index_promotions_table", fail_if_called)

    assert promotions.is_article_promoted(-1, conn=conn) is False
    conn.close()
