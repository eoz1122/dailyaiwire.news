import os
import sqlite3
from moviepy import *
import requests
from PIL import Image

# Config
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'news.db')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
VIDEO_DIR = os.path.join(STATIC_DIR, 'videos')

if not os.path.exists(VIDEO_DIR):
    os.makedirs(VIDEO_DIR)

def generate_audiogram(article_id):
    """
    Generates a 1:1 or 16:9 video for LinkedIn.
    1. Downloads Article Image.
    2. Downloads Audio Narration.
    3. Combines them into an MP4.
    """
    print(f"🎬 Starting Audiogram Generation for Article {article_id}...")
    
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute('SELECT title, image, narration_url, slug FROM articles WHERE id = ?', (article_id,)).fetchone()
    conn.close()
    
    if not row:
        print("❌ Article not found.")
        return False

    title, image_url, audio_url, slug = row
    
    if not audio_url:
        print("❌ No audio narration found.")
        return False
        
    if not image_url.startswith('http'):
        image_url = f"https://dailyaiwire.news{image_url}"

    # Filenames
    local_image_path = os.path.join(VIDEO_DIR, f"{slug}.jpg")
    local_audio_path = os.path.join(VIDEO_DIR, f"{slug}.mp3")
    output_video_path = os.path.join(VIDEO_DIR, f"{slug}.mp4")

    try:
        # Download Assets
        if not os.path.exists(local_image_path):
            with open(local_image_path, 'wb') as f:
                f.write(requests.get(image_url).content)
        
        if not os.path.exists(local_audio_path):
            with open(local_audio_path, 'wb') as f:
                f.write(requests.get(audio_url).content)

        # Create Video
        audio_clip = AudioFileClip(local_audio_path)
        
        # Image Clip (Loop for duration of audio)
        image_clip = ImageClip(local_image_path).with_duration(audio_clip.duration)
        image_clip = image_clip.with_fps(24) # Low FPS is fine for static image

        # Resize to square (1080x1080) or landscape? LinkedIn likes Square or Portrait.
        # Let's simple resize to fit 1080 width, keep aspect ratio, then pad?
        # For MVP: Just use the image as is.
        
        # Combine
        video = image_clip.with_audio(audio_clip)
        
        # Write File
        video.write_videofile(output_video_path, codec="libx264", audio_codec="aac")
        
        print(f"✅ Video Generated: {output_video_path}")
        
        # Clean up temp assets (optional, maybe keep for cache?)
        # os.remove(local_image_path)
        # os.remove(local_audio_path)
        
        return True

    except Exception as e:
        print(f"❌ Video Generation Failed: {e}")
        return False

if __name__ == "__main__":
    # Test
    import sys
    if len(sys.argv) > 1:
        generate_audiogram(sys.argv[1])
