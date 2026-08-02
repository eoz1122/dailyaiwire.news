from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTAGRAM_URL = "https://www.instagram.com/dailyaiwirenews/"


def test_public_site_and_schema_link_to_instagram():
    base_template = (ROOT / "templates" / "base.html").read_text()
    static_schema = (ROOT / "static" / "schema.json").read_text()
    article_template = (ROOT / "templates" / "article.html").read_text()

    assert INSTAGRAM_URL in base_template
    assert INSTAGRAM_URL in static_schema
    assert INSTAGRAM_URL in article_template


def test_weekly_briefing_links_to_instagram_with_tracking():
    briefing = (ROOT / "templates" / "email" / "briefing.html").read_text()

    assert (
        "https://www.instagram.com/dailyaiwirenews/"
        "?utm_source=newsletter&utm_medium=email&utm_campaign=weekly_briefing"
    ) in briefing
