import sqlite3
import os
import sys
import re
import json
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

# Add path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.lead_extractor import LeadExtractor
from urllib.parse import urlparse
import google.generativeai as genai

class AggressiveLeadExtractor(LeadExtractor):
    def _cheap_heuristic_filter(self, html_content: str, url: str) -> bool:
        print(f"   🔥 AGGRESSIVE MODE: Bypassing heuristic check for {url}")
        return True

    def extract_and_log(self, url: str, source_title: str):
        # 1. Budget check skipped for manual override
        
        # 2. Fetch
        import trafilatura
        print(f"   🕵️ Deep Scanning: {url}")
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            print("   ❌ Failed to download.")
            return

        # 3. LLM Extraction
        text_content = trafilatura.extract(downloaded) or ""
        text_preview = text_content[:6000] # Increased token limit for aggressive scan
        
        prompt = f"""
        Analyze this webpage for a startup/business.
        1. Extract the 'company_name'.
        2. Extract ANY contact email (look for support@, hello@, founders@) or "No Email".
        3. Estimate 'product_value' (HIGH_VALUE for SaaS/AI/B2B, MID for Tools, LOW for Spam).
        4. Confidence 0-100.
        
        JSON ONLY.
        {{ 
            "company_name": "string", 
            "email": "string", 
            "confidence": int,
            "product_value": "string",
            "reason": "string"
        }}
        
        TEXT:
        {text_preview}
        """
        
        try:
            model = genai.GenerativeModel(self.model_name)
            response = model.generate_content(prompt)
            
            # Simple clean
            txt = response.text.replace('```json', '').replace('```', '').strip()
            data = json.loads(txt)
            
            email = data.get("email")
            if email and "no email" in email.lower():
                email = None
                
            company = data.get("company_name")
            value = data.get("product_value", "LOW_VALUE")
            # Force high confidence for manual targets if they look like real businesses
            confidence = data.get("confidence", 50) 
            
            # --- AGGRESSIVE CONTACT HUNT ---
            if not email:
                print("   🦅 No email in main text. Hunting contact pages...")
                found_email, _ = self._hunt_for_contact_email(url)
                if found_email:
                    email = found_email
                    confidence = 90
                    print(f"   🎯 Found email: {email}")
            
            # --- SAVE EVEN IF NO EMAIL (If High/Mid Value) ---
            if email or value in ["HIGH_VALUE", "MID_VALUE"]:
                
                final_email = email or "MANUAL_LOOKUP_REQUIRED"
                print(f"   💾 SAVING CANDIDATE: {company} | {final_email} | {value}")
                
                self._save_lead(url, source_title, company, final_email, confidence, value, data.get("reason", "Aggressive Scan"))
            else:
                print(f"   🗑️ Discarding Low Value: {company} ({value})")

        except Exception as e:
            print(f"   ❌ Extraction Error: {e}")

def process():
    print("🚀 Starting Aggressive Recovery...")
    conn = sqlite3.connect('news.db')
    cursor = conn.cursor()
    
    # Get URL column
    cursor.execute("PRAGMA table_info(articles)")
    cols = [c[1] for c in cursor.fetchall()]
    url_col = 'source_url' if 'source_url' in cols else 'url'
    if 'original_url' in cols: url_col = 'original_url'
    
    # Get Manually Killed
    cursor.execute(f"SELECT {url_col}, title FROM articles WHERE is_published = 0")
    rows = cursor.fetchall()
    conn.close()
    
    extractor = AggressiveLeadExtractor()
    
    for url, title in rows:
        # Check if already has a VALID lead (with email)
        check_conn = sqlite3.connect('news.db')
        check_cur = check_conn.cursor()
        domain = urlparse(url).netloc
        # If we have a lead with an actual email, skip. If it's partial, maybe update? 
        # For now, let's just process everything that isn't a "perfect" lead.
        check_cur.execute("SELECT detected_email FROM leads WHERE domain = ?", (domain,))
        existing = check_cur.fetchone()
        check_conn.close()
        
        if existing and existing[0] and '@' in existing[0] and 'MANUAL' not in existing[0]:
             print(f"⏩ Skipping {domain} (Already good lead: {existing[0]})")
             continue
             
        # Run Aggressive
        print(f"\n⚡ AGGRESSIVE SCAN: {title}")
        extractor.extract_and_log(url, title)

if __name__ == "__main__":
    process()
