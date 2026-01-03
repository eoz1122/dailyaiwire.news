import sqlite3

conn = sqlite3.connect('news.db')
cursor = conn.cursor()

# Check for articles using fallback images
cursor.execute("""
    SELECT COUNT(*), image 
    FROM articles 
    WHERE image LIKE '%/static/fallbacks/%'
    GROUP BY image 
    ORDER BY image
""")

results = cursor.fetchall()

print('\n📊 Current Fallback Image Usage in Database:\n')
print(f"{'Count':<8} {'Image Path':<50}")
print("-" * 60)

for count, img in results:
    print(f"{count:<8} {img}")

print(f"\n{'='*60}")
print(f"Total articles using fallback images: {sum(r[0] for r in results)}")

conn.close()
