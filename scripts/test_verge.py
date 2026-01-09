import feedparser
import requests

url = "https://www.theverge.com/rss/artificial-intelligence/index.xml"

print(f"Testing URL: {url}")

# Method 1: requests with User-Agent
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

try:
    response = requests.get(url, headers=headers)
    print(f"Requests Status: {response.status_code}")
    if response.status_code == 200:
        print("Content fetched successfully.")
        # Parse content
        feed = feedparser.parse(response.content)
        print(f"Entries found via requests+feedparser: {len(feed.entries)}")
        if len(feed.entries) > 0:
            print(f"First entry: {feed.entries[0].title}")
    else:
        print("Failed to fetch with requests.")
except Exception as e:
    print(f"Requests Error: {e}")

# Method 2: pure feedparser (might be blocked)
print("\nTesting pure feedparser...")
feed_pure = feedparser.parse(url)
print(f"Entries found via pure feedparser: {len(feed_pure.entries)}")
if feed_pure.bozo:
    print(f"Bozo Error: {feed_pure.bozo_exception}")
