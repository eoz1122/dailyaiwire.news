
import os
import sqlite3
import sys
import json

# Robust Env Loading
def load_env_file():
    env_path = os.path.join(os.getcwd(), '.env')
    if os.path.exists(env_path):
        print(f"📄 Found .env at {env_path}")
        with open(env_path, 'r') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, val = line.strip().split('=', 1)
                    if not os.getenv(key):
                        os.environ[key] = val
    else:
        print("⚠️ No .env file found in CWD.")

load_env_file()

# Must have RESEND for this test
if not os.getenv("RESEND_API_KEY"):
    print("❌ ERROR: RESEND_API_KEY not set")

sys.path.append(os.getcwd())
# We import ProposalAgent but will mock the generate part to avoid Gemini issues
from services.proposal_agent import ProposalAgent

DB_PATH = "news.db"

def ensure_schema(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='leads'")
    if not cursor.fetchone():
        print("❌ Leads table missing!")
        return False
    # Assume schema is decent from previous runs
    return True

def run_verification():
    print("🕵️ STARING EMAIL SEND VERIFICATION (MOCK GEN)...")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        if not ensure_schema(conn): return
            
        test_email = "admin@dailyaiwire.news" 
        print(f"🧪 Creating Test Lead for: {test_email}")
        
        conn.execute("DELETE FROM leads WHERE title = 'IRON_JUDO_REV3_TARGET'")
        
        # Insert Lead
        conn.execute("""
            INSERT INTO leads (title, domain, detected_email, source_url, product_value, status, confidence_score)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            "IRON_JUDO_REV3_TARGET", 
            "example.com", 
            test_email, 
            "https://test.com/verification_v3", 
            "HIGH_VALUE", 
            "NEW", 
            99
        ))
        lead_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        conn.close()
        print(f"✅ Lead Created (ID: {lead_id})")
        
        # MOCK GENERATION (Skip Gemini)
        print("⏩ Skipping Gemini Generation (Mocking Draft)...")
        mock_draft = {
            "subject": "Iron Judo Link Test",
            "body_html": "<p>This is a verification email from the DailyAIWire Ad Engine.</p><p>If you see this, the Iron Judo pipe is FLOWING.</p>"
        }
        draft_json = json.dumps(mock_draft)
        
        agent = ProposalAgent()
        agent.save_draft(lead_id, draft_json)
        print("✅ Mock Draft Saved to DB")

        # TEST SENDING
        print("🚀 Sending via Resend...")
        success, msg = agent.send_active_proposal(lead_id)
        if success:
            print(f"✅ EMAIL SENT! Message: {msg}")
            print(f"📧 Check inbox for: {test_email}")
        else:
            print(f"❌ Sending Failed: {msg}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_verification()
