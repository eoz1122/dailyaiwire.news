import sqlite3
import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "news.db"
RESEND_API_KEY = os.getenv("RESEND_API_KEY")

def get_active_subscribers():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM subscribers WHERE status = 'ACTIVE'")
    subs = [row[0] for row in cursor.fetchall()]
    conn.close()
    return subs

def build_email_html(newsletter_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get newsletter
    cursor.execute("SELECT * FROM newsletters WHERE id = ?", (newsletter_id,))
    nl = cursor.fetchone()
    
    if not nl:
        return None
        
    article_ids = json.loads(nl['article_ids'])
    articles = []
    if article_ids:
        placeholders = ', '.join(['?'] * len(article_ids))
        cursor.execute(f"SELECT * FROM articles WHERE id IN ({placeholders})", article_ids)
        articles = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    # PREMIUM BRANDED HTML TEMPLATE
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: 'Inter', Helvetica, Arial, sans-serif; background-color: #050505; color: #ffffff; margin: 0; padding: 0; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 40px 20px; }}
            .header {{ text-align: center; margin-bottom: 40px; }}
            .logo {{ width: 80px; height: 80px; margin-bottom: 20px; }}
            .brand-name {{ font-size: 24px; font-weight: 900; letter-spacing: -1px; text-transform: uppercase; }}
            .blue-text {{ color: #2563eb; }}
            .intro {{ font-size: 18px; line-height: 1.6; color: #d1d5db; margin-bottom: 40px; border-left: 4px solid #2563eb; padding-left: 20px; }}
            .article-card {{ background-color: #111111; border: 1px solid #222222; border-radius: 16px; padding: 24px; margin-bottom: 24px; }}
            .category {{ font-size: 10px; font-weight: 900; text-transform: uppercase; letter-spacing: 2px; color: #2563eb; margin-bottom: 8px; }}
            .title {{ font-size: 20px; font-weight: 800; margin-bottom: 12px; color: #ffffff; text-decoration: none; display: block; }}
            .gist {{ font-size: 14px; line-height: 1.5; color: #9ca3af; }}
            .footer {{ text-align: center; margin-top: 60px; padding-top: 40px; border-top: 1px solid #222222; color: #4b5563; font-size: 12px; }}
            .btn {{ display: inline-block; background-color: #2563eb; color: #ffffff; padding: 12px 24px; border-radius: 8px; font-weight: 900; text-decoration: none; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <img src="https://dailyaiwire.news/static/img/brand/logo_nodes.png" class="logo" alt="DailyAIWire">
                <div class="brand-name">DailyAI<span class="blue-text">Wire</span></div>
                <div style="font-size: 10px; color: #4b5563; margin-top: 5px; letter-spacing: 2px;">WEEKLY INTELLIGENCE REPORT</div>
            </div>
            
            <div class="intro">
                {nl['intro_text'].replace('\\n', '<br>')}
            </div>
            
            <div class="briefing-header" style="margin-bottom: 24px; font-weight: 900; font-size: 12px; color: #4b5563; text-transform: uppercase; letter-spacing: 3px;">
                The Signal // This Week
            </div>
    """
    
    for art in articles:
        html += f"""
            <div class="article-card">
                <div class="category">{art['category']}</div>
                <a href="https://dailyaiwire.news/article/{art['slug']}" class="title">{art['title']}</a>
                <div class="gist">{art['gist']}</div>
                <a href="https://dailyaiwire.news/article/{art['slug']}" class="btn">Analyze Full Signal</a>
            </div>
        """
        
    html += """
            <div class="footer">
                <p>&copy; 2025 DailyAIWire. All rights reserved.</p>
                <p>You received this because you tuned into the Wire.</p>
                <p><a href="https://dailyaiwire.news/unsubscribe" style="color: #4b5563;">Unsubscribe from Intelligence Feed</a></p>
            </div>
        </div>
    </body>
    </html>
    """
    return html

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
