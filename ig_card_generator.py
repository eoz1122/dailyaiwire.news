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

    # ── Layout constants ──
    PAD_X = 60                     # horizontal padding
    MAX_TEXT_W = CARD_SIZE[0] - PAD_X * 2   # 960px usable width
    HEADER_BOTTOM = 180            # vertical space reserved for logo + brand
    FOOTER_HEIGHT = 120            # bottom bar height
    FOOTER_TOP = CARD_SIZE[1] - FOOTER_HEIGHT
    CONTENT_ZONE = FOOTER_TOP - HEADER_BOTTOM  # ~780px for text

    # 4. Logo (top-left area)
    try:
        logo = Image.open(LOGO_PATH).convert("RGBA")
        logo = logo.resize((100, 100), Image.LANCZOS)
        img.paste(logo, (PAD_X, 35), logo)
    except Exception:
        pass  # Skip logo if not found

    # 5. "DAILY AI WIRE" label next to logo
    label_font = _get_font(30, bold=True)
    draw.text((PAD_X + 115, 63), "DAILY AI WIRE", fill=ACCENT_COLOR, font=label_font)

    # 6. Accent dot + line separator
    draw.ellipse([(PAD_X, 158), (PAD_X + 12, 170)], fill=ACCENT_COLOR)
    draw.line([(PAD_X + 18, 164), (PAD_X + 180, 164)], fill=ACCENT_COLOR, width=3)

    # ── 7. Dynamic headline sizing ──────────────────────────────
    # Try progressively smaller fonts until the text fits the content zone,
    # picking the LARGEST size that works.  This ensures the card always
    # looks full regardless of headline length.

    gist_clean = ""
    if gist:
        gist_clean = gist.replace("**", "").replace("*", "")

    best = None
    for font_size in range(120, 38, -2):
        font = _get_font(font_size, bold=True)
        line_h = int(font_size * 1.25)

        # Estimate how many chars fit per line at this size
        # (avg char width ≈ 0.6 × font_size for bold sans-serif)
        avg_char_w = font_size * 0.58
        chars_per_line = max(10, int(MAX_TEXT_W / avg_char_w))

        wrapped = textwrap.fill(headline, width=chars_per_line)
        lines = wrapped.split("\n")
        if len(lines) > 7:
            continue  # too many lines, try smaller

        headline_h = len(lines) * line_h

        # Gist sizing: proportional to headline (roughly 40% of headline font)
        gist_h = 0
        gist_font_size = max(24, int(font_size * 0.42))
        gist_lines = []
        if gist_clean:
            gist_avg_w = gist_font_size * 0.52
            gist_chars = max(20, int(MAX_TEXT_W / gist_avg_w))
            gist_wrapped = textwrap.fill(gist_clean, width=gist_chars)
            gist_lines = gist_wrapped.split("\n")[:5]
            gist_line_h = int(gist_font_size * 1.4)
            gist_h = len(gist_lines) * gist_line_h + 30  # 30px gap above gist

        total_h = headline_h + gist_h

        if total_h <= CONTENT_ZONE:
            best = {
                "font_size": font_size, "font": font, "line_h": line_h,
                "lines": lines, "headline_h": headline_h,
                "gist_font_size": gist_font_size, "gist_lines": gist_lines,
                "gist_h": gist_h, "total_h": total_h,
            }
            break  # largest fitting size found

    if best is None:
        # Absolute fallback — smallest size
        best = {
            "font_size": 40, "font": _get_font(40, bold=True), "line_h": 50,
            "lines": textwrap.fill(headline, width=30).split("\n")[:7],
            "headline_h": 350, "gist_font_size": 24, "gist_lines": [],
            "gist_h": 0, "total_h": 350,
        }

    # Vertically center all content within the content zone
    y_cursor = HEADER_BOTTOM + (CONTENT_ZONE - best["total_h"]) // 2

    # Draw headline
    for line in best["lines"]:
        draw.text((PAD_X, y_cursor), line, fill=TEXT_COLOR, font=best["font"])
        y_cursor += best["line_h"]

    # Draw gist
    if best["gist_lines"]:
        y_cursor += 30  # gap
        gist_font = _get_font(best["gist_font_size"])
        gist_line_h = int(best["gist_font_size"] * 1.4)
        for line in best["gist_lines"]:
            draw.text((PAD_X, y_cursor), line, fill=SUBTEXT_COLOR, font=gist_font)
            y_cursor += gist_line_h

    # ── 9. Bottom bar ───────────────────────────────────────────
    draw.rectangle([(0, FOOTER_TOP), (CARD_SIZE[0], CARD_SIZE[1])], fill=(244, 244, 245))
    draw.rectangle([(0, FOOTER_TOP), (CARD_SIZE[0], FOOTER_TOP + 5)], fill=ACCENT_COLOR)

    # 10. Watermark
    watermark_font = _get_font(28)
    draw.text((PAD_X, CARD_SIZE[1] - 80), "dailyaiwire.news", fill=WATERMARK_COLOR, font=watermark_font)

    # 11. "Read Full Analysis →" CTA
    cta_font = _get_font(28, bold=True)
    cta_text = "Read Full Analysis →"
    cta_bbox = draw.textbbox((0, 0), cta_text, font=cta_font)
    cta_w = cta_bbox[2] - cta_bbox[0]
    draw.text((CARD_SIZE[0] - PAD_X - cta_w, CARD_SIZE[1] - 80), cta_text, fill=ACCENT_COLOR, font=cta_font)

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
