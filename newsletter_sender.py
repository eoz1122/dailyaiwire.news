import sqlite3
import json
import os
import hmac
import hashlib
import logging
import requests
import time
from datetime import datetime
from dotenv import load_dotenv
from markupsafe import escape

load_dotenv()

logger = logging.getLogger('newsletter')

DB_PATH = "news.db"
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
SENDER_EMAIL = "briefing@dailyaiwire.news"  # Verified Domain Sender


def _tracking_token(newsletter_id, email):
    """Generate a one-way HMAC token for newsletter open tracking (F-03).
    Replaces raw PII (email) in tracking URLs with an opaque token."""
    secret = os.getenv('SECRET_KEY', 'fallback-dev-key')
    msg = f"{newsletter_id}:{email}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()[:16]


def _newsletter_issue_context(newsletter_row):
    """Build display-friendly issue/date labels for the weekly briefing masthead."""
    raw_date = (
        newsletter_row["scheduled_date"]
        or newsletter_row["created_at"]
        or ""
    )
    try:
        parsed = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
    except Exception:
        parsed = datetime.utcnow()

    iso_week = parsed.isocalendar().week
    return {
        "newsletter_date_display": parsed.strftime("%d %b %Y").upper(),
        "newsletter_issue_label": f"W{iso_week:02d} · {parsed.year}",
    }


def _ensure_tracking_columns(conn):
    """Lazy migration: add tracking_token and opened_at columns if missing."""
    try:
        conn.execute('SELECT tracking_token FROM newsletter_deliveries LIMIT 1')
    except sqlite3.OperationalError:
        logger.info("MIGRATION: Adding 'tracking_token' column to newsletter_deliveries...")
        conn.execute('ALTER TABLE newsletter_deliveries ADD COLUMN tracking_token TEXT')
    try:
        conn.execute('SELECT opened_at FROM newsletter_deliveries LIMIT 1')
    except sqlite3.OperationalError:
        logger.info("MIGRATION: Adding 'opened_at' column to newsletter_deliveries...")
        conn.execute('ALTER TABLE newsletter_deliveries ADD COLUMN opened_at TIMESTAMP')
    conn.commit()

def send_welcome_email(recipient_email):
    """Sends a transactional welcome email to a new subscriber."""
    if not RESEND_API_KEY:
        logger.error("❌ ERROR: RESEND_API_KEY missing.")
        return False
        
    logger.info("🚀 Sending welcome email to %s...", recipient_email)
    
    # Simple HTML for the welcome email (inline for reliability if file read fails, or read from file)
    # Ideally reuse template logic, but keep it robust here.
    try:
        from flask import render_template
        from app import app
        with app.app_context():
            html_content = render_template('email/welcome.html')
    except Exception as e:
        logger.warning("⚠️ Template render failed (%s), using fallback HTML.", e)
        html_content = "<h1>Welcome to the Wire.</h1><p>You are subscribed.</p>"

    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "from": f"DailyAIWire <{SENDER_EMAIL}>",
        "to": [recipient_email],
        "subject": "Connection Established // DailyAIWire",
        "html": html_content
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code in [200, 201]:
            logger.info("✅ Welcome email sent successfully.")
            return True
        else:
            logger.error("❌ Welcome email failed: %s - %s", response.status_code, response.text)
            return False
    except Exception as e:
        logger.error("❌ Network error sending email: %s", e)
        return False


def send_confirmation_email(recipient_email, confirmation_url):
    """Send a double opt-in confirmation email before activating a subscriber."""
    if not RESEND_API_KEY:
        logger.error("❌ ERROR: RESEND_API_KEY missing.")
        return False

    try:
        from flask import render_template
        from app import app
        with app.app_context():
            html_content = render_template(
                'email/confirmation.html',
                confirmation_url=confirmation_url,
            )
    except Exception as e:
        logger.warning("⚠️ Confirmation template render failed (%s), using fallback HTML.", e)
        safe_url = escape(confirmation_url)
        html_content = f"""
        <h1>Confirm your DailyAIWire subscription</h1>
        <p>Click the link below to confirm that you requested DailyAIWire updates.</p>
        <p><a href="{safe_url}">Confirm subscription</a></p>
        <p>If you did not request this, ignore this email and you will not be added to the active newsletter list.</p>
        """

    payload = {
        "from": f"DailyAIWire <{SENDER_EMAIL}>",
        "to": [recipient_email],
        "subject": "Confirm your DailyAIWire subscription",
        "html": html_content,
    }
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post("https://api.resend.com/emails", headers=headers, json=payload, timeout=10)
        if response.status_code in [200, 201]:
            logger.info("✅ Confirmation email sent successfully.")
            return True
        logger.error("❌ Confirmation email failed: %s - %s", response.status_code, response.text)
        return False
    except Exception as e:
        logger.error("❌ Network error sending confirmation email: %s", e)
        return False

def get_active_subscribers():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM subscribers WHERE status = 'ACTIVE'")
    subs = [row[0] for row in cursor.fetchall()]
    conn.close()
    return subs

def build_email_html(newsletter_id, template='email/briefing.html', recipient_email=None):
    from flask import render_template
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get newsletter
    cursor.execute("SELECT * FROM newsletters WHERE id = ?", (newsletter_id,))
    nl = cursor.fetchone()
    
    if not nl:
        conn.close()
        return None
        
    article_ids = json.loads(nl['article_ids'])
    articles = []
    if article_ids:
        placeholders = ', '.join(['?'] * len(article_ids))
        cursor.execute(f"SELECT * FROM articles WHERE id IN ({placeholders})", article_ids)
        articles = [dict(row) for row in cursor.fetchall()]
        
    try:
        article_metadata = json.loads(nl['article_metadata']) if nl['article_metadata'] else {}
    except Exception:
        article_metadata = {}
    
    conn.close()

    issue_context = _newsletter_issue_context(nl)
    
    tracking_url = ""
    if recipient_email:
        token = _tracking_token(newsletter_id, recipient_email)
        tracking_url = f"https://dailyaiwire.news/t/nl/{newsletter_id}/{token}"
    
    # Render using the requested Jinja2 template
    from app import app
    with app.app_context():
        return render_template(template, 
                               subject=nl['subject'], 
                               intro_text=nl['intro_text'].replace('\n', '<br>'), 
                               articles=articles,
                               article_metadata=article_metadata,
                               newsletter_date_display=issue_context['newsletter_date_display'],
                               newsletter_issue_label=issue_context['newsletter_issue_label'],
                               tracking_pixel_url=tracking_url)

def send_newsletter(newsletter_id, is_apology=False):
    if not RESEND_API_KEY:
        logger.error("❌ ERROR: RESEND_API_KEY not found in environment.")
        return False
        
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM newsletters WHERE id = ?", (newsletter_id,))
    nl = cursor.fetchone()
    
    if not nl:
        logger.warning("⚠️ Newsletter %d not found.", newsletter_id)
        conn.close()
        return False

    # Ensure tracking columns exist (lazy migration)
    _ensure_tracking_columns(conn)
        
    subscribers = get_active_subscribers()
    if not subscribers:
        logger.info("📭 No active subscribers found.")
        conn.close()
        return False
        
    logger.info("🚀 Processing broadcast for '%s' to %d subscribers...", nl['subject'], len(subscribers))
    
    template = 'email/apology_briefing.html' if is_apology else 'email/briefing.html'

    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }

    success_count = 0
    skip_count = 0
    fail_count = 0

    for sub_email in subscribers:
        # 1. Check if already delivered
        check = conn.execute("SELECT id FROM newsletter_deliveries WHERE newsletter_id = ? AND recipient_email = ?",
                             (newsletter_id, sub_email)).fetchone()
        if check:
            logger.info("⏭️ Skipping %s (Already Delivered)", sub_email)
            skip_count += 1
            continue

        # 2. Render per-subscriber HTML with correct HMAC tracking token
        # (Must render per-subscriber so each tracking pixel URL has the right token)
        html_content = build_email_html(newsletter_id, template=template, recipient_email=sub_email)
        payload = {
            "from": "DailyAIWire <intelligence@dailyaiwire.news>",
            "to": [sub_email],
            "subject": nl['subject'],
            "html": html_content
        }

        # HARD SAFETY CHECK: Prevent Bulk Leaks
        if isinstance(payload['to'], list) and len(payload['to']) > 1:
             raise ValueError(f"CRITICAL PRIVACY ERROR: Attempted to send to {len(payload['to'])} people at once. ABORTING.")
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code in [200, 201]:
                logger.info("✅ Sent to %s", sub_email)
                # Log success with tracking token (F-03: store token for open tracking)
                token = _tracking_token(newsletter_id, sub_email)
                conn.execute(
                    "INSERT INTO newsletter_deliveries (newsletter_id, recipient_email, status, tracking_token) VALUES (?, ?, ?, ?)",
                    (newsletter_id, sub_email, 'DELIVERED', token)
                )
                conn.commit()
                success_count += 1
            else:
                logger.error("❌ Failed to %s: %s", sub_email, response.status_code)
                fail_count += 1
            
            # Rate limit politeness to prevent 429s (especially on broadcast)
            time.sleep(2.0)
            
        except Exception as e:
            logger.error("❌ Network Error for %s: %s", sub_email, e)
            fail_count += 1
            
    logger.info("🏁 Broadcast Complete. Sent: %d | Skipped: %d | Failed: %d", success_count, skip_count, fail_count)
    
    # Mark as SENT if we delivered to at least one subscriber (or all were already delivered/skipped).
    # Only stays DRAFT if we literally delivered nothing new AND had failures.
    if success_count > 0 or (skip_count > 0 and fail_count == 0):
        cursor.execute("UPDATE newsletters SET status = 'SENT' WHERE id = ?", (newsletter_id,))
        conn.commit()
        logger.info("✅ Newsletter marked as SENT (delivered: %d, skipped: %d, failed: %d)", success_count, skip_count, fail_count)
    elif fail_count > 0 and success_count == 0:
        cursor.execute("UPDATE newsletters SET status = 'PARTIAL' WHERE id = ?", (newsletter_id,))
        conn.commit()
        logger.warning("⚠️ Newsletter marked as PARTIAL - all sends failed but loop completed.")
    else:
        logger.warning("⚠️ Newsletter status unchanged (no subscribers processed).")
        
    conn.close()
    return True

if __name__ == "__main__":
    # For testing, you'd call send_newsletter with an ID
    pass

if __name__ == "__main__":
    # For testing, you'd call send_newsletter with an ID
    pass
