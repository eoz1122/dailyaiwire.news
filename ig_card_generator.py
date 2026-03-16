"""
Branded Social Card Generator for DailyAIWire.news
Generates 1080x1080 cards with headline text on a dark gradient background.
Used as fallback/default images for Instagram and Facebook posts.
"""

import os
import textwrap
from PIL import Image, ImageDraw, ImageFont, ImageFilter


# ── Card Design Tokens ──────────────────────────────────────────
CARD_SIZE = (1080, 1080)
BG_TOP = (255, 255, 255)       # #ffffff  — white
BG_BOTTOM = (244, 244, 245)    # #f4f4f5 — zinc-100
ACCENT_COLOR = (37, 99, 235)   # #2563eb — website blue-600
TEXT_COLOR = (9, 9, 11)        # #09090b — near-black
SUBTEXT_COLOR = (113, 113, 122)  # #71717a — zinc-500
WATERMARK_COLOR = (161, 161, 170)  # #a1a1aa — zinc-400

# Paths
LOGO_PATH = os.path.join(os.path.dirname(__file__), "static", "img", "brand", "logo_nodes.png")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "static", "img", "social")


def _draw_gradient(draw, width, height, top_color, bottom_color):
    """Draw a vertical gradient from top_color to bottom_color."""
    for y in range(height):
        ratio = y / height
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * ratio)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * ratio)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))


def _get_font(size, bold=False):
    """Get the best available font, falling back gracefully."""
    # Try common system fonts in order of preference
    font_candidates = []
    if bold:
        font_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNSDisplay.ttf",
        ]
    else:
        font_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNSDisplay.ttf",
        ]

    for font_path in font_candidates:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                continue

    # Final fallback: Pillow default
    return ImageFont.load_default()


def generate_card(headline, slug, gist=""):
    """Generate a branded 1080x1080 social card and return its file path.

    Args:
        headline: Article headline text
        slug: SEO slug for filename
        gist: Optional short summary (displayed below headline)

    Returns:
        Absolute file path to the generated PNG image
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, f"{slug}.png")

    # If card already exists, return it
    if os.path.exists(output_path):
        return output_path

    img = Image.new("RGB", CARD_SIZE)
    draw = ImageDraw.Draw(img)

    # 1. Draw gradient background
    _draw_gradient(draw, CARD_SIZE[0], CARD_SIZE[1], BG_TOP, BG_BOTTOM)

    # 2. Add subtle grid pattern for depth
    for x in range(0, CARD_SIZE[0], 60):
        draw.line([(x, 0), (x, CARD_SIZE[1])], fill=(228, 228, 231), width=1)
    for y in range(0, CARD_SIZE[1], 60):
        draw.line([(0, y), (CARD_SIZE[0], y)], fill=(228, 228, 231), width=1)

    # 3. Blue accent bar at top
    draw.rectangle([(0, 0), (CARD_SIZE[0], 6)], fill=ACCENT_COLOR)

    # 4. Logo (top-left area)
    try:
        logo = Image.open(LOGO_PATH).convert("RGBA")
        logo = logo.resize((80, 80), Image.LANCZOS)
        # Place logo with slight offset
        img.paste(logo, (60, 50), logo)
    except Exception:
        pass  # Skip logo if not found

    # 5. "DAILY AI WIRE" label next to logo
    label_font = _get_font(24, bold=True)
    draw.text((155, 72), "DAILY AI WIRE", fill=ACCENT_COLOR, font=label_font)

    # 6. Accent dot separator
    draw.ellipse([(60, 160), (68, 168)], fill=ACCENT_COLOR)
    draw.line([(74, 164), (200, 164)], fill=ACCENT_COLOR, width=2)

    # 7. Headline text (main content — auto-sized)
    headline_font_size = 56
    headline_font = _get_font(headline_font_size, bold=True)

    # Wrap text to fit width (with padding)
    max_width_chars = 24  # characters per line
    if len(headline) > 80:
        max_width_chars = 28
        headline_font_size = 48
        headline_font = _get_font(headline_font_size, bold=True)
    if len(headline) > 120:
        max_width_chars = 32
        headline_font_size = 42
        headline_font = _get_font(headline_font_size, bold=True)

    wrapped = textwrap.fill(headline, width=max_width_chars)
    lines = wrapped.split("\n")[:6]  # Max 6 lines

    y_start = 210
    line_height = int(headline_font_size * 1.35)
    for i, line in enumerate(lines):
        draw.text((60, y_start + i * line_height), line, fill=TEXT_COLOR, font=headline_font)

    # 8. Gist text (below headline, smaller)
    if gist:
        gist_y = y_start + len(lines) * line_height + 30
        gist_font = _get_font(26)
        gist_clean = gist.replace("**", "").replace("*", "")
        gist_wrapped = textwrap.fill(gist_clean, width=48)
        gist_lines = gist_wrapped.split("\n")[:4]  # Max 4 lines
        for i, line in enumerate(gist_lines):
            draw.text((60, gist_y + i * 36), line, fill=SUBTEXT_COLOR, font=gist_font)

    # 9. Bottom bar with gradient accent
    draw.rectangle([(0, CARD_SIZE[1] - 100), (CARD_SIZE[0], CARD_SIZE[1])], fill=(244, 244, 245))
    draw.rectangle([(0, CARD_SIZE[1] - 100), (CARD_SIZE[0], CARD_SIZE[1] - 96)], fill=ACCENT_COLOR)

    # 10. Watermark
    watermark_font = _get_font(22)
    draw.text((60, CARD_SIZE[1] - 70), "dailyaiwire.news", fill=WATERMARK_COLOR, font=watermark_font)

    # 11. "Read Full Analysis →" CTA
    cta_font = _get_font(22, bold=True)
    draw.text((CARD_SIZE[0] - 280, CARD_SIZE[1] - 70), "Read Full Analysis →", fill=ACCENT_COLOR, font=cta_font)

    # Save
    img.save(output_path, "PNG", quality=95)
    print(f"🎨 Generated social card: {output_path}")
    return output_path


if __name__ == "__main__":
    # Test card generation
    test_path = generate_card(
        headline="Email: The Unexpected Foundation for Ambient AI Agents",
        slug="test-card",
        gist="Email provides a readily available, high-signal context substrate for ambient AI agents."
    )
    print(f"Test card saved to: {test_path}")
