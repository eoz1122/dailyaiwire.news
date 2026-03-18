import pytest
import re
from app import app
from flask import session

class TestSecurityFeatures:

    @pytest.fixture
    def security_client(self, _patch_db):
        """Test client with security features ENFORCED (unlike the open conftest client)."""
        app.config['TESTING'] = True
        
        # Save original config to prevent leakage to other test files
        orig_csrf = app.config.get('WTF_CSRF_ENABLED')
        orig_limit = app.config.get('RATELIMIT_ENABLED')
        
        app.config['WTF_CSRF_ENABLED'] = True
        app.config['RATELIMIT_ENABLED'] = True
        
        with app.test_client() as c:
            yield c
            
        # Restore configuration
        app.config['WTF_CSRF_ENABLED'] = orig_csrf
        app.config['RATELIMIT_ENABLED'] = orig_limit

    def test_csrf_rejects_post_without_token(self, security_client):
        """POST to /login without CSRF token should return 400 Bad Request."""
        resp = security_client.post('/login', data={'username': 'testadmin', 'password': 'testpass'})
        assert resp.status_code == 400
        assert b'The CSRF token is missing.' in resp.data

    def test_api_exempt_from_csrf(self, security_client):
        """API endpoints should be exempt from CSRF (AJAX support)."""
        resp = security_client.post('/api/track-audio/1')
        assert resp.status_code in (200, 404, 500) # Anything but 400 CSRF Missing
        if resp.status_code == 400:
            assert b'The CSRF token is missing.' not in resp.data

    def test_rate_limit_search(self, security_client):
        """Search API should block after 30 requests per minute."""
        # Note: If limiter defaults to memory, this works out of the box.
        successes = 0
        blocks = 0
        for _ in range(35):
            resp = security_client.get('/api/search?q=AI')
            if resp.status_code == 200:
                successes += 1
            elif resp.status_code == 429:
                blocks += 1
        
        # We expect exactly 30 successes and 5 blocks
        assert successes == 30
        assert blocks == 5

    def _get_csrf_token(self, client, route):
        resp = client.get(route)
        match = re.search(rb'name="csrf_token" value="([^"]+)"', resp.data)
        return match.group(1).decode('utf-8') if match else None

    def test_login_brute_force_lockout(self, security_client):
        """After 5 failed login attempts, the account should lock and return 429."""
        csrf_token = self._get_csrf_token(security_client, '/login')
        
        for _ in range(5):
            resp = security_client.post('/login', data={'username': 'target_user', 'password': 'wrong', 'csrf_token': csrf_token})
            # We expect login to fail and return 200 with flash message, or redirect
        
        # 6th attempt should hit the 429 lockout
        resp = security_client.post('/login', data={'username': 'target_user', 'password': 'wrong2', 'csrf_token': csrf_token})
        assert resp.status_code == 429
        assert b'Account temporarily locked' in resp.data

    def test_rate_limit_subscribe(self, security_client):
        """Subscribe endpoint limits to 5 requests per minute."""
        csrf_token = self._get_csrf_token(security_client, '/subscribe')
        
        successes = 0
        blocks = 0
        for _ in range(7):
            resp = security_client.post('/subscribe', data={'email': 'test@example.com', 'csrf_token': csrf_token})
            if resp.status_code in (200, 302):
                successes += 1
            elif resp.status_code == 429:
                blocks += 1
        
        # We expect 5 successes and 2 blocks
        assert successes == 5
        assert blocks == 2

