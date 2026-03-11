
import os
import re
import subprocess

APP_FILE = "app.py"
NEWSLETTER_SENDER = "newsletter_sender.py"
THANK_YOU_TEMPLATE = "templates/thank_you.html"
WELCOME_EMAIL_TEMPLATE = "templates/email/welcome.html"

def run(cmd):
    print(f"Running: {cmd}")
    subprocess.run(cmd, shell=True)

def update_files():
    print("--- 1. Creating Welcome Email Template ---")
    os.makedirs("templates/email", exist_ok=True)
    with open(WELCOME_EMAIL_TEMPLATE, "w") as f:
        f.write("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Welcome to the Wire</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap');
        body { font-family: 'Inter', sans-serif; background-color: #fcfcfc; color: #0c0c0c; margin: 0; padding: 0; }
        .wrapper { width: 100%; background-color: #fcfcfc; padding-bottom: 60px; }
        .container { max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 40px; border: 1px solid #e4e4e7; border-radius: 24px; margin-top: 40px; }
        .logo { width: 60px; height: 60px; background-color: #f4f4f5; border-radius: 16px; padding: 8px; margin-bottom: 20px; }
        .h1 { font-size: 24px; font-weight: 900; letter-spacing: -1px; margin-bottom: 20px; }
        .p { font-size: 16px; line-height: 1.6; color: #52525b; margin-bottom: 24px; }
        .btn { display: inline-block; background-color: #2563eb; color: #ffffff; padding: 12px 24px; border-radius: 12px; text-decoration: none; font-weight: 700; font-size: 14px; }
    </style>
</head>
<body>
    <div class="wrapper">
        <div class="container">
            <img src="https://dailyaiwire.news/static/img/brand/logo_nodes.png" class="logo" alt="DailyAIWire">
            <div class="h1">Signal Acquired.</div>
            <p class="p">You have successfully connected to the Daily AI Wire.</p>
            <p class="p">This is your confirmation that you are now part of our autonomous intelligence network. Expect your first briefing this Sunday.</p>
            <p class="p">We filter the noise so you can focus on the signal.</p>
            <a href="https://dailyaiwire.news" class="btn">Access the Lab</a>
        </div>
    </div>
</body>
</html>""")

    print("--- 2. Updating Thank You Page (Light Mode) ---")
    with open(THANK_YOU_TEMPLATE, "w") as f:
        f.write("""{% extends "base.html" %}
{% block title %}Connection Established // The Signal{% endblock %}
{% block content %}
<div class="min-h-[85vh] flex items-center justify-center p-4 relative py-20">
    <!-- Light Background Overlay -->
    <div class="absolute inset-0 bg-[#F8FAFC] z-0"></div>

    <div class="relative z-10 max-w-2xl w-full bg-white rounded-[2rem] shadow-[0_20px_60px_-15px_rgba(0,0,0,0.1)] p-8 md:p-16 text-center border border-gray-100">
        
        <!-- Success Icon -->
        <div class="w-16 h-16 bg-green-50 rounded-full flex items-center justify-center mx-auto mb-8 shadow-sm">
            <svg class="w-6 h-6 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"></path>
            </svg>
        </div>

        <h1 class="text-4xl md:text-5xl font-black text-gray-900 mb-6 tracking-tight leading-none font-['Outfit'] uppercase">
            Connection<br>
            <span class="text-green-500">Established</span>
        </h1>

        <div class="w-16 h-1 bg-gradient-to-r from-blue-500 to-green-400 mx-auto mb-8 rounded-full"></div>

        <p class="text-xl text-gray-600 mb-10 leading-relaxed font-medium">
            Welcome to the inner circle. Your intelligence feed has been successfully activated.
        </p>

        <!-- Briefing Protocol Box -->
        <div class="bg-gray-50 rounded-2xl p-8 mb-10 text-left border border-gray-100">
            <h3 class="text-gray-900 font-bold uppercase tracking-widest text-xs mb-4 flex items-center gap-2">
                <svg class="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                </svg>
                Briefing Protocol
            </h3>
            <ul class="space-y-4 text-gray-600 text-sm font-medium">
                <li class="flex items-start gap-3">
                    <span class="text-green-500 mt-0.5 font-bold">✓</span>
                    <span><strong class="text-gray-900">Check your inbox:</strong> A confirmation signal is pending.</span>
                </li>
                <li class="flex items-start gap-3">
                    <span class="text-green-500 mt-0.5 font-bold">✓</span>
                    <span><strong class="text-gray-900">Mark as Safe:</strong> Ensure <em>briefing@dailyaiwire.news</em> is not filtered to spam.</span>
                </li>
                <li class="flex items-start gap-3">
                    <span class="text-green-500 mt-0.5 font-bold">✓</span>
                    <span><strong class="text-gray-900">Frequency:</strong> Expect high-signal updates every Sunday.</span>
                </li>
            </ul>
        </div>

        <div class="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <a href="/" class="text-gray-900 font-black uppercase tracking-widest text-xs hover:text-blue-600 transition-colors px-6 py-3">
                Return to Wire
            </a>
            <a href="/lab" class="px-8 py-4 bg-transparent border-2 border-gray-900 text-gray-900 font-black uppercase tracking-widest text-xs rounded-full hover:bg-gray-900 hover:text-white transition-all">
                Enter the Lab
            </a>
        </div>
    </div>
</div>
{% endblock %}""")

    print("--- 3. Updating Newsletter Sender (Adding logic) ---")
    with open(NEWSLETTER_SENDER, "r") as f:
        content = f.read()
    
    if "def send_welcome_email" not in content:
        sender_logic = """
SENDER_EMAIL = "briefing@dailyaiwire.news" 

def send_welcome_email(recipient_email):
    if not RESEND_API_KEY:
        print("Error: No API Key")
        return False
    
    print(f"Sending welcome email to {recipient_email}...")
    try:
        from flask import render_template
        from app import app
        with app.app_context():
            html_content = render_template('email/welcome.html')
    except Exception:
        html_content = "<h1>Welcome</h1><p>You are subscribed.</p>"

    url = "https://api.resend.com/emails"
    headers = {"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "from": f"DailyAIWire <{SENDER_EMAIL}>",
        "to": [recipient_email],
        "subject": "Connection Established // DailyAIWire",
        "html": html_content
    }
    requests.post(url, headers=headers, json=payload)
    print("Welcome email sent.")
"""
        content = content.replace('RESEND_API_KEY = os.getenv("RESEND_API_KEY")', 'RESEND_API_KEY = os.getenv("RESEND_API_KEY")\n' + sender_logic)
        with open(NEWSLETTER_SENDER, "w") as f:
            f.write(content)

    print("--- 4. Patching App.py (Triggering Email) ---")
    with open(APP_FILE, "r") as f:
        app_content = f.read()
    
    # Simple replace to inject the call
    if "send_welcome_email(email)" not in app_content:
        # We need to be careful with indentation here.
        # We will replace the commit line with commit + send
        app_content = app_content.replace(
            "conn.commit()\n                    return redirect(url_for('thank_you_page'))",
            """conn.commit()
                    # --- Send Welcome Email ---
                    try:
                        from newsletter_sender import send_welcome_email
                        send_welcome_email(email)
                    except Exception as e:
                        print(f"Email failed: {e}")
                    # --------------------------
                    return redirect(url_for('thank_you_page'))"""
        )
        with open(APP_FILE, "w") as f:
            f.write(app_content)

if __name__ == "__main__":
    update_files()
    print("--- Restarting Service ---")
    run("sudo supervisorctl restart dailyaiwire")
    print("DONE! Welcome email & New UI Deployed.")
