import os
import sys

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from moviepy import AudioFileClip
from video_renderer import render_briefing_video

def main():
    audio_path = "static/audio/daily_briefing_2025-12-28_podcast.mp3"
    if not os.path.exists(audio_path):
        print("❌ Full audio not found. Run generate_briefing.py first.")
        return

    # Load only first 60 seconds
    print("✂️ Creating 60s test audio clip...")
    full_audio = AudioFileClip(audio_path)
    test_audio_path = "static/audio/test_audio_60s.mp3"
    test_audio = full_audio.subclipped(0, 60)
    test_audio.write_audiofile(test_audio_path, logger=None)
    
    # Render Video
    headlines = [
        "AI Companionship: Unpacking Psychological Benefits",
        "Kurdistan's AI Surge Ignites Economic Debates",
        "AI Emerges as Top Conservation Trend for 2026",
        "Job Displacement by AI Spurs Rethink of Career Paths"
    ]
    output_video = "briefing_test_60s.mp4"
    background_template = "static/video/loops"
    
    print("🎬 Rendering 60s visual test...")
    success = render_briefing_video(test_audio_path, background_template, output_video, headlines=headlines)
    
    if success:
        print(f"✅ Test video ready: {output_video}")
    else:
        print("❌ Test rendering failed.")

if __name__ == "__main__":
    main()
