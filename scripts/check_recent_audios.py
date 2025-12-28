import sqlite3

def check_recent():
    conn = sqlite3.connect('news.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, slug, audio_male, audio_female, title FROM articles ORDER BY id DESC LIMIT 5')
    rows = cursor.fetchall()
    for r in rows:
        print(f"ID: {r[0]}, Title: {r[4][:30]}...")
        print(f"  Male: {r[2]}")
        print(f"  Female: {r[3]}")
    conn.close()

if __name__ == "__main__":
    check_recent()
