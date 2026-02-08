
import os
import sys
from dotenv import load_dotenv

# Load env
load_dotenv()

# Add root to path
sys.path.append(os.getcwd())

from services.proposal_agent import ProposalAgent
import sqlite3

def debug_proposal():
    # Find a lead
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "news.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    lead = conn.execute("SELECT id, title, domain FROM leads WHERE id = 13").fetchone()
    conn.close()
    
    if not lead:
        print("No leads found.")
        return

    print(f"Testing Proposal for Lead {lead['id']}: {lead['title']}")
    
    # Check Environment
    api_key = os.getenv("GEMINI_API_KEY")
    print(f"🔑 API Key Present: {'Yes' if api_key else 'NO'}")
    
    # Check Budget Explicitly
    from budget_tracker import BudgetTracker
    b = BudgetTracker()
    print(f"💰 Budget Check (300 tokens): {'PASS' if b.can_make_request(300) else 'FAIL'}")
    # print(f"   Current Usage: {b.get_usage()}")

    agent = ProposalAgent()
    try:
        result = agent.generate_pitch(lead['id'])
        if result:
            print("✅ Success:")
            # print(result[:100] + "...")
            
            # ATTEMPT SAVE
            print("💾 Attempting Save...")
            agent.save_draft(lead['id'], result)
            
            # Verify
            conn = sqlite3.connect(db_path)
            status = conn.execute("SELECT status FROM leads WHERE id = ?", (lead['id'],)).fetchone()[0]
            print(f"🕵️ Verification Status: {status}")
            conn.close()
            
        else:
            print("❌ Failed (Returned None)")
    except Exception as e:
        print(f"❌ Exception in agent: {e}")
    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    debug_proposal()
