import os
import requests
import time
from dotenv import load_dotenv

load_dotenv()

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

# The 3 emails that failed with 429
FAILED_RECIPIENTS = [
    "damlauzunhan@hotmail.com",
    "caner.turkel@gmail.com",
    "santif@gmail.com"
]

def retry_apology():
    if not RESEND_API_KEY:
        print("❌ RESEND_API_KEY missing.")
        return

    print(f"🚨 Retrying Apology for {len(FAILED_RECIPIENTS)} failed recipients...")
    print("---------------------------------------------------")

    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }

    for email in FAILED_RECIPIENTS:
        payload = {
            "from": SENDER_EMAIL,
            "to": [email],
            "subject": SUBJECT,
            "html": BODY_HTML
        }

        try:
            print(f"👉 Retrying {email}...", end=" ", flush=True)
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code in [200, 201]:
                print("✅ SENT")
            else:
                print(f"❌ FAILED ({response.status_code}) - {response.text}")
            
            # Increased delay to 2.0 seconds to be absolutely safe
            time.sleep(2.0)
            
        except Exception as e:
            print(f"❌ ERROR: {e}")

    print("---------------------------------------------------")
    print(f"🏁 Retry Complete.")

if __name__ == "__main__":
    retry_apology()
