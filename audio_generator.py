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
            # 1. Generate Male (Journey D - Futuristic/Human)
            if not male_path.exists():
                print(f"Generating Male Audio (Journey): {male_filename}")
                voice = texttospeech.VoiceSelectionParams(
                    language_code="en-US",
                    name="en-US-Journey-D" 
                )
                response = self.client.synthesize_speech(input=input_text, voice=voice, audio_config=audio_config)
                
                # Save Raw TTS temporarily
                temp_male = audio_dir / f"temp_{male_filename}"
                with open(temp_male, "wb") as out:
                    out.write(response.audio_content)
                
                # Apply Mixing
                try:
                    from audio_mixer_moviepy import mix_audio_moviepy
                    bg_music = "static/audio/ES_Cinematics - Blue Saga - 0000-58213.wav"
                    if os.path.exists(bg_music):
                        print("   🎛️ Mixing with background music...")
                        mix_audio_moviepy(str(temp_male), bg_music, str(male_path))
                        os.remove(temp_male) # Clean up raw
                    else:
                        print("   ⚠️ Background music not found, using raw TTS.")
                        os.rename(temp_male, male_path)
                except Exception as mix_err:
                    print(f"   ⚠️ Mixing failed ({mix_err}), using raw TTS.")
                    if os.path.exists(temp_male): os.rename(temp_male, male_path)

            
            # 2. Generate Female (Journey F - Futuristic/Human)
            if not female_path.exists():
                print(f"Generating Female Audio (Journey): {female_filename}")
                voice = texttospeech.VoiceSelectionParams(
                    language_code="en-US",
                    name="en-US-Journey-F" 
                )
                response = self.client.synthesize_speech(input=input_text, voice=voice, audio_config=audio_config)
                
                 # Save Raw TTS temporarily
                temp_female = audio_dir / f"temp_{female_filename}"
                with open(temp_female, "wb") as out:
                    out.write(response.audio_content)

                # Apply Mixing
                try:
                    from audio_mixer_moviepy import mix_audio_moviepy
                    bg_music = "static/audio/ES_Cinematics - Blue Saga - 0000-58213.wav"
                    if os.path.exists(bg_music):
                        print("   🎛️ Mixing with background music...")
                        mix_audio_moviepy(str(temp_female), bg_music, str(female_path))
                        os.remove(temp_female) # Clean up raw
                    else:
                        print("   ⚠️ Background music not found, using raw TTS.")
                        os.rename(temp_female, female_path)
                except Exception as mix_err:
                    print(f"   ⚠️ Mixing failed ({mix_err}), using raw TTS.")
                    if os.path.exists(temp_female): os.rename(temp_female, female_path)
                
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
