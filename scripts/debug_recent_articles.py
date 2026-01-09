import sqlite3
import pandas as pd

try:
    conn = sqlite3.connect('news.db')
    query = "SELECT id, title, published_at, source FROM articles ORDER BY id DESC LIMIT 10"
    df = pd.read_sql_query(query, conn)
    print(df)
    conn.close()
except Exception as e:
    print(e)
