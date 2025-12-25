import sqlite3
import pandas as pd

try:
    conn = sqlite3.connect('news.db')
    query = "SELECT id, title, published_at, source, created_at FROM articles ORDER BY id DESC LIMIT 10" # 'created_at' might not exist, let's check schema first or just check published_at
    # Actually published_at is the article date, not when it was scraped.
    # The schema has `published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP` but usually fetcher inserts the article's publish date.
    
    # Let's check if there is a scraped_at or if published_at is reliable for "when it was added".
    # Schema check:
    # 56:             published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    # But in insert:
    # 516:                 original.get('published'),
    
    # So published_at is the External date.
    # The ID is valid for insertion order.
    
    query = "SELECT id, title, published_at, source FROM articles ORDER BY id DESC LIMIT 20"
    df = pd.read_sql_query(query, conn)
    print(df)
    conn.close()
except Exception as e:
    print(e)
