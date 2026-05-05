"""
DailyAIWire.news — Main Application
Slim app factory: configuration, Blueprint registration, and middleware.
Refactored from 1,967-line monolith on 2026-03-10.
"""
import os
import secrets
import sqlite3
from datetime import datetime

from flask import Flask, request, redirect, url_for, has_request_context, render_template, g
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.model import BaseModelView
from flask_login import current_user, login_required
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

from extensions import csrf, limiter
from db import get_db_connection, DB_PATH
from helpers import register_filters
from logging_config import setup_logging
import logging

# --- App Setup ---
load_dotenv()
setup_logging()

logger = logging.getLogger('app')
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
logger.info("✅ APP BOOT: Blueprint Architecture Loaded at %s", datetime.utcnow())

# SECURITY: Force secure secret key
secret = os.getenv('SECRET_KEY')
if not secret:
    logger.warning("WARNING: SECRET_KEY not set in environment. Generating temporary secure key.")
    secret = os.urandom(24).hex()
app.config['SECRET_KEY'] = secret

# SECURITY: Session cookie hardening (F-02)
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['REMEMBER_COOKIE_SECURE'] = True
app.config['REMEMBER_COOKIE_HTTPONLY'] = True
app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'

# --- Extensions Init ---
csrf.init_app(app)
limiter.init_app(app)

# --- Auto-Migration on Startup ---
def init_db_migrations():
    try:
        conn = sqlite3.connect(DB_PATH)

        # 1. Kill Switch Column
        try:
            conn.execute('SELECT is_published FROM articles LIMIT 1')
        except sqlite3.OperationalError:
            logger.info("RUNNING DISASTER RECOVERY: Adding 'is_published' column...")
            conn.execute('ALTER TABLE articles ADD COLUMN is_published INTEGER DEFAULT 1')

        # 2. Admins Table
        try:
            conn.execute('CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT, created_at TEXT)')

            if not conn.execute('SELECT id FROM admins LIMIT 1').fetchone():
                logger.info("MIGRATION: Moving ENV Admin to Database...")
                env_user = os.getenv('ADMIN_USERNAME')
                env_pass = os.getenv('ADMIN_PASSWORD')
                if not env_user or not env_pass:
                    logger.critical("⚠️ ADMIN_USERNAME / ADMIN_PASSWORD not set! Cannot create admin.")
                    raise RuntimeError("Missing ADMIN_USERNAME or ADMIN_PASSWORD environment variables.")
                p_hash = generate_password_hash(env_pass)
                conn.execute('INSERT INTO admins (username, password_hash, created_at) VALUES (?, ?, ?)',
                             (env_user, p_hash, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit()
                logger.info("MIGRATION: Admin migrated successfully!")

        except sqlite3.Error as e:
            logger.error("Admin migration error: %s", e)

        # 3. Analytics Columns
        try:
            conn.execute('SELECT views FROM articles LIMIT 1')
        except sqlite3.OperationalError:
            logger.info("MIGRATION: Adding 'views' column...")
            conn.execute('ALTER TABLE articles ADD COLUMN views INTEGER DEFAULT 0')

        try:
            conn.execute('SELECT audio_plays FROM articles LIMIT 1')
        except sqlite3.OperationalError:
            logger.info("MIGRATION: Adding 'audio_plays' column...")
            conn.execute('ALTER TABLE articles ADD COLUMN audio_plays INTEGER DEFAULT 0')

        try:
            conn.execute('SELECT verified_views FROM articles LIMIT 1')
        except sqlite3.OperationalError:
            logger.info("MIGRATION: Adding 'verified_views' column...")
            conn.execute('ALTER TABLE articles ADD COLUMN verified_views INTEGER DEFAULT 0')

        try:
            conn.execute('SELECT social_image FROM articles LIMIT 1')
        except sqlite3.OperationalError:
            logger.info("MIGRATION: Adding 'social_image' column...")
            conn.execute('ALTER TABLE articles ADD COLUMN social_image TEXT')

        # 3b. View events for GA-comparable server-side analytics
        conn.execute('''CREATE TABLE IF NOT EXISTS article_view_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL,
            visitor_hash TEXT NOT NULL,
            ip_hash TEXT,
            user_agent TEXT,
            path TEXT,
            is_bot INTEGER DEFAULT 0,
            counted_verified INTEGER DEFAULT 0,
            viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_article_view_events_article_visitor_time ON article_view_events(article_id, visitor_hash, viewed_at)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_article_view_events_viewed_at ON article_view_events(viewed_at)')

        # 3c. Audio play events for anti-abuse dedupe.
        conn.execute('''CREATE TABLE IF NOT EXISTS audio_play_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL,
            visitor_hash TEXT NOT NULL,
            ip_hash TEXT,
            user_agent TEXT,
            path TEXT,
            is_bot INTEGER DEFAULT 0,
            counted_play INTEGER DEFAULT 0,
            played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_audio_play_events_article_visitor_time ON audio_play_events(article_id, visitor_hash, played_at)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_audio_play_events_played_at ON audio_play_events(played_at)')

        # 4. Carousel Slots Table (Manual editorial pinning)
        conn.execute('''CREATE TABLE IF NOT EXISTS carousel_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL UNIQUE,
            position INTEGER NOT NULL DEFAULT 0,
            pinned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            pinned_by TEXT,
            FOREIGN KEY (article_id) REFERENCES articles(id)
        )''')

        # 5. Google Indexing API audit trail
        from services.indexing_audit import ensure_indexing_notifications_table
        ensure_indexing_notifications_table(conn)

        conn.commit()
    except Exception as e:
        logger.error("Migration failed: %s", e)
    finally:
        if conn:
            conn.close()


init_db_migrations()


# --- Register Template Filters ---
register_filters(app)


# --- Authentication Setup ---
from routes.auth import auth_bp, init_login_manager
init_login_manager(app)


# --- Flask-Admin Dashboard ---
class SecureModelView(BaseModelView):
    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login', next=request.url))


class ArticleModelView(SecureModelView):
    pass


class MyAdminIndexView(AdminIndexView):
    @expose('/')
    def index(self):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login', next=request.url))

        page = request.args.get('page', 1, type=int)
        per_page = 50
        offset = (page - 1) * per_page

        date_filter = request.args.get('date', type=str)
        search_query = request.args.get('q', '', type=str)
        sort_by = request.args.get('sort', 'date')       # date | views | verified | score
        sort_dir = request.args.get('dir', 'desc')       # asc | desc
        status_filter = request.args.get('status', '')   # '' | live | offline

        # Whitelist sort columns to prevent SQL injection
        sort_column_map = {
            'date':  "replace(published_at, 'T', ' ')",
            'views': 'COALESCE(views, 0)',
            'verified': 'COALESCE(verified_views, 0)',
            'score': 'COALESCE(importance_score, 0)',
        }
        order_col = sort_column_map.get(sort_by, sort_column_map['date'])
        order_dir = 'ASC' if sort_dir == 'asc' else 'DESC'

        conn = get_db_connection()

        conditions = []
        params = []

        if date_filter:
            conditions.append('date(published_at) = ?')
            params.append(date_filter)

        if search_query:
            conditions.append('(title LIKE ? OR original_author LIKE ?)')
            params.append(f'%{search_query}%')
            params.append(f'%{search_query}%')

        if status_filter == 'live':
            conditions.append('is_published = 1')
        elif status_filter == 'offline':
            conditions.append('(is_published = 0 OR is_published IS NULL)')

        where_clause = ' WHERE ' + ' AND '.join(conditions) if conditions else ''

        query = (
            "SELECT id, title, category, published_at, slug, importance_score, is_published, views, verified_views, audio_plays, source, source_url "
            f"FROM articles{where_clause} "
            f"ORDER BY {order_col} {order_dir} LIMIT ? OFFSET ?"
        )
        query_params = params + [per_page, offset]

        articles = conn.execute(query, query_params).fetchall()

        total_query = f'SELECT COUNT(*) FROM articles{where_clause}'
        total_query_result = conn.execute(total_query, params).fetchone()
        total = total_query_result[0] if total_query_result else 0
        has_next = (offset + per_page) < total

        conn.close()

        # Fetch leads count for Target Acquisition widget
        try:
            conn2 = get_db_connection()
            leads = conn2.execute('SELECT id FROM leads WHERE status != ? ORDER BY found_at DESC', ('rejected',)).fetchall()
            conn2.close()
        except Exception as e:
            app.logger.error("Failed to fetch leads for dashboard: %s", e)
            leads = []

        # Fetch carousel pinned article IDs
        try:
            conn3 = get_db_connection()
            pinned_rows = conn3.execute('''
                SELECT article_id FROM carousel_slots
                WHERE expires_at IS NULL OR expires_at > datetime('now')
            ''').fetchall()
            carousel_pinned_ids = [r['article_id'] for r in pinned_rows]
            conn3.close()
        except Exception:
            carousel_pinned_ids = []

        return self.render(
            'admin/index.html',
            articles=articles, page=page, has_next=has_next,
            date_filter=date_filter, q=search_query, total=total,
            leads=leads, carousel_pinned_ids=carousel_pinned_ids,
            emergency_mode=is_emergency_mode(),
            sort_by=sort_by, sort_dir=sort_dir, status_filter=status_filter,
        )



admin = Admin(app, name='DailyAIWire Admin', index_view=MyAdminIndexView())


# --- Context Processor ---
def get_csp_nonce():
    nonce = getattr(g, 'csp_nonce', None)
    if nonce is None:
        nonce = secrets.token_urlsafe(16)
        g.csp_nonce = nonce
    return nonce


@app.context_processor
def inject_config():
    emre_data = {
        'name': 'Ali Emre Ozen',
        'title': 'VP, Head of Ad Operations & Analytics',
        'bio': "With 12 years in the programmatic space, I've managed complex campaigns across the US, UK, and Europe for both major agencies and global brands. Having mastered the full supply and demand ecosystem, I'm now focused on integrating AI and automation to streamline the heavy lifting of digital advertising.",
        'linkedin': 'https://www.linkedin.com/in/emreozen/',
        'image': '/static/emre.jpg'
    }

    cagri_data = {
        'name': 'Cagri Eralp',
        'title': 'Strategic Advisor — Business & Technology',
        'bio': "20 years building and scaling tech-driven businesses across Eurasia and the Middle East. Operating at the intersection of strategy and execution, taking products from zero to revenue. Background spans digital transformation, industrial engineering, automated retail, and large-scale commercial operations.",
        'linkedin': 'https://www.linkedin.com/in/cagrieralp/',
        'image': '/static/cagri.jpg'
    }

    try:
        conn = get_db_connection()
        conn.execute('CREATE TABLE IF NOT EXISTS author_config (id INTEGER PRIMARY KEY, name TEXT, title TEXT, bio TEXT, linkedin TEXT, image TEXT)')
        row = conn.execute('SELECT * FROM author_config LIMIT 1').fetchone()
        conn.close()

        if row:
            db_data = dict(row)
            if db_data.get('name'): emre_data['name'] = db_data['name']
            if db_data.get('title'): emre_data['title'] = db_data['title']
            if db_data.get('bio'): emre_data['bio'] = db_data['bio']
            if db_data.get('linkedin'): emre_data['linkedin'] = db_data['linkedin']
            if db_data.get('image'): emre_data['image'] = db_data['image']
    except Exception:
        pass

    current_img = emre_data.get('image', '')
    if current_img.startswith('/'):
        if current_img.startswith('/static/'):
            rel_path = current_img[8:]
            abs_path = os.path.join(app.static_folder, rel_path)

            if not os.path.exists(abs_path):
                fallback_local = os.path.join(app.static_folder, 'emre.jpg')
                if os.path.exists(fallback_local):
                    emre_data['image'] = '/static/emre.jpg'
                else:
                    emre_data['image'] = "https://ui-avatars.com/api/?name=Emre+Ozen&size=512&background=2563eb&color=fff"

    # Cagri image fallback
    cagri_img = cagri_data.get('image', '')
    if cagri_img.startswith('/static/'):
        cagri_abs = os.path.join(app.static_folder, cagri_img[8:])
        if not os.path.exists(cagri_abs):
            cagri_data['image'] = "https://ui-avatars.com/api/?name=Cagri+Eralp&size=512&background=2563eb&color=fff"

    def get_cat_color(c):
        colors = {
            'Business': 'bg-indigo-600',
            'Technology': 'bg-emerald-600',
            'Policy': 'bg-red-600',
            'Science': 'bg-teal-600',
            'Tools': 'bg-amber-600',
            'Security': 'bg-violet-600',
            'Finance': 'bg-green-600',
            'Health': 'bg-rose-600',
            'Energy': 'bg-yellow-600',
            'LLMs': 'bg-purple-600',
            'Robotics': 'bg-cyan-600',
            'Society': 'bg-pink-600',
            'AI Agents': 'bg-orange-600'
        }
        return colors.get(c, 'bg-blue-600')

    return {
        'current_year': datetime.now().year,
        'config_ga_id': os.getenv('GA_MEASUREMENT_ID'),
        'config_web3forms_key': os.getenv('WEB3FORMS_ACCESS_KEY'),
        'csp_nonce': get_csp_nonce,
        'subscribe_form_loaded_at': int(datetime.utcnow().timestamp()),
        'q': request.args.get('q', '') if has_request_context() else '',
        'emre': emre_data,
        'cagri': cagri_data,
        'category_color': get_cat_color
    }


# --- Security Headers ---
@app.after_request
def add_security_headers(response):
    nonce = get_csp_nonce()
    csp = (
        "default-src 'self' https: data: blob:; "
        "base-uri 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "script-src 'self' https://unpkg.com https://*.googletagmanager.com https://*.google.com https://*.googleapis.com https://*.google-analytics.com https://*.cloudflareinsights.com; "
        f"script-src-elem 'self' 'nonce-{nonce}' https://unpkg.com https://*.googletagmanager.com https://*.google.com https://*.googleapis.com https://*.google-analytics.com https://*.cloudflareinsights.com; "
        "script-src-attr 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' https: data: blob:; "
        "media-src 'self' https: data: blob:; "
        "connect-src 'self' https: https://*.cloudflareinsights.com; "
        "frame-src 'self' https: https://open.spotify.com; "
        "form-action 'self' https://api.web3forms.com;"
    )
    response.headers['Content-Security-Policy'] = csp
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    # Fixes Lighthouse Best Practices COOP warning
    response.headers['Cross-Origin-Opener-Policy'] = 'same-origin-allow-popups'
    return response



@app.after_request
def add_header(r):
    # Skip if route handler already set Cache-Control explicitly
    if 'Cache-Control' in r.headers:
        if (
            'text/html' in (r.content_type or '')
            and request.args
            and 'X-Robots-Tag' not in r.headers
        ):
            r.headers['X-Robots-Tag'] = 'noindex, follow'
        return r
    ct = r.content_type or ''
    if 'text/html' in ct:
        r.headers['Cache-Control'] = 'public, max-age=60, s-maxage=300'
        if request.args and 'X-Robots-Tag' not in r.headers:
            # Prevent indexing of query-string variants such as UTM/debug URLs.
            r.headers['X-Robots-Tag'] = 'noindex, follow'
    elif any(t in ct for t in ['image/', 'font/', 'css', 'javascript', 'audio/']):
        r.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    else:
        r.headers['Cache-Control'] = 'public, max-age=3600'
    return r


# --- Register Blueprints ---
from routes.public import public_bp
from routes.api import api_bp
from routes.seo import seo_bp
from routes.lab import lab_bp
from routes.admin_core import admin_core_bp
from routes.admin_content import admin_content_bp
from routes.admin_ops import admin_ops_bp
from routes.admin_carousel import admin_carousel_bp
from routes.admin_seo import admin_seo_bp
from routes.admin_indexing import admin_indexing_bp
from routes.admin_emergency import admin_emergency_bp, is_emergency_mode
from routes.signal import signal_bp
from routes.podcast import podcast_bp

app.register_blueprint(auth_bp)
app.register_blueprint(public_bp)
app.register_blueprint(api_bp)
app.register_blueprint(seo_bp)
app.register_blueprint(lab_bp)
app.register_blueprint(admin_core_bp)
app.register_blueprint(admin_content_bp)
app.register_blueprint(admin_ops_bp)
app.register_blueprint(admin_carousel_bp)
app.register_blueprint(admin_seo_bp)
app.register_blueprint(admin_indexing_bp)
app.register_blueprint(admin_emergency_bp)
app.register_blueprint(signal_bp)
app.register_blueprint(podcast_bp)


# --- Error Handlers ---
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(e):
    app.logger.error("500 Internal Server Error: %s", e)
    return render_template('500.html'), 500


@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403


@app.errorhandler(429)
def too_many_requests(e):
    return render_template('429.html'), 429


# --- Emergency Override Middleware ---
@app.before_request
def check_emergency_mode():
    """If emergency mode is active, serve maintenance page for all public routes."""
    # Allow admin routes, static files, and login through
    safe_prefixes = ('/admin', '/login', '/logout', '/static')
    if request.path.startswith(safe_prefixes):
        return None

    if is_emergency_mode():
        from flask import render_template, make_response
        resp = make_response(render_template('maintenance.html'), 503)
        resp.headers['Retry-After'] = '3600'
        return resp


# --- Health Check (F-23) ---
@app.route('/health')
def health_check():
    """Uptime probe with active database verification."""
    try:
        conn = get_db_connection()
        conn.execute('SELECT 1').fetchone()
        conn.close()
        return {"status": "ok", "database": "connected", "timestamp": datetime.utcnow().isoformat()}, 200
    except Exception as e:
        app.logger.error("Healthcheck DB failure: %s", e)
        return {"status": "error", "message": "Database connection failed"}, 503


if __name__ == '__main__':
    app.run(debug=False, port=8000)
