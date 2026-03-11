"""
Public routes — DailyAIWire.news
Homepage, article pages, static pages, and subscription.
"""
import json
import math
import sqlite3
from datetime import datetime

from flask import Blueprint, render_template, abort, request, redirect, url_for, flash, make_response
from flask_login import current_user

from db import get_db_connection

public_bp = Blueprint('public', __name__)


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

    search_mode = 'none'

    if q:
        # --- Phase 1: Semantic Search (Qdrant) with keyword fallback ---
        semantic_results = []
        try:
            from embedding_service import search_articles
            semantic_results = search_articles(q, limit=20)
        except (ImportError, Exception) as e:
            print(f"⚠️ Semantic search unavailable, falling back to keyword: {e}")

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

            # Grid: everything after carousel
            all_carousel_ids = [dict(r)['id'] for r in carousel]
            if all_carousel_ids:
                grid_exclude = ','.join('?' * len(all_carousel_ids))
                grid = conn.execute(f'''
                    SELECT * FROM articles
                    WHERE {published_condition} AND id NOT IN ({grid_exclude})
                    ORDER BY DATE(published_at) DESC,
                             (importance_score * COALESCE(compass_score, 0.7)) DESC, id DESC
                    LIMIT ?
                ''', all_carousel_ids + [ITEMS_PER_PAGE]).fetchall()
            else:
                grid = conn.execute(f'SELECT * FROM articles WHERE {published_condition} ORDER BY DATE(published_at) DESC, (importance_score * COALESCE(compass_score, 0.7)) DESC, id DESC LIMIT ? OFFSET 10', (ITEMS_PER_PAGE,)).fetchall()

            total_arts_count = conn.execute(f'SELECT COUNT(*) FROM articles WHERE {published_condition}').fetchone()[0]
            total_arts = max(0, total_arts_count - len(carousel))
        else:
            db_offset = 10 + ((page - 1) * ITEMS_PER_PAGE)
            grid = conn.execute('SELECT * FROM articles WHERE is_published = 1 ORDER BY DATE(published_at) DESC, (importance_score * COALESCE(compass_score, 0.7)) DESC, id DESC LIMIT ? OFFSET ?', (ITEMS_PER_PAGE, db_offset)).fetchall()
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
            print(f"⚠️ Trend engine error (non-blocking): {trend_err}")

    conn.close()

    total_pages = math.ceil(total_arts / ITEMS_PER_PAGE) if total_arts > 0 else 1

    processed_grid = []
    for a in grid:
        d = dict(a)
        try: d['key_details'] = json.loads(d['key_details'])
        except (ValueError, json.JSONDecodeError, TypeError, KeyError): d['key_details'] = []
        try: d['design_tokens'] = json.loads(d.get('design_tokens') or '{}')
        except (ValueError, json.JSONDecodeError, TypeError, KeyError): d['design_tokens'] = {}
        processed_grid.append(d)

    processed_carousel = []
    for a in carousel:
        d = dict(a)
        try: d['key_details'] = json.loads(d['key_details'])
        except (ValueError, json.JSONDecodeError, TypeError, KeyError): d['key_details'] = []
        try: d['design_tokens'] = json.loads(d.get('design_tokens') or '{}')
        except (ValueError, json.JSONDecodeError, TypeError, KeyError): d['design_tokens'] = {}
        processed_carousel.append(d)

    resp = make_response(render_template('index.html', articles=processed_grid, carousel_articles=processed_carousel, page=page, total_pages=total_pages, categories=categories, category=cat_arg, q=q, now_utc=datetime.utcnow(), search_mode=search_mode, trends=trends))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


@public_bp.route('/how-it-works')
def how_it_works():
    return render_template('how_it_works.html')


@public_bp.route('/article/<slug>')
def article(slug):
    conn = get_db_connection()
    art = conn.execute('SELECT * FROM articles WHERE slug = ?', (slug,)).fetchone()
    conn.close()
    if not art:
        abort(404)
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

    # SEO Internal Linking: 3 Related Articles (Same Category)
    conn = get_db_connection()
    related = conn.execute('''
        SELECT title, slug, image, category, published_at
        FROM articles
        WHERE category = ? AND id != ?
        ORDER BY published_at DESC LIMIT 3
    ''', (d['category'], d['id'])).fetchall()
    conn.close()

    related_articles = []
    for r in related:
        rd = dict(r)
        if rd['image'] and not rd['image'].startswith('http') and not rd['image'].startswith('/'):
            rd['image'] = '/' + rd['image']
        related_articles.append(rd)

    # Analytics: Increment Views
    try:
        conn = get_db_connection()
        conn.execute('UPDATE articles SET views = views + 1 WHERE id = ?', (d['id'],))
        conn.commit()
    except Exception as e:
        print(f"Analytics Error: {e}")
    finally:
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
def subscribe():
    import sqlite3
    from newsletter_sender import send_welcome_email

    if request.method == 'POST':
        email = request.form.get('email')
        if email:
            conn = get_db_connection()
            conn.execute('''
                CREATE TABLE IF NOT EXISTS subscribers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE,
                    status TEXT DEFAULT 'ACTIVE',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            try:
                conn.execute('INSERT INTO subscribers (email) VALUES (?)', (email,))
                conn.commit()

                try:
                    send_welcome_email(email)
                except Exception as e:
                    print(f"Failed to send welcome email: {e}")

                return redirect(url_for('public.thank_you_page'))
            except sqlite3.IntegrityError:
                flash('You are already subscribed. Welcome back!')
                return redirect(url_for('public.thank_you_page', status='existing'))
            finally:
                conn.close()
    return render_template('subscribe.html')
