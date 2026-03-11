"""
Admin Carousel routes — DailyAIWire.news
Manual pinning, reordering, and expiry timers for homepage carousel.
"""
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from db import get_db_connection

admin_carousel_bp = Blueprint('admin_carousel', __name__)

# --- Duration presets (in hours) ---
DURATION_PRESETS = {
    '1h': 1,
    '4h': 4,
    '12h': 12,
    '24h': 24,
    '48h': 48,
    '1w': 168,
}


@admin_carousel_bp.route('/admin/carousel')
@login_required
def admin_carousel():
    """Show carousel management page."""
    conn = get_db_connection()

    # Active carousel slots (not expired)
    slots = conn.execute('''
        SELECT cs.*, a.title, a.image, a.category, a.published_at, a.importance_score, a.source
        FROM carousel_slots cs
        JOIN articles a ON cs.article_id = a.id
        WHERE a.is_published = 1
        ORDER BY cs.position ASC, cs.pinned_at ASC
    ''').fetchall()

    # Clean expired slots
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    expired = [dict(s) for s in slots if s['expires_at'] and s['expires_at'] < now]
    active_slots = [dict(s) for s in slots if not s['expires_at'] or s['expires_at'] >= now]

    if expired:
        for exp in expired:
            conn.execute('DELETE FROM carousel_slots WHERE id = ?', (exp['id'],))
        conn.commit()

    # Recent articles for pinning (top 20, not already pinned)
    pinned_ids = [s['article_id'] for s in active_slots]
    if pinned_ids:
        placeholders = ','.join('?' * len(pinned_ids))
        recent = conn.execute(f'''
            SELECT id, title, image, category, published_at, importance_score, source
            FROM articles
            WHERE is_published = 1 AND id NOT IN ({placeholders})
            ORDER BY published_at DESC
            LIMIT 20
        ''', pinned_ids).fetchall()
    else:
        recent = conn.execute('''
            SELECT id, title, image, category, published_at, importance_score, source
            FROM articles
            WHERE is_published = 1
            ORDER BY published_at DESC
            LIMIT 20
        ''').fetchall()

    conn.close()

    return render_template('admin/carousel.html',
                           slots=active_slots,
                           recent_articles=[dict(r) for r in recent],
                           presets=DURATION_PRESETS)


@admin_carousel_bp.route('/admin/carousel/pin/<int:article_id>', methods=['POST'])
@login_required
def pin_article(article_id):
    """Pin an article to the carousel."""
    conn = get_db_connection()

    # Check if already pinned
    existing = conn.execute('SELECT id FROM carousel_slots WHERE article_id = ?', (article_id,)).fetchone()
    if existing:
        flash('Article is already pinned to carousel.', 'info')
        conn.close()
        return redirect(request.referrer or url_for('admin_carousel.admin_carousel'))

    # Calculate expiry
    duration = request.form.get('duration', '')
    custom_expiry = request.form.get('custom_expiry', '')
    expires_at = None

    if duration in DURATION_PRESETS:
        hours = DURATION_PRESETS[duration]
        expires_at = (datetime.utcnow() + timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
    elif custom_expiry:
        try:
            expires_at = datetime.strptime(custom_expiry, '%Y-%m-%dT%H:%M').strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            flash('Invalid expiry date format.', 'error')
            conn.close()
            return redirect(url_for('admin_carousel.admin_carousel'))

    # Get next position
    max_pos = conn.execute('SELECT COALESCE(MAX(position), 0) FROM carousel_slots').fetchone()[0]
    new_pos = max_pos + 1

    # Get position from form if specified
    form_pos = request.form.get('position', type=int)
    if form_pos is not None and form_pos > 0:
        new_pos = form_pos

    username = current_user.username if hasattr(current_user, 'username') else 'admin'

    conn.execute('''
        INSERT INTO carousel_slots (article_id, position, pinned_at, expires_at, pinned_by)
        VALUES (?, ?, ?, ?, ?)
    ''', (article_id, new_pos, datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), expires_at, username))
    conn.commit()
    conn.close()

    flash('Article pinned to carousel! 📌', 'success')
    return redirect(request.referrer or url_for('admin_carousel.admin_carousel'))


@admin_carousel_bp.route('/admin/carousel/unpin/<int:article_id>', methods=['POST'])
@login_required
def unpin_article(article_id):
    """Remove article from carousel."""
    conn = get_db_connection()
    conn.execute('DELETE FROM carousel_slots WHERE article_id = ?', (article_id,))
    conn.commit()
    conn.close()
    flash('Article removed from carousel.', 'success')
    return redirect(request.referrer or url_for('admin_carousel.admin_carousel'))


@admin_carousel_bp.route('/admin/carousel/reorder', methods=['POST'])
@login_required
def reorder_carousel():
    """Update positions for all carousel slots."""
    conn = get_db_connection()

    # Expect form data like: order[]=article_id_1&order[]=article_id_2&...
    order = request.form.getlist('order[]')

    if not order:
        # Fallback: try JSON body
        import json
        try:
            data = request.get_json(force=True)
            order = data.get('order', [])
        except Exception:
            pass

    if order:
        for idx, article_id in enumerate(order):
            conn.execute(
                'UPDATE carousel_slots SET position = ? WHERE article_id = ?',
                (idx + 1, int(article_id))
            )
        conn.commit()
        flash('Carousel order updated! ✅', 'success')
    else:
        flash('No order data received.', 'error')

    conn.close()
    return redirect(url_for('admin_carousel.admin_carousel'))


@admin_carousel_bp.route('/admin/carousel/update-timer/<int:article_id>', methods=['POST'])
@login_required
def update_timer(article_id):
    """Update the expiry timer for a carousel slot."""
    conn = get_db_connection()

    duration = request.form.get('duration', '')
    custom_expiry = request.form.get('custom_expiry', '')
    expires_at = None

    if duration == 'infinite':
        expires_at = None
    elif duration in DURATION_PRESETS:
        hours = DURATION_PRESETS[duration]
        expires_at = (datetime.utcnow() + timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
    elif custom_expiry:
        try:
            expires_at = datetime.strptime(custom_expiry, '%Y-%m-%dT%H:%M').strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            flash('Invalid expiry date format.', 'error')
            conn.close()
            return redirect(url_for('admin_carousel.admin_carousel'))

    conn.execute('UPDATE carousel_slots SET expires_at = ? WHERE article_id = ?', (expires_at, article_id))
    conn.commit()
    conn.close()

    flash('Timer updated! ⏱️', 'success')
    return redirect(url_for('admin_carousel.admin_carousel'))
