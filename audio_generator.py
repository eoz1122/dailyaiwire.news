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

    def fix_pronunciation(self, text):
        """Fixes common AI mispronunciations for a more natural sound."""
        if not text: return ""
        # Force "AI" to be pronounced as "A.I." with natural pauses
        text = text.replace('AI ', 'A.I. ').replace(' AI', ' A.I.').replace('AI.', 'A.I.').replace('AI,', 'A.I.,')
        return text

    def generate_audio_reads(self, slug, text):
        """Generates male and female audio reads handled as high-fidelity narrations."""
        if not self.client:
            return None, None

        # Clean text and fix pronunciation
        clean_text = self.fix_pronunciation(text.replace('**', '').replace('###', ' ').replace('\n', ' '))
        
        # Audio storage path
        audio_dir = Path("static/audio")
        audio_dir.mkdir(parents=True, exist_ok=True)
        
        male_filename = f"{slug}_male.mp3"
        female_filename = f"{slug}_female.mp3"
        
        male_path = audio_dir / male_filename
        female_path = audio_dir / female_filename

        # Only chunk if absolutely necessary (limit is 5000 bytes). 
        # For 1-min narrative scripts, we avoid chunking to keep natural prosody.
        if len(clean_text) > 4000:
            chunks = [clean_text[i:i+4000] for i in range(0, len(clean_text), 4000)]
        else:
            chunks = [clean_text]
        
        if len(chunks) > 1:
            print(f"   ℹ️ Text length {len(clean_text)} chars. Splitting into {len(chunks)} chunks.")

        try:
            # 1. Generate Male (Journey D)
            if not male_path.exists():
                print(f"Generating Male Audio (Journey): {male_filename}")
                combined_audio = b""
                
                for i, chunk in enumerate(chunks):
                    # Journey-D (Deep, Authoritative)
                    # Wrap in SSML for natural pacing
                    safe_text = chunk.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
                    ssml_text = f"<speak>{safe_text}</speak>"
                    input_text = texttospeech.SynthesisInput(ssml=ssml_text)
                    
                    # News-N (Broadcast Male - $16/1M tier)
                    voice = texttospeech.VoiceSelectionParams(language_code="en-US", name="en-US-News-N")
                    
                    # Use Linear16 for high fidelity
                    audio_config = texttospeech.AudioConfig(
                        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
                        sample_rate_hertz=44100
                    )
                    
                    response = self.client.synthesize_speech(input=input_text, voice=voice, audio_config=audio_config)
                    combined_audio += response.audio_content
                    if len(chunks) > 1: print(f"      Processed Chunk {i+1}/{len(chunks)}")

                # Save Raw TTS temporarily
                temp_male = audio_dir / f"temp_{male_filename}"
                with open(temp_male, "wb") as out:
                    out.write(combined_audio)
                
                # Apply Mixing
                try:
                    from audio_mixer_moviepy import mix_audio_moviepy
                    # Prioritize the same background music used in Daily Briefing
                    bg_music = "static/audio/Background Mucis.mp3"
                    if not os.path.exists(bg_music):
                        bg_music = "static/audio/ES_Cinematics - Blue Saga - 0000-58213.wav"
                    
                    if os.path.exists(bg_music):
                        print(f"   🎛️ Mixing with background music: {os.path.basename(bg_music)}")
                        mix_audio_moviepy(str(temp_male), bg_music, str(male_path))
                        os.remove(temp_male) 
                    else:
                        print("   ⚠️ Background music not found, using raw TTS.")
                        os.rename(temp_male, male_path)
                except Exception as mix_err:
                    print(f"   ⚠️ Mixing failed ({mix_err}), using raw TTS.")
                    if os.path.exists(temp_male): os.rename(temp_male, male_path)

            
            # 2. Generate Female (Journey F)
            if not female_path.exists():
                print(f"Generating Female Audio (Journey): {female_filename}")
                combined_audio = b""
                
                for i, chunk in enumerate(chunks):
                    # Journey-F (Warm, Professional)
                    # Wrap in SSML
                    safe_text = chunk.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
                    ssml_text = f"<speak>{safe_text}</speak>"
                    input_text = texttospeech.SynthesisInput(ssml=ssml_text)
                    
                    # Neural2-C (Smooth Female - $16/1M tier)
                    voice = texttospeech.VoiceSelectionParams(language_code="en-US", name="en-US-Neural2-C")
                    
                    # Use Linear16 for high fidelity
                    audio_config = texttospeech.AudioConfig(
                        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
                        sample_rate_hertz=44100
                    )
                    
                    response = self.client.synthesize_speech(input=input_text, voice=voice, audio_config=audio_config)
                    combined_audio += response.audio_content
                
                # Save Raw TTS temporarily
                temp_female = audio_dir / f"temp_{female_filename}"
                with open(temp_female, "wb") as out:
                    out.write(combined_audio)

                # Apply Mixing
                try:
                    from audio_mixer_moviepy import mix_audio_moviepy
                    bg_music = "static/audio/Background Mucis.mp3"
                    if not os.path.exists(bg_music):
                        bg_music = "static/audio/ES_Cinematics - Blue Saga - 0000-58213.wav"
                    
                    if os.path.exists(bg_music):
                        print(f"   🎛️ Mixing with background music: {os.path.basename(bg_music)}")
                        mix_audio_moviepy(str(temp_female), bg_music, str(female_path))
                        os.remove(temp_female)
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

    def generate_podcast_audio(self, slug, script_text):
        """
        Parses a dialogue script (Host A/Host B) and generates a mixed podcast.
        """
        if not self.client:
            return None

        print(f"🎙️ Processing Podcast Audio for {slug}...")
        
        audio_dir = Path("static/audio")
        final_output = audio_dir / f"{slug}_podcast.mp3"
        raw_output = audio_dir / f"{slug}_raw_talk.wav"

        audio_dir.mkdir(parents=True, exist_ok=True) # Ensure audio_dir exists early
        final_output = audio_dir / f"{slug}_podcast.mp3"
        raw_output = audio_dir / f"{slug}_raw_talk.wav"

        # Import moviepy for concatenation (needed for both generation and loading raw_output)
        try:
            from moviepy import AudioFileClip, concatenate_audioclips
        except ImportError:
            # Fallback for v2 vs v1
            from moviepy.editor import AudioFileClip, concatenate_audioclips

        conversation_clip = None
        temp_clips = [] # To store temporary line files if generated

        # CACHE CHECK 1: Final MP3
        if os.path.exists(final_output):
            print(f"   ✅ Found cached podcast audio: {final_output}")
            print("   (Delete this file to force re-generation)")
            return str(final_output)

        # CACHE CHECK 2: Remastering (Music Mix)
        # If the user deleted the final MP3 but kept the RAW WAV, they want to re-mix.
        if os.path.exists(raw_output):
            print(f"   ✅ Found cached raw speech: {raw_output}")
            print("   ⏩ Skipping TTS generation. Proceeding to mix...")
            # Load the existing raw conversation clip
            conversation_clip = AudioFileClip(str(raw_output))
            
        else:
            # 1. Parse Script
            lines = []
            # Simple parsing logic
            raw_lines = script_text.split('\n')
            for line in raw_lines:
                line = line.strip()
                if not line: continue
                
                # Detect Speaker
                if ':' not in line:
                    continue
                
                parts = line.split(':', 1)
                prefix = parts[0].strip()
                text = parts[1].strip()
                
                speaker = None
                if any(x in prefix for x in ["Host A", "HOST A", "Marcus"]):
                    speaker = "A"
                elif any(x in prefix for x in ["Host B", "HOST B", "Sarah"]):
                    speaker = "B"
                else:
                    continue
            
                if text:
                    # CLEANING:
                    # 1. Phonetic fixes for better TTS
                    text = text.replace("A.I.", "Ay Eye").replace("AI", "Ay Eye")
                    
                    # 2. Remove markdown bold/italic asterisks
                    text = text.replace("**", "").replace("*", "")
                    
                    # 3. Ignore sound cues like (Music fades)
                    import re
                    text = re.sub(r'\(.*?\)', '', text).strip()
                    
                    if text:
                        lines.append((speaker, text))
            
            if not lines:
                print("❌ No dialogue lines detected.")
                return None

            print(f"   found {len(lines)} lines of dialogue.")
            
            # 2. Synthesize each line
            clip_objects = []

            for i, (speaker, text) in enumerate(lines):
                # Select Voice
                if speaker == "A":
                    name = "en-US-Journey-D" # Male
                else:
                    name = "en-US-Journey-F" # Female
                    
                input_text = texttospeech.SynthesisInput(text=text)
                voice = texttospeech.VoiceSelectionParams(language_code="en-US", name=name)
                # High Fidelity Config: Linear16 (WAV) + 44.1kHz
                audio_config = texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.LINEAR16,
                    sample_rate_hertz=44100
                )
                
                try:
                    # We save each line to disk as WAV
                    line_filename = audio_dir / f"temp_{slug}_line_{i}.wav"
                    
                    # Check cache (optional, skipping for now)
                    response = self.client.synthesize_speech(input=input_text, voice=voice, audio_config=audio_config)
                    
                    with open(line_filename, "wb") as out:
                        out.write(response.audio_content)
                    
                    temp_clips.append(line_filename)
                    clip_objects.append(AudioFileClip(str(line_filename)))
                    
                except Exception as e:
                    print(f"❌ Error generating line {i}: {e}")
                    
            # 3. Concatenate (Raw Conversation)
            print("   🔗 Stitching conversation...")
            conversation_clip = concatenate_audioclips(clip_objects)
            
            # Export raw conversation temporarily (WAV)
            conversation_clip.write_audiofile(str(raw_output), fps=44100, logger=None)
            
            # Close clip objects
            for c in clip_objects: c.close()
            
            # Cleanup temps
            for f in temp_clips:
                try:
                    os.remove(f)
                except: pass

        # Ensure conversation_clip is not None before proceeding
        if conversation_clip is None:
            print("❌ Failed to get conversation audio clip.")
            return None

        # 4. Mix with Music
        
        try:
            from audio_mixer_moviepy import mix_audio_moviepy
            # Priority: 1. User Added Music ("Background Mucis.mp3"), 2. Default "Blue Saga"
            bg_music = "static/audio/Background Mucis.mp3"
            if not os.path.exists(bg_music):
                bg_music = "static/audio/ES_Cinematics - Blue Saga - 0000-58213.wav"
            
            if os.path.exists(bg_music):
                print(f"   🎛️ Mixing with background music: {os.path.basename(bg_music)}")
                mix_audio_moviepy(str(raw_output), bg_music, str(final_output))
            else:
                print("   ⚠️ Background music not found, using raw.")
                # Convert WAV to MP3 final
                conversation_clip.write_audiofile(str(final_output), fps=44100, logger=None) # write directly to mp3 if no mix
                
        except Exception as mx:
            print(f"   ⚠️ Mixing failed: {mx}")
            # Fallback conver to MP3
            # We need to load raw_output as clip if we skipped generation
            try:
                from moviepy import AudioFileClip
                raw_clip = AudioFileClip(str(raw_output))
                raw_clip.write_audiofile(str(final_output), fps=44100, logger=None)
                raw_clip.close()
            except:
                pass

        # We keep the raw_output now (to allow re-mixing without re-generating TTS)
        # if os.path.exists(raw_output): os.remove(raw_output)

        return str(final_output)

if __name__ == "__main__":
    # Test block
    gen = AudioGenerator()
    # To test locally, set GOOGLE_APPLICATION_CREDENTIALS in your .env pointing to a valid JSON
    m, f = gen.generate_audio_reads("test-wire-signal", "Testing Google Cloud intelligence read-aloud functionality.")
    print(f"Results -> Male: {m}, Female: {f}")
