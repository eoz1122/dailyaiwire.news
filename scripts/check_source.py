import feedparser

feed = feedparser.parse('https://news.google.com/rss/search?q=Artificial+Intelligence+when:1d&hl=en-US&gl=US&ceid=US:en')
if feed.entries:
    entry = feed.entries[0]
    print(f"Has source key: {'source' in entry}")
    if 'source' in entry:
        print(f"Source value: {entry.source}")
