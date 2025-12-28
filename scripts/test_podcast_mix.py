import os
from google.cloud import texttospeech
from moviepy import AudioFileClip, concatenate_audioclips
from dotenv import load_dotenv

load_dotenv(override=True)

def generate_podcast_sample():
    print("🎙️ Generating Podcast Sample (Two-Host Banter)...")
    
    # 1. Hardcoded Dialogue Script
    script = [
        ("Host A", "Welcome back to the Daily AI Wire. I'm Marcus."),
        ("Host B", "And I'm Sarah. Today we're talking about the new Gemini model. Marcus, have you seen the benchmarks?"),
        ("Host A", "I have, and frankly, I'm skeptical. They claim a 40% jump in reasoning, but is that just on synthetic data?"),
        ("Host B", "That's a fair point, but look at the coding scores. It's not just memorization anymore; it's actually solving novel problems."),
        ("Host A", "Maybe. But until I see it debug my spaghetti code, I'm holding my applause."),
        ("Host B", "Fair enough! Let's dive into the details.")
    ]

    client = texttospeech.TextToSpeechClient()
    audio_clips = []
    
    temp_files = []

    for i, (speaker, text) in enumerate(script):
        print(f"   Generating line {i+1}: {speaker}...")
        
        # Select Voice
        if speaker == "Host A":
            name = "en-US-Journey-D" # Male, Deep
            gender = texttospeech.SsmlVoiceGender.MALE
        else:
            name = "en-US-Journey-F" # Female, Warm
            gender = texttospeech.SsmlVoiceGender.FEMALE
            
        input_text = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(language_code="en-US", name=name)
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
        
        try:
            response = client.synthesize_speech(input=input_text, voice=voice, audio_config=audio_config)
            
            filename = f"static/audio/temp_line_{i}.mp3"
            with open(filename, "wb") as out:
                out.write(response.audio_content)
            
            temp_files.append(filename)
            audio_clips.append(AudioFileClip(filename))
            
        except Exception as e:
            print(f"❌ Error generating line {i}: {e}")
            return

    # 2. Concatenate
    print("   🔗 Stitching audio clips...")
    final_audio = concatenate_audioclips(audio_clips)
    
    output_path = "static/audio/sample_podcast_banter.mp3"
    final_audio.write_audiofile(output_path, logger=None)
    
    # Cleanup
    for f in temp_files:
        try:
            os.remove(f)
        except:
            pass
            
    print(f"✅ Sample ready: {output_path}")

if __name__ == "__main__":
    generate_podcast_sample()
