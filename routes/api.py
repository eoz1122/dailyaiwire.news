"""
API routes — DailyAIWire.news
Search, trends, and tracking endpoints.
"""
import base64

from flask import Blueprint, request, Response
from flask_login import current_user

from db import get_db_connection

api_bp = Blueprint('api', __name__)


@api_bp.route('/api/search')
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
        print(f"⚠️ API semantic search fallback: {e}")

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
        return {"error": str(e), "has_trends": False}, 200


@api_bp.route('/api/track-audio/<int:id>', methods=['POST'])
def track_audio_play(id):
    try:
        conn = get_db_connection()
        conn.execute('UPDATE articles SET audio_plays = audio_plays + 1 WHERE id = ?', (id,))
        conn.commit()
        conn.close()
        return {"status": "success", "id": id}, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500


@api_bp.route('/t/nl/<int:newsletter_id>/<string:recipient_email>')
def track_newsletter_open(newsletter_id, recipient_email):
    """Tracks newsletter opens via a 1x1 pixel."""
    try:
        conn = get_db_connection()
        conn.execute('''
            UPDATE newsletter_deliveries
            SET status = 'OPENED', opened_at = CURRENT_TIMESTAMP
            WHERE newsletter_id = ? AND recipient_email = ? AND (opened_at IS NULL OR status = 'DELIVERED')
        ''', (newsletter_id, recipient_email))
        conn.commit()
    except Exception as e:
        print(f"Tracking error: {e}")
    finally:
        conn.close()

    pixel_data = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
    return Response(pixel_data, mimetype='image/gif')
