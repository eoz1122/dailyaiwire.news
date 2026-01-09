import numpy as np
from moviepy import VideoClip, TextClip, CompositeVideoClip, ColorClip
import os

def make_frame(t):
    return np.random.randint(0, 100, (480, 640, 3), dtype=np.uint8) # Dark noise

try:
    print("🎬 Attempting Noise + TextClip composite render...")
    duration = 5
    bg = VideoClip(make_frame, duration=duration)
    bg.fps = 24
    
    txt = TextClip(text="OVERLAY TEST", font_size=50, color='white').with_duration(duration)
    txt.fps = 24
    txt = txt.with_position('center')
    
    final = CompositeVideoClip([bg, txt]).with_duration(duration)
    final.fps = 24
    
    output = "composite_noise_test.mp4"
    final.write_videofile(output, fps=24, logger='bar')
    
    if os.path.exists(output):
        size = os.path.getsize(output)
        print(f"✅ Render finished. File size: {size} bytes")
    else:
        print("❌ File was not created.")
except Exception as e:
    print(f"❌ Composite render failed with error: {e}")
