import requests
import feedparser

sources = [
    ("Ben's Bites", "https://bensbites.beehiiv.com/feed"),
    ("MIT Technology Review", "https://www.technologyreview.com/feed/topic/artificial-intelligence"),
    ("VentureBeat", "https://venturebeat.com/category/ai/feed/"),
    ("Import AI", "https://importai.substack.com/feed"),
    ("The Verge", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml")
]

print("🔍 Testing Feed Connectivity & Parsing...\n")

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

for name, url in sources:
    try:
        print(f"Testing {name}...", end=" ", flush=True)
        resp = requests.get(url, headers=headers, timeout=10)
        
        if resp.status_code == 200:
            # excessive check: is it valid XML/RSS?
            feed = feedparser.parse(resp.content)
            if feed.bozo and feed.bozo_exception:
                print(f"⚠️  200 OK, but Parse Warning: {feed.bozo_exception}")
            elif len(feed.entries) == 0:
                print(f"⚠️  200 OK, but Standard RSS Empty (Might be HTML?)")
            else:
                print(f"✅  OK ({len(feed.entries)} items)")
        else:
            print(f"❌  Failed: HTTP {resp.status_code}")
    except Exception as e:
        print(f"❌  Error: {e}")

print("\nDone.")
