import sqlite3
import random

DB_PATH = "news.db"

CAT_MAP = {
    "LLMs": [
        "https://images.unsplash.com/photo-1677442136019-21780ecad995",
        "https://images.unsplash.com/photo-1673187115862-5bd33cf48831",
        "https://images.unsplash.com/photo-1697577418970-95d99b5a55cf",
        "https://images.unsplash.com/photo-1675271591211-126ad94e495d"
    ],
    "Robotics": [
        "https://images.unsplash.com/photo-1485827404703-89b55fcc595e",
        "https://images.unsplash.com/photo-1581091226825-a6a2a5aee158",
        "https://images.unsplash.com/photo-1516110833967-0b5716ca1387",
        "https://images.unsplash.com/photo-1535378917042-10a22c95931a"
    ],
    "Business": [
        "https://images.unsplash.com/photo-1507679799987-c73779587ccf",
        "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab",
        "https://images.unsplash.com/photo-1497366216548-37526070297c",
        "https://images.unsplash.com/photo-1664575602276-acd073f104c1"
    ],
    "Tools": [
        "https://images.unsplash.com/photo-1518770660439-4636190af475",
        "https://images.unsplash.com/photo-1550009158-9ebf69173e03",
        "https://images.unsplash.com/photo-1519389950473-47ba0277781c",
        "https://images.unsplash.com/photo-1517077304055-6e89abbf09b0"
    ],
    "Policy": [
        "https://images.unsplash.com/photo-1450101499163-c8848c66ca85",
        "https://images.unsplash.com/photo-1589829545856-d10d557cf95f",
        "https://images.unsplash.com/photo-1423592707957-3b212afa6733",
        "https://images.unsplash.com/photo-1505664194779-8beaceb93744"
    ],
    "Science": [
        "https://images.unsplash.com/photo-1507413245164-6160d8298b31",
        "https://images.unsplash.com/photo-1530210124550-912dc1381cb8",
        "https://images.unsplash.com/photo-1532094349884-543bb1198c33",
        "https://images.unsplash.com/photo-1518152006812-edab29b069ac"
    ],
    "Security": [
        "https://images.unsplash.com/photo-1550751827-4bd374c3f58b",
        "https://images.unsplash.com/photo-1563986768609-322da13575f3",
        "https://images.unsplash.com/photo-1614064641938-3bbee52942c7",
        "https://images.unsplash.com/photo-1558494949-ef010955d0ef"
    ],
    "Society": [
        "https://images.unsplash.com/photo-1529107386315-e1a2ed48a620",
        "https://images.unsplash.com/photo-1491438590914-bc09fcaaf77a",
        "https://images.unsplash.com/photo-1517245386807-bb43f82c33c4",
        "https://images.unsplash.com/photo-1521737604893-d14cc237f11d"
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
