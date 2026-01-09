import feedparser

feed = feedparser.parse('https://news.google.com/rss/search?q=Artificial+Intelligence+when:1d&hl=en-US&gl=US&ceid=US:en')
if feed.entries:
    entry = feed.entries[0]
    print(entry.keys())
    if 'source' in entry:
        print(f"Source: {entry.source}")
    print(f"Title: {entry.title}")
