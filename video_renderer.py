import os
# MoviePy v2 imports
from moviepy import AudioFileClip, VideoFileClip, ColorClip, TextClip, CompositeVideoClip, concatenate_videoclips, VideoClip
# Import effects classes
try:
    from moviepy.video.fx import Loop
except ImportError:
    print("⚠️ Could not import Loop from moviepy.video.fx")
    Loop = None

def create_news_ticker(headlines, duration, video_size=(1920, 1080)):
    """
    Creates a scrolling news ticker with a 'Tech/AI' aesthetic.
    Returns a CompositeVideoClip containing the bar and scrolling text.
    """
    w, h = video_size
    bar_height = 80
    bar_y = h - bar_height
    
    # MoviePy v2: Standardize FPS to 24 for all clips
    FPS = 24

    # 1. Tech Background Bar (Dark Blue/Black with opacity)
    # Color: #050A14 (Very dark blue)
    bar_bg = ColorClip(size=(w, bar_height), color=(5, 10, 20)).with_duration(duration)
    # Ensure it has FPS
    bar_bg.fps = FPS
    bar_bg = bar_bg.with_opacity(0.90).with_position((0, bar_y))
    
    # 2. Cyan Accent Line (Top of bar)
    # Color: #00FFFF (Cyan) or #007BFF (Electric Blue)
    accent_height = 4
    accent_line = ColorClip(size=(w, accent_height), color=(0, 255, 255)).with_duration(duration)
    accent_line.fps = FPS
    accent_line = accent_line.with_position((0, bar_y)) # Sits right on top of the bg
    
    print(f"   📰 News Ticker: Building string with {len(headlines)} items...")
    full_text = "   ///   ".join([h.upper() for h in headlines]) + "   ///   DAILY AI WIRE   ///   " * 2
    
    try:
        # Create a long text clip
        # Try multiple common fonts, or fall back to system default
        font_choices = ['Arial', 'Verdana', 'Helvetica', 'DejaVu-Sans']
        txt_clip = None
        
        for font in font_choices:
            try:
                # Use default method (label) for single-line scrolling text
                txt_clip = TextClip(
                    text=full_text, 
                    font_size=45, 
                    color='white', 
                    font=font
                ).with_duration(duration)
                if txt_clip: break
            except:
                continue
        
        if not txt_clip:
            # Absolute fallback
            txt_clip = TextClip(
                text=full_text, 
                font_size=45, 
                color='white'
            ).with_duration(duration)
        
        txt_clip.fps = FPS
        print("   ✅ TextClip created successfully.")
        
        # Calculate scrolling speed
        # We want it to scroll from Right to Left
        txt_w = txt_clip.w
        print(f"   📏 Ticker width: {txt_w}px")
        
        # Speed: pixels per second (adjust 1.0 for speed)
        speed = (txt_w + w) / duration 
        
        # Define position function: x(t) = w - speed * t
        def scroll_func(t):
            x = w - (speed * t * 0.9) # Slightly faster
            return (int(x), bar_y + 15) 
            
        txt_clip = txt_clip.with_position(scroll_func)
        
        # 4. Logo Overlay (Left side)
        logo_path = "static/logo.png"
        if os.path.exists(logo_path):
            try:
                try:
                    from moviepy import ImageClip
                except ImportError:
                    from moviepy.editor import ImageClip
                    
                logo = ImageClip(logo_path).with_duration(duration)
                logo.fps = FPS
                # Resize to fit bar (sqaure-ish)
                logo_size = bar_height - 10 # padding
                logo = logo.resized(height=logo_size)
                # Position: Leftmost, centered vertically in bar
                logo = logo.with_position((10, bar_y + 5))
                
                # 5. Logo Background (Opaque box to hide scrolling text)
                logo_bg_w = logo.w + 40
                logo_bg = ColorClip(size=(logo_bg_w, bar_height), color=(5, 10, 20)).with_duration(duration)
                logo_bg.fps = FPS
                logo_bg = logo_bg.with_position((0, bar_y))
                
                print("   🎨 Logo and Ticker integrated.")
                # Order: BarBG, Text, LogoBox, Logo, Accent
                return [bar_bg, txt_clip, logo_bg, logo, accent_line]
                
            except Exception as e:
                print(f"   ⚠️ Logo load failed: {e}")
                
        # If no logo, just add accent on top
        print("   🎨 Ticker (without logo) integrated.")
        return [bar_bg, txt_clip, accent_line]
        
    except Exception as e:
        print(f"   ❌ Ticker generation CRITICAL failure: {e}")
        return []

def render_briefing_video(audio_path, background_video_path, output_path="daily_briefing.mp4", headlines=[]):
    """
    Creates a video by looping a background template to match the narration audio.
    """
    print(f"🎬 Starting Video Render...")
    FPS = 24
    print(f"   Audio: {audio_path}")
    print(f"   Background: {background_video_path}")

    if not os.path.exists(audio_path):
        print("❌ Error: Audio file not found.")
        return False

    try:
        # Load Audio
        audio = AudioFileClip(audio_path)
        duration = audio.duration
        print(f"   Duration: {duration:.2f}s")
        
        # Load Background
        if background_video_path and os.path.exists(background_video_path):
            # Check if it's a directory (Multi-Clip Mode) or file
            if os.path.isdir(background_video_path):
                print(f"   📂 Detected Multi-Clip Directory: {background_video_path}")
                clips = []
                # Find all .mp4 files
                for f in os.listdir(background_video_path):
                    if f.lower().endswith(".mp4"):
                        full_p = os.path.join(background_video_path, f)
                        try:
                            clips.append(VideoFileClip(full_p))
                            print(f"      + Loaded clip: {f}")
                        except Exception as e:
                            print(f"      ⚠️ Failed to load {f}: {e}")
                
                if clips:
                     # Concatenate all found clips into one base clip
                     print(f"   🔗 Stitching {len(clips)} clips into a mega-loop...")
                     # Resize all to 1080p to ensure consistency (optional but safe)
                     # clips = [c.resize(height=1080) for c in clips] 
                     bg_clip = concatenate_videoclips(clips, method="compose")
                else:
                    print("      ❌ No MP4s found in directory.")
                    bg_clip = None
            else:
                # Single File Mode
                bg_clip = VideoFileClip(background_video_path)
            
            if bg_clip:
                # Manual fallback is often MORE stable in MoviePy v2 on Windows
                print("   🔄 Looping background manually for stability...")
                count = int(duration / bg_clip.duration) + 1
                clips = [bg_clip] * count
                final_clip = concatenate_videoclips(clips)
                final_clip = final_clip.subclipped(0, duration)
            else:
                final_clip = None 
        else:
            final_clip = None 

        if not final_clip:
            # Check for Image Fallback (e.g. static/video/background.png)
            bg_image_path = "static/video/background.png"
            if not os.path.exists(bg_image_path):
                 # Try typical extensions
                 if os.path.exists("static/video/background.jpg"): bg_image_path = "static/video/background.jpg"
            
            if os.path.exists(bg_image_path):
                print(f"⚠️ Background video not found. Using Image Fallback: {bg_image_path}")
                try:
                    from moviepy import ImageClip
                except ImportError:
                    from moviepy.editor import ImageClip
                    
                final_clip = ImageClip(bg_image_path).with_duration(duration)
                final_clip.fps = FPS
                
                # Add Title Overlay
                txt = TextClip(text="Daily AI Wire", font_size=70, color='white', size=(1920, 1080)).with_duration(duration)
                txt.fps = FPS
                final_clip = CompositeVideoClip([final_clip, txt.with_position('center')])
            else:
                print("⚠️ Background video/image not found. Using solid color fallback.")
                final_clip = ColorClip(size=(1920, 1080), color=(10, 20, 60)).with_duration(duration)
                final_clip.fps = FPS
                
                txt = TextClip(text="Daily AI Wire", font_size=70, color='white', size=(1920, 1080)).with_duration(duration)
                txt.fps = FPS
                final_clip = CompositeVideoClip([final_clip, txt.with_position('center')])

        # === ADD NEWS TICKER ===
        if headlines:
            print(f"   📰 Generatng News Ticker with {len(headlines)} headlines...")
            ticker_layers = create_news_ticker(headlines, duration)
            if ticker_layers:
                # Standardize all layers
                ready_layers = []
                for layer in ticker_layers:
                    layer = layer.with_duration(duration)
                    layer.fps = FPS
                    ready_layers.append(layer)
                
                final_clip = CompositeVideoClip([final_clip] + ready_layers).with_duration(duration)
                final_clip.fps = FPS

        # === FINAL ASSEMBLY ===
        if audio:
            final_clip = final_clip.with_audio(audio)
            final_clip = final_clip.with_duration(audio.duration)
        else:
            final_clip = final_clip.with_duration(duration)

        final_clip.fps = FPS

        # Write Output
        print(f"💾 Rendering to {output_path} (Forced Frame Mode, Duration: {final_clip.duration}s)...")
        
        # BRIDGE: Force MoviePy to render the composite clip frame-by-frame
        # This is the most reliable way to avoid the '0 second' video bug in v2.
        def get_frame_at_t(t):
            return final_clip.get_frame(t)
            
        final_render_clip = VideoClip(get_frame_at_t, duration=final_clip.duration)
        final_render_clip.fps = FPS
        if final_clip.audio:
            final_render_clip.audio = final_clip.audio

        try:
            # Using libx264 with sensible defaults
            final_render_clip.write_videofile(
                output_path, 
                fps=FPS,
                codec="libx264",
                audio_codec="aac",
                logger='bar'
            )
        except Exception as write_err:
             print(f"   ⚠️ Bridge render failed, trying basic: {write_err}")
             final_clip.write_videofile(output_path, fps=FPS)
        
        print("✅ Video Render Complete!")
        return True

    except Exception as e:
        print(f"❌ Render Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Test Render
    # Dummy audio (ensure one exists or create dummy)
    test_audio = "static/audio/test_mix_output_moviepy.mp3" 
    # Use existing audio if available from previous steps
    if os.path.exists(test_audio):
        render_briefing_video(test_audio, "static/video/background_loop.mp4", "test_briefing.mp4")
    else:
        print("Skipping test: No audio file found.")
