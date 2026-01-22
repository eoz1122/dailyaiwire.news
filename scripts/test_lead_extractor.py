
import sys
import os
sys.path.append(os.getcwd())
from services.lead_extractor import LeadExtractor

print("🧪 Testing Lead Extractor on a known target...")
extractor = LeadExtractor()

# Use a URL that likely has contact info or commercial intent
# We'll use a dummy "write for us" style url or a real one if we can guess.
# Let's try a generic techno-commercial site or a specific test case.
# Since I can't browse the web to find one easily without guessing, 
# I will use a simulated HTML content test directly if possible, 
# but the extractor fetches URL. 
# Let's try to fetch a real URL that is likely to have an email.
# Example: A tech blog or agency site. 
# Let's try 'https://dailyaiwire.news/contact' (our own site) just to see if it finds the email? 
# Or better, a known external site. 
# Let's try to extract from a dummy mocked fetch if possible, but the code calls trafilatura.fetch_url.
# I will try to extract from a real live URL: 'https://www.eriklabs.com/' (Competitor analysis showed this exists).
# It likely has contact info.

target_url = "https://www.eriklabs.com/"
print(f"Target: {target_url}")
extractor.extract_and_log(target_url, "Test Execution")
print("✅ Test Pulse Sent.")
