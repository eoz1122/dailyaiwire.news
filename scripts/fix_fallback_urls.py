"""
Fix broken fallback image URLs in the database.

This script:
1. Removes Unsplash query parameters from local image paths
2. Converts full domain URLs to relative paths
3. Updates all affected articles in the database
"""

import sqlite3
import re

DB_PATH = "news.db"

def fix_image_urls():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all articles with fallback images
    cursor.execute("""
        SELECT id, image 
        FROM articles 
        WHERE image LIKE '%/static/fallbacks/%'
    """)
    
    articles = cursor.fetchall()
    
    print(f"\n🔧 Fixing {len(articles)} articles with fallback images...\n")
    
    fixed_count = 0
    
    for article_id, old_image in articles:
        # Extract just the path part
        # Example: https://dailyaiwire.news/static/fallbacks/business_0.jpg?auto=format&fit=crop&q=80&w=1200
        # Should become: /static/fallbacks/business_0.jpg
        
        # Remove domain if present
        new_image = old_image.replace('https://dailyaiwire.news', '')
        
        # Remove query parameters
        new_image = re.sub(r'\?.*$', '', new_image)
        
        # Ensure it starts with /
        if not new_image.startswith('/'):
            new_image = '/' + new_image
        
        if old_image != new_image:
            cursor.execute("UPDATE articles SET image = ? WHERE id = ?", (new_image, article_id))
            fixed_count += 1
            if fixed_count <= 5:  # Show first 5 examples
                print(f"  ✓ Fixed article {article_id}:")
                print(f"    OLD: {old_image[:80]}...")
                print(f"    NEW: {new_image}\n")
    
    conn.commit()
    conn.close()
    
    print(f"{'='*60}")
    print(f"✅ Successfully fixed {fixed_count} image URLs!")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    fix_image_urls()
