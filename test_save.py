
import os
import sys
import sqlite3

# Add root to path
sys.path.append(os.getcwd())

from services.proposal_agent import ProposalAgent

def test_save():
    agent = ProposalAgent()
    # Find a lead
    conn = sqlite3.connect('news.db')
    conn.row_factory = sqlite3.Row
    lead = conn.execute("SELECT id FROM leads LIMIT 1").fetchone()
    conn.close()
    
    if not lead:
        print("No leads.")
        return

    print(f"Testing Save for Lead {lead['id']}")
    dummy_json = '{"subject": "Test", "body_html": "<p>Test</p>"}'
    
    agent.save_draft(lead['id'], dummy_json)
    
    # Verify
    conn = sqlite3.connect('news.db')
    row = conn.execute("SELECT status, draft_proposal FROM leads WHERE id = ?", (lead['id'],)).fetchone()
    print(f"Status: {row[0]}")
    print(f"Draft: {row[1]}")
    conn.close()

if __name__ == "__main__":
    test_save()
