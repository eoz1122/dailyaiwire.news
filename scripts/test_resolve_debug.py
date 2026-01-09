import requests
import feedparser

def resolve_google_news_link(url):
    try:
        response = requests.get(url, allow_redirects=True, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Final URL: {response.url}")
        if "news.google.com" in response.url:
            print("Content preview:")
            print(response.text[:500])
        return response.url
    except Exception as e:
        print(f"Error: {e}")
        return url

feed = feedparser.parse('https://news.google.com/rss/search?q=Artificial+Intelligence+when:1d&hl=en-US&gl=US&ceid=US:en')
if feed.entries:
    link = feed.entries[0].link
    print(f"Original: {link}")
    resolved = resolve_google_news_link(link)
else:
    print("No entries found")
