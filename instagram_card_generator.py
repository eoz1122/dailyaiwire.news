"""Generate portrait cards for browser-posted DailyAIWire Instagram articles."""
from __future__ import annotations

import os
from typing import Any

from PIL import Image, ImageDraw, ImageFont


CARD_SIZE = (1080, 1350)
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "static", "img", "social")
LOGO_PATH = os.path.join(
    os.path.dirname(__file__), "static", "img", "brand", "logo_nodes.png"
)
ACCENT = (37, 99, 235)
TEXT = (9, 9, 11)
MUTED = (82, 82, 91)
GRID = (228, 228, 231)
CARD_VERSION = "instagram-v1"


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    names = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        ]
        if bold
        else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ]
    )
    for path in names:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _line_width(text: str, font: ImageFont.ImageFont) -> int:
    left, _, right, _ = font.getbbox(text)
    return right - left


def _wrap_words(text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = str(text or "").split()
    lines: list[str] = []
    current = ""
    for word in words:
        proposed = f"{current} {word}".strip()
        if current and _line_width(proposed, font) > max_width:
            lines.append(current)
            current = word
        else:
            current = proposed
    if current:
        lines.append(current)
    return lines


def _fit_title(text: str, *, max_width: int, max_height: int) -> dict[str, Any]:
    for size in range(92, 43, -2):
        title_font = _font(size, bold=True)
        lines = _wrap_words(text, title_font, max_width)
        line_height = int(size * 1.2)
        height = len(lines) * line_height
        if len(lines) <= 6 and height <= max_height:
            return {
                "font": title_font,
                "font_size": size,
                "lines": lines,
                "line_height": line_height,
                "height": height,
            }
    title_font = _font(44, bold=True)
    lines = _wrap_words(text, title_font, max_width)[:6]
    return {
        "font": title_font,
        "font_size": 44,
        "lines": lines,
        "line_height": 53,
        "height": len(lines) * 53,
    }


def generate_card(headline: str, slug: str, gist: str = "") -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, f"{slug}-{CARD_VERSION}.png")
    if os.path.exists(output_path):
        return output_path

    image = Image.new("RGB", CARD_SIZE, (250, 250, 250))
    draw = ImageDraw.Draw(image)
    for x in range(0, CARD_SIZE[0], 60):
        draw.line([(x, 0), (x, CARD_SIZE[1])], fill=GRID, width=1)
    for y in range(0, CARD_SIZE[1], 60):
        draw.line([(0, y), (CARD_SIZE[0], y)], fill=GRID, width=1)
    draw.rectangle([(0, 0), (CARD_SIZE[0], 8)], fill=ACCENT)

    try:
        logo = Image.open(LOGO_PATH).convert("RGBA").resize((94, 94), Image.Resampling.LANCZOS)
        image.paste(logo, (72, 60), logo)
    except (OSError, ValueError):
        pass
    draw.text((188, 86), "DAILY AI WIRE", font=_font(31, bold=True), fill=ACCENT)
    draw.text((72, 178), "AI NEWS THAT MOVES THE INDUSTRY", font=_font(22), fill=MUTED)

    title_layout = _fit_title(headline, max_width=936, max_height=720)
    y = 300
    for line in title_layout["lines"]:
        draw.text((72, y), line, font=title_layout["font"], fill=TEXT)
        y += title_layout["line_height"]

    clean_gist = " ".join(str(gist or "").replace("**", "").split())
    gist_font = _font(29)
    gist_lines = _wrap_words(clean_gist, gist_font, 936)[:3]
    if gist_lines:
        y += 36
        for line in gist_lines:
            draw.text((72, y), line, font=gist_font, fill=MUTED)
            y += 42

    footer_top = 1190
    draw.rectangle([(0, footer_top), (1080, 1350)], fill=(244, 244, 245))
    draw.rectangle([(0, footer_top), (1080, footer_top + 6)], fill=ACCENT)
    draw.text((72, 1250), "dailyaiwire.news", font=_font(27), fill=MUTED)
    cta = "Read the full story"
    cta_font = _font(27, bold=True)
    cta_width = _line_width(cta, cta_font)
    draw.text((1008 - cta_width, 1250), cta, font=cta_font, fill=ACCENT)

    image.save(output_path, "PNG", optimize=True)
    return output_path

