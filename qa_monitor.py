import requests
from bs4 import BeautifulSoup
import os
import sys

# PROTOCOL: CLOUDFLARE BYPASS
# Using a secret header to allow localhost/monitoring traffic to bypass typical blocks.
# Ensure your Nginx config allows this header or whitelist 127.0.0.1
MONITOR_USER_AGENT = "DailyAIWire-Monitor/1.0"
SECRET_HEADER_Token = os.getenv("MONITOR_SECRET_TOKEN", "internal_monitor_key")

def run_post_publication_audit(url: str):
    """
    Verifies that a newly published article renders correctly.
    Checks for: Headline (H1), Gist, and Read Full Story CTA.
    """
    print(f"🕵️ Starting QA Audit for: {url}")
    
    headers = {
        "User-Agent": MONITOR_USER_AGENT,
        "X-Monitoring-Token": SECRET_HEADER_Token
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"❌ QA FAILED: HTTP {response.status_code}")
            return False
            
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 1. VERIFY HEADLINE (H1)
        h1 = soup.find('h1')
        if not h1 or not h1.text.strip():
            print("❌ QA FAILED: H1 Headline missing or empty.")
            return False
        print(f"✅ Headline Detected: {h1.text.strip()[:30]}...")

        # 2. VERIFY "GIST" BLOCK
        # Looking for the specific "The Gist" header text
        gist_header = soup.find(string=lambda text: "the gist" in text.lower() if text else False)
        if not gist_header:
             print("❌ QA FAILED: 'The Gist' block missing.")
             return False
        print("✅ Gist Block Verified.")

        # 3. VERIFY CTA BUTTON
        # Looking for link that contains "Read Full Story"
        cta = soup.find('a', string=lambda text: "read full story" in text.lower() if text else False)
        # Note: Text might be inside a span, so we check stricter if needed.
        # Fallback check on href
        if not cta:
            cta = soup.find(lambda tag: tag.name == "a" and "Read Full Story" in tag.text)
            
        if not cta:
            print("❌ QA FAILED: 'Read Full Story' CTA missing.")
            return False
        print("✅ CTA Verified.")
        
        print("🎉 STATUS: SUCCESS. Article is live and healthy.")
        return True

    except Exception as e:
        print(f"❌ QA ERROR: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_post_publication_audit(sys.argv[1])
    else:
        print("Usage: python qa_monitor.py <url>")
