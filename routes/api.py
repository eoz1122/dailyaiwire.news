"""
API routes — DailyAIWire.news
Search, trends, and tracking endpoints.
"""
import base64
import logging

from flask import Blueprint, request, Response
from flask_login import current_user

from extensions import csrf, limiter
from db import get_db_connection

logger = logging.getLogger('api')

api_bp = Blueprint('api', __name__)



@api_bp.route('/api/search')
@limiter.limit("30 per minute")
def api_search():
    """Semantic search API endpoint for typeahead and programmatic access."""
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return {"results": [], "mode": "none"}, 200

    # Try semantic search first
    try:
        from embedding_service import search_articles
        results = search_articles(q, limit=10)
        if results:
            conn = get_db_connection()
            ids = [r['id'] for r in results]
            placeholders = ','.join('?' * len(ids))
            rows = conn.execute(
                f'SELECT id, slug FROM articles WHERE id IN ({placeholders}) AND is_published = 1',
                ids
            ).fetchall()
            conn.close()
            slug_map = {r['id']: r['slug'] for r in rows}

            enriched = []
            for r in results:
                if r['id'] in slug_map:
                    r['slug'] = slug_map[r['id']]
                    enriched.append(r)

            return {"results": enriched, "mode": "semantic"}, 200
    except (ImportError, Exception) as e:
        logger.warning("API semantic search fallback: %s", e)

    # Fallback: keyword search
    conn = get_db_connection()
    query = f"%{q}%"
    rows = conn.execute(
        'SELECT id, title, slug, category, source FROM articles WHERE (title LIKE ? OR gist LIKE ?) AND is_published = 1 ORDER BY published_at DESC LIMIT 10',
        (query, query)
    ).fetchall()
    conn.close()

    return {
        "results": [{"id": r['id'], "title": r['title'], "slug": r['slug'], "category": r['category'], "source": r['source'], "score": None} for r in rows],
        "mode": "keyword"
    }, 200


@api_bp.route('/api/trends')
def api_trends():
    """Trend Intelligence API endpoint."""
    try:
        from trend_engine import get_trend_snapshot
        conn = get_db_connection()
        snapshot = get_trend_snapshot(conn)
        conn.close()
        return snapshot, 200
    except Exception as e:
        logger.error("Trend API error: %s", e)
        return {"error": "Trend data temporarily unavailable.", "has_trends": False}, 200


@api_bp.route('/api/track-audio/<int:id>', methods=['POST'])
@csrf.exempt
@limiter.limit("5 per minute")
def track_audio_play(id):
    try:
        conn = get_db_connection()
        conn.execute('UPDATE articles SET audio_plays = audio_plays + 1 WHERE id = ?', (id,))
        conn.commit()
        conn.close()
        return {"status": "success", "id": id}, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500


@api_bp.route('/t/nl/<int:newsletter_id>/<string:token>')
def track_newsletter_open(newsletter_id, token):
    """Tracks newsletter opens via a 1x1 pixel. Uses HMAC token instead of raw email (F-03)."""
    try:
        conn = get_db_connection()
        conn.execute('''
            UPDATE newsletter_deliveries
            SET status = 'OPENED', opened_at = CURRENT_TIMESTAMP
            WHERE newsletter_id = ? AND tracking_token = ? AND (opened_at IS NULL OR status = 'DELIVERED')
        ''', (newsletter_id, token))
        conn.commit()
    except Exception as e:
        logger.error("Tracking error: %s", e)
    finally:
        conn.close()

    pixel_data = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
    return Response(pixel_data, mimetype='image/gif')


# ── Answer-Engine API (Phase 3: GEO) ────────────────────────────────

@api_bp.route('/api/intelligence')
def api_intelligence():
    """
    Structured intelligence feed for AI agents (Perplexity, SearchGPT, custom RAG).
    Returns articles as structured JSON with filtering and pagination.
    """
    import json as _json
    from datetime import datetime

    limit = min(request.args.get('limit', 10, type=int), 50)
    category = request.args.get('category')
    min_score = request.args.get('min_score', 50, type=int)
    since = request.args.get('since')  # ISO date string

    conn = get_db_connection()

    query_parts = ["SELECT id, slug, title, category, gist, why_it_matters, key_details, "
                   "importance_score, source, source_url, published_at, hashtags "
                   "FROM articles WHERE is_published = 1"]
    params = []

    if category:
        query_parts.append("AND category = ?")
        params.append(category)

    if min_score:
        query_parts.append("AND importance_score >= ?")
        params.append(min_score)

    if since:
        query_parts.append("AND published_at >= ?")
        params.append(since)

    query_parts.append("ORDER BY published_at DESC LIMIT ?")
    params.append(limit)

    rows = conn.execute(" ".join(query_parts), params).fetchall()
    total = conn.execute("SELECT COUNT(*) FROM articles WHERE is_published = 1").fetchone()[0]
    conn.close()

    articles = []
    for r in rows:
        d = dict(r)
        try:
            d['key_details'] = _json.loads(d['key_details'])
        except Exception:
            d['key_details'] = []
        try:
            d['hashtags'] = _json.loads(d['hashtags'])
        except Exception:
            d['hashtags'] = []
        d['url'] = f"https://dailyaiwire.news/article/{d['slug']}"
        articles.append(d)

    resp = {
        "articles": articles,
        "meta": {
            "total_articles": total,
            "returned": len(articles),
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "api_version": "1.0",
            "documentation": "https://dailyaiwire.news/llms.txt"
        }
    }

    response = Response(
        _json.dumps(resp, ensure_ascii=False, default=str),
        mimetype='application/json'
    )
    response.headers['Cache-Control'] = 'public, max-age=300'
    response.headers['Access-Control-Allow-Origin'] = 'https://dailyaiwire.news'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@api_bp.route('/api/intelligence/<slug>')
def api_intelligence_detail(slug):
    """Full article detail for AI agent consumption."""
    import json as _json

    conn = get_db_connection()
    art = conn.execute('SELECT * FROM articles WHERE slug = ? AND is_published = 1', (slug,)).fetchone()
    conn.close()

    if not art:
        return {"error": "Article not found", "slug": slug}, 404

    d = dict(art)

    # Parse JSON fields
    for field in ['key_details', 'hashtags', 'design_tokens']:
        try:
            d[field] = _json.loads(d.get(field) or '[]')
        except Exception:
            d[field] = [] if field != 'design_tokens' else {}

    # Remove internal fields
    for internal in ['full_json', 'shared_on_x', 'shared_at', 'audio_male', 'audio_female']:
        d.pop(internal, None)

    d['url'] = f"https://dailyaiwire.news/article/{d['slug']}"

    response = Response(
        _json.dumps(d, ensure_ascii=False, default=str),
        mimetype='application/json'
    )
    response.headers['Cache-Control'] = 'public, max-age=300'
    response.headers['Access-Control-Allow-Origin'] = 'https://dailyaiwire.news'
    return response
