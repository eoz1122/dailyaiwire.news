import os
import random
from moviepy import (
    VideoFileClip, 
    AudioFileClip, 
    TextClip, 
    ImageClip, 
    CompositeVideoClip, 
    ColorClip
)

def render_briefing_video(audio_path, background_template, output_file, headlines=None):
    """
    Renders a briefing video with:
    - Background (video loop or image)
    - Logo overlay
    - News Ticker (Sliding banner at the bottom)
    - Audio track
    """
    print(f"🎬 Rendering briefing video: {output_file}")
    
    if not os.path.exists(audio_path):
        print(f"❌ Audio file not found: {audio_path}")
        return False

    audio = AudioFileClip(audio_path)
    duration = audio.duration
    size = (1920, 1080)
    
    # 1. Background
    bg = None
    if os.path.isdir(background_template):
        loops = [os.path.join(background_template, f) for f in os.listdir(background_template) if f.endswith(('.mp4', '.mov'))]
        if loops:
            bg_path = random.choice(loops)
            print(f"🖼️ Using random background loop: {bg_path}")
            bg = VideoFileClip(bg_path).with_duration(duration)
            if bg.size != size:
                bg = bg.resized(height=size[1]).cropped(width=size[0], height=size[1], x_center=bg.size[0]/2, y_center=bg.size[1]/2)
        else:
            print("⚠️ No video loops found in directory. Using fallback image.")
            
    if not bg:
        # Fallback to static image or ColorClip
        fallback_img = "static/video/intro_bg.png"
        if os.path.exists(fallback_img):
            print(f"🖼️ Using fallback background image: {fallback_img}")
            bg = ImageClip(fallback_img).with_duration(duration)
            # Center-crop/Fill scaling
            w, h = bg.size
            scale = max(size[0]/w, size[1]/h)
            bg = bg.resized(scale).cropped(width=size[0], height=size[1], x_center=bg.size[0]/2, y_center=bg.size[1]/2)
        else:
            print("🎨 Using solid color background.")
            bg = ColorClip(size=size, color=(10, 10, 20), duration=duration)

    # 2. Logo Overlay
    logo_path = "static/video/logo.png"
    logo = None
    if os.path.exists(logo_path):
        logo = ImageClip(logo_path).with_duration(duration)
        logo_h = 180
        logo = logo.resized(height=logo_h)
        # Position top right
        logo = logo.with_position((size[0] - logo.size[0] - 50, 50))

    # 3. News Ticker (Sliding Banner)
    ticker_group = None
    if headlines:
        ticker_height = 100
        ticker_bg = ColorClip(size=(size[0], ticker_height), color=(0, 0, 0, 180)).with_duration(duration)
        ticker_bg = ticker_bg.with_position(('center', size[1] - ticker_height))
        
        # Combine headlines into a single long string
        full_text = " • ".join(headlines)
        full_text = "     " + full_text + "     " # Padding
        
        # Determine font
        font_path = "C:/Windows/Fonts/bahnschrift.ttf"
        if not os.path.exists(font_path): font_path = "C:/Windows/Fonts/arial.ttf"
        
        try:
            txt = TextClip(
                text=full_text, 
                font=font_path, 
                font_size=50, 
                color='white',
                method='label'
            ).with_duration(duration)
            
            # Animation: Scroll from right to left with looping
            scroll_speed = 150 
            text_width = txt.size[0]
            total_scroll_width = size[0] + text_width
            
            def scroll_pos(t):
                # Start at screen-right (size[0]), move to -text_width
                # Offset cycles every (total_scroll_width / scroll_speed) seconds
                x = size[0] - (scroll_speed * t) % total_scroll_width
                return (x, size[1] - ticker_height + 25)
            
            txt = txt.with_position(scroll_pos)
            ticker_group = [ticker_bg, txt]
        except Exception as e:
            print(f"⚠️ Ticker rendering failed: {e}")

    # 4. Composite
    clips = [bg]
    if logo: clips.append(logo)
    if ticker_group: clips.extend(ticker_group)
    
    final = CompositeVideoClip(clips, size=size).with_duration(duration)
    final.audio = audio
    
    # 5. Write
    final.write_videofile(output_file, fps=24, codec='libx264', audio_codec='aac', logger=None)
    print(f"✅ Video saved: {output_file}")
    
    # Cleanup
    bg.close()
    if logo: logo.close()
    audio.close()
    
    return True

if __name__ == "__main__":
    # Test
    render_briefing_video("dummy_silence.mp3", "static/video/loops", "test_render.mp4", headlines=["Headline 1", "Headline 2"])
