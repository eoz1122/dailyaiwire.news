import os
import numpy as np
from moviepy import ColorClip, TextClip, CompositeVideoClip

def debug_composition():
    duration = 2
    w, h = 1920, 1080
    
    print("🧪 Debugging Frame Composition...")
    
    # Create layers
    bg = ColorClip(size=(w, h), color=(10, 20, 60)).with_duration(duration)
    txt = TextClip(text="DEBUG", font_size=100, color='white').with_duration(duration)
    txt = txt.with_position('center')
    
    comp = CompositeVideoClip([bg, txt]).with_duration(duration)
    
    print(f"   Clip Duration: {comp.duration}")
    
    frame = comp.get_frame(0)
    print(f"   Frame Shape: {frame.shape}")
    print(f"   Frame Dtype: {frame.dtype}")
    print(f"   Unique Colors count: {len(np.unique(frame.reshape(-1, 3), axis=0))}")
    print(f"   Mean Pixel Value: {np.mean(frame)}")
    
    if np.mean(frame) < 1:
        print("❌ CRITICAL: Frame is nearly black/empty!")
    else:
        print("✅ Frame contains data.")

if __name__ == "__main__":
    debug_composition()
