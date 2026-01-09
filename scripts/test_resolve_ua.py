import requests
import feedparser

def resolve_google_news_link(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    try:
        response = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Final URL: {response.url}")
        return response.url
    except Exception as e:
        print(f"Error: {e}")
        return url

feed = feedparser.parse('https://news.google.com/rss/search?q=Artificial+Intelligence+when:1d&hl=en-US&gl=US&ceid=US:en')
if feed.entries:
    link = feed.entries[0].link
    print(f"Original: {link}")
    resolve_google_news_link(link)
