from google.cloud import texttospeech
import os
from dotenv import load_dotenv

load_dotenv()

def generate_voice_samples():
    """Generates audio samples for different Google Neural2 voices."""
    
    # Voices to test (US English mostly for consistency)
    voices_to_test = {
        "en-US-Neural2-A": "Male - Balanced",
        "en-US-Neural2-C": "Female - Balanced",
        "en-US-Neural2-D": "Male - Deep",
        "en-US-Neural2-E": "Female - Professional",
        "en-US-Neural2-F": "Female - Soft",
        "en-US-Neural2-H": "Female - Bright",
        "en-US-Neural2-I": "Male - Authoritative", 
        "en-UK-Neural2-A": "UK Female",
        "en-UK-Neural2-B": "UK Male",
    }
    
    # We currently use:
    # Male: en-US-Neural2-J 
    # Female: en-US-Neural2-F

    print("🎙️ Initializing Google Cloud TTS...")
    try:
        client = texttospeech.TextToSpeechClient()
    except Exception as e:
        print(f"❌ Error initializing client: {e}")
        return

    sample_text = "This is a sample of the Daily AI Wire intelligence briefing. We deliver autonomous news updates."

    output_dir = "static/audio/samples"
    os.makedirs(output_dir, exist_ok=True)

    print(f"🚀 Generating {len(voices_to_test)} samples...")

    for voice_name, description in voices_to_test.items():
        print(f"   - Generating {voice_name} ({description})...")
        
        try:
            # Configure Request
            input_text = texttospeech.SynthesisInput(text=sample_text)
            
            # Parse language code from voice name (e.g. en-US)
            lang_code = "-".join(voice_name.split("-")[:2]) 
            
            voice_params = texttospeech.VoiceSelectionParams(
                language_code=lang_code,
                name=voice_name
            )
            
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3
            )

            # API Call
            response = client.synthesize_speech(
                input=input_text, 
                voice=voice_params, 
                audio_config=audio_config
            )

            # Save
            filename = f"{voice_name}.mp3"
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, "wb") as out:
                out.write(response.audio_content)
                
        except Exception as e:
            print(f"   ⚠️ Failed to generate {voice_name}: {e}")

    print(f"\n✅ Done! Samples saved to {output_dir}")

if __name__ == "__main__":
    generate_voice_samples()
