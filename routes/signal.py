"""
The Signal — DailyAIWire.news
Public newsletter archive routes.
Phase 3: GEO — Automated weekly curation with public archive.
"""
import json
from flask import Blueprint, render_template, abort
from db import get_db_connection
from helpers import format_plaintext_html

signal_bp = Blueprint('signal', __name__)


@signal_bp.route('/signal')
def signal_archive():
    """Public archive of past newsletter editions."""
    conn = get_db_connection()
    try:
        newsletters = conn.execute('''
            SELECT n.id, n.subject, n.intro_text, n.scheduled_date, n.status,
                   n.article_ids,
                   (SELECT COUNT(*) FROM newsletter_deliveries WHERE newsletter_id = n.id) as sent_count
            FROM newsletters n
            WHERE n.status = 'SENT'
            ORDER BY n.scheduled_date DESC
            LIMIT 50
        ''').fetchall()
    except Exception:
        newsletters = []
    conn.close()

    editions = []
    for nl in newsletters:
        d = dict(nl)
        try:
            d['article_count'] = len(json.loads(d['article_ids']))
        except Exception:
            d['article_count'] = 0
        # Truncate intro for the archive card
        intro = d.get('intro_text', '') or ''
        d['intro_preview'] = intro[:200] + '...' if len(intro) > 200 else intro
        editions.append(d)

    return render_template('signal.html', editions=editions)


@signal_bp.route('/signal/<int:newsletter_id>')
def signal_detail(newsletter_id):
    """Individual newsletter web view — readable version of emailed content."""
    conn = get_db_connection()
    try:
        nl = conn.execute('SELECT * FROM newsletters WHERE id = ? AND status = ?',
                          (newsletter_id, 'SENT')).fetchone()
    except Exception:
        nl = None

    if not nl:
        conn.close()
        abort(404)

    nl_dict = dict(nl)

    # Fetch linked articles
    articles = []
    try:
        article_ids = json.loads(nl_dict['article_ids'])
        if article_ids:
            placeholders = ', '.join(['?'] * len(article_ids))
            rows = conn.execute(
                f'SELECT id, slug, title, gist, category, importance_score, source, published_at '
                f'FROM articles WHERE id IN ({placeholders})',
                article_ids
            ).fetchall()
            articles = [dict(r) for r in rows]
    except Exception:
        pass

    # Parse article metadata (per-article blurbs)
    article_metadata = {}
    try:
        article_metadata = json.loads(nl_dict.get('article_metadata') or '{}')
    except Exception:
        pass

    conn.close()

    newsletter_intro_html = format_plaintext_html(nl_dict.get('intro_text', ''))

    return render_template('signal_detail.html',
                           newsletter=nl_dict,
                           articles=articles,
                           article_metadata=article_metadata,
                           newsletter_intro_html=newsletter_intro_html)
