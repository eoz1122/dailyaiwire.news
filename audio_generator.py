import os
import io
from google.cloud import texttospeech
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class AudioGenerator:
    def __init__(self):
        # Google Cloud looks for GOOGLE_APPLICATION_CREDENTIALS environment variable
        # which should point to your service account JSON file.
        self.credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        
        try:
            if self.credentials_path and os.path.exists(self.credentials_path):
                self.client = texttospeech.TextToSpeechClient()
                print("Google Cloud TTS Client Initialized.")
            else:
                self.client = None
                print("GOOGLE_APPLICATION_CREDENTIALS not set or file missing. Skipping audio.")
        except Exception as e:
            self.client = None
            print(f"Error initializing Google TTS: {e}")

    def generate_audio_reads(self, slug, text):
        """Generates male and female audio reads using Google Neural2 voices."""
        if not self.client:
            return None, None

        # Clean text
        clean_text = text.replace('**', '').replace('###', '').replace('\n', ' ')
        
        # Audio storage path
        audio_dir = Path("static/audio")
        audio_dir.mkdir(parents=True, exist_ok=True)
        
        male_filename = f"{slug}_male.mp3"
        female_filename = f"{slug}_female.mp3"
        
        male_path = audio_dir / male_filename
        female_path = audio_dir / female_filename

        # Synthesis parameters
        input_text = texttospeech.SynthesisInput(text=clean_text[:4500])
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)

        try:
            # 1. Generate Male (Neutral Neural2)
            if not male_path.exists():
                print(f"Generating Male Audio (Google): {male_filename}")
                voice = texttospeech.VoiceSelectionParams(
                    language_code="en-US",
                    name="en-US-Neural2-J" # High-quality Neutral Male
                )
                response = self.client.synthesize_speech(input=input_text, voice=voice, audio_config=audio_config)
                with open(male_path, "wb") as out:
                    out.write(response.audio_content)
            
            # 2. Generate Female (Neutral Neural2)
            if not female_path.exists():
                print(f"Generating Female Audio (Google): {female_filename}")
                voice = texttospeech.VoiceSelectionParams(
                    language_code="en-US",
                    name="en-US-Neural2-F" # High-quality Neutral Female
                )
                response = self.client.synthesize_speech(input=input_text, voice=voice, audio_config=audio_config)
                with open(female_path, "wb") as out:
                    out.write(response.audio_content)
                
            return f"/static/audio/{male_filename}", f"/static/audio/{female_filename}"
            
        except Exception as e:
            print(f"Error during Google audio generation: {e}")
            return None, None

if __name__ == "__main__":
    # Test block
    gen = AudioGenerator()
    # To test locally, set GOOGLE_APPLICATION_CREDENTIALS in your .env pointing to a valid JSON
    m, f = gen.generate_audio_reads("test-wire-signal", "Testing Google Cloud intelligence read-aloud functionality.")
    print(f"Results -> Male: {m}, Female: {f}")
