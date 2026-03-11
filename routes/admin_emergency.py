"""
Emergency Override routes — DailyAIWire.news
Global site kill switch with optional Google deindexing.
Phase 4: Administrative Supremacy.
"""
from flask import Blueprint, redirect, url_for, flash, request
from flask_login import login_required

from db import get_db_connection

admin_emergency_bp = Blueprint('admin_emergency', __name__)


def is_emergency_mode():
    """Check if emergency mode is currently active."""
    try:
        conn = get_db_connection()
        row = conn.execute(
            "SELECT value FROM metadata WHERE key = 'emergency_mode'"
        ).fetchone()
        conn.close()
        return row and row['value'] == '1'
    except Exception:
        return False


@admin_emergency_bp.route('/admin/emergency-override', methods=['POST'])
@login_required
def toggle_emergency():
    """Toggle emergency override mode on/off with confirmation safety."""
    confirm = request.form.get('confirm', '')

    if confirm != 'CONFIRM':
        flash("⚠️ Emergency override requires typing CONFIRM. Action aborted.", "warning")
        return redirect(url_for('admin.index'))

    conn = get_db_connection()

    # Ensure metadata table exists
    conn.execute('''
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    # Check current state
    row = conn.execute(
        "SELECT value FROM metadata WHERE key = 'emergency_mode'"
    ).fetchone()
    currently_active = row and row['value'] == '1'

    if currently_active:
        # DEACTIVATE — bring site back online
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('emergency_mode', '0')"
        )
        conn.commit()
        conn.close()

        # Request Google re-crawl
        try:
            from google_indexer import notify_google_index
            notify_google_index("https://dailyaiwire.news/")
        except Exception as e:
            print(f"⚠️ Google re-crawl request failed: {e}")

        flash("✅ EMERGENCY OVERRIDE LIFTED — Site is back ONLINE.", "success")
    else:
        # ACTIVATE — take site offline
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('emergency_mode', '1')"
        )
        conn.commit()
        conn.close()

        # Optionally request Google URL removal
        try:
            from google_indexer import notify_google_index
            # Send URL_DELETED signal to accelerate de-indexing
            notify_google_index("https://dailyaiwire.news/", action="URL_DELETED")
        except Exception as e:
            print(f"⚠️ Google deindex signal failed (non-critical): {e}")

        flash("🚨 EMERGENCY OVERRIDE ACTIVATED — Public site is OFFLINE. Admin panel remains accessible.", "error")

    return redirect(url_for('admin.index'))
