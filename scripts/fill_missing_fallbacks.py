import os
import shutil

BASE_DIR = "static/fallbacks"
CATEGORIES = ["llms", "robotics", "business", "tools", "policy", "science", "security", "society"]

def fill_gaps():
    print("🛡️ Checking for missing fallback variants...")
    
    for cat in CATEGORIES:
        src_0 = os.path.join(BASE_DIR, f"{cat}_0.jpg")
        dest_1 = os.path.join(BASE_DIR, f"{cat}_1.jpg")
        
        # Ensure source exists (should be there from download_fallbacks.py)
        if not os.path.exists(src_0):
            print(f"⚠️ Warning: Primary fallback {cat}_0.jpg is missing!")
            continue
            
        # If variant 1 is missing, copy 0 to 1 as placeholder
        if not os.path.exists(dest_1):
            try:
                shutil.copy2(src_0, dest_1)
                print(f"✅ Created placeholder {cat}_1.jpg (copy of {cat}_0.jpg)")
            except Exception as e:
                print(f"❌ Failed to copy for {cat}: {e}")
        else:
            print(f"👍 {cat}_1.jpg already exists.")

if __name__ == "__main__":
    fill_gaps()
