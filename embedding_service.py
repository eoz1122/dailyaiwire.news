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
AD_COLLECTION_NAME = "ad_reference_vectors"
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

        # Create collections if they don't exist
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

        # Ad-reference collection (separate from editorial corpus)
        if AD_COLLECTION_NAME not in collections:
            _qdrant_client.create_collection(
                collection_name=AD_COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIM,
                    distance=Distance.COSINE
                )
            )
            print(f"✅ Created ad-reference collection: {AD_COLLECTION_NAME}")
        else:
            ad_count = _qdrant_client.count(AD_COLLECTION_NAME).count
            print(f"🛡️ Ad-reference collection exists: {ad_count} vectors")

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


def search_articles(query: str, limit: int = 20, score_threshold: float = 0.35) -> List[Dict]:
    """
    Semantic search: find articles matching a natural-language query.

    Uses bge-large-en-v1.5 retrieval prefix for optimal recall.
    Returns list of {id, title, score, category, source} ranked by relevance.
    Never raises — returns empty list on any failure.
    """
    try:
        client = get_qdrant()
        model = get_model()

        # BGE retrieval best practice: prefix query for asymmetric search
        query_text = f"Represent this sentence for searching relevant passages: {query}"
        query_embedding = model.encode([query_text], normalize_embeddings=True)[0]

        results = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_embedding.tolist(),
            limit=limit,
            score_threshold=score_threshold
        )

        return [
            {
                "id": r.id,
                "title": r.payload.get("title", ""),
                "score": round(r.score, 3),
                "category": r.payload.get("category", ""),
                "source": r.payload.get("source", "")
            }
            for r in results
        ]
    except Exception as e:
        print(f"⚠️ Semantic search failed: {e}")
        return []


def find_all_duplicates(threshold: float = 0.88, batch_size: int = 100) -> List[Dict]:
    """
    Batch scan: find ALL duplicate clusters in the corpus.

    Scrolls through every vector in Qdrant, finds nearest neighbors
    above threshold, and groups them into clusters via union-find.

    Returns: [{
        'keeper_id': int,       # Newest article in cluster
        'keeper_title': str,
        'articles': [{'id': int, 'title': str, 'score': float}],
        'max_score': float      # Highest pairwise similarity
    }]

    Sorted by max_score descending (most obvious duplicates first).
    """
    try:
        client = get_qdrant()
        total = client.count(COLLECTION_NAME).count
        if total == 0:
            return []

        print(f"🔍 Scanning {total} articles for duplicates (threshold={threshold})...")

        # Union-Find for clustering
        parent = {}
        def find(x):
            while parent.get(x, x) != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x
        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        # Track pairwise scores and metadata
        pair_scores = {}  # (min_id, max_id) -> score
        metadata = {}     # id -> {title, ...}
        processed = set()

        # Scroll through all vectors
        offset = None
        scanned = 0
        while True:
            results, offset = client.scroll(
                collection_name=COLLECTION_NAME,
                limit=batch_size,
                offset=offset,
                with_vectors=True,
                with_payload=True
            )

            if not results:
                break

            for point in results:
                pid = point.id
                if pid in processed:
                    continue
                processed.add(pid)

                metadata[pid] = {
                    "title": point.payload.get("title", ""),
                    "category": point.payload.get("category", ""),
                    "source": point.payload.get("source", "")
                }

                # Search for neighbors
                neighbors = client.search(
                    collection_name=COLLECTION_NAME,
                    query_vector=point.vector,
                    limit=5,
                    score_threshold=threshold
                )

                for nb in neighbors:
                    if nb.id == pid:
                        continue  # Skip self
                    pair_key = (min(pid, nb.id), max(pid, nb.id))
                    if pair_key not in pair_scores or nb.score > pair_scores[pair_key]:
                        pair_scores[pair_key] = nb.score
                    union(pid, nb.id)

                    # Store metadata for neighbor too
                    if nb.id not in metadata:
                        metadata[nb.id] = {
                            "title": nb.payload.get("title", ""),
                            "category": nb.payload.get("category", ""),
                            "source": nb.payload.get("source", "")
                        }

            scanned += len(results)
            if scanned % 500 == 0:
                print(f"   Scanned {scanned}/{total} articles...")

            if offset is None:
                break

        print(f"✅ Scan complete. {len(pair_scores)} duplicate pairs found.")

        # Build clusters from union-find
        clusters_map = {}  # root -> [member_ids]
        for mid in metadata:
            root = find(mid)
            if root not in clusters_map:
                clusters_map[root] = []
            clusters_map[root].append(mid)

        # Filter to clusters with 2+ members
        clusters = []
        for root, members in clusters_map.items():
            if len(members) < 2:
                continue

            # Keeper = highest ID (newest article)
            keeper_id = max(members)
            max_score = 0.0

            articles = []
            for mid in sorted(members):
                # Find the max pairwise score involving this member
                member_max = 0.0
                for other in members:
                    if other == mid:
                        continue
                    pk = (min(mid, other), max(mid, other))
                    s = pair_scores.get(pk, 0.0)
                    member_max = max(member_max, s)
                    max_score = max(max_score, s)

                articles.append({
                    "id": mid,
                    "title": metadata.get(mid, {}).get("title", ""),
                    "score": round(member_max, 3),
                    "category": metadata.get(mid, {}).get("category", ""),
                    "source": metadata.get(mid, {}).get("source", "")
                })

            clusters.append({
                "keeper_id": keeper_id,
                "keeper_title": metadata.get(keeper_id, {}).get("title", ""),
                "articles": articles,
                "max_score": round(max_score, 3)
            })

        # Sort by highest similarity first
        clusters.sort(key=lambda c: c["max_score"], reverse=True)
        print(f"📊 {len(clusters)} duplicate clusters identified.")
        return clusters

    except Exception as e:
        print(f"⚠️ Batch dedup scan failed: {e}")
        import traceback
        traceback.print_exc()
        return []


def get_collection_stats() -> Dict:
    """Get stats about the vector collection."""
    client = get_qdrant()
    count = client.count(COLLECTION_NAME).count
    ad_count = client.count(AD_COLLECTION_NAME).count
    return {
        "collection": COLLECTION_NAME,
        "total_vectors": count,
        "ad_reference_vectors": ad_count,
        "embedding_dim": EMBEDDING_DIM,
        "model": "bge-large-en-v1.5"
    }


# ── Ad / Promotional Content Detection ──────────────────────────────

# Reference texts representing promotional content patterns.
# These are generic templates — not targeting any specific company.
_AD_REFERENCE_TEXTS = [
    # Product launch announcements
    "Company launches new feature that lets users protect their data and privacy with advanced tools",
    "New product release allows customers to seamlessly manage their accounts and subscriptions",
    "Company unveils revolutionary new tool designed to help businesses streamline their workflow",
    "Tech company rolls out new service that gives users more control over their digital experience",
    "Startup introduces innovative platform that transforms how people interact with technology",

    # Feature promotion / product PR
    "New feature now available for free lets you remotely manage and protect family members",
    "The app now lets users block unwanted calls and messages with a single tap",
    "Users can now upgrade to premium for enhanced features including advanced analytics",
    "Company announces free tier expansion giving all users access to previously paid features",
    "New update brings faster performance and improved user interface to millions of users",

    # Download / signup CTAs
    "Download the app today and start protecting your family from online threats",
    "Sign up now to get early access to the latest features and exclusive benefits",
    "Get started for free and discover how our platform can transform your business",
    "Try the new premium plan free for 30 days with no credit card required",
    "Join millions of satisfied users who trust our platform for their daily needs",

    # Corporate PR / earnings disguised as news
    "Company reports record growth with over 450 million active users worldwide",
    "Platform reaches new milestone with expansion to 50 new countries and regions",
    "Company CEO announces ambitious roadmap including AI integration and global expansion",
    "Quarterly earnings exceed expectations as company doubles down on new product offerings",
    "Company secures major partnership to bring its services to enterprise customers globally",

    # Pricing / commercial push
    "Starting at just $9.99 per month the new plan includes unlimited access to all features",
    "Enterprise pricing now available with custom solutions for businesses of all sizes",
    "Limited time offer gives new subscribers 50 percent off their first year of service",
    "Free version available with optional premium upgrade for power users and teams",

    # Single-product puff pieces
    "This new app is a game changer for anyone looking to improve their productivity",
    "The tool every professional needs to stay ahead in today's competitive landscape",
    "Why this startup's approach to solving everyday problems is winning over millions",
    "How one company's innovative feature is reshaping the way families stay safe online",
    "Review: this new service delivers on its promise of simplicity and power for all users",

    # Telecom/app-specific promo patterns
    "Caller ID app adds family protection feature allowing admin control over scam blocking",
    "Messaging platform launches new safety features to protect vulnerable users from fraud",
]


def seed_ad_references() -> int:
    """
    Populate the ad-reference Qdrant collection with promotional content vectors.
    Safe to re-run (uses upsert). Returns count of indexed references.
    """
    from qdrant_client.models import PointStruct

    client = get_qdrant()
    embeddings = embed_texts(_AD_REFERENCE_TEXTS)

    points = [
        PointStruct(
            id=i + 1,  # 1-indexed IDs
            vector=embeddings[i].tolist(),
            payload={"text": text, "category": "ad_reference"}
        )
        for i, text in enumerate(_AD_REFERENCE_TEXTS)
    ]

    client.upsert(collection_name=AD_COLLECTION_NAME, points=points)
    count = client.count(AD_COLLECTION_NAME).count
    print(f"🛡️ Seeded {count} ad-reference vectors into '{AD_COLLECTION_NAME}'.")
    return count


def score_ad_likelihood(title: str, gist: str, why_it_matters: str = "") -> float:
    """
    Score how likely an article is promotional/ad content.

    Embeds the article text and queries the ad-reference collection.
    Returns max cosine similarity (0.0–1.0).
    Score >= 0.72 → likely ad/promotional content.

    Never raises — returns 0.0 on any failure (fail-open, no blocking).
    """
    try:
        client = get_qdrant()

        # Check if ad collection has vectors
        ad_count = client.count(AD_COLLECTION_NAME).count
        if ad_count == 0:
            return 0.0

        text = build_article_text(title, gist, why_it_matters)
        embedding = embed_texts([text])[0]

        results = client.search(
            collection_name=AD_COLLECTION_NAME,
            query_vector=embedding.tolist(),
            limit=3,
            score_threshold=0.5
        )

        if not results:
            return 0.0

        # Return max similarity to any ad-reference vector
        max_score = max(r.score for r in results)
        return round(max_score, 3)

    except Exception as e:
        print(f"⚠️ Ad-likelihood scoring failed (non-blocking): {e}")
        return 0.0
