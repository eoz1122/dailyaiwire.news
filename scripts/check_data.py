import sqlite3
import json

def check_article():
    conn = sqlite3.connect("news.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Check for the specific article shown in the screenshot
    cursor.execute("SELECT title, gist, why_it_matters FROM articles WHERE title LIKE '%Google Launches%' LIMIT 1")
    row = cursor.fetchone()
    
    if row:
        with open("full_content_check.txt", "w", encoding="utf-8") as f:
            f.write(f"TITLE: {row['title']}\n")
            f.write(f"GIST: {row['gist']}\n")
            f.write(f"IMPACT: {row['why_it_matters']}\n")
        print("Done. Content written to full_content_check.txt")
    else:
        print("Article not found.")
            
    conn.close()

if __name__ == "__main__":
    check_article()
