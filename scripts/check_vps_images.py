"""
Diagnostic script to check what images are in the database
"""

import sqlite3

DB_PATH = "news.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

print("\n" + "="*70)
print("📊 DATABASE IMAGE ANALYSIS")
print("="*70)

# Total articles
cursor.execute("SELECT COUNT(*) FROM articles")
total = cursor.fetchone()[0]
print(f"\nTotal articles in database: {total}")

# Articles with images
cursor.execute("SELECT COUNT(*) FROM articles WHERE image IS NOT NULL AND image != ''")
with_images = cursor.fetchone()[0]
print(f"Articles with images: {with_images}")

# Articles without images
print(f"Articles without images: {total - with_images}")

print("\n" + "-"*70)
print("IMAGE URL PATTERNS:")
print("-"*70)

# Group by image URL patterns
patterns = [
    ("Local fallbacks (/static/fallbacks/...)", "image LIKE '/static/fallbacks/%'"),
    ("Full domain fallbacks (https://dailyaiwire.news/static/fallbacks/...)", "image LIKE 'https://dailyaiwire.news/static/fallbacks/%'"),
    ("Unsplash URLs", "image LIKE '%unsplash.com%'"),
    ("Other external URLs", "image LIKE 'http%' AND image NOT LIKE '%dailyaiwire.news%' AND image NOT LIKE '%unsplash.com%'"),
    ("Relative paths (other)", "image LIKE '/%' AND image NOT LIKE '/static/fallbacks/%'"),
]

for label, condition in patterns:
    cursor.execute(f"SELECT COUNT(*) FROM articles WHERE {condition}")
    count = cursor.fetchone()[0]
    if count > 0:
        print(f"{label:<50} {count:>5} articles")

print("\n" + "-"*70)
print("SAMPLE IMAGE URLs (first 10):")
print("-"*70)

cursor.execute("SELECT id, title, image FROM articles WHERE image IS NOT NULL AND image != '' LIMIT 10")
for row in cursor.fetchall():
    article_id, title, image = row
    print(f"\nID {article_id}: {title[:50]}...")
    print(f"  Image: {image[:100]}{'...' if len(image) > 100 else ''}")

# Check for broken fallback URLs
print("\n" + "-"*70)
print("CHECKING FOR BROKEN FALLBACK URLs:")
print("-"*70)

cursor.execute("""
    SELECT COUNT(*) FROM articles 
    WHERE image LIKE '%/static/fallbacks/%' 
    AND (image LIKE '%?%' OR image LIKE 'https://%')
""")
broken = cursor.fetchone()[0]

if broken > 0:
    print(f"⚠️  Found {broken} articles with potentially broken fallback URLs")
    cursor.execute("""
        SELECT id, image FROM articles 
        WHERE image LIKE '%/static/fallbacks/%' 
        AND (image LIKE '%?%' OR image LIKE 'https://%')
        LIMIT 5
    """)
    print("\nExamples:")
    for article_id, image in cursor.fetchall():
        print(f"  ID {article_id}: {image}")
else:
    print("✅ No broken fallback URLs found")

conn.close()

print("\n" + "="*70 + "\n")
