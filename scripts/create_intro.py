import os
try:
    from moviepy import ColorClip, TextClip, CompositeVideoClip, ImageClip
except ImportError:
    from moviepy.editor import ColorClip, TextClip, CompositeVideoClip, ImageClip

def create_intro_video(output_file="static/video/intro.mp4"):
    print("🎬 Creating branded intro video...")
    
    # Settings
    duration = 5
    size = (1920, 1080)
    bg_color = (10, 10, 20)
    text_color = 'white'
    font_size = 150
    text_content = "DAILY AI WIRE"
    font_path = "C:/Windows/Fonts/bahnschrift.ttf"
    if not os.path.exists(font_path):
        font_path = "C:/Windows/Fonts/arialbi.ttf"
    if not os.path.exists(font_path):
        font_path = "C:/Windows/Fonts/arial.ttf"
    
    bg_image_path = "static/video/intro_bg.png"
    logo_path = "static/video/logo.png"
    
    # 1. Background
    try:
        if os.path.exists(bg_image_path):
            print(f"🖼️ Loading background image: {bg_image_path}")
            bg_clip = ImageClip(bg_image_path)
            
            # Duration helper
            if hasattr(bg_clip, 'with_duration'):
                bg_clip = bg_clip.with_duration(duration)
            else:
                bg_clip = bg_clip.set_duration(duration)
            
            # Scaling logic: COVER
            w, h = bg_clip.size
            scale = max(size[0]/w, size[1]/h) * 1.1 # 10% extra for zoom
            
            if hasattr(bg_clip, 'resize'):
                bg_clip = bg_clip.resize(scale)
            else:
                bg_clip = bg_clip.resized(scale)
            
            # Zoom Animation
            try:
                if hasattr(bg_clip, 'resize'):
                    bg = bg_clip.resize(lambda t: 1.0 + 0.1 * (t / duration))
                else:
                    bg = bg_clip
            except Exception:
                bg = bg_clip
                
            # Center it
            if hasattr(bg, 'with_position'):
                bg = bg.with_position('center')
            else:
                bg = bg.set_position('center')
            
        else:
            print("🎨 Using solid background color.")
            bg = ColorClip(size=size, color=bg_color, duration=duration)
    except Exception as e:
        print(f"⚠️ Background error: {e}")
        bg = ColorClip(size=size, color=bg_color, duration=duration)

    # 2. Logo Overlay
    logo = None
    if os.path.exists(logo_path):
        try:
            print(f"🎨 Loading logo: {logo_path}")
            logo = ImageClip(logo_path)
            logo_h = 240
            l_scale = logo_h / logo.size[1]
            if hasattr(logo, 'resize'):
                logo = logo.resize(l_scale)
            else:
                logo = logo.resized(l_scale)
            
            logo_duration = duration
            if hasattr(logo, 'with_duration'):
                logo = logo.with_duration(logo_duration)
            else:
                logo = logo.set_duration(logo_duration)
            
            # Center and offset upward
            l_pos = ('center', size[1]//2 - logo_h - 20)
            if hasattr(logo, 'with_position'):
                logo = logo.with_position(l_pos)
            else:
                logo = logo.set_position(l_pos)
            
            # Fade
            try:
                if hasattr(logo, 'fadein'):
                    logo = logo.fadein(1).fadeout(1)
                else:
                    from moviepy.video.fx import FadeIn, FadeOut
                    logo = logo.with_effects([FadeIn(1.0), FadeOut(1.0)])
            except Exception:
                pass
        except Exception as e:
            print(f"⚠️ Logo error: {e}")

    # 3. Text Overlay
    try:
        txt = TextClip(
            text=text_content,
            font=font_path,
            font_size=font_size,
            color=text_color,
            method='caption',
            size=(int(size[0]*0.9), None),
            stroke_color='black',
            stroke_width=4
        )
    except Exception as e:
        print(f"⚠️ Text error: {e}")
        txt = TextClip(text=text_content, font_size=font_size, color=text_color, size=(int(size[0]*0.9), None), method='caption')

    if hasattr(txt, 'with_duration'):
        txt = txt.with_duration(duration)
    else:
        txt = txt.set_duration(duration)

    # Position text below logo or center
    t_pos = ('center', size[1]//2 + 20) if logo else 'center'
    if hasattr(txt, 'with_position'):
        txt = txt.with_position(t_pos)
    else:
        txt = txt.set_position(t_pos)

    try:
        if hasattr(txt, 'fadein'):
            txt = txt.fadein(1).fadeout(1)
        else:
            from moviepy.video.fx import FadeIn, FadeOut
            txt = txt.with_effects([FadeIn(1.0), FadeOut(1.0)])
    except Exception:
        pass

    # 4. Composite
    clips = [bg]
    if logo: clips.append(logo)
    clips.append(txt)
    
    final = CompositeVideoClip(clips, size=size)
    if hasattr(final, 'with_duration'):
        final = final.with_duration(duration)
    else:
        final = final.set_duration(duration)

    # 5. Write
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    final.write_videofile(output_file, fps=24, codec='libx264', audio_codec='aac')
    print(f"✅ Branded intro video saved to: {output_file}")
    return output_file


if __name__ == "__main__":
    create_intro_video()
