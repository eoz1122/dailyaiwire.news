import sqlite3
from datetime import datetime


def _create_newsletters_table(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE newsletters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT,
            status TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


def test_weekly_runner_skips_when_recent_issue_exists(tmp_path, monkeypatch):
    from services import weekly_newsletter_runner

    db_path = tmp_path / "news.db"
    _create_newsletters_table(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO newsletters (subject, status, created_at) VALUES (?, ?, ?)",
        ("Existing weekly issue", "DRAFT", "2026-07-25T17:30:00"),
    )
    conn.commit()
    conn.close()

    generated = []
    monkeypatch.setattr(
        weekly_newsletter_runner.weekly_curator,
        "generate_newsletter_draft",
        lambda: generated.append(True),
    )

    outcome = weekly_newsletter_runner.run_weekly_newsletter(
        db_path=str(db_path),
        now=datetime.fromisoformat("2026-07-25T18:05:00"),
    )

    assert outcome == "skipped_recent"
    assert generated == []


def test_weekly_runner_generates_when_no_recent_issue_exists(tmp_path, monkeypatch):
    from services import weekly_newsletter_runner

    db_path = tmp_path / "news.db"
    _create_newsletters_table(db_path)
    monkeypatch.setattr(
        weekly_newsletter_runner.weekly_curator,
        "generate_newsletter_draft",
        lambda: 42,
    )

    outcome = weekly_newsletter_runner.run_weekly_newsletter(
        db_path=str(db_path),
        now=datetime.fromisoformat("2026-07-25T18:05:00"),
    )

    assert outcome == "created:42"
