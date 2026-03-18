"""
Flask extensions — DailyAIWire.news
Defines global extensions to avoid circular imports.
"""
from flask import current_app
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

csrf = CSRFProtect()

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://"
)

@limiter.request_filter
def bypass_in_tests():
    """Bypass rate limiting strictly during tests, unless explicitly enforced."""
    if current_app.config.get('TESTING'):
        return not current_app.config.get('RATELIMIT_ENABLED', False)
    return False
