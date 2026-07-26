from types import SimpleNamespace
import sqlite3

import embedding_service


def test_delete_article_vectors_uses_explicit_point_ids(monkeypatch):
    deletes = []

    class FakeClient:
        def delete(self, **kwargs):
            deletes.append(kwargs)

    monkeypatch.setattr(embedding_service, "get_qdrant", lambda: FakeClient())

    embedding_service.delete_article_vectors([7, 11])

    request = deletes[0]
    assert request["collection_name"] == embedding_service.COLLECTION_NAME
    assert request["points_selector"].points == [7, 11]
    assert request["wait"] is True


def test_remote_qdrant_configuration_uses_url_and_api_key(monkeypatch):
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def get_collections(self):
            return SimpleNamespace(collections=[])

        def create_collection(self, **_kwargs):
            return None

    monkeypatch.setenv("QDRANT_URL", "http://127.0.0.1:6433")
    monkeypatch.setenv("QDRANT_API_KEY", "test-secret")
    monkeypatch.setattr(embedding_service, "_qdrant_client", None)
    monkeypatch.setattr("qdrant_client.QdrantClient", FakeClient)

    client = embedding_service.get_qdrant()

    assert isinstance(client, FakeClient)
    assert calls == [
        {
            "url": "http://127.0.0.1:6433",
            "api_key": "test-secret",
        }
    ]


def test_find_duplicates_filters_qdrant_to_recent_published_articles(tmp_path, monkeypatch):
    db_path = tmp_path / "news.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            is_published INTEGER NOT NULL,
            published_at TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO articles (id, is_published, published_at) VALUES (?, ?, ?)",
        [
            (101, 1, "2099-01-01T12:00:00+00:00"),
            (102, 0, "2099-01-01T12:00:00+00:00"),
            (103, 1, "2020-01-01T12:00:00+00:00"),
        ],
    )
    conn.commit()
    conn.close()

    searches = []

    class FakeClient:
        def search(self, **kwargs):
            searches.append(kwargs)
            return []

    monkeypatch.setattr(embedding_service, "DB_PATH", str(db_path))
    monkeypatch.setattr(embedding_service, "get_qdrant", lambda: FakeClient())
    monkeypatch.setattr(
        embedding_service,
        "embed_texts",
        lambda _texts: embedding_service.np.array(
            [[0.1] * embedding_service.EMBEDDING_DIM]
        ),
    )

    assert embedding_service.find_duplicates("Recent title", "Recent gist") is None

    id_filter = searches[0]["query_filter"].must[0]
    assert id_filter.has_id == [101]


def test_find_duplicates_skips_vector_search_without_recent_articles(tmp_path, monkeypatch):
    db_path = tmp_path / "news.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            is_published INTEGER NOT NULL,
            published_at TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO articles (id, is_published, published_at) VALUES (?, ?, ?)",
        (103, 1, "2020-01-01T12:00:00+00:00"),
    )
    conn.commit()
    conn.close()

    class FailIfSearched:
        def search(self, **_kwargs):
            raise AssertionError("Qdrant should not be searched without recent candidates")

    monkeypatch.setattr(embedding_service, "DB_PATH", str(db_path))
    monkeypatch.setattr(embedding_service, "get_qdrant", lambda: FailIfSearched())
    monkeypatch.setattr(
        embedding_service,
        "embed_texts",
        lambda _texts: embedding_service.np.array(
            [[0.1] * embedding_service.EMBEDDING_DIM]
        ),
    )

    assert embedding_service.find_duplicates("Old topic", "Old gist") is None


def test_find_duplicates_embeds_the_same_fields_as_article_indexing(tmp_path, monkeypatch):
    db_path = tmp_path / "news.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            is_published INTEGER NOT NULL,
            published_at TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO articles (id, is_published, published_at) VALUES (?, ?, ?)",
        (101, 1, "2099-01-01T12:00:00+00:00"),
    )
    conn.commit()
    conn.close()

    embedded_texts = []

    class FakeClient:
        def search(self, **_kwargs):
            return []

    def capture_embeddings(texts):
        embedded_texts.extend(texts)
        return embedding_service.np.array(
            [[0.1] * embedding_service.EMBEDDING_DIM]
        )

    monkeypatch.setattr(embedding_service, "DB_PATH", str(db_path))
    monkeypatch.setattr(embedding_service, "get_qdrant", lambda: FakeClient())
    monkeypatch.setattr(embedding_service, "embed_texts", capture_embeddings)

    embedding_service.find_duplicates(
        "Recent title",
        "Recent gist",
        0.92,
        "Material operational impact",
    )

    assert embedded_texts == [
        embedding_service.build_article_text(
            "Recent title",
            "Recent gist",
            "Material operational impact",
        )
    ]
