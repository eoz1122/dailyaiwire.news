from pathlib import Path


def test_curated_fallbacks_exclude_irrelevant_or_missing_assets():
    from services.image_fallbacks import (
        DISALLOWED_FALLBACK_IMAGES,
        FALLBACK_IMAGES,
    )

    assert "/static/fallbacks/science_1.jpg" in DISALLOWED_FALLBACK_IMAGES
    assert "/static/fallbacks/science_1.jpg" not in FALLBACK_IMAGES["Science"]
    assert all("agents_" not in image for image in FALLBACK_IMAGES["AI Agents"])

    for category, images in FALLBACK_IMAGES.items():
        assert images, f"{category} has no fallback images"
        for image in images:
            local_path = Path(image.lstrip("/"))
            assert local_path.exists(), f"{category} fallback missing: {image}"


def test_deterministic_fallback_avoids_disallowed_science_heart():
    from services.image_fallbacks import deterministic_fallback

    assert deterministic_fallback(
        "machine-collective-intelligence-explainable-science",
        "Science",
    ) != "/static/fallbacks/science_1.jpg"
    assert deterministic_fallback(
        "personalized-digital-twins-cognitive-decline-ai",
        "Science",
    ) != "/static/fallbacks/science_1.jpg"
