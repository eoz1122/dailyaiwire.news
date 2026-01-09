import requests
import feedparser

def resolve_google_news_link(url):
    try:
        # Google News sometimes requires specific headers or cookies, but simple requests often work for RSS links
        # However, recently Google News links are obfuscated and might need decoding or proper following.
        # Let's try simple requests.get first.
        response = requests.get(url, allow_redirects=True, timeout=10)
        return response.url
    except Exception as e:
        print(f"Error: {e}")
        return url

feed = feedparser.parse('https://news.google.com/rss/search?q=Artificial+Intelligence+when:1d&hl=en-US&gl=US&ceid=US:en')
if feed.entries:
    link = feed.entries[0].link
    print(f"Original: {link}")
    resolved = resolve_google_news_link(link)
    print(f"Resolved: {resolved}")
else:
    print("No entries found")
