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
