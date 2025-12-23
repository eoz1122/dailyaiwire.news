import sqlite3
import pytz
from datetime import datetime, timedelta
import os

DB_PATH = "news.db"
TIMEZONE = pytz.timezone("Europe/Berlin")
QUIET_START = 4
QUIET_END = 9
INTERVAL_SECONDS = 14400

def diagnose():
    print("\n" + "="*50)
    print("🔍 DailyAIWire Twitter Diagnostic Tool")
    print("="*50)
    
    # 1. System Info
    now_de = datetime.now(TIMEZONE)
    print(f"Current Time (DE):  {now_de.strftime('%Y-%m-%d %H:%M:%S')} (Hour: {now_de.hour})")
    
    # 2. Quiet Window Check
    is_quiet = QUIET_START <= now_de.hour < QUIET_END
    status_emoji = '🔴' if is_quiet else '🟢'
    print(f"Quiet Window:       {status_emoji} {'ACTIVE (Sleeping)' if is_quiet else 'INACTIVE (Running)'}")
    print(f"Allowed Window:     09:00 - 04:00 (Next day)")

    # 3. Database Check
    if not os.path.exists(DB_PATH):
        print(f"❌ Error: {DB_PATH} not found!")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Check for Articles
    try:
        total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        shared = conn.execute("SELECT COUNT(*) FROM articles WHERE shared_on_x = 1").fetchone()[0]
        unshared = conn.execute("SELECT COUNT(*) FROM articles WHERE shared_on_x = 0 OR shared_on_x IS NULL").fetchone()[0]
        
        # Newest Articles check
        latest_fetch = conn.execute("SELECT published_at FROM articles ORDER BY published_at DESC LIMIT 1").fetchone()
        
        print(f"\n--- Database Stats ---")
        print(f"Total Articles:     {total}")
        print(f"Already Posted:     {shared}")
        print(f"Waiting in Queue:   {unshared}")
        if latest_fetch:
            print(f"Latest Ingestion:   {latest_fetch[0]}")
        
        # 4. Recent Sharing Activity (Last 5)
        # Note: Since we don't have a shared_at timestamp, we look at newest articles marked as shared
        print(f"\n--- Newest Articles Marked Shared ---")
        recent_shared = conn.execute("""
            SELECT title, published_at FROM articles 
            WHERE shared_on_x = 1 
            ORDER BY published_at DESC LIMIT 5
        """).fetchall()
        
        if recent_shared:
            for i, art in enumerate(recent_shared):
                print(f"{i+1}. {art['title'][:60]}... (Pub: {art['published_at']})")
        else:
            print("No articles marked as shared yet.")

        # 5. Next in line
        print(f"\n--- Priority for Next Post ---")
        next_art = conn.execute("""
            SELECT title, published_at FROM articles 
            WHERE shared_on_x = 0 OR shared_on_x IS NULL 
            ORDER BY published_at DESC LIMIT 1
        """).fetchone()
        
        if next_art:
            print(f"🔥 Target: {next_art['title'][:60]}...")
            print(f"📅 Source Date: {next_art['published_at']}")
        else:
            print("📭 Queue is empty! Check fetcher.py logs.")

    except Exception as e:
        print(f"❌ Database Schema Error: {e}")
        print("   (Ensure shared_on_x column exists)")

    conn.close()
    print("\n" + "="*50)
    print("💡 Debugging Tips:")
    print("1. If 'Waiting in Queue' is 0: Your fetcher isn't finding new news.")
    print("2. If 'Waiting' is > 0 but nothing posts: Check 'twitter-error.log' for API errors.")
    print("3. Check 'twitter-access.log' to see if the script is sleeping or checking.")
    print("4. Try running the scheduler manually to see real-time errors:")
    print("   source venv/bin/activate && python tweet_scheduler.py")
    print("="*50 + "\n")

if __name__ == "__main__":
    diagnose()
