
import sqlite3
import os

DB_PATH = "news.db"

def migrate_sources():
    print(f"Connecting to {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Create Table
    print("Creating 'sources' table...")
    cursor.execute('''
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
    ''')

    # 2. Define Sources (From fetcher.py)
    # Format: (Name, URL, Category, IsActive)
    sources_data = [
        # PRIMARY WIRE
        ("The Verge", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "Primary Wire", 1),
        ("TechCrunch", "https://techcrunch.com/category/artificial-intelligence/feed/", "Primary Wire", 1),
        ("Wired", "https://www.wired.com/feed/tag/ai/latest/rss", "Primary Wire", 1),
        ("Import AI", "https://importai.substack.com/feed", "Primary Wire", 1),
        ("MIT Technology Review", "https://www.technologyreview.com/topic/artificial-intelligence/feed", "Primary Wire", 1),
        
        # RESEARCH LABS
        ("OpenAI", "https://openai.com/news/rss.xml", "Research Lab", 1),
        ("DeepMind", "https://deepmind.google/blog/rss.xml", "Research Lab", 1),
        ("BAIR Blog", "https://bair.berkeley.edu/blog/feed.xml", "Research Lab", 1),
        ("Microsoft Research", "https://azure.microsoft.com/en-us/blog/feed/", "Research Lab", 1),
        ("Anthropic", "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_news.xml", "Research Lab", 1),
        ("Cambridge University AI", "https://www.cam.ac.uk/taxonomy/term/51032/feed", "Research Lab", 1),
        
        # ENTERPRISE & MARKETS
        ("VentureBeat", "https://venturebeat.com/category/ai/feed/", "Enterprise", 1),
        
        # DEV TERMINAL
        ("NVIDIA Dev", "https://developer.nvidia.com/blog/feed/", "Dev Terminal", 1),
        ("Hugging Face", "https://huggingface.co/blog/feed.xml", "Dev Terminal", 1),
        ("Papers with Code", "https://paperswithcode.com/rss/latest", "Dev Terminal", 1),
        ("Hacker News (AI)", "https://hnrss.org/newest?q=AI+OR+LLM", "Dev Terminal", 1),

        # INACTIVE / BROKEN (Kept for historical record or future fix)
        ("The Batch", "https://read.deeplearning.ai/the-batch/feed", "Primary Wire", 0),
        ("Ben's Bites", "https://bensbites.beehiiv.com/feed", "Primary Wire", 0),
        ("Meta AI (FAIR)", "https://ai.meta.com/blog/rss.xml", "Research Lab", 0),
        ("AI Business", "https://aibusiness.com/rss.xml", "Enterprise", 0),
        ("ML Mastery", "https://machinelearningmastery.com/blog/feed/", "Dev Terminal", 0),
        ("Google News", "https://news.google.com/rss/search?q=Artificial+Intelligence+when:1d&hl=en-US&gl=US&ceid=US:en", "Aggregator", 0)
    ]

    print(f"Seeding {len(sources_data)} sources...")
    added_count = 0
    skipped_count = 0

    for name, url, category, is_active in sources_data:
        try:
            cursor.execute('''
                INSERT INTO sources (name, url, category, is_active) 
                VALUES (?, ?, ?, ?)
            ''', (name, url, category, is_active))
            added_count += 1
        except sqlite3.IntegrityError:
            # Already exists (URL is UNIQUE)
            # Optional: Update the definition if we wanted to enforce code-state
            skipped_count += 1
            pass
    
    conn.commit()
    conn.close()
    print(f"Migration Complete. Added: {added_count}, Skipped (Duplicate): {skipped_count}")

if __name__ == "__main__":
    migrate_sources()
