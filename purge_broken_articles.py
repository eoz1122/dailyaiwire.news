import sqlite3

def delete_broken_articles():
    DB_PATH = "news.db"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("🚀 Initiating purge of 'Source content missing' articles...")
    
    # Identify and delete articles with broken content signals or generic Google News images
    cursor.execute('''
        DELETE FROM articles 
        WHERE (LOWER(gist) LIKE '%source content missing%' 
           OR LOWER(why_it_matters) LIKE '%source content missing%'
           OR LOWER(title) LIKE '%source content missing%')
           OR (source = 'Google News' AND (image LIKE '%unsplash.com/photo-1677442136019-21780ecad995%' 
               OR image LIKE '%unsplash.com/photo-1485827404703-89b55fcc595e%'
               OR image LIKE '%unsplash.com/photo-1507679799987-c73779587ccf%'
               OR image LIKE '%unsplash.com/photo-1518770660439-4636190af475%'))
    ''')
    
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()
    
    print(f"✅ Purge complete. Removed {deleted_count} broken articles from the database.")

if __name__ == "__main__":
    delete_broken_articles()
