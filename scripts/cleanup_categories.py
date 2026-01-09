import sqlite3

def cleanup():
    DB_PATH = "news.db"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    mapping = {
        'LLMs': ['AI', 'MACHINE LEARNING', 'ARTIFICIAL GENERAL INTELLIGENCE', 'LLMS'],
        'Business': ['AI & CLOUD', 'AI INFRASTRUCTURE', 'ENTERPRISE', 'FINANCE', 'STARTUPS'],
        'Tools': ['AI AGENTS', 'TECHNOLOGY', 'HARDWARE', 'APPS'],
        'Policy': ['POLICY', 'LAW', 'LEGAL', 'GOVERNMENT', 'ETHICS', 'SUSTAINABILITY', 'AI POLICY', 'AI ETHICS'],
        'Science': ['HEALTHCARE', 'MEDICINE', 'BIOTECH', 'PHARMACEUTICALS', 'HEALTHCARE AI', 'RESEARCH'],
        'Security': ['CYBERSECURITY', 'AI SECURITY', 'SECURITY'],
        'Society': ['SOCIETAL IMPACT', 'EDUCATION', 'PHILOSOPHY', 'ENTERTAINMENT & AI']
    }

    print("🧹 Starting Category Intelligence Cleanup...")
    
    total_updated = 0
    for target, sources in mapping.items():
        for source in sources:
            cursor.execute("UPDATE articles SET category = ? WHERE UPPER(category) = ?", (target, source))
            total_updated += cursor.rowcount

    conn.commit()
    conn.close()
    print(f"✅ Cleanup complete. {total_updated} articles re-categorized into clean pillars.")

if __name__ == "__main__":
    cleanup()
