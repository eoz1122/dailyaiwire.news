import sqlite3
import datetime

DB_PATH = "news.db"

def reset_scan_time():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Set to 24 hours ago
    new_time = (datetime.datetime.utcnow() - datetime.timedelta(hours=24)).isoformat()
    
    print(f"Resetting last_scan_timestamp to: {new_time}")
    cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_scan_timestamp', ?)", (new_time,))
    
    conn.commit()
    conn.close()
    print("Done. Run fetcher.py now.")

if __name__ == "__main__":
    reset_scan_time()
