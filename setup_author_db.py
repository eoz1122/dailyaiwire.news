
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "news.db")

def init_author_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS author_config (
            id INTEGER PRIMARY KEY,
            name TEXT,
            title TEXT,
            bio TEXT,
            linkedin TEXT,
            image TEXT
        )
    ''')
    
    # Check if empty
    c.execute('SELECT COUNT(*) FROM author_config')
    if c.fetchone()[0] == 0:
        print("Initializing author config with default values...")
        c.execute('''
            INSERT INTO author_config (name, title, bio, linkedin, image)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            'Ali Emre Ozen', 
            'VP, Head of Ad Operations & Analytics', 
            "With 12 years in the programmatic space, I’ve managed complex campaigns across the US, UK, and Europe for both major agencies and global brands. Having mastered the full supply and demand ecosystem, I'm now focused on integrating AI and automation to streamline the heavy lifting of digital advertising.", 
            'https://www.linkedin.com/in/emreozen/',
            '/static/emre.jpg'
        ))
        conn.commit()
    else:
        print("Author config already exists.")
    
    conn.close()
    print("Author DB setup complete.")

if __name__ == '__main__':
    init_author_db()
