
import os
import re
import sqlite3
import trafilatura
from urllib.parse import urlparse
import google.generativeai as genai

# Using absolute import for root modules
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from budget_tracker import BudgetTracker

DB_PATH = "news.db"
budget = BudgetTracker()

class LeadExtractor:
    def __init__(self):
        self.model_name = "gemini-2.0-flash-exp" # Low cost model
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

    def _cheap_heuristic_filter(self, html_content: str, url: str) -> bool:
        """
        Layer 1: Zero-Cost Regex Filter.
        Returns True if the page looks like it has commercial intent or contact info.
        """
        if not html_content:
            return False

        # 1. Keywords (Commercial Intent)
        keywords = [
            r"write for us", r"advertising", r"sponsor", r"media kit", 
            r"contact us", r"get in touch", r"partnership", r"collaborate"
        ]
        
        # 2. Email Patterns (The Prize)
        # Simple regex for mailto: or email-like strings
        email_pattern = r'mailto:[\w\.-]+@[\w\.-]+'
        
        content_lower = html_content.lower()
        
        # Check Keywords
        for k in keywords:
            if re.search(k, content_lower):
                print(f"🎯 Heuristic Hit: '{k}' found in {url}")
                return True
                
        # Check Emails
        if re.search(email_pattern, content_lower):
             print(f"🎯 Heuristic Hit: Email pattern found in {url}")
             return True
             
        return False

    def extract_and_log(self, url: str, source_title: str):
        """
        Main pipeline: Fetch -> Filter -> LLM Extract -> Save to DB
        """
        # 1. Check Budget & Safety
        if not budget.can_make_request(estimated_tokens=500):
            print("💰 Budget Guard: Skipping Lead Extraction.")
            return

        # 2. Fetch Content
        print(f"🕵️ Investigating potential lead: {url}")
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return

        # 3. Layer 1: Heuristic Filter (Cost: $0)
        if not self._cheap_heuristic_filter(downloaded, url):
            print("Start of Lead Extraction Pipeline - Failed Heuristic Check. Skipping LLM.")
            return

        # 4. Layer 2: LLM Extraction (Cost: Low)
        text_content = trafilatura.extract(downloaded) or ""
        text_preview = text_content[:4000] # Limit tokens
        
        prompt = f"""
        Analyze this webpage to extract contact info AND estimate the "Product Value" of the entity behind it.
        
        Is this a:
        - "HIGH_VALUE": Venture-backed SaaS, established agency, or high-ticket B2B service?
        - "MID_VALUE": Indie developer tool, paid course, or affiliate product?
        - "LOW_VALUE": SEO spam blog, cheap script, or generic dropshipping?

        JSON ONLY. No markdown.
        Format: {{ 
            "company_name": "string", 
            "email": "string", 
            "confidence": 0-100,
            "product_value": "HIGH_VALUE | MID_VALUE | LOW_VALUE",
            "reason": "Why is it high/low value? (Max 10 words)"
        }}
        
        TEXT:
        {text_preview}
        """
        
        try:
            model = genai.GenerativeModel(self.model_name)
            response = model.generate_content(prompt)
            
            # Log Cost
            if hasattr(response, 'usage_metadata'):
                budget.log_request(
                    getattr(response.usage_metadata, 'prompt_token_count', 0),
                    getattr(response.usage_metadata, 'candidates_token_count', 0),
                    category="Lead Extraction"
                )

            # Parse JSON
            result_text = response.text.replace('```json', '').replace('```', '').strip()
            import json
            data = json.loads(result_text)
            
            email = data.get("email")
            company = data.get("company_name")
            confidence = data.get("confidence", 0)
            value = data.get("product_value", "LOW_VALUE")
            reason = data.get("reason", "")

            # --- DEEP CRAWL: If no email, check /contact or /about ---
            if not email or confidence < 40:
                print(f"   Searching for Contact Page on {url}...")
                email, secondary_source  = self._hunt_for_contact_email(url)
                if email:
                    print(f"   🎯 Found email on secondary page: {email}")
                    confidence = 85 # Boost confidence if found on contact page
                    # Re-verify company name if needed, or keep existing
            # ---------------------------------------------------------

            if email:
                print(f"🤑 LEAD CAPTURED: {company} ({email}) - {value}")
                self._save_lead(url, source_title, company, email, confidence, value, reason)
            else:
                print("No high-quality lead found (checked article + contact pages).")

        except Exception as e:
            print(f"Extraction Error: {e}")

    def _hunt_for_contact_email(self, original_url):
        """
        Tries to guess and scrape the contact page.
        Returns: (email, source_url)
        """
        from urllib.parse import urljoin
        base_domain = urlparse(original_url).scheme + "://" + urlparse(original_url).netloc
        
        # Common endpoint guesses
        guesses = ["/contact", "/contact-us", "/about", "/about-us", "/advertise"]
        
        email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
        
        for path in guesses:
            target_url = urljoin(base_domain, path)
            try:
                # Quick fetch
                downloaded = trafilatura.fetch_url(target_url)
                if downloaded:
                    text = trafilatura.extract(downloaded)
                    if not text: continue
                    
                    # Simple Regex Search first (Cheap)
                    match = re.search(email_pattern, text)
                    if match:
                        found_email = match.group(0)
                        # Filter out common false positives
                        if not any(x in found_email for x in ['example.com', 'domain.com', 'sentry.io', 'wixpress']):
                            return found_email, target_url
            except:
                continue
                
        return None, None

    def _save_lead(self, url, title, company, email, score, value, reason):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            # Lazy migration in case columns don't exist yet (handled by separate script, but safe fallback)
            cursor.execute('''
                INSERT INTO leads (domain, source_url, title, detected_email, confidence_score, product_value, opportunity_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (urlparse(url).netloc, url, company or title, email, score, value, reason))
            conn.commit()
        except sqlite3.IntegrityError:
            print("Lead already exists.")
        except sqlite3.OperationalError:
             print("⚠️ DB Error: Columns missing. Run migration.")
        finally:
            conn.close()

if __name__ == "__main__":
    # Test Run
    extractor = LeadExtractor()
    extractor.extract_and_log("https://example.com", "Test Source")
