
import sqlite3
import json
import os
import requests
import time
from dotenv import load_dotenv
from flask import Flask, render_template

# Load Env
load_dotenv()

DB_PATH = "news.db"
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
SENDER_EMAIL = "briefing@dailyaiwire.news" 

# Setup minimal Flask app for rendering context
app = Flask(__name__)

def build_email_html(newsletter_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get newsletter
    cursor.execute("SELECT * FROM newsletters WHERE id = ?", (newsletter_id,))
    nl = cursor.fetchone()
    
    if not nl:
        conn.close()
        return None, None
        
    article_ids = json.loads(nl['article_ids'])
    articles = []
    if article_ids:
        placeholders = ', '.join(['?'] * len(article_ids))
        cursor.execute(f"SELECT * FROM articles WHERE id IN ({placeholders})", article_ids)
        articles = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    # Render using the SAME template as production
    with app.app_context():
        # Mocking generic template availability or using direct string if simple
        # But we assume 'email/briefing.html' exists as per newsletter_sender.py
        try:
            html = render_template('email/briefing.html', 
                                   subject=nl['subject'], 
                                   intro_text=nl['intro_text'].replace('\n', '<br>'), 
                                   articles=articles)
            return html, nl['subject']
        except Exception as e:
            print(f"Template Error: {e}")
            return None, None

def send_test_blast(target_pattern="emrre", newsletter_id=9):
    print(f"🧪 STARTING TEST RUN for filtering '{target_pattern}' on Newsletter ID {newsletter_id}...")
    
    # 1. Fetch Test Subscribers
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM subscribers WHERE email LIKE ?", (f'%{target_pattern}%',))
    test_subs = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    if not test_subs:
        print(f"❌ No subscribers found matching '{target_pattern}'")
        return

    print(f"🎯 Target Audience (Test): {test_subs}")
    
    # 2. Build Content
    html_content, subject = build_email_html(newsletter_id)
    if not html_content:
        print("❌ Failed to build HTML content.")
        return

    # 3. Send Individual Emails (Mirroring Production Logic)
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }

    for sub_email in test_subs:
        print(f"📤 Sending to {sub_email}...")
        
        payload = {
            "from": "DailyAIWire <intelligence@dailyaiwire.news>",
            "to": [sub_email], # ARRAY OF ONE - Crucial for privacy
            "subject": f"[TEST] {subject}",
            "html": html_content
        }
        
        # DOUBLE CHECK: SAFETY ASSERTION
        if len(payload['to']) > 1:
            print("🚨 CRITICAL: STOPPING. ATTEMPTED TO SEND TO MULTIPLE RECIPIENTS.")
            return

        try:
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code in [200, 201]:
                print(f"✅ DELIVERED to {sub_email}")
            else:
                print(f"❌ FAILED {sub_email}: {response.text}")
        except Exception as e:
            print(f"❌ NETWORK ERROR {sub_email}: {e}")
            
    print("🏁 Test Run Complete. Check your inbox.")

if __name__ == "__main__":
    # Get the latest/draft newsletter ID
    conn = sqlite3.connect(DB_PATH)
    latest_id = conn.execute("SELECT id FROM newsletters ORDER BY created_at DESC LIMIT 1").fetchone()[0]
    conn.close()
    
    send_test_blast("emreozen", latest_id)
