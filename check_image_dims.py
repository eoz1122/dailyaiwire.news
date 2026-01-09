from PIL import Image
import os

fallbacks_dir = "static/fallbacks"

print("Current Fallback Image Specifications:\n")
print(f"{'Filename':<20} {'Dimensions':<15} {'Aspect Ratio':<15} {'Size (KB)':<10}")
print("-" * 70)

for filename in sorted(os.listdir(fallbacks_dir)):
    if filename.endswith('.jpg'):
        filepath = os.path.join(fallbacks_dir, filename)
        img = Image.open(filepath)
        width, height = img.size
        aspect = round(width / height, 2)
        size_kb = round(os.path.getsize(filepath) / 1024, 1)
        print(f"{filename:<20} {width}x{height:<10} {aspect}:1{'':<10} {size_kb} KB")
        img.close()

print("\n" + "="*70)
print("\n📐 RECOMMENDED SPECS FOR YOUR CUSTOM IMAGES:")
print("="*70)
print("✓ Dimensions: 1200px × 800px (or similar 3:2 ratio)")
print("✓ Aspect Ratio: 3:2 (landscape)")
print("✓ Format: JPEG (.jpg)")
print("✓ File Size: 80-400 KB")
print("✓ Quality: 80-85% JPEG compression")
print("\nAlternative dimensions that work:")
print("  • 1200px × 675px (16:9 ratio)")
print("  • 1920px × 1280px (3:2 ratio, higher quality)")
print("  • 1600px × 900px (16:9 ratio)")
