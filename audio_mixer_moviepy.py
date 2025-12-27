from moviepy import AudioFileClip, CompositeAudioClip, concatenate_audioclips
import os

def mix_audio_moviepy(narration_path, music_path, output_path, music_volume=0.08, delay_sec=1.0):
    """
    Mixes narration with background music using moviepy.
    
    Structure:
      [ 1s Music Intro ] + [ Narration ] + [ 1s Music Outro ]
      
    Music is looped to cover the full duration and volume is lowered (ducking).
    """
    print(f"🎵 Loading Audio (MoviePy)...")
    try:
        # Load clips
        narration = AudioFileClip(narration_path)
        music_source = AudioFileClip(music_path)
    except Exception as e:
        print(f"❌ Error loading audio: {e}")
        return False

    # Calculate total target duration
    # Duration = 1s intro + narration + 1s outro
    total_duration = delay_sec + narration.duration + delay_sec
    
    print(f"⏱️  Durations:")
    print(f"   - Narration: {narration.duration:.2f}s")
    print(f"   - Total Mix: {total_duration:.2f}s")

    # Prepare Music Track
    # 1. Loop music if it's shorter than needed
    if music_source.duration < total_duration:
        # Calculate how many times to loop
        loop_count = int(total_duration / music_source.duration) + 2
        # Create a list of the same clip repeated
        music_clips = [music_source] * loop_count
        # Concatenate them
        bg_music = concatenate_audioclips(music_clips)
    else:
        bg_music = music_source

    # 2. Advanced Ducking Strategy: GRADUAL FADE
    # - Intro: 0 to delay_sec (Vol 0.12) -> Fade OUT last 0.5s
    # - Body:  delay_sec to delay_sec + narr_len (Vol 0.03) -> Fade IN first 0.5s
    # - Outro: delay_sec + narr_len to end (Vol 0.12) -> Fade IN first 0.5s
    
    vol_high = 0.12
    vol_low = 0.03
    narr_len = narration.duration
    fade_duration = 0.8 # Smooth transition time

    # MoviePy v2 Compatibility Fix: Use v2 effects
    # Import effects inside function or at top (adding at top is cleaner but editing here)
    from moviepy.audio.fx import AudioFadeIn, AudioFadeOut
    
    # Intro: Starts High, stays High
    bg_intro = bg_music.subclipped(0, delay_sec).with_volume_scaled(vol_high)
    # Apply fade out to the END of intro
    bg_intro = bg_intro.with_effects([AudioFadeOut(duration=fade_duration)])

    # Body: Starts Low, stays Low
    bg_body = bg_music.subclipped(delay_sec, delay_sec + narr_len).with_volume_scaled(vol_low)
    # Fade IN (from intro) and Fade OUT (to outro)
    bg_body = bg_body.with_effects([AudioFadeIn(duration=fade_duration), AudioFadeOut(duration=fade_duration)])

    # Outro: Starts High
    bg_outro = bg_music.subclipped(delay_sec + narr_len, total_duration).with_volume_scaled(vol_high)
    # Fade IN from body
    bg_outro = bg_outro.with_effects([AudioFadeIn(duration=fade_duration)])

    # Reassemble music track with ducking
    bg_music_ducked = concatenate_audioclips([bg_intro, bg_body, bg_outro])

    # Prepare Narration Track
    # Shift narration start time by 'delay_sec'
    # We use CompositeAudioClip to layer them. 
    # Narration needs to be "set_start" to delay it.
    narration = narration.with_start(delay_sec)

    # Mix
    print("🎛️  Mixing...")
    final_mix = CompositeAudioClip([bg_music_ducked, narration])

    # Export
    print(f"💾 Saving to {output_path}...")
    try:
        # standard bitrate 192k is good for speech+music
        final_mix.write_audiofile(output_path, fps=44100, bitrate="192k", logger=None)
        print("✅ Done!")
        
        # Cleanup resource handles
        narration.close()
        music_source.close()
        bg_music.close()
        final_mix.close()
        return True
    except Exception as e:
        print(f"❌ Error exporting: {e}")
        return False

if __name__ == "__main__":
    # Test Configuration
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    STATIC_AUDIO = os.path.join(BASE_DIR, "static", "audio")
    
    # Input Files
    narration_file = os.path.join(STATIC_AUDIO, "gemini-2-5-flash-lite-release_male.mp3")
    music_file = os.path.join(STATIC_AUDIO, "ES_Cinematics - Blue Saga - 0000-58213.wav")
    
    # Output File
    output_file = os.path.join(STATIC_AUDIO, "test_mix_output_moviepy.mp3")
    
    if os.path.exists(narration_file) and os.path.exists(music_file):
        mix_audio_moviepy(narration_file, music_file, output_file)
    else:
        print("⚠️  Files not found.")
        if not os.path.exists(narration_file): print(f"Missing: {narration_file}")
        if not os.path.exists(music_file): print(f"Missing: {music_file}")
