import sqlite3
import os

DB_PATH = "news.db"

def init_tracking():
    print("🚀 Initializing Delivery Tracking...")
    
    if not os.path.exists(DB_PATH):
        print("❌ DB not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Create Table
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS newsletter_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                newsletter_id INTEGER,
                recipient_email TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT
            )
        ''')
        print("✅ Table 'newsletter_deliveries' created.")
    except Exception as e:
        print(f"Error creating table: {e}")

    # 2. Seed Data (The Fix)
    # Mark mdshafeeq@gmail.com as having received Newsletter #7
    # We verify if it exists first
    recipient = "mdshafeeq@gmail.com"
    newsletter_id = 7
    
    row = cursor.execute("SELECT id FROM newsletter_deliveries WHERE newsletter_id = ? AND recipient_email = ?", 
                         (newsletter_id, recipient)).fetchone()
    
    if not row:
        cursor.execute("INSERT INTO newsletter_deliveries (newsletter_id, recipient_email, status) VALUES (?, ?, 'DELIVERED')",
                       (newsletter_id, recipient))
        print(f"✅ Marked {recipient} as DELIVERED for Newsletter {newsletter_id}")
    else:
        print(f"ℹ️ {recipient} already marked as delivered.")

    # 3. Reset Newsletter Status so it can be 'Resumed'
    # We set it to DRAFT (or we could handle SENT, but the UI hides SENT buttons)
    # The user wants to send to the REST. So if we set to DRAFT, the new sender script
    # will iterate all subs, finding mdshafeeq is done, and send to others.
    cursor.execute("UPDATE newsletters SET status = 'DRAFT' WHERE id = ?", (newsletter_id,))
    print(f"✅ Reset Newsletter {newsletter_id} status to 'DRAFT' for resumption.")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_tracking()
