import sqlite3
import os
import requests
import time
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "news.db"
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
SENDER_EMAIL = "DailyAIWire <intelligence@dailyaiwire.news>"

SUBJECT = "Important: Apology regarding subscriber privacy"

BODY_HTML = """
<div style="font-family: sans-serif; font-size: 16px; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <p>Hello,</p>
    
    <p>I am writing to sincerely apologize for a privacy oversight in our recent newsletter broadcast. Due to a technical configuration error on our side, recipient email addresses were visible in the "To" field of the previous message.</p>
    
    <p><strong>We have identified the issue and have already deployed a fix.</strong> The broadcasting system has been updated to ensure that all future communications are strictly individual and secure.</p>
    
    <p>I understand that privacy is paramount, and I deeply regret this mistake. We value your trust and are committed to improving our systems to ensure this does not happen again.</p>
    
    <p>Sincerely,</p>
    <p><strong>The DailyAIWire Team</strong></p>
</div>
"""

def get_active_subscribers():
    if not os.path.exists(DB_PATH):
        print("❌ Database not found.")
        return []
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM subscribers WHERE status = 'ACTIVE'")
    subs = [row[0] for row in cursor.fetchall()]
    conn.close()
    return subs

def send_apology():
    if not RESEND_API_KEY:
        print("❌ RESEND_API_KEY missing.")
        return

    subscribers = get_active_subscribers()
    if not subscribers:
        print("📭 No subscribers found.")
        return

    print(f"🚨 Initiating Apology Broadcast to {len(subscribers)} subscribers...")
    print("---------------------------------------------------")
    print(f"Subject: {SUBJECT}")
    print("---------------------------------------------------")

    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }

    success_count = 0
    fail_count = 0

    for email in subscribers:
        # Safety Check: Individual Send
        payload = {
            "from": SENDER_EMAIL,
            "to": [email], # STRICTLY SINGLE RECIPIENT
            "subject": SUBJECT,
            "html": BODY_HTML
        }

        try:
            print(f"👉 Sending to {email}...", end=" ", flush=True)
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code in [200, 201]:
                print("✅ SENT")
                success_count += 1
            else:
                print(f"❌ FAILED ({response.status_code})")
                fail_count += 1
            
            # Rate limit politeness
            time.sleep(0.2)
            
        except Exception as e:
            print(f"❌ ERROR: {e}")
            fail_count += 1

    print("---------------------------------------------------")
    print(f"🏁 Broadcast Complete. Success: {success_count}, Failed: {fail_count}")

if __name__ == "__main__":
    confirm = input("Type 'CONFIRM' to send this apology to ALL active subscribers: ")
    if confirm == "CONFIRM":
        send_apology()
    else:
        print("❌ Operation cancelled.")
