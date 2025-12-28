import os
import requests
import time

# The curated list of premium Unsplash images (same as in fetcher.py)
CAT_MAP = {
    "LLMs": [
        "https://images.unsplash.com/photo-1677442136019-21780ecad995",
        "https://images.unsplash.com/photo-1697577418970-95d99b5a55cf"
    ],
    "Robotics": [
        "https://images.unsplash.com/photo-1485827404703-89b55fcc595e",
        "https://images.unsplash.com/photo-1581091226825-a6a2a5aee158"
    ],
    "Business": [
        "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab",
        "https://images.unsplash.com/photo-1551434678-e076c223a692"
    ],
    "Tools": [
        "https://images.unsplash.com/photo-1518770660439-4636190af475",
        "https://images.unsplash.com/photo-1519389950473-47ba0277781c"
    ],
    "Policy": [
        "https://images.unsplash.com/photo-1450101499163-c8848c66ca85",
        "https://images.unsplash.com/photo-1589829545856-d10d557cf95f"
    ],
    "Science": [
        "https://images.unsplash.com/photo-1507413245164-6160d8298b31",
        "https://images.unsplash.com/photo-1530026405186-ed1f139313f8"
    ],
    "Security": [
        "https://images.unsplash.com/photo-1550751827-4bd374c3f58b",
        "https://images.unsplash.com/photo-1563986768609-322da13575f3"
    ],
    "Society": [
        "https://images.unsplash.com/photo-1529107386315-e1a2ed48a620",
        "https://images.unsplash.com/photo-1491438590914-bc09fcaaf77a"
    ]
}

TARGET_DIR = os.path.join("static", "fallbacks")
os.makedirs(TARGET_DIR, exist_ok=True)

def download_fallbacks():
    print(f"⬇️ Downloading fallback images to {TARGET_DIR}...")
    
    downloaded_map = {}

    for category, urls in CAT_MAP.items():
        downloaded_map[category] = []
        for i, url in enumerate(urls):
            try:
                # Add optimization params for download
                download_url = f"{url}?auto=format&fit=crop&q=80&w=1200"
                
                # Filename: category_index.jpg (e.g., llms_0.jpg)
                filename = f"{category.lower()}_{i}.jpg"
                filepath = os.path.join(TARGET_DIR, filename)
                
                print(f"   Downloading {category} [{i+1}/{len(urls)}] -> {filename}...")
                
                response = requests.get(download_url, timeout=10)
                if response.status_code == 200:
                    with open(filepath, 'wb') as f:
                        f.write(response.content)
                    
                    # Store the RELATIVE web path
                    web_path = f"/static/fallbacks/{filename}"
                    downloaded_map[category].append(web_path)
                else:
                    print(f"❌ Failed to download {url}: {response.status_code}")
            
            except Exception as e:
                print(f"❌ Error downloading {url}: {e}")
            
            # Be nice to Unsplash
            time.sleep(1)

    print("\n✅ Download complete. New local mapping generated.")
    return downloaded_map

if __name__ == "__main__":
    download_fallbacks()
