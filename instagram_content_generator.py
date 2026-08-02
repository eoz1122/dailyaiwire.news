"""Generate factual DailyAIWire carousels and Reel-ready vertical videos."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from instagram_card_generator import (
    ACCENT,
    GRID,
    LOGO_PATH,
    MUTED,
    TEXT,
    _fit_title,
    _font,
    _line_width,
    _wrap_words,
)


CAROUSEL_SIZE = (1080, 1350)
REEL_SIZE = (1080, 1920)
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "static", "img", "social")
CAROUSEL_VERSION = "instagram-carousel-v1"
REEL_VERSION = "instagram-reel-v1"
BACKGROUND = (250, 250, 250)
PANEL = (244, 244, 245)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("**", "")).strip()


def _safe_slug(value: Any) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", _clean(value).lower()).strip("-")
    if not slug:
        raise ValueError("A non-empty article slug is required")
    return slug


def _base_canvas(size: tuple[int, int], *, category: str, marker: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", size, BACKGROUND)
    draw = ImageDraw.Draw(image)
    for x in range(0, size[0], 60):
        draw.line([(x, 0), (x, size[1])], fill=GRID, width=1)
    for y in range(0, size[1], 60):
        draw.line([(0, y), (size[0], y)], fill=GRID, width=1)
    draw.rectangle([(0, 0), (size[0], 8)], fill=ACCENT)

    try:
        logo = Image.open(LOGO_PATH).convert("RGBA").resize((84, 84), Image.Resampling.LANCZOS)
        image.paste(logo, (72, 58), logo)
    except (OSError, ValueError):
        pass
    draw.text((178, 78), "DAILY AI WIRE", font=_font(30, bold=True), fill=ACCENT)
    category_label = _clean(category).upper() or "AI INTELLIGENCE"
    draw.text((72, 172), category_label, font=_font(21, bold=True), fill=MUTED)
    marker_font = _font(21, bold=True)
    draw.text((1008 - _line_width(marker, marker_font), 172), marker, font=marker_font, fill=MUTED)
    return image, draw


def _fit_block(
    text: str,
    *,
    max_width: int,
    max_lines: int,
    start_size: int = 48,
    min_size: int = 28,
) -> dict[str, Any]:
    clean_text = _clean(text)
    for size in range(start_size, min_size - 1, -2):
        font = _font(size, bold=False)
        lines = _wrap_words(clean_text, font, max_width)
        if len(lines) <= max_lines:
            return {"font": font, "lines": lines, "line_height": round(size * 1.35)}

    font = _font(min_size)
    lines = _wrap_words(clean_text, font, max_width)[:max_lines]
    if lines and len(_wrap_words(clean_text, font, max_width)) > max_lines:
        final = lines[-1]
        while final and _line_width(f"{final}...", font) > max_width:
            final = final.rsplit(" ", 1)[0] if " " in final else final[:-1]
        lines[-1] = f"{final}..." if final else ""
    return {"font": font, "lines": [line for line in lines if line], "line_height": round(min_size * 1.35)}


def _draw_text_block(
    draw: ImageDraw.ImageDraw,
    *,
    label: str,
    text: str,
    top: int,
    max_lines: int,
    max_width: int = 936,
) -> int:
    draw.text((72, top), label.upper(), font=_font(25, bold=True), fill=ACCENT)
    layout = _fit_block(text, max_width=max_width, max_lines=max_lines)
    y = top + 62
    for line in layout["lines"]:
        draw.text((72, y), line, font=layout["font"], fill=TEXT)
        y += layout["line_height"]
    return y


def _draw_carousel_footer(draw: ImageDraw.ImageDraw, *, slide_number: int) -> None:
    draw.rectangle([(0, 1190), (1080, 1350)], fill=PANEL)
    draw.rectangle([(0, 1190), (1080, 1196)], fill=ACCENT)
    draw.text((72, 1250), "dailyaiwire.news", font=_font(27), fill=MUTED)
    text = f"SAVE + SHARE  {slide_number}/5"
    font = _font(24, bold=True)
    draw.text((1008 - _line_width(text, font), 1252), text, font=font, fill=ACCENT)


def generate_carousel(article: dict[str, Any]) -> list[str]:
    """Create five 1080 x 1350 slides without inventing article claims."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    slug = _safe_slug(article.get("slug"))
    title = _clean(article.get("title"))
    category = _clean(article.get("category"))
    gist = _clean(article.get("gist")) or _clean(article.get("why_it_matters"))
    why = _clean(article.get("why_it_matters")) or gist
    bull = _clean(article.get("bull_case")) or "The opportunity depends on measurable adoption and execution."
    bear = _clean(article.get("bear_case")) or "The risk depends on reliability, cost, and responsible oversight."
    paths = [
        os.path.join(OUTPUT_DIR, f"{slug}-{CAROUSEL_VERSION}-{number:02d}.png")
        for number in range(1, 6)
    ]
    if all(os.path.exists(path) for path in paths):
        return paths

    image, draw = _base_canvas(CAROUSEL_SIZE, category=category, marker="01 / HEADLINE")
    title_layout = _fit_title(title, max_width=936, max_height=720)
    y = 320
    for line in title_layout["lines"]:
        draw.text((72, y), line, font=title_layout["font"], fill=TEXT)
        y += title_layout["line_height"]
    draw.text((72, min(y + 52, 1045)), "Swipe for the signal, impact, and trade-offs.", font=_font(30), fill=MUTED)
    _draw_carousel_footer(draw, slide_number=1)
    image.save(paths[0], "PNG", optimize=True)

    image, draw = _base_canvas(CAROUSEL_SIZE, category=category, marker="02 / SIGNAL")
    _draw_text_block(draw, label="The signal", text=gist, top=330, max_lines=10)
    _draw_carousel_footer(draw, slide_number=2)
    image.save(paths[1], "PNG", optimize=True)

    image, draw = _base_canvas(CAROUSEL_SIZE, category=category, marker="03 / IMPACT")
    _draw_text_block(draw, label="Why it matters", text=why, top=330, max_lines=10)
    _draw_carousel_footer(draw, slide_number=3)
    image.save(paths[2], "PNG", optimize=True)

    image, draw = _base_canvas(CAROUSEL_SIZE, category=category, marker="04 / BALANCE")
    bottom = _draw_text_block(draw, label="Bull case", text=bull, top=300, max_lines=5)
    draw.line([(72, bottom + 55), (1008, bottom + 55)], fill=GRID, width=3)
    _draw_text_block(draw, label="Bear case", text=bear, top=bottom + 105, max_lines=5)
    _draw_carousel_footer(draw, slide_number=4)
    image.save(paths[3], "PNG", optimize=True)

    image, draw = _base_canvas(CAROUSEL_SIZE, category=category, marker="05 / NEXT")
    _draw_text_block(draw, label="What to watch", text=why, top=300, max_lines=7)
    draw.text((72, 900), "FOLLOW @DAILYAIWIRENEWS", font=_font(42, bold=True), fill=TEXT)
    draw.text((72, 970), "Three concise AI briefings every day.", font=_font(31), fill=MUTED)
    _draw_carousel_footer(draw, slide_number=5)
    image.save(paths[4], "PNG", optimize=True)
    return paths


def _draw_reel_frame(article: dict[str, Any], *, frame_number: int) -> Image.Image:
    image, draw = _base_canvas(
        REEL_SIZE,
        category=_clean(article.get("category")),
        marker=f"{frame_number:02d} / 04",
    )
    title = _clean(article.get("title"))
    gist = _clean(article.get("gist")) or _clean(article.get("why_it_matters"))
    why = _clean(article.get("why_it_matters")) or gist
    bull = _clean(article.get("bull_case")) or "Opportunity: adoption and execution can compound."
    bear = _clean(article.get("bear_case")) or "Risk: reliability, cost, and oversight can slow adoption."

    if frame_number == 1:
        draw.text((72, 360), "AI NEWS IN 60 SECONDS", font=_font(27, bold=True), fill=ACCENT)
        layout = _fit_title(title, max_width=936, max_height=950)
        y = 440
        for line in layout["lines"]:
            draw.text((72, y), line, font=layout["font"], fill=TEXT)
            y += layout["line_height"]
    elif frame_number == 2:
        _draw_text_block(draw, label="The signal", text=gist, top=390, max_lines=11)
        _draw_text_block(draw, label="Why it matters", text=why, top=1050, max_lines=8)
    elif frame_number == 3:
        bottom = _draw_text_block(draw, label="Bull case", text=bull, top=390, max_lines=7)
        draw.line([(72, bottom + 75), (1008, bottom + 75)], fill=GRID, width=3)
        _draw_text_block(draw, label="Bear case", text=bear, top=bottom + 140, max_lines=7)
    else:
        draw.text((72, 560), "THE FULL SIGNAL", font=_font(30, bold=True), fill=ACCENT)
        draw.text((72, 650), "dailyaiwire.news", font=_font(72, bold=True), fill=TEXT)
        draw.text((72, 790), "Follow @dailyaiwirenews", font=_font(42), fill=MUTED)
        draw.text((72, 880), "Three concise AI briefings every day.", font=_font(32), fill=MUTED)

    draw.rectangle([(0, 1740), (1080, 1920)], fill=PANEL)
    draw.rectangle([(0, 1740), (1080, 1746)], fill=ACCENT)
    draw.text((72, 1810), "AI-ASSISTED. HUMAN-REVIEWED.", font=_font(26, bold=True), fill=MUTED)
    return image


def generate_reel(article: dict[str, Any]) -> str:
    """Create a silent, branded H.264 Reel-ready MP4 from verified article fields."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required to generate Instagram Reels")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    slug = _safe_slug(article.get("slug"))
    output_path = os.path.join(OUTPUT_DIR, f"{slug}-{REEL_VERSION}.mp4")
    if os.path.exists(output_path):
        return output_path

    with tempfile.TemporaryDirectory(prefix="dailyaiwire-reel-") as temp_dir:
        temp_path = Path(temp_dir)
        frame_paths: list[Path] = []
        for number in range(1, 5):
            frame_path = temp_path / f"frame-{number:02d}.png"
            _draw_reel_frame(article, frame_number=number).save(frame_path, "PNG", optimize=True)
            frame_paths.append(frame_path)

        manifest = temp_path / "frames.txt"
        manifest.write_text(
            "".join(f"file '{path.as_posix()}'\nduration 3\n" for path in frame_paths)
            + f"file '{frame_paths[-1].as_posix()}'\n",
            encoding="utf-8",
        )
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(manifest),
                "-vf",
                "fps=30,format=yuv420p",
                "-c:v",
                "libx264",
                "-movflags",
                "+faststart",
                output_path,
            ],
            check=True,
        )
    return output_path


def probe_video(path: str) -> dict[str, Any]:
    """Return the first video stream dimensions, codec, pixel format, and duration."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("FFprobe is required to validate Instagram Reels")
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,codec_name,pix_fmt:format=duration",
            "-of",
            "json",
            path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    stream = payload["streams"][0]
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "codec_name": stream["codec_name"],
        "pix_fmt": stream["pix_fmt"],
        "duration": float(payload["format"]["duration"]),
    }
