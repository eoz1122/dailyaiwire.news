"""
Embedding Service for DailyAIWire Editorial Compass.

Uses bge-large-en-v1.5 (HuggingFace) + Qdrant for semantic
article indexing and editorial relevance scoring.

Per AIRULES.md §1: All features remain free.
Per GEMINI.md §4: No hardcoded credentials.
"""

import os
import sqlite3
import numpy as np
from typing import List, Dict, Optional, Tuple


# Lazy-load heavy models to avoid memory on import
_model = None
_qdrant_client = None

COLLECTION_NAME = "dailyaiwire_articles"
QDRANT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qdrant_data")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "news.db")
EMBEDDING_DIM = 1024


def get_model():
    """Lazy-load bge-large-en-v1.5 to avoid RAM usage on import."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        print("🧠 Loading bge-large-en-v1.5 embedding model...")
        _model = SentenceTransformer("BAAI/bge-large-en-v1.5")
        print("✅ Model loaded.")
    return _model


def get_qdrant():
    """Get or create Qdrant client with local disk persistence."""
    global _qdrant_client
    if _qdrant_client is None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        os.makedirs(QDRANT_PATH, exist_ok=True)
        _qdrant_client = QdrantClient(path=QDRANT_PATH)

        # Create collection if it doesn't exist
        collections = [c.name for c in _qdrant_client.get_collections().collections]
        if COLLECTION_NAME not in collections:
            _qdrant_client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIM,
                    distance=Distance.COSINE
                )
            )
            print(f"✅ Created Qdrant collection: {COLLECTION_NAME}")
        else:
            count = _qdrant_client.count(COLLECTION_NAME).count
            print(f"📦 Qdrant collection exists: {count} vectors")

    return _qdrant_client


def build_article_text(title: str, gist: str, why_it_matters: str = "") -> str:
    """
    Build the text representation of an article for embedding.
    bge-large uses a query prefix for retrieval; for indexing we use passage format.
    """
    parts = [title or ""]
    if gist:
        parts.append(gist)
    if why_it_matters:
        parts.append(why_it_matters)
    return ". ".join(parts)


def embed_texts(texts: List[str]) -> np.ndarray:
    """Embed a batch of texts using bge-large-en-v1.5."""
    model = get_model()
    # bge models recommend "Represent this sentence: " prefix for passages
    embeddings = model.encode(texts, show_progress_bar=len(texts) > 10, normalize_embeddings=True)
    return embeddings


def index_article(article_id: int, title: str, gist: str,
                  why_it_matters: str = "", category: str = "",
                  source: str = "", importance_score: int = 0) -> None:
    """Index a single article into Qdrant."""
    from qdrant_client.models import PointStruct

    client = get_qdrant()
    text = build_article_text(title, gist, why_it_matters)
    embedding = embed_texts([text])[0]

    point = PointStruct(
        id=article_id,
        vector=embedding.tolist(),
        payload={
            "title": title,
            "category": category,
            "source": source,
            "importance_score": importance_score
        }
    )

    client.upsert(collection_name=COLLECTION_NAME, points=[point])


def index_batch(articles: List[Dict]) -> int:
    """
    Batch-index articles into Qdrant.
    Each dict must have: id, title, gist. Optional: why_it_matters, category, source.
    Returns count of indexed articles.
    """
    from qdrant_client.models import PointStruct

    if not articles:
        return 0

    client = get_qdrant()

    texts = [
        build_article_text(
            a.get("title", ""),
            a.get("gist", ""),
            a.get("why_it_matters", "")
        )
        for a in articles
    ]

    embeddings = embed_texts(texts)

    points = [
        PointStruct(
            id=a["id"],
            vector=embeddings[i].tolist(),
            payload={
                "title": a.get("title", ""),
                "category": a.get("category", ""),
                "source": a.get("source", ""),
                "importance_score": int(a.get("importance_score", 0) or 0)
            }
        )
        for i, a in enumerate(articles)
    ]

    # Qdrant supports batch upsert up to ~100 at a time
    BATCH_SIZE = 64
    for i in range(0, len(points), BATCH_SIZE):
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=points[i:i + BATCH_SIZE]
        )

    return len(points)


def score_article(title: str, gist: str, why_it_matters: str = "") -> Tuple[float, List[Dict]]:
    """
    Score an incoming article against the Editorial Compass.
    
    Returns:
        (relevance_score, similar_articles)
        - relevance_score: 0.0 to 1.0 (cosine similarity to existing corpus)
        - similar_articles: top 3 most similar existing articles
    """
    client = get_qdrant()
    text = build_article_text(title, gist, why_it_matters)
    embedding = embed_texts([text])[0]

    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=embedding.tolist(),
        limit=5,
        score_threshold=0.3
    )

    if not results:
        return 0.0, []

    # Average of top 3 scores = editorial relevance
    top_scores = [r.score for r in results[:3]]
    avg_score = sum(top_scores) / len(top_scores)

    similar = [
        {
            "id": r.id,
            "title": r.payload.get("title", ""),
            "score": round(r.score, 3),
            "category": r.payload.get("category", "")
        }
        for r in results[:3]
    ]

    return round(avg_score, 3), similar


def find_duplicates(title: str, gist: str, threshold: float = 0.92) -> Optional[Dict]:
    """
    Check if an article is a semantic duplicate of an existing one.
    
    Returns the duplicate article info if similarity > threshold, else None.
    """
    client = get_qdrant()
    text = build_article_text(title, gist)
    embedding = embed_texts([text])[0]

    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=embedding.tolist(),
        limit=1,
        score_threshold=threshold
    )

    if results:
        return {
            "id": results[0].id,
            "title": results[0].payload.get("title", ""),
            "score": round(results[0].score, 3)
        }
    return None


def get_collection_stats() -> Dict:
    """Get stats about the vector collection."""
    client = get_qdrant()
    count = client.count(COLLECTION_NAME).count
    return {
        "collection": COLLECTION_NAME,
        "total_vectors": count,
        "embedding_dim": EMBEDDING_DIM,
        "model": "bge-large-en-v1.5"
    }
