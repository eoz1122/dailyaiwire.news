"""
API routes — DailyAIWire.news
Search, trends, and tracking endpoints.
"""
import base64
import hashlib
import logging
import os

from flask import Blueprint, jsonify, request, Response
from flask_login import current_user

from extensions import csrf, limiter
from db import get_db_connection
from services.resend_webhooks import process_resend_event, verify_resend_webhook
from services.traffic_quality import is_likely_bot
from services.subscribers import (
    SUBSCRIBE_PLACEMENTS,
    ensure_subscriber_events_schema,
    record_subscriber_event,
)

logger = logging.getLogger('api')

api_bp = Blueprint('api', __name__)

AUDIO_DEDUPE_MINUTES = 30
SUBSCRIBE_VIEW_DEDUPE_MINUTES = 30
RESEND_WEBHOOK_MAX_BYTES = 256 * 1024
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
    return is_likely_bot(
        user_agent,
        purpose=request.headers.get("Purpose", ""),
        sec_purpose=request.headers.get("Sec-Purpose", ""),
    )


def _visitor_hash() -> str:
    client_ip = _extract_client_ip()
    user_agent = (request.headers.get('User-Agent') or '').strip().lower()
    accept_lang = (request.headers.get('Accept-Language') or '').strip().lower()
    return _hash_value(f"{client_ip}|{user_agent}|{accept_lang}")


def _ensure_audio_play_events_table(conn):
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS audio_play_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL,
            visitor_hash TEXT NOT NULL,
            ip_hash TEXT,
            user_agent TEXT,
            path TEXT,
            is_bot INTEGER DEFAULT 0,
            counted_play INTEGER DEFAULT 0,
            played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )
    conn.execute(
        '''
        CREATE INDEX IF NOT EXISTS idx_audio_play_events_article_visitor_time
        ON audio_play_events(article_id, visitor_hash, played_at)
        '''
    )
    conn.execute(
        '''
        CREATE INDEX IF NOT EXISTS idx_audio_play_events_played_at
        ON audio_play_events(played_at)
        '''
    )


def _no_store_json(payload, status=200):
    response = jsonify(payload)
    response.status_code = status
    response.headers['Cache-Control'] = 'no-store'
    return response


@api_bp.route('/api/track-subscribe-view', methods=['POST'])
@csrf.exempt
@limiter.limit("30 per minute")
def track_subscribe_view():
    """Record a privacy-safe, deduplicated view of a newsletter signup form."""
    placement = (request.form.get('placement') or '').strip().lower()[:50]
    if placement not in SUBSCRIBE_PLACEMENTS:
        return _no_store_json({"error": "Invalid placement"}, 400)

    user_agent = (request.headers.get('User-Agent') or '')[:500]
    if _is_likely_bot(user_agent):
        return _no_store_json({"counted": False, "reason": "bot"})

    conn = None
    try:
        conn = get_db_connection()
        ensure_subscriber_events_schema(conn)
        ip_hash = _hash_value(_extract_client_ip())
        recent = conn.execute(
            '''
            SELECT 1
            FROM subscriber_events
            WHERE event_type = 'form_view'
              AND placement = ?
              AND ip_hash = ?
              AND datetime(created_at) >= datetime('now', ?)
            LIMIT 1
            ''',
            (
                placement,
                ip_hash,
                f'-{SUBSCRIBE_VIEW_DEDUPE_MINUTES} minutes',
            ),
        ).fetchone()
        counted = not bool(recent)
        if counted:
            record_subscriber_event(
                conn,
                email='',
                event_type='form_view',
                reason='visible_1s',
                ip_hash=ip_hash,
                user_agent=user_agent,
                referrer=(request.referrer or '')[:500],
                source_path=(request.form.get('source_path') or '')[:500],
                placement=placement,
            )
            conn.commit()
        return _no_store_json({"counted": counted})
    except Exception:
        logger.exception("Subscriber form view tracking failed")
        return _no_store_json({"error": "Tracking failed"}, 500)
    finally:
        if conn:
            conn.close()



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
    conn = None
    try:
        conn = get_db_connection()
        _ensure_audio_play_events_table(conn)

        article = conn.execute(
            'SELECT id FROM articles WHERE id = ? LIMIT 1',
            (id,),
        ).fetchone()
        if not article:
            conn.close()
            return {"status": "error", "message": "Article not found"}, 404

        user_agent = (request.headers.get('User-Agent') or '')[:512]
        is_bot = 1 if _is_likely_bot(user_agent) else 0
        visitor_hash = _visitor_hash()
        ip_hash = _hash_value(_extract_client_ip())
        counted_play = 0

        if not is_bot:
            window_expr = f'-{AUDIO_DEDUPE_MINUTES} minutes'
            recent = conn.execute(
                '''
                SELECT 1
                FROM audio_play_events
                WHERE article_id = ?
                  AND visitor_hash = ?
                  AND played_at >= datetime('now', ?)
                LIMIT 1
                ''',
                (id, visitor_hash, window_expr)
            ).fetchone()
            if not recent:
                conn.execute(
                    'UPDATE articles SET audio_plays = COALESCE(audio_plays, 0) + 1 WHERE id = ?',
                    (id,),
                )
                counted_play = 1

        conn.execute(
            '''
            INSERT INTO audio_play_events (
                article_id, visitor_hash, ip_hash, user_agent, path, is_bot, counted_play
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (id, visitor_hash, ip_hash, user_agent, request.path, is_bot, counted_play)
        )
        conn.commit()
        return {
            "status": "success",
            "id": id,
            "counted": bool(counted_play),
            "deduped": not bool(counted_play),
        }, 200
    except Exception as e:
        logger.error("Audio tracking error for article %s: %s", id, e, exc_info=True)
        return {"status": "error", "message": "Audio tracking failed"}, 500
    finally:
        if conn:
            conn.close()


@api_bp.route('/t/nl/<int:newsletter_id>/<string:token>')
def track_newsletter_open(newsletter_id, token):
    """Tracks newsletter opens via a 1x1 pixel. Uses HMAC token instead of raw email (F-03)."""
    conn = None
    try:
        conn = get_db_connection()
        conn.execute('''
            UPDATE newsletter_deliveries
            SET opened_at = COALESCE(opened_at, CURRENT_TIMESTAMP)
            WHERE newsletter_id = ? AND tracking_token = ?
        ''', (newsletter_id, token))
        conn.commit()
    except Exception as e:
        logger.error("Tracking error: %s", e)
    finally:
        if conn:
            conn.close()

    pixel_data = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
    return Response(pixel_data, mimetype='image/gif')


@api_bp.route('/api/webhooks/resend', methods=['POST'])
@csrf.exempt
@limiter.limit("120 per minute")
def resend_webhook():
    """Verify and idempotently process Resend provider events."""
    webhook_secret = os.getenv("RESEND_WEBHOOK_SECRET")
    if not webhook_secret:
        logger.critical("RESEND_WEBHOOK_SECRET is not configured")
        return {"error": "Webhook unavailable"}, 503

    if request.content_length and request.content_length > RESEND_WEBHOOK_MAX_BYTES:
        return {"error": "Payload too large"}, 413

    signature_headers = {
        "svix-id": request.headers.get("svix-id", ""),
        "svix-timestamp": request.headers.get("svix-timestamp", ""),
        "svix-signature": request.headers.get("svix-signature", ""),
    }
    if not all(signature_headers.values()):
        return {"error": "Invalid webhook"}, 400

    raw_body = request.get_data(cache=False)
    if not raw_body or len(raw_body) > RESEND_WEBHOOK_MAX_BYTES:
        return {"error": "Invalid webhook"}, 400

    try:
        payload = verify_resend_webhook(raw_body, signature_headers, webhook_secret)
    except Exception:
        logger.warning("Rejected webhook with invalid Resend signature")
        return {"error": "Invalid webhook"}, 400

    try:
        result = process_resend_event(signature_headers["svix-id"], payload)
        return {"received": True, **result}, 200
    except ValueError:
        logger.warning("Rejected malformed verified Resend event")
        return {"error": "Invalid event"}, 400
    except Exception:
        logger.exception("Failed to persist verified Resend webhook")
        return {"error": "Webhook processing failed"}, 500


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
