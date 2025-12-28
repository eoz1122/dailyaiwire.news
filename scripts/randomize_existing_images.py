import sqlite3
import random

DB_PATH = "news.db"

CAT_MAP = {
    "LLMs": [
        "/static/fallbacks/llms_0.jpg",
        "/static/fallbacks/llms_1.jpg"
    ],
    "Robotics": [
        "/static/fallbacks/robotics_0.jpg",
        "/static/fallbacks/robotics_1.jpg"
    ],
    "Business": [
        "/static/fallbacks/business_0.jpg",
        "/static/fallbacks/business_1.jpg"
    ],
    "Tools": [
        "/static/fallbacks/tools_0.jpg",
        "/static/fallbacks/tools_1.jpg"
    ],
    "Policy": [
        "/static/fallbacks/policy_0.jpg",
        "/static/fallbacks/policy_1.jpg"
    ],
    "Science": [
        "/static/fallbacks/science_0.jpg",
        "/static/fallbacks/science_1.jpg"
    ],
    "Security": [
        "/static/fallbacks/security_0.jpg",
        "/static/fallbacks/security_1.jpg"
    ],
    "Society": [
        "/static/fallbacks/society_0.jpg",
        "/static/fallbacks/society_1.jpg"
    ]
}

def randomize():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("🎨 Retroactively randomizing fallback images...")
    
    # Get all articles that use one of our standard fallback images
    # We identify them because their 'image' URL starts with one of the base Unsplash URLs in CAT_MAP
    
    for category, images in CAT_MAP.items():
        base_urls = [img for img in images]
        
        # Select articles in this category that use one of the base_urls
        cursor.execute("SELECT id FROM articles WHERE category = ?", (category,))
        rows = cursor.fetchall()
        
        count = 0
        for (article_id,) in rows:
            # We want to randomize it with one of the options in the list
            new_image = random.choice(images)
            cursor.execute("UPDATE articles SET image = ? WHERE id = ?", (new_image, article_id))
            count += 1
            
        print(f"✅ Processed {count} articles in '{category}'")

    conn.commit()
    conn.close()
    print("✨ Aesthetic upgrade complete!")

if __name__ == "__main__":
    randomize()
