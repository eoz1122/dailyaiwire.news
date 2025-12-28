from audio_generator import AudioGenerator
import os
import time

def generate_production_sample():
    print("🚀 Generating Production Sample (Journey Voice + Ducked Music)...")
    
    # 1. Initialize Generator
    gen = AudioGenerator()
    if not gen.client:
        print("❌ Failed to initialize Google TTS client. Check credentials.")
        return

    # 2. Define Sample Article (Simulating a real news piece)
    sample_slug = "production-sample-v1"
    sample_text = """
    Daily A I Wire Intelligence Briefing.
    
    Google has officially released the Gemini 2.5 Flash Lite model, setting a new standard for on-device processing. 
    This lightweight architecture allows for millisecond-latency responses on mobile hardware, effectively checking the box for real-time robotic control and offline assistants.
    
    In other news, OpenAI is reportedly restructuring its safety division to prioritize agentic alignment. 
    Sources close to the matter suggest this move comes in response to increasing regulatory pressure in the European Union.
    
    Finally, Tesla's Optimus Gen 3 prototype was spotted performing autonomous warehouse tasks with 99% success rate, a significant leap from previous demonstrations.
    
    This has been your Daily A I Wire update.
    """

    print("🎙️ Synthesizing and Mixing...")
    start_time = time.time()
    
    # 3. Generate
    male_url, female_url = gen.generate_audio_reads(sample_slug, sample_text)
    
    duration = time.time() - start_time
    print(f"✅ Completed in {duration:.2f} seconds.")
    
    print("\n🎧 Listen to the samples here:")
    print(f"   Male (Journey-D):   https://dailyaiwire.news{male_url}")
    print(f"   Female (Journey-F): https://dailyaiwire.news{female_url}")

if __name__ == "__main__":
    generate_production_sample()
