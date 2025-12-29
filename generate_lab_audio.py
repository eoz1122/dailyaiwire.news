
import os
from audio_generator import AudioGenerator

def generate_lab_narration():
    gen = AudioGenerator()
    if not gen.client:
        print("❌ Google Cloud credentials not found. Cannot generate audio.")
        return

    text = """
    Welcome to the Daily AI Wire Lab. 
    In this report, we analyze the top automation platforms: n8n, Make.com, Pipedream, and Activepieces.
    Our mission was clear: Automate LinkedIn company posts for free, with no monthly subscriptions or credit limits.
    After 40 hours of stress-testing, here is the verdict:
    n8n is the Powerhouse winner for scalability and self-hosting.
    Make.com is the Visual King, perfect for simplicity but limited by credits.
    Activepieces is a strong sleeper contender with a clean open-source approach.
    And Pipedream is powerful but too technical for quick wins.
    Read the full report below for the deep dive comparisons and our final recommendation.
    This is Daily AI Wire, signing off.
    """
    
    slug = "lab_audio_001"
    # We use generate_audio_reads which creates male/female versions. 
    # Or generate_podcast_audio for a mix. Let's use podcast for the "Briefing" feel if possible, 
    # but generate_audio_reads is simpler if we just want a single voice reading (it returns both).
    
    # Actually, generate_audio_reads mixes music too!
    male_path, female_path = gen.generate_audio_reads(slug, text)
    
    if male_path:
        print(f"✅ Audio generated at: {male_path}")
        # We need to rename or copy one of them to /static/lab/lab_audio_001.mp3
        # The script saves to static/audio/
        # We want static/lab/lab_audio_001.mp3
        
        import shutil
        import Path
        
        # Determine source (Male voice is usually better for "Briefing" style News-N)
        src = f"static/audio/{slug}_male.mp3"
        dst = "static/lab/lab_audio_001.mp3"
        
        if os.path.exists(src):
            shutil.copy(src, dst)
            print(f"✅ Copied to {dst}")
        else:
            print("❌ Source audio file missing after generation")
            
    else:
        print("❌ Audio generation returned None")

if __name__ == "__main__":
    generate_lab_narration()
