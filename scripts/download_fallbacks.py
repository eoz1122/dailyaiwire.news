import os
import requests
import shutil

# Target Directory
TARGET_DIR = "static/fallbacks"
os.makedirs(TARGET_DIR, exist_ok=True)

# Map categories to Unsplash Source URLs (high quality, royalty free)
UNSPLASH_MAP = {
    "llms": "https://images.unsplash.com/photo-1677442136019-21780ecad995?auto=format&fit=crop&q=80&w=1200",
    "robotics": "https://images.unsplash.com/photo-1485827404703-89b55fcc595e?auto=format&fit=crop&q=80&w=1200",
    "business": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&q=80&w=1200",
    "tools": "https://images.unsplash.com/photo-1555774698-0b77e0d5fac6?auto=format&fit=crop&q=80&w=1200",
    "policy": "https://images.unsplash.com/photo-1589829085413-56de8ae18c73?auto=format&fit=crop&q=80&w=1200",
    "science": "https://images.unsplash.com/photo-1532094349884-543bc11b234d?auto=format&fit=crop&q=80&w=1200",
    "security": "https://images.unsplash.com/photo-1563206767-5b1d97299337?auto=format&fit=crop&q=80&w=1200",
    "society": "https://images.unsplash.com/photo-1531482615713-2afd69097998?auto=format&fit=crop&q=80&w=1200"
}

def download_file(url, filename):
    try:
        response = requests.get(url, stream=True, timeout=10)
        response.raise_for_status()
        file_path = os.path.join(TARGET_DIR, filename)
        with open(file_path, 'wb') as f:
            shutil.copyfileobj(response.raw, f)
        print(f"✅ Downloaded: {filename}")
    except Exception as e:
        print(f"❌ Failed to download {filename}: {e}")

def main():
    print(f"⬇️  Downloading Fallback Images to {TARGET_DIR}...")
    
    # 1. Download Unsplash Recommendations
    for category, url in UNSPLASH_MAP.items():
        filename = f"{category}_unsplash.jpg"
        download_file(url, filename)

if __name__ == "__main__":
    main()
