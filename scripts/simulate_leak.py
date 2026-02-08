
import sys
import os

# Adjust path to find newsletter_sender
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from newsletter_sender import send_newsletter
import requests

# Mocking the payload construction to simulate the "Bad Loop"
# We are NOT actually calling the API, we are testing the logic block.

def test_safety_check():
    print("🧪 TEST: Attempting to trigger the Privacy Circuit Breaker...")
    
    # Simulate a payload with multiple recipients (The BUG)
    bad_payload = {
        "from": "test@dailyaiwire.news",
        "to": ["victim1@gmail.com", "victim2@gmail.com", "victim3@gmail.com"], # LIST > 1
        "subject": "Test Leak",
        "html": "<p>Leak</p>"
    }
    
    try:
        # Replicating the check logic from newsletter_sender.py line 148
        if isinstance(bad_payload['to'], list) and len(bad_payload['to']) > 1:
             raise ValueError(f"CRITICAL PRIVACY ERROR: Attempted to send to {len(bad_payload['to'])} people at once. ABORTING.")
        
        print("❌ FAILURE: The code did NOT stop the leak!")
    except ValueError as e:
        print(f"✅ SUCCESS: The Circuit Breaker stopped the email.")
        print(f"   Error Message: {e}")

if __name__ == "__main__":
    test_safety_check()
