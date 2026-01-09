import requests
import feedparser
from bs4 import BeautifulSoup

def resolve_google_news_link(url):
    try:
        response = requests.get(url, allow_redirects=True, timeout=10)
        final_url = response.url
        if "news.google.com" in final_url:
            soup = BeautifulSoup(response.content, 'html.parser')
            # Check for meta refresh
            meta_refresh = soup.find('meta', attrs={'http-equiv': 'refresh'})
            if meta_refresh:
                content = meta_refresh.get('content', '')
                if 'url=' in content:
                    redirect_url = content.split('url=')[1]
                    return redirect_url
            
            # Check for link in a tag (often "Opening...")
            links = soup.find_all('a')
            for a in links:
                if a.get('href') and a.get('href').startswith('http'):
                    print(f"Found link: {a.get('href')}")
                    # return a.get('href') # unsafe to just return first link

        return final_url
    except Exception as e:
        print(f"Error: {e}")
        return url

feed = feedparser.parse('https://news.google.com/rss/search?q=Artificial+Intelligence+when:1d&hl=en-US&gl=US&ceid=US:en')
if feed.entries:
    link = feed.entries[0].link
    print(f"Original: {link}")
    resolved = resolve_google_news_link(link)
    print(f"Resolved: {resolved}")
