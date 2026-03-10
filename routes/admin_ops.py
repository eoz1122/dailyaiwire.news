"""
Admin Ops routes — DailyAIWire.news
Sources, leads, duplicates, budget, kill article.
"""
import sqlite3
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from db import get_db_connection
from budget_tracker import BudgetTracker

admin_ops_bp = Blueprint('admin_ops', __name__)


# --- Sources ---

@admin_ops_bp.route('/admin/sources', methods=['GET', 'POST'])
@login_required
def admin_sources():
    conn = get_db_connection()

    if request.method == 'POST':
        name = request.form.get('name')
        url = request.form.get('url')
        if name and url:
            try:
                conn.execute('INSERT INTO sources (name, url, is_active) VALUES (?, ?, 1)', (name, url))
                conn.commit()
                flash(f"Source added: {name}", "success")
            except sqlite3.IntegrityError:
                flash("Source URL already exists.", "error")
        elif request.form.get('toggle_id'):
            sid = request.form.get('toggle_id')
            conn.execute('UPDATE sources SET is_active = NOT is_active WHERE id = ?', (sid,))
            conn.commit()
            flash("Source status updated.", "success")
        elif request.form.get('delete_id'):
            sid = request.form.get('delete_id')
            conn.execute('DELETE FROM sources WHERE id = ?', (sid,))
            conn.commit()
            flash("Source deleted.", "warning")

    # Auto-Discover Sources from Articles
    try:
        conn.execute('''
            INSERT OR IGNORE INTO sources (name, is_active)
            SELECT DISTINCT source, 1 FROM articles
            WHERE source IS NOT NULL AND source != ''
        ''')
        conn.commit()
    except Exception as e:
        print(f"Source discovery warning: {e}")

    try:
        sources_managed = conn.execute('''
            SELECT s.*, COUNT(a.id) as count
            FROM sources s
            LEFT JOIN articles a ON a.source = s.name
            GROUP BY s.id
            ORDER BY s.is_active DESC, count DESC
        ''').fetchall()
    except sqlite3.OperationalError:
        flash("Sources table missing or query error. Please run migration.", "error")
        sources_managed = []

    blocked_raw = conn.execute('SELECT * FROM blocked_sources ORDER BY added_at DESC').fetchall()

    conn.close()
    return render_template('admin/sources.html', sources=sources_managed, blocked=blocked_raw)


@admin_ops_bp.route('/admin/block-source', methods=['POST'])
@login_required
def admin_block_source():
    domain = request.form.get('domain')
    nuke = request.form.get('nuke')

    if domain:
        conn = get_db_connection()
        try:
            conn.execute('INSERT OR IGNORE INTO blocked_sources (domain) VALUES (?)', (domain,))

            if nuke:
                conn.execute('DELETE FROM articles WHERE source = ?', (domain,))
                flash(f"NUKED source: {domain} (Blocked + Deleted Articles)")
            else:
                flash(f"Blocked source: {domain}")

            conn.commit()
        except Exception as e:
            flash(f"Error blocking source: {e}")
        conn.close()
    return redirect(url_for('admin_ops.admin_sources'))


@admin_ops_bp.route('/admin/unblock-source', methods=['POST'])
@login_required
def admin_unblock_source():
    domain = request.form.get('domain')
    if domain:
        conn = get_db_connection()
        conn.execute('DELETE FROM blocked_sources WHERE domain = ?', (domain,))
        conn.commit()
        conn.close()
        flash(f"Unblocked source: {domain}")
    return redirect(url_for('admin_ops.admin_sources'))


# --- Leads ---

@admin_ops_bp.route('/admin/leads')
@login_required
def admin_leads():
    conn = get_db_connection()
    try:
        leads = conn.execute('''
            SELECT * FROM leads
            ORDER BY
            CASE status
                WHEN 'DRAFT_READY' THEN 1
                WHEN 'NEW' THEN 2
                WHEN 'PROPOSAL_SENT' THEN 3
                ELSE 4
            END,
            confidence_score DESC
        ''').fetchall()
    except sqlite3.OperationalError:
        leads = []
        flash("Leads table missing.", "error")

    conn.close()
    return render_template('admin/leads.html', leads=leads)


@admin_ops_bp.route('/admin/leads/delete/<int:id>', methods=['POST'])
@login_required
def admin_delete_lead(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM leads WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Lead deleted successfully.', 'success')
    return redirect(url_for('admin_ops.admin_leads'))


@admin_ops_bp.route('/admin/leads/generate/<int:id>', methods=['POST'])
@login_required
def admin_generate_lead_draft(id):
    from services.proposal_agent import ProposalAgent
    agent = ProposalAgent()

    draft_json = agent.generate_pitch(id)
    if draft_json:
        agent.save_draft(id, draft_json)
        flash("Draft Proposal Generated", "success")
    else:
        flash("Failed to generate draft (Budget or Error)", "error")

    return redirect(url_for('admin_ops.admin_leads'))


@admin_ops_bp.route('/admin/leads/send/<int:id>', methods=['POST'])
@login_required
def admin_send_lead_proposal(id):
    from services.proposal_agent import ProposalAgent
    agent = ProposalAgent()

    success, msg = agent.send_active_proposal(id)
    if success:
        flash(f"🚀 Proposal sent via Resend! (Ref: {msg})", "success")
    else:
        flash(f"Failed to send: {msg}", "error")

    return redirect(url_for('admin_ops.admin_leads'))


# --- Duplicates ---

@admin_ops_bp.route('/admin/duplicates')
@login_required
def admin_duplicates():
    conn = get_db_connection()
    try:
        conn.execute("SELECT 1 FROM duplicate_clusters LIMIT 1")
    except Exception:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS duplicate_clusters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keeper_id INTEGER NOT NULL,
                keeper_title TEXT,
                articles_json TEXT NOT NULL,
                max_score REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                resolved_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

    clusters_raw = conn.execute(
        "SELECT * FROM duplicate_clusters WHERE status = 'pending' ORDER BY max_score DESC"
    ).fetchall()
    resolved_count = conn.execute(
        "SELECT COUNT(*) FROM duplicate_clusters WHERE status != 'pending'"
    ).fetchone()[0]
    conn.close()

    import json as json_module
    clusters = []
    for c in clusters_raw:
        d = dict(c)
        try:
            d['articles'] = json_module.loads(d['articles_json'])
        except Exception:
            d['articles'] = []
        clusters.append(d)

    return render_template('admin/duplicates.html', clusters=clusters, resolved_count=resolved_count)


@admin_ops_bp.route('/admin/duplicates/merge/<int:cluster_id>', methods=['POST'])
@login_required
def admin_dedup_merge(cluster_id):
    conn = get_db_connection()
    cluster = conn.execute("SELECT * FROM duplicate_clusters WHERE id = ?", (cluster_id,)).fetchone()
    if not cluster:
        flash("Cluster not found.", "error")
        conn.close()
        return redirect(url_for('admin_ops.admin_duplicates'))

    import json as json_module
    articles = json_module.loads(cluster['articles_json'])
    keeper_id = cluster['keeper_id']

    unpublished = 0
    for art in articles:
        if art['id'] != keeper_id:
            conn.execute("UPDATE articles SET is_published = 0 WHERE id = ?", (art['id'],))
            unpublished += 1

    conn.execute(
        "UPDATE duplicate_clusters SET status = 'merged', resolved_at = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), cluster_id)
    )
    conn.commit()
    conn.close()

    flash(f"Merged: kept #{keeper_id}, unpublished {unpublished} duplicates.", "success")
    return redirect(url_for('admin_ops.admin_duplicates'))


@admin_ops_bp.route('/admin/duplicates/dismiss/<int:cluster_id>', methods=['POST'])
@login_required
def admin_dedup_dismiss(cluster_id):
    conn = get_db_connection()
    conn.execute(
        "UPDATE duplicate_clusters SET status = 'dismissed', resolved_at = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), cluster_id)
    )
    conn.commit()
    conn.close()
    flash("Cluster dismissed as false positive.", "success")
    return redirect(url_for('admin_ops.admin_duplicates'))


# --- Budget ---

@admin_ops_bp.route('/admin/budget')
@login_required
def admin_budget():
    tracker = BudgetTracker()
    usage = tracker.data

    total_spent = usage.get('total_spent', 0.0)
    monthly_cap = tracker.monthly_cap
    percent_used = (total_spent / monthly_cap * 100) if monthly_cap > 0 else 0

    budget_view = {
        'current_month': usage.get('current_month'),
        'total_spent': total_spent,
        'percent_used': percent_used,
        'monthly_cap': monthly_cap,
        'remaining': max(0, monthly_cap - total_spent),
        'breakdown': usage.get('breakdown', {}),
        'requests': usage.get('requests', 0),
        'tokens_used': usage.get('tokens_used', 0)
    }

    return render_template('admin/budget.html', budget=budget_view)


# --- Kill Article ---

@admin_ops_bp.route('/admin/kill/<int:id>', methods=['POST'])
@login_required
def admin_kill_article(id):
    conn = get_db_connection()
    row = conn.execute('SELECT is_published, source, title, source_url FROM articles WHERE id = ?', (id,)).fetchone()

    if row:
        current_status = row['is_published']
        new_status = 0 if current_status else 1

        conn.execute('UPDATE articles SET is_published = ? WHERE id = ?', (new_status, id))

        status_msg = "LIVE" if new_status else "OFFLINE"
        flash_color = "success" if new_status else "warning"

        if new_status == 0:
            try:
                from urllib.parse import urlparse
                domain = row['source']
                if row['source_url']:
                    try:
                        domain = urlparse(row['source_url']).netloc.replace('www.', '')
                    except Exception:
                        pass

                conn.execute('''
                    INSERT OR IGNORE INTO leads (domain, source_url, title, status, confidence_score, opportunity_reason)
                    VALUES (?, ?, ?, 'NEW', 85, 'Manually Killed Signal (High Conversion Potential)')
                ''', (domain, row['source_url'], row['title']))
                status_msg += " + COPIED TO LEADS"
            except Exception as e:
                print(f"Error moving to leads: {e}")

        if new_status == 0 and request.args.get('block_source') == 'true':
            source_to_block = row['source']
            if source_to_block:
                conn.execute('INSERT OR IGNORE INTO blocked_sources (domain) VALUES (?)', (source_to_block,))
                flash(f"☢️ NUCLEAR LAUNCH DETECTED: Source '{source_to_block}' has been blacklisted.", "error")
            else:
                flash(f"Article {id} is {status_msg}, but Source was missing/empty.", flash_color)
        else:
            flash(f"Article {id} Status: {status_msg}", flash_color)

        conn.commit()
    conn.close()

    return redirect(request.referrer or url_for('admin.index'))
