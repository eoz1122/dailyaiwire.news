import sqlite3
import json
import os
import requests
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

def build_email_html(newsletter_id):
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
    
    # Render using the premium Jinja2 template
    # Note: We need a Flask app context to use render_template
    from app import app
    with app.app_context():
        return render_template('email/briefing.html', 
                               subject=nl['subject'], 
                               intro_text=nl['intro_text'].replace('\n', '<br>'), 
                               articles=articles)

def send_newsletter(newsletter_id):
    if not RESEND_API_KEY:
        print("❌ ERROR: RESEND_API_KEY not found in environment.")
        return False
        
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM newsletters WHERE id = ?", (newsletter_id,))
    nl = cursor.fetchone()
    
    if not nl or nl['status'] == 'SENT':
        print(f"⚠️ Newsletter {newsletter_id} not found or already sent.")
        conn.close()
        return False
        
    subscribers = get_active_subscribers()
    if not subscribers:
        print("📭 No active subscribers found.")
        conn.close()
        return False
        
    print(f"🚀 Preparing to broadcast report '{nl['subject']}' to {len(subscribers)} subscribers...")
    
    html_content = build_email_html(newsletter_id)
    
    # Broadcast (In production, use batching or BCC if allowed, or individual calls)
    # Resend allows single call to many recipients in 'to' as a list
    
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "from": "DailyAIWire <intelligence@dailyaiwire.news>",
        "to": subscribers, # List format
        "subject": nl['subject'],
        "html": html_content
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code in [200, 201]:
            print(f"✅ SIGNAL BROADCAST SUCCESSFUL: {response.json().get('id')}")
            # Mark as sent
            cursor.execute("UPDATE newsletters SET status = 'SENT' WHERE id = ?", (newsletter_id,))
            conn.commit()
            return True
        else:
            print(f"❌ BROADCAST FAILED: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ CRITICAL DELIVERY ERROR: {e}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    # For testing, you'd call send_newsletter with an ID
    pass
