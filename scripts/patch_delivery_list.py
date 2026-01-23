import sqlite3
import os

DB_PATH = "news.db"

# List extracted from user screenshot of the "CC'd" email
ALREADY_SENT_EMAILS = [
    "mdshafeeq@gmail.com",
    "emreozen1122@hotmail.com",
    "damlauzunhan@hotmail.com",
    "ozen.ali.aaron@gmail.com",
    "emreozen1122@gmail.com",
    "caner.turkel@gmail.com",
    "deniz.eyvel@gmail.com",
    "sr.mohitkr@gmail.com",
    "santif@gmail.com"
]

NEWSLETTER_ID = 7

def patch_tracking():
    print("🩹 Patching Delivery Tracking...")
    
    if not os.path.exists(DB_PATH):
        print("❌ DB not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    added_count = 0
    
    for recipient in ALREADY_SENT_EMAILS:
        # Check if exists
        row = cursor.execute("SELECT id FROM newsletter_deliveries WHERE newsletter_id = ? AND recipient_email = ?", 
                             (NEWSLETTER_ID, recipient)).fetchone()
        
        if not row:
            cursor.execute("INSERT INTO newsletter_deliveries (newsletter_id, recipient_email, status) VALUES (?, ?, 'DELIVERED')",
                           (NEWSLETTER_ID, recipient))
            print(f"✅ Marked {recipient} as DELIVERED")
            added_count += 1
        else:
            print(f"ℹ️ {recipient} already marked.")

    conn.commit()
    conn.close()
    print(f"🏁 Patch Complete. Added {added_count} new exclusions.")

if __name__ == "__main__":
    patch_tracking()
