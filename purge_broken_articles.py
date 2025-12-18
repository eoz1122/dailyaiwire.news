import sqlite3

def delete_broken_articles():
    DB_PATH = "news.db"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("🚀 Initiating purge of 'Source content missing' articles...")
    
    # Identify and delete articles with broken content signals
    cursor.execute('''
        DELETE FROM articles 
        WHERE LOWER(gist) LIKE '%source content missing%' 
           OR LOWER(why_it_matters) LIKE '%source content missing%'
           OR LOWER(title) LIKE '%source content missing%'
    ''')
    
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()
    
    print(f"✅ Purge complete. Removed {deleted_count} broken articles from the database.")

if __name__ == "__main__":
    delete_broken_articles()
