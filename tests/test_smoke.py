"""
Smoke tests — DailyAIWire.news
Validates that the app boots and all critical routes respond correctly.
"""


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
                    'admin_content', 'admin_ops', 'admin_carousel']
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

    def test_homepage_pagination(self, client):
        resp = client.get('/?page=2')
        assert resp.status_code == 200

    def test_article_page(self, client):
        resp = client.get('/article/test-article-slug')
        assert resp.status_code == 200

    def test_article_not_found(self, client):
        resp = client.get('/article/nonexistent-slug-xyz')
        assert resp.status_code == 404

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
        assert resp.headers.get('Access-Control-Allow-Origin') == '*'

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
        assert resp.status_code == 404
        assert b'Intelligence Not Found' in resp.data

    def test_error_handlers_registered(self, client):
        from app import app
        handlers = app.error_handler_spec.get(None, {})
        assert 404 in handlers
        assert 500 in handlers
        assert 403 in handlers
        assert 429 in handlers

