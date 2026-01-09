import os
import sys

try:
    from moviepy import AudioClip
except ImportError:
    from moviepy.editor import AudioClip

from video_renderer import render_briefing_video

def create_dummy_audio(filename="dummy_silence.mp3", duration=10):
    if os.path.exists(filename):
        return filename
    print(f"🔊 Creating {duration}s dummy audio...")
    # Silent clip
    silent_clip = AudioClip(lambda t: [0], duration=duration, fps=44100) 
    silent_clip.write_audiofile(filename, fps=44100, logger=None)
    return filename

def run_visual_test():
    print("🧪 Starting Visual Verification (Ticker + Logo + Background)...")
    
    # 1. Create Dummy Audio (10s)
    audio_path = create_dummy_audio()
    
    # 2. Define Sample Headlines
    headlines = [
        "Google Releases Gemini 2.0 Flash",
        "OpenAI Announces New Safety Framework",
        "Daily AI Wire: Intelligence for the Future",
        "Market Watch: NVIDIA Surpasses Microsoft"
    ]
    
    # 3. Render Video
    output_file = "visual_test_final.mp4"
    # Use existing logic for background selection
    background_template = "static/video/loops"
    if not os.path.exists(background_template) or not os.listdir(background_template):
        background_template = "static/video/background_loop.mp4"
        
    print(f"🎬 Rendering FINAL verification video to: {output_file}")
    if os.path.exists(output_file): os.remove(output_file)
    success = render_briefing_video(audio_path, background_template, output_file, headlines=headlines)
    
    if success:
        print(f"✅ Test Complete! Check {output_file}")
    else:
        print("❌ Test Failed during rendering.")

if __name__ == "__main__":
    run_visual_test()
