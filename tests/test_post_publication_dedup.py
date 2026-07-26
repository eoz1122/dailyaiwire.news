import sqlite3

import remove_duplicates


def _create_recent_article_db(path):
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            title TEXT,
            slug TEXT,
            published_at TEXT,
            is_published INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        INSERT INTO articles (id, title, slug, published_at)
        VALUES (1, 'A recent article', 'a-recent-article', datetime('now'))
        """
    )
    conn.commit()
    conn.close()


def _create_fuzzy_duplicate_db(path):
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            title TEXT,
            slug TEXT,
            published_at TEXT,
            is_published INTEGER DEFAULT 1
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO articles (id, title, slug, published_at, is_published)
        VALUES (?, ?, ?, datetime('now'), 1)
        """,
        [
            (1, "OpenAI releases a new reasoning model", "openai-reasoning-model"),
            (2, "OpenAI releases its new reasoning model", "openai-new-reasoning-model"),
        ],
    )
    conn.commit()
    conn.close()


def test_post_publication_ai_dedup_is_disabled_by_default(tmp_path, monkeypatch):
    db_path = tmp_path / "news.db"
    _create_recent_article_db(db_path)
    calls = []

    monkeypatch.setattr(remove_duplicates.db, "DB_PATH", str(db_path))
    monkeypatch.delenv("ENABLE_POST_PUBLICATION_AI_DEDUP", raising=False)
    monkeypatch.setattr(
        remove_duplicates,
        "ai_deduplicate",
        lambda **kwargs: calls.append(kwargs),
    )

    remove_duplicates.remove_duplicates()

    assert calls == []


def test_post_publication_ai_dedup_can_be_enabled_explicitly(tmp_path, monkeypatch):
    db_path = tmp_path / "news.db"
    _create_recent_article_db(db_path)
    calls = []

    monkeypatch.setattr(remove_duplicates.db, "DB_PATH", str(db_path))
    monkeypatch.setenv("ENABLE_POST_PUBLICATION_AI_DEDUP", "true")
    monkeypatch.setattr(
        remove_duplicates,
        "ai_deduplicate",
        lambda **kwargs: calls.append(kwargs),
    )

    remove_duplicates.remove_duplicates()

    assert calls == [{"recent_only": True}]


def test_fuzzy_duplicates_are_retired_and_removed_from_qdrant(tmp_path, monkeypatch):
    db_path = tmp_path / "news.db"
    _create_fuzzy_duplicate_db(db_path)
    deleted_vectors = []

    monkeypatch.setattr(remove_duplicates.db, "DB_PATH", str(db_path))
    monkeypatch.delenv("ENABLE_POST_PUBLICATION_AI_DEDUP", raising=False)
    monkeypatch.setattr(
        "embedding_service.delete_article_vectors",
        lambda article_ids: deleted_vectors.append(article_ids),
        raising=False,
    )

    remove_duplicates.remove_duplicates()

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, is_published FROM articles ORDER BY id"
        ).fetchall()

    assert rows == [(1, 1), (2, 0)]
    assert deleted_vectors == [[2]]


def test_fuzzy_dedup_ignores_already_unpublished_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "news.db"
    _create_fuzzy_duplicate_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE articles SET is_published = 0 WHERE id = 1")
        conn.commit()
    deleted_vectors = []

    monkeypatch.setattr(remove_duplicates.db, "DB_PATH", str(db_path))
    monkeypatch.delenv("ENABLE_POST_PUBLICATION_AI_DEDUP", raising=False)
    monkeypatch.setattr(
        "embedding_service.delete_article_vectors",
        lambda article_ids: deleted_vectors.append(article_ids),
        raising=False,
    )

    remove_duplicates.remove_duplicates()

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, is_published FROM articles ORDER BY id"
        ).fetchall()

    assert rows == [(1, 0), (2, 1)]
    assert deleted_vectors == []
