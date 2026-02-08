import sqlite3
import json
import os
import requests
import time
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "news.db"
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
SENDER_EMAIL = "briefing@dailyaiwire.news"  # Verified Domain Sender

def send_welcome_email(recipient_email):
    """Sends a transactional welcome email to a new subscriber."""
    if not RESEND_API_KEY:
        print("❌ ERROR: RESEND_API_KEY missing.")
        return False
        
    print(f"🚀 Sending welcome email to {recipient_email}...")
    
    # Simple HTML for the welcome email (inline for reliability if file read fails, or read from file)
    # Ideally reuse template logic, but keep it robust here.
    try:
        from flask import render_template
        from app import app
        with app.app_context():
            html_content = render_template('email/welcome.html')
    except Exception as e:
        print(f"⚠️ Template render failed ({e}), using fallback HTML.")
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
            print("✅ Welcome email sent successfully.")
            return True
        else:
            print(f"❌ Welcome email failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Network error sending email: {e}")
        return False

def get_active_subscribers():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM subscribers WHERE status = 'ACTIVE'")
    subs = [row[0] for row in cursor.fetchall()]
    conn.close()
    return subs

def build_email_html(newsletter_id, template='email/briefing.html'):
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
    
    # Render using the requested Jinja2 template
    from app import app
    with app.app_context():
        return render_template(template, 
                               subject=nl['subject'], 
                               intro_text=nl['intro_text'].replace('\n', '<br>'), 
                               articles=articles)

def send_newsletter(newsletter_id, is_apology=False):
    if not RESEND_API_KEY:
        print("❌ ERROR: RESEND_API_KEY not found in environment.")
        return False
        
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM newsletters WHERE id = ?", (newsletter_id,))
    nl = cursor.fetchone()
    
    if not nl:
        print(f"⚠️ Newsletter {newsletter_id} not found.")
        conn.close()
        return False
        
    subscribers = get_active_subscribers()
    if not subscribers:
        print("📭 No active subscribers found.")
        conn.close()
        return False
        
    print(f"🚀 Processing broadcast for '{nl['subject']}' to {len(subscribers)} subscribers...")
    
    template = 'email/apology_briefing.html' if is_apology else 'email/briefing.html'
    html_content = build_email_html(newsletter_id, template=template)
    
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
            print(f"⏭️ Skipping {sub_email} (Already Delivered)")
            skip_count += 1
            continue
            
        # 2. Send Individual Email
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
                print(f"✅ Sent to {sub_email}")
                # Log success
                conn.execute("INSERT INTO newsletter_deliveries (newsletter_id, recipient_email, status) VALUES (?, ?, 'DELIVERED')",
                             (newsletter_id, sub_email, 'DELIVERED'))
                conn.commit()
                success_count += 1
            else:
                print(f"❌ Failed to {sub_email}: {response.status_code}")
                fail_count += 1
            
            # Rate limit politeness to prevent 429s (especially on broadcast)
            time.sleep(1.0)
            
        except Exception as e:
            print(f"❌ Network Error for {sub_email}: {e}")
            fail_count += 1
            
    print(f"🏁 Broadcast Complete. Sent: {success_count} | Skipped: {skip_count} | Failed: {fail_count}")
    
    # Mark as SENT only if we processed everyone successfully or mostly successfully?
    # Actually, always mark as SENT if we finished the loop. If we crash, it stays DRAFT/resumable.
    if success_count + skip_count == len(subscribers):
        cursor.execute("UPDATE newsletters SET status = 'SENT' WHERE id = ?", (newsletter_id,))
        conn.commit()
        print("✅ Newsletter marked as FULLY SENT")
    else:
        print("⚠️ Newsletter status remains DRAFT/PARTIAL (Some failures occurred)")
        
    conn.close()
    return True

if __name__ == "__main__":
    # For testing, you'd call send_newsletter with an ID
    pass

if __name__ == "__main__":
    # For testing, you'd call send_newsletter with an ID
    pass
