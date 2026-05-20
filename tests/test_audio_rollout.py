import sqlite3

import db as db_module
import generate_missing_audio as missing_audio_module
from generate_missing_audio import generate_audio_for_recent_articles


def _insert_article(slug, *, audio_male=None, audio_female=None, published_at="2026-05-20T12:00:00+00:00"):
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.execute(
        """
        INSERT INTO articles (
            slug, title, image, category, gist, why_it_matters, bull_case, bear_case,
            key_details, eli5, deep_analysis, source, source_url, full_json, published_at,
            importance_score, is_published, narration_script, audio_male, audio_female
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            slug,
            f"Title for {slug}",
            "/static/fallbacks/tools_0.jpg",
            "Tools",
            "Test gist.",
            "Why it matters.",
            "Bull case.",
            "Bear case.",
            "[]",
            "ELI5",
            "Deep analysis.",
            "Test Source",
            f"https://example.com/{slug}",
            "{}",
            published_at,
            70,
            1,
            "Intelligence from DailyAIWire dot news. Test narration script.",
            audio_male,
            audio_female,
        ),
    )
    conn.commit()
    conn.close()


def _get_audio(slug):
    conn = sqlite3.connect(db_module.DB_PATH)
    row = conn.execute(
        "SELECT audio_male, audio_female FROM articles WHERE slug = ?",
        (slug,),
    ).fetchone()
    conn.close()
    return row


def _delete_articles(*slugs):
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.executemany("DELETE FROM articles WHERE slug = ?", [(slug,) for slug in slugs])
    conn.commit()
    conn.close()


def test_generate_audio_for_recent_articles_treats_male_only_as_complete(monkeypatch):
    _delete_articles("male-complete", "needs-male")
    monkeypatch.setattr(missing_audio_module, "DB_PATH", db_module.DB_PATH)
    _insert_article(
        "male-complete",
        audio_male="/static/audio/male-complete_male.mp3",
        audio_female=None,
        published_at="2099-05-20T11:59:00+00:00",
    )
    _insert_article(
        "needs-male",
        audio_male=None,
        audio_female=None,
        published_at="2099-05-20T12:00:00+00:00",
    )

    calls = []

    class StubAudioGenerator:
        def generate_audio_reads(self, slug, text):
            calls.append(slug)
            return (f"/static/audio/{slug}_male.mp3", None)

    monkeypatch.setattr("generate_missing_audio.AudioGenerator", StubAudioGenerator)

    generate_audio_for_recent_articles(limit=1)

    assert calls == ["needs-male"]
    assert _get_audio("male-complete") == (
        "/static/audio/male-complete_male.mp3",
        None,
    )
    assert _get_audio("needs-male") == (
        "/static/audio/needs-male_male.mp3",
        None,
    )


def test_generate_audio_for_recent_articles_preserves_legacy_female_reference(monkeypatch):
    _delete_articles("legacy-female-only")
    monkeypatch.setattr(missing_audio_module, "DB_PATH", db_module.DB_PATH)
    _insert_article(
        "legacy-female-only",
        audio_male=None,
        audio_female="/static/audio/legacy-female-only_female.mp3",
        published_at="2099-05-20T12:01:00+00:00",
    )

    class StubAudioGenerator:
        def generate_audio_reads(self, slug, text):
            return (f"/static/audio/{slug}_male.mp3", None)

    monkeypatch.setattr("generate_missing_audio.AudioGenerator", StubAudioGenerator)

    generate_audio_for_recent_articles(limit=1)

    assert _get_audio("legacy-female-only") == (
        "/static/audio/legacy-female-only_male.mp3",
        "/static/audio/legacy-female-only_female.mp3",
    )
