"""
Site health regression tests for DailyAIWire.news.
Guards against broken public routes, feed leakage, and missing machine-facing assets.
"""

import sqlite3
from bs4 import BeautifulSoup

import db as db_module


def _create_blog_posts_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS blog_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE,
            title TEXT,
            subtitle TEXT,
            content TEXT,
            image TEXT,
            author_name TEXT,
            author_title TEXT,
            author_image TEXT,
            author_linkedin TEXT,
            meta_description TEXT,
            published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_published BOOLEAN DEFAULT 0
        )
        """
    )


class TestSiteHealthRegressions:
    def test_lab_route_ignores_unpublished_editorials(self, client):
        conn = sqlite3.connect(db_module.DB_PATH)
        _create_blog_posts_table(conn)
        conn.execute(
            """
            INSERT INTO blog_posts
                (slug, title, subtitle, content, published_at, is_published)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "draft-editorial",
                "Draft Editorial Should Not Render",
                "This should stay hidden.",
                "<p>Draft content</p>",
                None,
                0,
            ),
        )
        conn.commit()
        conn.close()

        resp = client.get("/lab")
        assert resp.status_code == 200
        assert b"Draft Editorial Should Not Render" not in resp.data

    def test_rss_route_excludes_unpublished_editorials(self, client):
        conn = sqlite3.connect(db_module.DB_PATH)
        _create_blog_posts_table(conn)
        conn.execute(
            """
            INSERT INTO blog_posts
                (slug, title, subtitle, content, published_at, is_published)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "published-editorial",
                "Published Editorial",
                "This should be visible in the feed.",
                "<p>Published content</p>",
                "2026-03-12 10:00:00",
                1,
            ),
        )
        conn.execute(
            """
            INSERT INTO blog_posts
                (slug, title, subtitle, content, published_at, is_published)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "draft-editorial-rss",
                "Draft Editorial",
                "This should not be visible in the feed.",
                "<p>Draft content</p>",
                None,
                0,
            ),
        )
        conn.commit()
        conn.close()

        resp = client.get("/rss")
        assert resp.status_code == 200
        assert b"<rss" in resp.data
        assert b"Published Editorial" in resp.data
        assert b"Draft Editorial" not in resp.data

    def test_schema_json_asset_exists(self, client):
        resp = client.get("/static/schema.json")
        assert resp.status_code == 200
        assert b"NewsMediaOrganization" in resp.data

    def test_homepage_ai_disclosure_meta_matches_visible_copy(self, client):
        resp = client.get("/")
        page = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert 'meta name="ai-content-declaration" content="ai-assisted-human-reviewed"' in page
        assert "AI-assisted, human-reviewed" in page

    def test_public_disclosure_pages_use_one_consistent_phrase(self, client):
        legacy_phrases = (
            "AI-orchestration",
            "expert-vetted",
            "expert curation",
            "expert curated",
            "machine-generated",
        )

        for route in ("/about", "/how-it-works"):
            resp = client.get(route)
            page = resp.get_data(as_text=True)

            assert resp.status_code == 200
            assert "AI-assisted, human-reviewed" in page
            for phrase in legacy_phrases:
                assert phrase not in page

    def test_homepage_first_grid_keeps_nine_tile_budget(self, client):
        conn = sqlite3.connect(db_module.DB_PATH)
        _create_blog_posts_table(conn)

        for idx in range(4, 22):
            conn.execute(
                """
                INSERT INTO articles (
                    slug, title, image, category, gist, why_it_matters,
                    bull_case, bear_case, key_details, eli5, deep_analysis,
                    source, source_url, full_json, published_at,
                    importance_score, is_published, design_tokens
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"homepage-budget-{idx}",
                    f"Homepage Budget Article {idx}",
                    "/static/fallbacks/tools_0.jpg",
                    "Tools",
                    f"Gist for homepage article {idx}.",
                    f"Why it matters for homepage article {idx}.",
                    "Bull case.",
                    "Bear case.",
                    '["Fact 1"]',
                    "ELI5 text.",
                    "Deep analysis.",
                    "Test Source",
                    f"https://example.com/homepage-budget-{idx}",
                    "{}",
                    f"2026-03-{idx:02d}T12:00:00",
                    80,
                    1,
                    '{"intensity": "standard", "sentiment_pallet": "techno-optimist", "component_triggers": []}',
                ),
            )

        conn.execute(
            """
            INSERT INTO blog_posts
                (slug, title, subtitle, content, author_name, published_at, is_published)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "editorial-homepage-1",
                "Homepage Editorial One",
                "Editorial slot one.",
                "<p>Editorial content one</p>",
                "Editor One",
                "2026-03-21 10:00:00",
                1,
            ),
        )
        conn.execute(
            """
            INSERT INTO blog_posts
                (slug, title, subtitle, content, author_name, published_at, is_published)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "editorial-homepage-2",
                "Homepage Editorial Two",
                "Editorial slot two.",
                "<p>Editorial content two</p>",
                "Editor Two",
                "2026-03-20 10:00:00",
                1,
            ),
        )
        conn.commit()
        conn.close()

        resp = client.get("/")
        soup = BeautifulSoup(resp.get_data(as_text=True), "html.parser")

        assert resp.status_code == 200

        grid_child_counts = []
        for div in soup.find_all("div"):
            classes = div.get("class") or []
            if "grid" in classes and "lg:grid-cols-3" in classes and "gap-6" in classes:
                grid_child_counts.append(len(div.find_all("div", recursive=False)))

        assert grid_child_counts
        assert max(grid_child_counts) == 9
