import trafilatura
import feedparser
import json

def test_trafilatura(url):
    downloaded = trafilatura.fetch_url(url)
    if downloaded:
        metadata = trafilatura.extract_metadata(downloaded)
        if metadata:
            print(f"Sitename: {metadata.sitename}")
            print(f"URL: {metadata.url}")
            print(f"Title: {metadata.title}")
            print(f"Author: {metadata.author}")
        else:
            print("No metadata extracted")
    else:
        print("Download failed")

feed = feedparser.parse('https://news.google.com/rss/search?q=Artificial+Intelligence+when:1d&hl=en-US&gl=US&ceid=US:en')
if feed.entries:
    link = feed.entries[0].link
    print(f"Testing link: {link}")
    test_trafilatura(link)
