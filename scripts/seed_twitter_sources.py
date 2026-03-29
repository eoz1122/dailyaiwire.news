"""
Seed Twitter RSS sources into the DB using the local RSS-Bridge docker container.

Run once: python scripts/seed_twitter_sources.py
"""
import sqlite3

DB_PATH = "news.db"
LOCAL_BRIDGE_URL = "http://127.0.0.1:8333"

TWITTER_ACCOUNTS = [
    ("OpenAI", "@openai"),
    ("Anthropic AI", "@AnthropicAI"),
    ("Google DeepMind", "@GoogleDeepMind"),
    ("Sam Altman", "@sama"),
    ("Yann LeCun", "@ylecun"),
    ("Andrej Karpathy", "@karpathy"),
    ("Demis Hassabis", "@demishassabis"),
    ("Ilya Sutskever", "@ilyasut"),
    ("Gary Marcus", "@GaryMarcus"),
    ("Hugging Face", "@huggingface"),
    ("Mistral AI", "@MistralAI"),
    ("Scale AI", "@scale_ai"),
]

def seed_sources():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Ensure table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            url TEXT UNIQUE,
            category TEXT DEFAULT 'General',
            is_active BOOLEAN DEFAULT 1,
            last_scraped_at TIMESTAMP,
            consecutive_failures INTEGER DEFAULT 0,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Clear old Nitter sources completely
    cursor.execute("DELETE FROM sources WHERE category = 'Twitter'")
    deleted = cursor.rowcount
    print(f"🧹 Cleared {deleted} old obsolete Nitter sources.")

    inserted = 0

    for display_name, handle in TWITTER_ACCOUNTS:
        username = handle.lstrip("@")
        rss_url = f"{LOCAL_BRIDGE_URL}/?action=display&bridge=Twitter&context=By+username&u={username}&format=Atom"
        source_name = f"{display_name} (Twitter)"

        try:
            cursor.execute(
                "INSERT INTO sources (name, url, category, is_active) VALUES (?, ?, ?, 1)",
                (source_name, rss_url, "Twitter")
            )
            print(f"  + {source_name}")
            inserted += 1
        except sqlite3.IntegrityError:
            print(f"  - {source_name} already exists, skipping")

    conn.commit()
    conn.close()
    print(f"\n✅ Done: {inserted} local RSS-Bridge sources added.")

if __name__ == "__main__":
    print(f"\n🚀 Seeding Twitter sources using local RSS-Bridge: {LOCAL_BRIDGE_URL}\n")
    seed_sources()
