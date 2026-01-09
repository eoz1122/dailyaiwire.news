try:
    import moviepy
    print(f"MoviePy Version: {moviepy.__version__}")
except Exception as e:
    print(f"Error importing moviepy: {e}")

try:
    from moviepy import vfx
    print("Successfully imported vfx from moviepy")
    if hasattr(vfx, 'loop'):
        print("Found loop in vfx")
except ImportError:
    print("Could not import vfx from moviepy")

try:
    import moviepy.video.fx.all as vfx_all
    print("Successfully imported moviepy.video.fx.all")
except ImportError as e:
    print(f"Failed to import moviepy.video.fx.all: {e}")
