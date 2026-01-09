import os
from pydub import AudioSegment
import math

def mix_audio(narration_path, music_path, output_path, music_volume_percent=0.15, delay_ms=1000):
    """
    Mixes narration with background music.
    
    Args:
        narration_path (str): Path to the TTS narration file (MP3/WAV).
        music_path (str): Path to the background music file (MP3/WAV).
        output_path (str): Path to save the mixed audio.
        music_volume_percent (float): Volume of music relative to original (0.0 to 1.0). 
                                      Default 0.15 (15%).
        delay_ms (int): Delay in milliseconds for narration start (and buffer at end).
    """
    print(f"🎵 Loading Audio...")
    print(f"   - Narration: {narration_path}")
    print(f"   - Music:     {music_path}")

    try:
        # Load audio files
        narration = AudioSegment.from_file(narration_path)
        music = AudioSegment.from_file(music_path)
    except Exception as e:
        print(f"❌ Error loading audio files. Ensure ffmpeg is installed if using MP3.\nError: {e}")
        return False

    # Calculate target duration
    # Structure: [Music Only (delay_ms)] + [Narration] + [Music Only (delay_ms)]
    total_duration_ms = len(narration) + (delay_ms * 2)
    
    print(f"⏱️  Duration Calc:")
    print(f"   - Narration: {len(narration)} ms")
    print(f"   - Total Mix: {total_duration_ms} ms")

    # Process Music
    # 1. Loop if too short
    if len(music) < total_duration_ms:
        loop_count = math.ceil(total_duration_ms / len(music))
        music = music * loop_count
    
    # 2. Trim to exact length
    bg_music = music[:total_duration_ms]

    # 3. Lower Volume (Ducking)
    # Convert percentage to dB: 20 * log10(percent)
    # e.g., 0.15 -> -16.47 dB
    if music_volume_percent > 0:
        gain_db = 20 * math.log10(music_volume_percent)
        bg_music = bg_music.apply_gain(gain_db)
    else:
        bg_music = bg_music - 100 # Silence

    # Mix
    # Overlay narration onto music starting at delay_ms
    print("🎛️  Mixing...")
    mixed = bg_music.overlay(narration, position=delay_ms)

    # Export
    print(f"💾 Saving to {output_path}...")
    try:
        mixed.export(output_path, format="mp3")
        print("✅ Done!")
        return True
    except Exception as e:
        print(f"❌ Error exporting: {e}")
        return False

if __name__ == "__main__":
    # Test Configuration
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    STATIC_AUDIO = os.path.join(BASE_DIR, "static", "audio")
    
    # Input Files
    narration_file = os.path.join(STATIC_AUDIO, "test-wire-signal_male.mp3")
    music_file = os.path.join(STATIC_AUDIO, "ES_Cinematics - Blue Saga - 0000-58213.wav")
    
    # Output File
    output_file = os.path.join(STATIC_AUDIO, "test_mix_output.mp3")

    if os.path.exists(narration_file) and os.path.exists(music_file):
        mix_audio(narration_file, music_file, output_file)
    else:
        print("⚠️  Test files not found:")
        if not os.path.exists(narration_file): print(f"   - Missing: {narration_file}")
        if not os.path.exists(music_file): print(f"   - Missing: {music_file}")
