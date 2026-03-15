import sqlite3
import json
import os
import logging
import requests
import time
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger('newsletter')

DB_PATH = "news.db"
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
SENDER_EMAIL = "briefing@dailyaiwire.news"  # Verified Domain Sender

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
    
    conn.close()
    
    tracking_url = ""
    if recipient_email:
        tracking_url = f"https://dailyaiwire.news/t/nl/{newsletter_id}/{recipient_email}"
    
    # Render using the requested Jinja2 template
    from app import app
    with app.app_context():
        return render_template(template, 
                               subject=nl['subject'], 
                               intro_text=nl['intro_text'].replace('\n', '<br>'), 
                               articles=articles,
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
        
    subscribers = get_active_subscribers()
    if not subscribers:
        logger.info("📭 No active subscribers found.")
        conn.close()
        return False
        
    logger.info("🚀 Processing broadcast for '%s' to %d subscribers...", nl['subject'], len(subscribers))
    
    template = 'email/apology_briefing.html' if is_apology else 'email/briefing.html'
    html_base = build_email_html(newsletter_id, template=template, recipient_email="TRACK_ME_TOKEN")
    
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
            
        # 2. Send Individual Email
        html_content = html_base.replace("TRACK_ME_TOKEN", sub_email)
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
                # Log success
                conn.execute("INSERT INTO newsletter_deliveries (newsletter_id, recipient_email, status) VALUES (?, ?, ?)",
                             (newsletter_id, sub_email, 'DELIVERED'))
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
        logger.warning("⚠️ Newsletter marked as PARTIAL — all sends failed but loop completed.")
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
