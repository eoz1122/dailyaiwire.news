from PIL import Image


def test_instagram_card_is_portrait_and_versioned(tmp_path, monkeypatch):
    import instagram_card_generator

    monkeypatch.setattr(instagram_card_generator, "OUTPUT_DIR", str(tmp_path))

    card_path = instagram_card_generator.generate_card(
        "A Long DailyAIWire Headline That Must Stay Inside the Instagram Safe Area",
        "portrait-card",
        "A concise explanation of why this development matters.",
    )

    assert card_path.endswith("portrait-card-instagram-v2.png")
    with Image.open(card_path) as image:
        assert image.size == (1080, 1350)


def test_instagram_title_layout_stays_inside_safe_area():
    from instagram_card_generator import _fit_title

    layout = _fit_title(
        "Autonomous AI Agents Change Enterprise Security and Software Operations Worldwide",
        max_width=920,
        max_height=720,
    )

    assert layout["lines"]
    assert len(layout["lines"]) <= 6
    assert layout["height"] <= 720


def test_gist_layout_keeps_only_complete_sentences():
    from instagram_card_generator import _fit_gist

    layout = _fit_gist(
        "The first sentence fits safely. The second sentence is deliberately long "
        "enough that adding it would exceed the three-line summary area on the card.",
        max_width=520,
        max_lines=3,
    )

    assert " ".join(layout["lines"]) == "The first sentence fits safely."


def test_gist_layout_omits_text_instead_of_cutting_a_sentence():
    from instagram_card_generator import _fit_gist

    layout = _fit_gist(
        "One extremely long sentence without an early stopping point that cannot fit "
        "inside the deliberately tiny summary area provided by this regression test.",
        max_width=120,
        max_lines=1,
    )

    assert layout["lines"] == []


def test_instagram_carousel_has_five_safe_portrait_slides(tmp_path, monkeypatch):
    import instagram_content_generator

    monkeypatch.setattr(instagram_content_generator, "OUTPUT_DIR", str(tmp_path))
    article = {
        "title": "Open Models Reshape Enterprise AI Procurement",
        "slug": "open-models-enterprise-ai",
        "category": "Business",
        "gist": "Open models are gaining adoption across enterprise AI teams.",
        "why_it_matters": "Lower switching costs could reshape vendor negotiations.",
        "bull_case": "Competition can reduce prices and speed up deployment.",
        "bear_case": "Fragmentation can increase integration and governance work.",
    }

    paths = instagram_content_generator.generate_carousel(article)

    assert len(paths) == 5
    assert [path.rsplit("/", 1)[-1] for path in paths] == [
        f"open-models-enterprise-ai-instagram-carousel-v1-{number:02d}.png"
        for number in range(1, 6)
    ]
    for path in paths:
        with Image.open(path) as image:
            assert image.size == (1080, 1350)


def test_instagram_reel_is_vertical_h264_video(tmp_path, monkeypatch):
    import shutil

    import pytest

    import instagram_content_generator

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg is required for Reel integration verification")

    monkeypatch.setattr(instagram_content_generator, "OUTPUT_DIR", str(tmp_path))
    article = {
        "title": "AI Security Teams Shift Toward Autonomous Detection",
        "slug": "ai-security-autonomous-detection",
        "category": "Security",
        "gist": "Security teams are testing autonomous detection workflows.",
        "why_it_matters": "The shift changes response speed and oversight requirements.",
        "bull_case": "Automation can shorten the time between detection and containment.",
        "bear_case": "Weak oversight can amplify false positives and automated mistakes.",
    }

    path = instagram_content_generator.generate_reel(article)
    probe = instagram_content_generator.probe_video(path)

    assert path.endswith("ai-security-autonomous-detection-instagram-reel-v1.mp4")
    assert probe["width"] == 1080
    assert probe["height"] == 1920
    assert probe["codec_name"] == "h264"
    assert probe["pix_fmt"] == "yuv420p"
    assert 8 <= probe["duration"] <= 20
