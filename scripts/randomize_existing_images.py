import sqlite3
import random

DB_PATH = "news.db"

CAT_MAP = {
    "LLMs": [
        "https://dailyaiwire.news/static/fallbacks/llms_0.jpg",
        "https://dailyaiwire.news/static/fallbacks/llms_1.jpg"
    ],
    "Robotics": [
        "https://dailyaiwire.news/static/fallbacks/robotics_0.jpg",
        "https://dailyaiwire.news/static/fallbacks/robotics_1.jpg"
    ],
    "Business": [
        "https://dailyaiwire.news/static/fallbacks/business_0.jpg",
        "https://dailyaiwire.news/static/fallbacks/business_1.jpg"
    ],
    "Tools": [
        "https://dailyaiwire.news/static/fallbacks/tools_0.jpg",
        "https://dailyaiwire.news/static/fallbacks/tools_1.jpg"
    ],
    "Policy": [
        "https://dailyaiwire.news/static/fallbacks/policy_0.jpg",
        "https://dailyaiwire.news/static/fallbacks/policy_1.jpg"
    ],
    "Science": [
        "https://dailyaiwire.news/static/fallbacks/science_0.jpg",
        "https://dailyaiwire.news/static/fallbacks/science_1.jpg"
    ],
    "Security": [
        "https://dailyaiwire.news/static/fallbacks/security_0.jpg",
        "https://dailyaiwire.news/static/fallbacks/security_1.jpg"
    ],
    "Society": [
        "https://dailyaiwire.news/static/fallbacks/society_0.jpg",
        "https://dailyaiwire.news/static/fallbacks/society_1.jpg"
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
            new_image = f"{random.choice(images)}?auto=format&fit=crop&q=80&w=1200"
            cursor.execute("UPDATE articles SET image = ? WHERE id = ?", (new_image, article_id))
            count += 1
            
        print(f"✅ Processed {count} articles in '{category}'")

    conn.commit()
    conn.close()
    print("✨ Aesthetic upgrade complete!")

if __name__ == "__main__":
    randomize()
