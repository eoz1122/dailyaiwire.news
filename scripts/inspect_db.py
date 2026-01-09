import sqlite3

def check_schema():
    conn = sqlite3.connect("news.db")
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(articles)")
    columns = cursor.fetchall()
    print("Columns in articles table:")
    for col in columns:
        print(col)
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print("\nTables in DB:")
    for table in tables:
        print(table)
    
    conn.close()

if __name__ == "__main__":
    check_schema()
