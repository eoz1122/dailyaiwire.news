
import os
import sqlite3
import google.generativeai as genai
from datetime import datetime

# Root imports
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from budget_tracker import BudgetTracker

DB_PATH = "news.db"
budget = BudgetTracker()

class ProposalAgent:
    def __init__(self):
        self.model_name = "gemini-2.0-flash-exp"
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

    def generate_pitch(self, lead_id: int):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        conn.close()

        if not lead:
            return None

        # 1. Budget Check
        if not budget.can_make_request(estimated_tokens=300):
            print("💰 Budget Guard: Skipping Layout Generation.")
            return None

        # 2. Determine Pricing Tier
        val = lead['product_value']
        if val == 'HIGH_VALUE':
            price_context = "Offer the 'Enterprise Sponsorship' pilot at $900/month."
        elif val == 'MID_VALUE':
            price_context = "Offer a 'Feature Spotlight' for $500 (one-time)."
        else:
            price_context = "Offer a 'Verified Link' slot for $150."

        # 3. Construct Prompt (The "Witty Judo" Structure)
        prompt = f"""
        You are an elite Sales Copywriter specializing in "Pattern Interrupts".
        
        GOAL: Write a witty, high-converting cold email to {lead['title']} (Domain: {lead['domain']}).
        CONTEXT: We found their content via: {lead['source_url']}.
        PRICING TIER: {val} -> {price_context}
        
        THE STRICT "JUDO" STRUCTURE:
        1. **The Hook (Wit):** Acknowledge their recent content, but call out the elephant in the room (they want AI users). Use a slightly cheeky/meta tone.
        2. **The "Keep It Real" Moment:** "Look, I know this was probably an SEO play or a PR blast..."
        3. **The Pivot (Value):** "But honestly? The product actually looks kinda useful for our audience."
        4. **The Mic Drop (Authority):** "We run DailyAIWire. We have the exact 10,000+ AI engineers you're trying to reach, but we don't do 'guest posts'. We do official sponsorships."
        5. **The Ask:** Mention the price: {price_context} "Want to lock this in? Reply 'Yes' and I'll send the invoice."

        TONE:
        - Confidential (like a whisper at a bar)
        - Short sentences.
        - No corporate jargon ("synergy", "solutioning").
        - Witty/Smart.
        
        OUTPUT FORMAT (JSON):
        {{
            "subject": "3-4 word pattern interrupt subject line",
            "body_html": "The email body in HTML. Use <br> for line breaks."
        }}
        """

        try:
            model = genai.GenerativeModel(self.model_name)
            response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
            
            # Log Usage
            if hasattr(response, 'usage_metadata'):
                budget.log_request(
                    getattr(response.usage_metadata, 'prompt_token_count', 0),
                    getattr(response.usage_metadata, 'candidates_token_count', 0),
                    category="Proposal Gen"
                )

            return response.text # Returns JSON string
            
        except Exception as e:
            print(f"Proposal Generation Error: {e}")
            return None

    def save_draft(self, lead_id, draft_json):
        """Saves the generated draft to the leads table."""
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute('UPDATE leads SET draft_proposal = ?, status = "DRAFT_READY" WHERE id = ?', 
                        (draft_json, lead_id))
            conn.commit()
            print(f"💾 Draft saved for Lead {lead_id}")
        except Exception as e:
            print(f"Error saving draft: {e}")
        finally:
            conn.close()

    def send_active_proposal(self, lead_id):
        """Sends the saved draft via Resend."""
        import requests
        import json
        
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        
        if not lead or not lead['draft_proposal']:
            conn.close()
            return False, "No draft found"
            
        draft = json.loads(lead['draft_proposal'])
        recipient = lead['detected_email']
        subject = draft['subject']
        html_body = draft['body_html']
        
        # Resend API
        api_key = os.getenv("RESEND_API_KEY")
        if not api_key:
            conn.close()
            return False, "No Resend API Key"
            
        url = "https://api.resend.com/emails"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "from": "DailyAIWire Partnerships <partners@dailyaiwire.news>",
            "reply_to": "admin@dailyaiwire.news",
            "to": [recipient],
            "bcc": ["admin@dailyaiwire.news"], # Safety copy
            "subject": subject,
            "html": html_body
        }
        
        try:
            resp = requests.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                conn.execute("UPDATE leads SET status = 'PROPOSAL_SENT' WHERE id = ?", (lead_id,))
                conn.commit()
                conn.close()
                return True, "Sent"
            else:
                conn.close()
                return False, f"Resend API Error: {resp.text}"
        except Exception as e:
            conn.close()
            return False, str(e)

if __name__ == "__main__":
    agent = ProposalAgent()
    # Test with a dummy ID (assuming 1 exists)
    print(agent.generate_pitch(1))
