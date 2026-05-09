"""
Smoke tests — DailyAIWire.news
Validates that the app boots and all critical routes respond correctly.
"""
import sqlite3


def _seed_published_editorial():
    import db as db_module

    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS blog_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            slug TEXT,
            content TEXT,
            subtitle TEXT,
            author_name TEXT,
            author_title TEXT,
            meta_description TEXT,
            is_published BOOLEAN DEFAULT 0,
            published_at TIMESTAMP
        )
        """
    )
    cursor = conn.execute(
        """
        INSERT OR REPLACE INTO blog_posts (
            title, slug, content, subtitle, author_name, author_title,
            meta_description, is_published, published_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "Editorial Test",
            "editorial-test",
            "<p>Test editorial body</p>",
            "Editorial subtitle",
            "Ali Emre Ozen",
            "The Architect",
            "Editorial description",
            1,
            "2026-04-27 20:00:00",
        ),
    )
    conn.commit()
    editorial_id = cursor.lastrowid
    conn.close()
    return editorial_id


# ── App Factory ──────────────────────────────────────────────────────

class TestAppBoot:
    """Verify the Flask app initializes without errors."""

    def test_app_exists(self, client):
        from app import app
        assert app is not None

    def test_app_is_testing(self, client):
        from app import app
        assert app.config['TESTING'] is True

    def test_blueprints_registered(self, client):
        from app import app
        bp_names = list(app.blueprints.keys())
        expected = ['auth', 'public', 'api', 'seo', 'lab', 'admin_core',
                    'admin_content', 'admin_ops', 'admin_carousel', 'admin_seo',
                    'admin_indexing']
        for bp in expected:
            assert bp in bp_names, f"Blueprint '{bp}' not registered"


# ── Public Routes ────────────────────────────────────────────────────

class TestPublicRoutes:
    """All public-facing routes should return 200."""

    def test_homepage(self, client):
        resp = client.get('/')
        assert resp.status_code == 200

    def test_homepage_with_search(self, client):
        resp = client.get('/?q=test')
        assert resp.status_code == 200

    def test_homepage_with_category(self, client):
        resp = client.get('/?category=Tools')
        assert resp.status_code == 200

    def test_homepage_with_editorial_category(self, client):
        resp = client.get('/?category=Editorial')
        assert resp.status_code == 200

    def test_homepage_pagination(self, client):
        resp = client.get('/?page=2')
        assert resp.status_code == 200

    def test_article_page(self, client):
        resp = client.get('/article/test-article-slug')
        assert resp.status_code == 200

    def test_article_verified_views_dedup_and_bot_filter(self, client):
        import db as db_module
        import sqlite3

        def get_counts():
            conn = sqlite3.connect(db_module.DB_PATH)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT views, verified_views FROM articles WHERE slug = ?",
                ('test-article-slug',)
            ).fetchone()
            conn.close()
            return int(row['views'] or 0), int(row['verified_views'] or 0)

        before_views, before_verified = get_counts()

        human_headers = {'User-Agent': 'Mozilla/5.0 (DailyAIWire-Test)'}
        bot_headers = {'User-Agent': 'Googlebot/2.1 (+http://www.google.com/bot.html)'}

        resp = client.get('/article/test-article-slug', headers=human_headers)
        assert resp.status_code == 200
        h1_views, h1_verified = get_counts()
        assert h1_views == before_views + 1
        assert h1_verified == before_verified + 1

        # Same visitor in dedupe window: raw views increments, verified does not.
        resp = client.get('/article/test-article-slug', headers=human_headers)
        assert resp.status_code == 200
        h2_views, h2_verified = get_counts()
        assert h2_views == h1_views + 1
        assert h2_verified == h1_verified

        # Bot request should not count as verified.
        resp = client.get('/article/test-article-slug', headers=bot_headers)
        assert resp.status_code == 200
        b_views, b_verified = get_counts()
        assert b_views == h2_views + 1
        assert b_verified == h2_verified

    def test_article_not_found(self, client):
        resp = client.get('/article/nonexistent-slug-xyz')
        assert resp.status_code == 410

    def test_about_page(self, client):
        resp = client.get('/about')
        assert resp.status_code == 200

    def test_contact_page(self, client):
        resp = client.get('/contact')
        assert resp.status_code == 200

    def test_privacy_page(self, client):
        resp = client.get('/privacy')
        assert resp.status_code == 200

    def test_impressum_page(self, client):
        resp = client.get('/impressum')
        assert resp.status_code == 200

    def test_how_it_works_page(self, client):
        resp = client.get('/how-it-works')
        assert resp.status_code == 200

    def test_thank_you_page(self, client):
        resp = client.get('/thank-you')
        assert resp.status_code == 200

    def test_subscribe_get(self, client):
        resp = client.get('/subscribe')
        assert resp.status_code == 200

    def test_podcast_page(self, client):
        resp = client.get('/podcast')
        assert resp.status_code == 200
        assert b'Podcast' in resp.data


# ── Auth Guard ───────────────────────────────────────────────────────

class TestAuthGuard:
    """Admin routes should redirect to login when unauthenticated."""

    def test_admin_dashboard_requires_login(self, client):
        resp = client.get('/admin/', follow_redirects=False)
        assert resp.status_code in (302, 308)
        assert '/login' in resp.headers.get('Location', '')

    def test_admin_sources_requires_login(self, client):
        resp = client.get('/admin/sources', follow_redirects=False)
        assert resp.status_code in (302, 308)

    def test_admin_leads_requires_login(self, client):
        resp = client.get('/admin/leads', follow_redirects=False)
        assert resp.status_code in (302, 308)

    def test_admin_budget_requires_login(self, client):
        resp = client.get('/admin/budget', follow_redirects=False)
        assert resp.status_code in (302, 308)

    def test_admin_duplicates_requires_login(self, client):
        resp = client.get('/admin/duplicates', follow_redirects=False)
        assert resp.status_code in (302, 308)


# ── Admin Routes (Authenticated) ────────────────────────────────────

class TestAdminRoutesAuthenticated:
    """Admin routes should return 200 when logged in."""

    def test_admin_dashboard(self, auth_client):
        resp = auth_client.get('/admin/')
        assert resp.status_code == 200

    def test_admin_dashboard_includes_verified_views_column(self, auth_client):
        resp = auth_client.get('/admin/')
        assert resp.status_code == 200
        assert b'Verified' in resp.data

    def test_admin_sources(self, auth_client):
        resp = auth_client.get('/admin/sources')
        assert resp.status_code == 200

    def test_admin_leads(self, auth_client):
        resp = auth_client.get('/admin/leads')
        assert resp.status_code == 200

    def test_admin_budget(self, auth_client):
        resp = auth_client.get('/admin/budget')
        assert resp.status_code == 200

    def test_admin_duplicates(self, auth_client):
        resp = auth_client.get('/admin/duplicates')
        assert resp.status_code == 200

    def test_admin_carousel(self, auth_client):
        resp = auth_client.get('/admin/carousel')
        assert resp.status_code == 200

    def test_admin_social_queue_uses_url_free_x_copy(self, auth_client):
        resp = auth_client.get('/admin/social-queue')
        assert resp.status_code == 200
        assert b'Why it matters:' in resp.data
        assert b'Follow DailyAIWire for the full brief.' in resp.data
        assert b'utm_source=twitter' not in resp.data
        assert b's.dailyaiwire.news' not in resp.data

    def test_admin_newsletter_preview(self, auth_client):
        resp = auth_client.get('/admin/newsletter/preview')
        assert resp.status_code == 200
        assert b'Weekly Intelligence Briefing' in resp.data
        assert b'[Editorial]' in resp.data
        assert b'read_full_intelligence();' in resp.data

    def test_admin_editorial_share_page_only_shows_x(self, auth_client):
        editorial_id = _seed_published_editorial()

        resp = auth_client.get(f'/admin/editorial/edit/{editorial_id}')

        assert resp.status_code == 200
        assert b'Post to X' in resp.data
        assert b'Post to Instagram' not in resp.data
        assert b'Post to Facebook' not in resp.data

    def test_admin_editorial_share_rejects_meta_platform(self, auth_client):
        editorial_id = _seed_published_editorial()

        resp = auth_client.post(
            f'/admin/editorial/share/{editorial_id}',
            data={'platform': 'instagram'},
        )

        assert resp.status_code == 400
        assert resp.get_json()['error'] == 'Invalid platform'


# ── API Routes ───────────────────────────────────────────────────────

class TestAPIRoutes:
    """API endpoints should return 200 JSON responses."""

    def test_search_empty_query(self, client):
        resp = client.get('/api/search')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['results'] == []
        assert data['mode'] == 'none'

    def test_search_short_query(self, client):
        resp = client.get('/api/search?q=a')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['mode'] == 'none'

    def test_search_valid_query(self, client):
        resp = client.get('/api/search?q=test')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'results' in data
        assert 'mode' in data

    def test_trends_endpoint(self, client):
        resp = client.get('/api/trends')
        assert resp.status_code == 200

    def test_audio_tracking(self, client):
        resp = client.post('/api/track-audio/1')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'


# ── SEO Routes ───────────────────────────────────────────────────────

class TestSEORoutes:
    """SEO endpoints should return valid responses."""

    def test_robots_txt(self, client):
        resp = client.get('/robots.txt')
        assert resp.status_code == 200
        text = resp.get_data(as_text=True)
        assert text.count('Sitemap:') == 1
        assert 'Sitemap: https://dailyaiwire.news/sitemap.xml' in text
        assert 'sitemap-core.xml' not in text
        assert 'sitemap-archive.xml' not in text

    def test_sitemap(self, client):
        resp = client.get('/sitemap.xml')
        assert resp.status_code == 200

    def test_rss_feed(self, client):
        resp = client.get('/rss.xml')
        assert resp.status_code == 200

    def test_login_page(self, client):
        resp = client.get('/login')
        assert resp.status_code == 200

    def test_llms_txt(self, client):
        resp = client.get('/llms.txt')
        assert resp.status_code == 200
        assert b'dailyaiwire.news' in resp.data

    def test_linkedin_rss_feed(self, client):
        resp = client.get('/rss/linkedin')
        assert resp.status_code == 200
        assert b'<rss' in resp.data

    def test_touch_icon_aliases(self, client):
        for path in ('/apple-touch-icon.png', '/apple-touch-icon-precomposed.png'):
            resp = client.get(path)
            assert resp.status_code == 200
            assert resp.content_type == 'image/png'


class TestSEORobotsDirectives:
    """Robots directives should be deterministic and query-safe."""

    def test_search_page_has_single_noindex_meta(self, client):
        resp = client.get('/?q=ai')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert html.count('<meta name="robots"') == 1
        assert 'content="noindex, follow"' in html
        assert resp.headers.get('X-Robots-Tag') == 'noindex, follow'

    def test_article_with_query_params_is_noindex(self, client):
        resp = client.get('/article/test-article-slug?utm_source=x&utm_medium=y')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert html.count('<meta name="robots"') == 1
        assert 'content="noindex, follow"' in html
        assert resp.headers.get('X-Robots-Tag') == 'noindex, follow'

    def test_clean_article_url_stays_indexable(self, client):
        resp = client.get('/article/test-article-slug')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert html.count('<meta name="robots"') == 1
        assert 'content="index, follow' in html


# ── Phase 3: Answer-Engine API ──────────────────────────────────────

class TestAnswerEngineAPI:
    """Answer-Engine intelligence feed endpoints."""

    def test_intelligence_feed(self, client):
        resp = client.get('/api/intelligence')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'articles' in data
        assert 'meta' in data
        assert data['meta']['api_version'] == '1.0'

    def test_intelligence_feed_with_limit(self, client):
        resp = client.get('/api/intelligence?limit=2')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['meta']['returned'] <= 2

    def test_intelligence_feed_with_category(self, client):
        resp = client.get('/api/intelligence?category=Tools')
        assert resp.status_code == 200

    def test_intelligence_detail(self, client):
        resp = client.get('/api/intelligence/test-article-slug')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['slug'] == 'test-article-slug'

    def test_intelligence_detail_not_found(self, client):
        resp = client.get('/api/intelligence/nonexistent-slug-xyz')
        assert resp.status_code == 404

    def test_cors_headers(self, client):
        resp = client.get('/api/intelligence')
        assert resp.headers.get('Access-Control-Allow-Origin') == 'https://dailyaiwire.news'

    def test_cache_headers(self, client):
        resp = client.get('/api/intelligence')
        # Flask test mode may set no-store; verify header is present
        assert resp.headers.get('Cache-Control') is not None


# ── Phase 3: The Signal Newsletter ──────────────────────────────────

class TestSignalRoutes:
    """The Signal newsletter archive routes."""

    def test_signal_archive(self, client):
        resp = client.get('/signal')
        assert resp.status_code == 200
        assert b'The Signal' in resp.data

    def test_signal_detail_not_found(self, client):
        resp = client.get('/signal/99999')
        assert resp.status_code == 404


# ── Phase 2: DeepDiagram (Visual Intelligence) ─────────────────────

class TestDiagramRendering:
    """Mermaid diagram rendering on article pages."""

    def test_article_with_diagram_renders_mermaid(self, client):
        resp = client.get('/article/test-article-with-diagram')
        assert resp.status_code == 200
        assert b'mermaid' in resp.data
        assert b'Visual Intelligence' in resp.data
        assert b'flowchart LR' in resp.data

    def test_article_without_diagram_no_mermaid(self, client):
        resp = client.get('/article/test-article-slug')
        assert resp.status_code == 200
        # Check the actual rendered section ID (not the HTML comment)
        assert b'id="visual-intelligence"' not in resp.data


# ── Error Handling ──────────────────────────────────────────────────

class TestErrorPages:
    """Branded error pages should render correctly."""

    def test_404_branded_page(self, client):
        resp = client.get('/this-page-does-not-exist')
        assert resp.status_code == 404
        assert b'Intelligence Not Found' in resp.data

    def test_404_article_not_found(self, client):
        resp = client.get('/article/definitely-not-a-real-slug-xyz')
        assert resp.status_code == 410

    def test_error_handlers_registered(self, client):
        from app import app
        handlers = app.error_handler_spec.get(None, {})
        assert 404 in handlers
        assert 500 in handlers
        assert 403 in handlers
        assert 429 in handlers


# ── P1/P2 SEO Indexing Fixes ───────────────────────────────────────

class TestSitemapCaching:
    """Sitemap endpoints should include Cache-Control headers."""

    def test_sitemap_index_cache_header(self, client):
        resp = client.get('/sitemap.xml')
        assert resp.status_code == 200
        cc = resp.headers.get('Cache-Control', '')
        assert 'max-age=3600' in cc

    def test_sitemap_core_returns_200(self, client):
        resp = client.get('/sitemap-core.xml')
        assert resp.status_code == 200
        cc = resp.headers.get('Cache-Control', '')
        assert 'max-age=3600' in cc

    def test_sitemap_archive_returns_200(self, client):
        resp = client.get('/sitemap-archive.xml')
        assert resp.status_code == 200
        cc = resp.headers.get('Cache-Control', '')
        assert 'max-age=21600' in cc

    def test_sitemap_archive_is_contracted_for_indexing_recovery(self, client):
        from routes import seo
        from services.indexability import SITEMAP_ELIGIBILITY_THRESHOLD

        assert seo.ARCHIVE_SITEMAP_LIMIT <= 500
        assert SITEMAP_ELIGIBILITY_THRESHOLD >= 88


class TestArticleSEOEnhancements:
    """P2: Article pages should have improved SEO signals."""

    def test_article_has_reading_time(self, client):
        resp = client.get('/article/test-article-slug')
        assert resp.status_code == 200
        assert b'min read' in resp.data

    def test_article_json_ld_present(self, client):
        resp = client.get('/article/test-article-slug')
        assert resp.status_code == 200
        assert b'application/ld+json' in resp.data
        assert b'NewsArticle' in resp.data
