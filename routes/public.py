"""
Public routes — DailyAIWire.news
Homepage, article pages, static pages, and subscription.
"""
import json
import math
import sqlite3
import hashlib
import re
import secrets
import time
from datetime import datetime, timedelta

from flask import Blueprint, render_template, abort, request, redirect, url_for, flash, make_response, send_from_directory
from flask_login import current_user

from extensions import limiter
from db import get_db_connection
from services.editorials import get_db_blog_posts
import logging

logger = logging.getLogger('public')

public_bp = Blueprint('public', __name__)

VIEW_DEDUPE_MINUTES = 30
SUBSCRIBE_MIN_SECONDS = 4
MAX_EMAIL_LENGTH = 254
BOT_UA_PATTERN = re.compile(
    r"(bot|spider|crawl|slurp|headless|facebookexternalhit|whatsapp|telegrambot|"
    r"linkedinbot|python-requests|curl|wget|uptimerobot|datadog|pingdom)",
    re.IGNORECASE,
)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@public_bp.route('/social-image/<path:filename>')
def social_image(filename):
    if "/" in filename or "\\" in filename:
        abort(404)
    response = send_from_directory(
        "static/img/social",
        filename,
        max_age=31536000,
    )
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    response.headers.pop("X-Robots-Tag", None)
    return response


def _hash_value(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _extract_client_ip() -> str:
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        first = forwarded.split(',')[0].strip()
        if first:
            return first
    real_ip = (request.headers.get('X-Real-IP') or '').strip()
    if real_ip:
        return real_ip
    remote = (request.remote_addr or '').strip()
    return remote or 'unknown'


def _is_likely_bot(user_agent: str) -> bool:
    if not user_agent:
        return True
    if BOT_UA_PATTERN.search(user_agent):
        return True
    purpose = (request.headers.get('Purpose') or request.headers.get('Sec-Purpose') or '').lower()
    return 'prefetch' in purpose


def _visitor_hash() -> str:
    client_ip = _extract_client_ip()
    user_agent = (request.headers.get('User-Agent') or '').strip().lower()
    accept_lang = (request.headers.get('Accept-Language') or '').strip().lower()
    return _hash_value(f"{client_ip}|{user_agent}|{accept_lang}")


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _is_valid_email(email: str) -> bool:
    return bool(email and len(email) <= MAX_EMAIL_LENGTH and EMAIL_PATTERN.match(email))


def _sanitize_form_text(value: str, max_len: int = 500) -> str:
    return (value or "").strip()[:max_len]


def _ensure_subscribers_schema(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            status TEXT DEFAULT 'ACTIVE',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(subscribers)").fetchall()}
    migrations = {
        "signup_ip_hash": "ALTER TABLE subscribers ADD COLUMN signup_ip_hash TEXT",
        "signup_user_agent": "ALTER TABLE subscribers ADD COLUMN signup_user_agent TEXT",
        "signup_referrer": "ALTER TABLE subscribers ADD COLUMN signup_referrer TEXT",
        "signup_source_path": "ALTER TABLE subscribers ADD COLUMN signup_source_path TEXT",
        "signup_accept_language": "ALTER TABLE subscribers ADD COLUMN signup_accept_language TEXT",
        "signup_fingerprint_hash": "ALTER TABLE subscribers ADD COLUMN signup_fingerprint_hash TEXT",
        "confirmation_token_hash": "ALTER TABLE subscribers ADD COLUMN confirmation_token_hash TEXT",
        "confirmed_at": "ALTER TABLE subscribers ADD COLUMN confirmed_at TIMESTAMP",
    }
    for column, sql in migrations.items():
        if column not in existing:
            conn.execute(sql)


def _record_subscriber_event(conn, *, email: str, event_type: str, reason: str):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS subscriber_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_hash TEXT,
            event_type TEXT NOT NULL,
            reason TEXT,
            ip_hash TEXT,
            user_agent TEXT,
            referrer TEXT,
            source_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    user_agent = _sanitize_form_text(request.headers.get("User-Agent", ""), 500)
    referrer = _sanitize_form_text(request.referrer or request.headers.get("Referer", ""), 500)
    source_path = _sanitize_form_text(request.form.get("subscribe_source_path", ""), 500)
    conn.execute(
        '''
        INSERT INTO subscriber_events (
            email_hash, event_type, reason, ip_hash, user_agent, referrer, source_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            _hash_value(_normalize_email(email)) if email else None,
            event_type,
            reason,
            _hash_value(_extract_client_ip()),
            user_agent,
            referrer,
            source_path,
        ),
    )


def _is_subscribe_submission_suspicious():
    if request.form.get("newsletter_website"):
        return True, "honeypot"

    raw_loaded_at = request.form.get("form_loaded_at", "")
    try:
        loaded_at = float(raw_loaded_at)
    except (TypeError, ValueError):
        return True, "missing_form_loaded_at"

    if time.time() - loaded_at < SUBSCRIBE_MIN_SECONDS:
        return True, "submitted_too_fast"

    return False, ""


def _confirmation_token_hash(token: str) -> str:
    return _hash_value(token)


def _create_confirmation_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, _confirmation_token_hash(token)


def _fetch_editorials():
    """Fetch published editorials and map them to article-like dicts."""
    rows = get_db_blog_posts(published_only=True)[:10]
    editorials = []
    for r in rows:
        editorials.append({
            'id': f"editorial_{r['id']}",
            'title': r['title'],
            'slug': r['slug'],
            'category': 'Editorial',
            'source': r['author_name'] or 'DailyAIWire',
            'author_name': r['author_name'] or 'DailyAIWire',
            'author_title': r.get('author_title', ''),
            'gist': r['subtitle'] or r.get('meta_description', '') or '',
            'why_it_matters': r['subtitle'] or '',
            'bull_case': None,
            'bear_case': None,
            'eli5': None,
            'image': '/static/fallbacks/editorial_0.jpg',
            'published_at': r['published_at'] or '',
            'importance_score': 80,
            'compass_score': 0.9,
            'key_details': [],
            'design_tokens': {},
            'is_editorial': True,
            'is_published': 1,
            'audio_male': None,
            'audio_female': None,
        })
    return editorials


@public_bp.route('/')
def index():
    conn = get_db_connection()

    # Lazy migration: ensure compass_score column exists (added in Phase 0)
    try:
        conn.execute("SELECT compass_score FROM articles LIMIT 1")
    except Exception:
        conn.execute("ALTER TABLE articles ADD COLUMN compass_score REAL DEFAULT 0.7")
        conn.commit()

    cats = conn.execute('''
        SELECT category, COUNT(*) as cnt FROM articles
        WHERE category IS NOT NULL AND is_published = 1
        GROUP BY category HAVING cnt > 0
        LIMIT 12
    ''').fetchall()
    categories = sorted([c['category'] for c in cats])

    page = request.args.get('page', 1, type=int)
    cat_arg = request.args.get('category')
    q = request.args.get('q', '')

    ITEMS_PER_PAGE = 9
    # Homepage page 1 has a newsletter card injected, so 8 + 1 = 9 = 3 clean rows
    HOMEPAGE_GRID_CARD_SLOTS = 8

    search_mode = 'none'
    homepage_grid_article_slots = HOMEPAGE_GRID_CARD_SLOTS

    if q:
        # --- Phase 1: Semantic Search (Qdrant) with keyword fallback ---
        semantic_results = []
        try:
            from embedding_service import search_articles
            semantic_results = search_articles(q, limit=20)
        except (ImportError, Exception) as e:
            logger.warning("Semantic search unavailable, falling back to keyword: %s", e)

        if semantic_results:
            search_mode = 'semantic'
            ranked_ids = [r['id'] for r in semantic_results]
            score_lookup = {r['id']: r['score'] for r in semantic_results}

            placeholders = ','.join('?' * len(ranked_ids))
            rows = conn.execute(
                f'SELECT * FROM articles WHERE id IN ({placeholders}) AND is_published = 1',
                ranked_ids
            ).fetchall()

            row_map = {dict(r)['id']: r for r in rows}
            grid = [row_map[aid] for aid in ranked_ids if aid in row_map]
            total_arts = len(grid)
            carousel = []
        else:
            search_mode = 'keyword'
            query = f"%{q}%"
            offset = (page - 1) * ITEMS_PER_PAGE
            total_arts = conn.execute('SELECT COUNT(*) FROM articles WHERE (title LIKE ? OR gist LIKE ? OR deep_analysis LIKE ?) AND is_published = 1', (query, query, query)).fetchone()[0]
            grid = conn.execute('SELECT * FROM articles WHERE (title LIKE ? OR gist LIKE ? OR deep_analysis LIKE ?) AND is_published = 1 ORDER BY published_at DESC, id DESC LIMIT ? OFFSET ?', (query, query, query, ITEMS_PER_PAGE, offset)).fetchall()
            carousel = []
    elif cat_arg:
        if cat_arg == 'Editorial':
            # Special handling: editorial category filter shows only editorials
            editorials = _fetch_editorials()
            offset = (page - 1) * ITEMS_PER_PAGE
            total_arts = len(editorials)
            grid = editorials[offset:offset + ITEMS_PER_PAGE]
            carousel = []
        else:
            offset = (page - 1) * ITEMS_PER_PAGE
            query_base = 'FROM articles WHERE category = ? AND is_published = 1 AND replace(published_at, "T", " ") <= datetime("now")'
            query_params = (cat_arg,)

            offset = (page - 1) * ITEMS_PER_PAGE
            total_arts_count = conn.execute(f'SELECT COUNT(*) {query_base}', query_params).fetchone()[0]
            total_arts = total_arts_count
            grid = conn.execute(f'SELECT * {query_base} ORDER BY published_at DESC, id DESC LIMIT ? OFFSET ?', query_params + (ITEMS_PER_PAGE, offset)).fetchall()
            carousel = []
    else:
        published_condition = 'is_published = 1 AND replace(published_at, "T", " ") <= datetime("now")'

        # Fetch editorials to merge into the feed
        editorials = _fetch_editorials()
        homepage_grid_editorials = editorials[1:3]
        homepage_grid_article_slots = max(
            0,
            HOMEPAGE_GRID_CARD_SLOTS - len(homepage_grid_editorials),
        )

        if page == 1:
            # --- Carousel: Pinned-first hybrid logic ---
            # 1. Manually pinned articles (not expired)
            try:
                pinned = conn.execute('''
                    SELECT a.* FROM carousel_slots cs
                    JOIN articles a ON cs.article_id = a.id
                    WHERE a.is_published = 1
                      AND (cs.expires_at IS NULL OR cs.expires_at > datetime('now'))
                    ORDER BY cs.position ASC
                ''').fetchall()
            except Exception:
                pinned = []

            pinned_ids = [dict(r)['id'] for r in pinned]

            # 2. Fill remaining carousel slots with auto-selected articles
            remaining = 10 - len(pinned_ids)
            if remaining > 0:
                if pinned_ids:
                    exclude_placeholders = ','.join('?' * len(pinned_ids))
                    auto = conn.execute(f'''
                        SELECT * FROM articles
                        WHERE {published_condition} AND id NOT IN ({exclude_placeholders})
                        ORDER BY DATE(published_at) DESC,
                                 (importance_score * COALESCE(compass_score, 0.7)) DESC, id DESC
                        LIMIT ?
                    ''', pinned_ids + [remaining]).fetchall()
                else:
                    auto = conn.execute(f'''
                        SELECT * FROM articles
                        WHERE {published_condition}
                        ORDER BY DATE(published_at) DESC,
                                 (importance_score * COALESCE(compass_score, 0.7)) DESC, id DESC
                        LIMIT ?
                    ''', (remaining,)).fetchall()
            else:
                auto = []

            carousel = list(pinned) + list(auto)

            # Inject the most recent editorial into carousel (position 3) if fresh (<7 days)
            if editorials:
                ed = editorials[0]
                ed_date = ed.get('published_at', '')
                try:
                    ed_dt = datetime.fromisoformat(ed_date.replace(' ', 'T'))
                    if datetime.now() - ed_dt < timedelta(days=1):
                        carousel.insert(min(2, len(carousel)), ed)
                except (ValueError, TypeError):
                    pass  # Skip if date parsing fails

            # Grid: everything after carousel
            all_carousel_ids = [dict(r)['id'] for r in carousel if not isinstance(dict(r).get('id', ''), str)]
            if all_carousel_ids:
                grid_exclude = ','.join('?' * len(all_carousel_ids))
                grid = conn.execute(f'''
                    SELECT * FROM articles
                    WHERE {published_condition} AND id NOT IN ({grid_exclude})
                    ORDER BY DATE(published_at) DESC,
                             (importance_score * COALESCE(compass_score, 0.7)) DESC, id DESC
                    LIMIT ?
                ''', all_carousel_ids + [homepage_grid_article_slots]).fetchall()
            else:
                grid = conn.execute(
                    f'''
                    SELECT * FROM articles
                    WHERE {published_condition}
                    ORDER BY DATE(published_at) DESC,
                             (importance_score * COALESCE(compass_score, 0.7)) DESC, id DESC
                    LIMIT ? OFFSET 10
                    ''',
                    (homepage_grid_article_slots,),
                ).fetchall()

            # Merge remaining editorials into the fixed 8-card homepage budget.
            grid = list(grid)
            insertion_index = min(3, len(grid))
            grid[insertion_index:insertion_index] = homepage_grid_editorials
            grid = grid[:HOMEPAGE_GRID_CARD_SLOTS]

            total_arts_count = conn.execute(f'SELECT COUNT(*) FROM articles WHERE {published_condition}').fetchone()[0]
            total_arts = max(0, total_arts_count - len(carousel))
        else:
            db_offset = 10 + homepage_grid_article_slots + ((page - 2) * ITEMS_PER_PAGE)
            grid = conn.execute(
                '''
                SELECT * FROM articles
                WHERE is_published = 1
                ORDER BY DATE(published_at) DESC,
                         (importance_score * COALESCE(compass_score, 0.7)) DESC, id DESC
                LIMIT ? OFFSET ?
                ''',
                (ITEMS_PER_PAGE, db_offset),
            ).fetchall()
            carousel = []
            total_arts_count = conn.execute('SELECT COUNT(*) FROM articles WHERE is_published = 1').fetchone()[0]
            total_arts = max(0, total_arts_count - 10)

    # Phase 4: Trend Intelligence
    trends = None
    if not q:
        try:
            from trend_engine import get_trend_snapshot
            trends = get_trend_snapshot(conn)
        except Exception as trend_err:
            logger.warning("Trend engine error (non-blocking): %s", trend_err)

    conn.close()

    if not q and not cat_arg:
        if total_arts <= homepage_grid_article_slots:
            total_pages = 1
        else:
            remaining_pages = math.ceil(
                (total_arts - homepage_grid_article_slots) / ITEMS_PER_PAGE
            )
            total_pages = 1 + remaining_pages
    else:
        total_pages = math.ceil(total_arts / ITEMS_PER_PAGE) if total_arts > 0 else 1

    processed_grid = []
    for a in grid:
        d = dict(a) if not isinstance(a, dict) else a
        if not d.get('is_editorial'):
            try: d['key_details'] = json.loads(d['key_details'])
            except (ValueError, json.JSONDecodeError, TypeError, KeyError): d['key_details'] = []
            try: d['design_tokens'] = json.loads(d.get('design_tokens') or '{}')
            except (ValueError, json.JSONDecodeError, TypeError, KeyError): d['design_tokens'] = {}
        processed_grid.append(d)

    processed_carousel = []
    for a in carousel:
        d = dict(a) if not isinstance(a, dict) else a
        if not d.get('is_editorial'):
            try: d['key_details'] = json.loads(d['key_details'])
            except (ValueError, json.JSONDecodeError, TypeError, KeyError): d['key_details'] = []
            try: d['design_tokens'] = json.loads(d.get('design_tokens') or '{}')
            except (ValueError, json.JSONDecodeError, TypeError, KeyError): d['design_tokens'] = {}
        processed_carousel.append(d)

    # Add 'Editorial' to categories list if editorials exist
    if 'Editorial' not in categories:
        try:
            ed_count = conn if not isinstance(conn, type(None)) else get_db_connection()
        except Exception:
            pass
        categories = sorted(set(categories + ['Editorial']))

    response = make_response(
        render_template(
            'index.html',
            articles=processed_grid,
            carousel_articles=processed_carousel,
            page=page,
            total_pages=total_pages,
            categories=categories,
            category=cat_arg,
            q=q,
            now_utc=datetime.utcnow(),
            search_mode=search_mode,
            trends=trends,
        )
    )

    host = request.host.split(':')[0].lower()
    if host in {'127.0.0.1', 'localhost'}:
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

    return response


@public_bp.route('/how-it-works')
def how_it_works():
    return render_template('how_it_works.html')


@public_bp.route('/article/<slug>')
def article(slug):
    conn = get_db_connection()
    art = conn.execute('SELECT * FROM articles WHERE slug = ?', (slug,)).fetchone()
    conn.close()
    if not art:
        # 410 Gone — tells Google to permanently drop this URL from index
        # (faster than 404, which Google retries for weeks)
        abort(410)
    d = dict(art)
    try: d['key_details'] = json.loads(art['key_details'])
    except (ValueError, json.JSONDecodeError, TypeError, KeyError): d['key_details'] = []

    # GenUI Token Parsing
    try: d['design_tokens'] = json.loads(art['design_tokens'])
    except (ValueError, json.JSONDecodeError, TypeError, KeyError): d['design_tokens'] = {}

    # DeepDiagram: Extract mermaid diagram from full AI response
    try:
        full = json.loads(art['full_json'] or '{}')
        d['mermaid_diagram'] = full.get('mermaid_diagram')
    except (ValueError, json.JSONDecodeError, TypeError, KeyError):
        d['mermaid_diagram'] = None

    # SEO Internal Linking: 6 Related Articles (3 same-category + 3 cross-category)
    conn = get_db_connection()
    same_cat = conn.execute('''
        SELECT title, slug, image, category, published_at, gist
        FROM articles
        WHERE category = ? AND id != ? AND is_published = 1
        ORDER BY published_at DESC LIMIT 3
    ''', (d['category'], d['id'])).fetchall()

    same_cat_slugs = [dict(r)['slug'] for r in same_cat]
    exclude_ids = [d['id']]

    cross_cat = conn.execute('''
        SELECT title, slug, image, category, published_at, gist
        FROM articles
        WHERE category != ? AND id != ? AND is_published = 1
        ORDER BY published_at DESC LIMIT 3
    ''', (d['category'], d['id'])).fetchall()
    conn.close()

    related_articles = []
    for r in list(same_cat) + list(cross_cat):
        rd = dict(r)
        if rd['image'] and not rd['image'].startswith('http') and not rd['image'].startswith('/'):
            rd['image'] = '/' + rd['image']
        related_articles.append(rd)

    # Analytics: track both raw hits and GA-comparable verified views.
    conn = None
    try:
        conn = get_db_connection()
        conn.execute('UPDATE articles SET views = COALESCE(views, 0) + 1 WHERE id = ?', (d['id'],))

        # Skip verified counting for non-GET fallbacks.
        if request.method == 'GET':
            user_agent = (request.headers.get('User-Agent') or '')[:512]
            is_bot = 1 if _is_likely_bot(user_agent) else 0
            visitor_hash = _visitor_hash()
            ip_hash = _hash_value(_extract_client_ip())
            counted_verified = 0

            if not is_bot:
                window_expr = f'-{VIEW_DEDUPE_MINUTES} minutes'
                recent = conn.execute(
                    '''
                    SELECT 1
                    FROM article_view_events
                    WHERE article_id = ?
                      AND visitor_hash = ?
                      AND viewed_at >= datetime('now', ?)
                    LIMIT 1
                    ''',
                    (d['id'], visitor_hash, window_expr)
                ).fetchone()
                if not recent:
                    conn.execute(
                        'UPDATE articles SET verified_views = COALESCE(verified_views, 0) + 1 WHERE id = ?',
                        (d['id'],)
                    )
                    counted_verified = 1

            conn.execute(
                '''
                INSERT INTO article_view_events (
                    article_id, visitor_hash, ip_hash, user_agent, path, is_bot, counted_verified
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                (d['id'], visitor_hash, ip_hash, user_agent, request.path, is_bot, counted_verified)
            )

        conn.commit()
    except Exception as e:
        logger.error("Analytics Error: %s", e)
    finally:
        if conn:
            conn.close()

    return render_template('article.html', article=d, related_articles=related_articles)


@public_bp.route('/about')
def about():
    return render_template('about.html')


@public_bp.route('/contact')
def contact():
    return render_template('contact.html')


@public_bp.route('/privacy')
def privacy():
    return render_template('privacy.html')


@public_bp.route('/impressum')
def impressum():
    return render_template('impressum.html')


@public_bp.route('/thank-you')
def thank_you_page():
    return render_template('thank_you.html')


@public_bp.route('/subscribe', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def subscribe():
    import sqlite3
    from newsletter_sender import send_confirmation_email

    if request.method == 'POST':
        email = _normalize_email(request.form.get('email'))
        conn = get_db_connection()
        try:
            _ensure_subscribers_schema(conn)

            suspicious, reason = _is_subscribe_submission_suspicious()
            if suspicious:
                _record_subscriber_event(conn, email=email, event_type="blocked", reason=reason)
                conn.commit()
                logger.warning("Blocked suspicious subscribe submission: %s", reason)
                return redirect(url_for('public.thank_you_page', status='review'))

            if not _is_valid_email(email):
                _record_subscriber_event(conn, email=email, event_type="blocked", reason="invalid_email")
                conn.commit()
                return redirect(url_for('public.thank_you_page', status='review'))

            existing = conn.execute(
                'SELECT id FROM subscribers WHERE lower(email) = lower(?) LIMIT 1',
                (email,),
            ).fetchone()
            if existing:
                flash('You are already subscribed. Welcome back!')
                return redirect(url_for('public.thank_you_page', status='existing'))

            user_agent = _sanitize_form_text(request.headers.get("User-Agent", ""), 500)
            referrer = _sanitize_form_text(request.referrer or request.headers.get("Referer", ""), 500)
            source_path = _sanitize_form_text(request.form.get("subscribe_source_path", ""), 500)
            accept_language = _sanitize_form_text(request.headers.get("Accept-Language", ""), 200)
            ip_hash = _hash_value(_extract_client_ip())
            fingerprint_hash = _hash_value(
                f"{_extract_client_ip()}|{user_agent.lower()}|{accept_language.lower()}"
            )
            confirmation_token, confirmation_hash = _create_confirmation_token()

            conn.execute(
                '''
                INSERT INTO subscribers (
                    email, status, signup_ip_hash, signup_user_agent, signup_referrer,
                    signup_source_path, signup_accept_language, signup_fingerprint_hash,
                    confirmation_token_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    email,
                    "PENDING",
                    ip_hash,
                    user_agent,
                    referrer,
                    source_path,
                    accept_language,
                    fingerprint_hash,
                    confirmation_hash,
                ),
            )
            _record_subscriber_event(conn, email=email, event_type="created", reason="pending_confirmation")
            conn.commit()

            try:
                confirmation_url = url_for(
                    "public.confirm_subscription",
                    token=confirmation_token,
                    _external=True,
                )
                send_confirmation_email(email, confirmation_url)
            except Exception as e:
                logger.error("Failed to send confirmation email: %s", e)

            return redirect(url_for('public.thank_you_page', status='pending'))
        except sqlite3.IntegrityError:
            flash('You are already subscribed. Welcome back!')
            return redirect(url_for('public.thank_you_page', status='existing'))
        finally:
            conn.close()
    return render_template('subscribe.html')


@public_bp.route('/confirm-subscription/<token>')
def confirm_subscription(token):
    token = (token or "").strip()
    if not token:
        abort(404)

    conn = get_db_connection()
    try:
        _ensure_subscribers_schema(conn)
        token_hash = _confirmation_token_hash(token)
        subscriber = conn.execute(
            '''
            SELECT id, email
            FROM subscribers
            WHERE confirmation_token_hash = ?
              AND status = 'PENDING'
            LIMIT 1
            ''',
            (token_hash,),
        ).fetchone()
        if not subscriber:
            return redirect(url_for('public.thank_you_page', status='invalid'))

        conn.execute(
            '''
            UPDATE subscribers
            SET status = 'ACTIVE',
                confirmed_at = CURRENT_TIMESTAMP,
                confirmation_token_hash = NULL
            WHERE id = ?
            ''',
            (subscriber["id"],),
        )
        _record_subscriber_event(
            conn,
            email=subscriber["email"],
            event_type="confirmed",
            reason="double_opt_in",
        )
        conn.commit()
        return redirect(url_for('public.thank_you_page', status='confirmed'))
    finally:
        conn.close()
