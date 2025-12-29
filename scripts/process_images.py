import os
from PIL import Image, ImageOps

BASE_DIR = "static/fallbacks"
CATEGORIES = ["llms", "robotics", "business", "tools", "policy", "science", "security", "society"]
TARGET_SIZE = (1200, 800)

def process_image(src_path, dest_path):
    try:
        if not os.path.exists(src_path):
            return False
            
        with Image.open(src_path) as img:
            # Convert to RBG if needed (e.g. PNG with transparency)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            # Resize and Crop to fill target size (Center Crop)
            img_processed = ImageOps.fit(img, TARGET_SIZE, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
            
            # Save as optimized JPEG
            img_processed.save(dest_path, 'JPEG', quality=90)
            print(f"✅ Processed & Saved: {dest_path} ({TARGET_SIZE[0]}x{TARGET_SIZE[1]})")
            return True
            
    except Exception as e:
        print(f"❌ Error processing {src_path}: {e}")
        return False

def main():
    print(f"🔄 Processing images to match standard format {TARGET_SIZE}...")
    
    for cat in CATEGORIES:
        # 1. Process Unsplash Download -> category_0.jpg
        unsplash_src = os.path.join(BASE_DIR, f"{cat}_unsplash.jpg")
        dest_0 = os.path.join(BASE_DIR, f"{cat}_0.jpg")
        process_image(unsplash_src, dest_0)
        
        # 2. Process Generated PNG -> category_1.jpg
        # Only for those that exist (currently llms, robotics)
        gen_src = os.path.join(BASE_DIR, f"{cat}_generated.png")
        dest_1 = os.path.join(BASE_DIR, f"{cat}_1.jpg")
        process_image(gen_src, dest_1)

if __name__ == "__main__":
    main()
