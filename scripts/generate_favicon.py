from PIL import Image, ImageDraw

def create_favicon():
    # Size 64x64
    size = (64, 64)
    # New Blue Color #2563eb is (37, 99, 235)
    color = (37, 99, 235)
    
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw circle
    draw.ellipse([0, 0, 64, 64], fill=color)
    
    # Draw simple "AI" text or dot in white
    # Since I don't want to rely on fonts, I'll draw a white circle inside
    # to make it look like a "target" or "wire" node
    draw.ellipse([20, 20, 44, 44], fill=(255, 255, 255))
    
    img.save("static/favicon.png")
    print("✅ Created blue favicon.png")

if __name__ == "__main__":
    create_favicon()
