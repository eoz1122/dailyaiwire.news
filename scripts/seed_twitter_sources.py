"""
Seed Twitter/Nitter RSS sources into the sources table.

Finds a healthy Nitter instance, then inserts RSS feeds for key AI accounts.
Run once: python scripts/seed_twitter_sources.py

To test a different instance or add accounts, edit NITTER_INSTANCES and TWITTER_ACCOUNTS below.
"""
import sqlite3
import sys
import requests

DB_PATH = "news.db"

# Ordered by reliability - script picks the first healthy one
NITTER_INSTANCES = [
    "nitter.poast.org",
    "nitter.privacydev.net",
    "nitter.1d4.us",
    "nitter.kavin.rocks",
    "nitter.catsarch.com",
]

# Key AI accounts to follow
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


def find_healthy_instance() -> str | None:
    """Returns the first Nitter instance that responds with a valid RSS feed."""
    test_account = "openai"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; DailyAIWire/1.0)"}

    for instance in NITTER_INSTANCES:
        url = f"https://{instance}/{test_account}/rss"
        try:
            r = requests.get(url, headers=headers, timeout=8)
            if r.status_code == 200 and "<rss" in r.text[:500]:
                print(f"  Healthy instance found: {instance}")
                return instance
            else:
                print(f"  {instance} - HTTP {r.status_code}, skipping")
        except Exception as e:
            print(f"  {instance} - unreachable ({e}), skipping")

    return None


def seed_sources(instance: str):
    """Inserts Nitter RSS sources into the sources table."""
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

    inserted = 0
    skipped = 0

    for display_name, handle in TWITTER_ACCOUNTS:
        username = handle.lstrip("@")
        rss_url = f"https://{instance}/{username}/rss"
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
            skipped += 1

    conn.commit()
    conn.close()
    print(f"\nDone: {inserted} added, {skipped} already existed.")
    print(f"Instance in use: {instance}")
    print("\nTo switch instance later, run:")
    print(f"  python scripts/seed_twitter_sources.py --instance <hostname>")


def update_instance(new_instance: str):
    """Updates all existing Twitter sources to use a different Nitter instance."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, url FROM sources WHERE category = 'Twitter'")
    rows = cursor.fetchall()

    if not rows:
        print("No Twitter sources found in DB.")
        conn.close()
        return

    for row_id, old_url in rows:
        # Replace the old instance hostname with the new one
        parts = old_url.split("/")
        if len(parts) >= 3:
            parts[2] = new_instance
            new_url = "/".join(parts)
            cursor.execute("UPDATE sources SET url = ? WHERE id = ?", (new_url, row_id))
            print(f"  Updated: {new_url}")

    conn.commit()
    conn.close()
    print(f"\nAll Twitter sources now point to: {new_instance}")


if __name__ == "__main__":
    if "--instance" in sys.argv:
        idx = sys.argv.index("--instance")
        if idx + 1 < len(sys.argv):
            target = sys.argv[idx + 1]
            print(f"Updating all Twitter sources to instance: {target}")
            update_instance(target)
            sys.exit(0)

    print("Scanning for a healthy Nitter instance...")
    instance = find_healthy_instance()

    if not instance:
        print(
            "\nNo healthy Nitter instance found. Public instances may be blocked by X.\n"
            "Options:\n"
            "  1. Try again later (instances rotate availability)\n"
            "  2. Self-host RSS Bridge: https://github.com/RSS-Bridge/rss-bridge\n"
            "  3. Manually specify an instance: python scripts/seed_twitter_sources.py --instance <hostname>"
        )
        sys.exit(1)

    print(f"\nSeeding sources using: {instance}\n")
    seed_sources(instance)
