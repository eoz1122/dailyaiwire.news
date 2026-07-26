"""
Embedding Service for DailyAIWire Editorial Compass.

Uses bge-large-en-v1.5 (HuggingFace) + Qdrant for semantic
article indexing and editorial relevance scoring.

Per AIRULES.md §1: All features remain free.
Per GEMINI.md §4: No hardcoded credentials.
"""

import os
import sqlite3
import logging
import numpy as np
from typing import List, Dict, Optional, Tuple
from datetime import datetime


# Lazy-load heavy models to avoid memory on import
_model = None
_qdrant_client = None
logger = logging.getLogger('embedding_service')

COLLECTION_NAME = "dailyaiwire_articles"
AD_COLLECTION_NAME = "ad_reference_vectors"
QDRANT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qdrant_data")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "news.db")
EMBEDDING_DIM = 1024
DUPLICATE_RECENCY_HOURS = 36


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
    """Get or create the configured Qdrant client."""
    global _qdrant_client
    if _qdrant_client is None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        remote_url = os.getenv("QDRANT_URL", "").strip()
        api_key = os.getenv("QDRANT_API_KEY", "").strip()
        if remote_url:
            client_options = {"url": remote_url}
            if api_key:
                client_options["api_key"] = api_key
            _qdrant_client = QdrantClient(**client_options)
        else:
            os.makedirs(QDRANT_PATH, exist_ok=True)
            try:
                _qdrant_client = QdrantClient(path=QDRANT_PATH)
            except Exception as exc:
                backup_path = None
                if os.path.isdir(QDRANT_PATH):
                    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
                    backup_path = f"{QDRANT_PATH}_incompatible_{stamp}"
                    os.replace(QDRANT_PATH, backup_path)
                    os.makedirs(QDRANT_PATH, exist_ok=True)
                logger.warning(
                    "Qdrant local store was incompatible and has been reset. Backup: %s. Error: %s",
                    backup_path,
                    exc,
                )
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


def delete_article_vectors(article_ids: List[int]) -> None:
    """Delete article points from the editorial Qdrant collection."""
    normalized_ids = sorted({int(article_id) for article_id in article_ids})
    if not normalized_ids:
        return

    from qdrant_client.models import PointIdsList

    get_qdrant().delete(
        collection_name=COLLECTION_NAME,
        points_selector=PointIdsList(points=normalized_ids),
        wait=True,
    )


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


def _recent_published_article_ids(hours: int = DUPLICATE_RECENCY_HOURS) -> List[int]:
    """Return published article IDs eligible for recent-story deduplication."""
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            """
            SELECT id
            FROM articles
            WHERE is_published = 1
              AND published_at IS NOT NULL
              AND datetime(replace(published_at, 'T', ' ')) >= datetime('now', ?)
            """,
            (f"-{max(1, int(hours))} hours",),
        ).fetchall()
        return [int(row[0]) for row in rows]
    except sqlite3.Error as exc:
        logger.warning("Recent article lookup failed for semantic dedup: %s", exc)
        return []
    finally:
        if 'conn' in locals():
            conn.close()


def find_duplicates(
    title: str,
    gist: str,
    threshold: float = 0.92,
    why_it_matters: str = "",
) -> Optional[Dict]:
    """
    Check if an article is a semantic duplicate of an existing one.
    
    Returns the duplicate article info if similarity > threshold, else None.
    """
    recent_article_ids = _recent_published_article_ids()
    if not recent_article_ids:
        return None

    from qdrant_client.models import Filter, HasIdCondition

    client = get_qdrant()
    text = build_article_text(title, gist, why_it_matters)
    embedding = embed_texts([text])[0]

    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=embedding.tolist(),
        query_filter=Filter(
            must=[HasIdCondition(has_id=recent_article_ids)]
        ),
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
# IMPORTANT: These must sound like PR copy / marketing language, NOT news headlines.
# Neutral phrasing like "Company launches X" is too close to legitimate news.
# Use obviously promotional, sales-y, or press-release tone instead.
_AD_REFERENCE_TEXTS = [
    # Press release / PR wire tone (corporate self-promotion)
    "We are thrilled to announce our groundbreaking new feature that empowers users to take control of their digital safety and protect loved ones",
    "Today we are proud to unveil our latest innovation that revolutionizes the way millions of people stay safe and connected",
    "Our team has been working tirelessly to deliver this exciting new capability that our customers have been asking for",
    "We are excited to share that our platform now offers an industry-first solution that sets a new standard for user protection",
    "This milestone release reflects our unwavering commitment to delivering cutting-edge technology that makes a real difference in people's lives",

    # Marketing copy / sales push
    "Download our award-winning app today and discover why over 450 million users trust us to keep their family safe from scammers",
    "Sign up now for a free trial and experience the future of personal digital security with our premium protection suite",
    "Get started in seconds with our easy-to-use platform and unlock powerful features designed to simplify your life",
    "Upgrade to our premium plan today and enjoy unlimited access to advanced protection features for your entire family",
    "Join the millions who have already made the switch and see the difference our innovative solution can make",

    # Feature promotion with product-centric breathless enthusiasm
    "Our all-new family protection feature lets any family member act as a security admin to remotely block scam calls and shield vulnerable loved ones",
    "With just one tap you can now block unwanted callers, filter spam messages, and protect everyone in your household",
    "Our redesigned dashboard puts you in complete control with real-time alerts and one-click protection for the people who matter most",
    "Experience seamless call blocking and intelligent spam detection powered by our proprietary AI that learns and adapts to new threats",

    # Pricing / commercial conversion copy
    "Starting at just $9.99 per month our comprehensive plan gives you and your family unlimited protection with no hidden fees",
    "Limited time offer for new subscribers: get 50 percent off your first year of our premium protection service",
    "Free for all users with optional premium tier for power users who want advanced analytics and priority support",
    "Enterprise pricing available with volume discounts custom deployment options and dedicated account management",

    # Puff piece / sponsored review tone
    "This game-changing app is the must-have tool for anyone serious about protecting their family from the growing epidemic of phone scams",
    "We tested the new family protection feature and were blown away by how easy it makes keeping elderly parents safe from scammers",
    "If you are not using this incredible new security feature yet you are leaving your family exposed to increasingly sophisticated fraud",
    "This is hands down the best call protection solution we have ever used and the free tier alone makes it worth downloading immediately",

    # App store description / product page copy
    "The number one trusted caller ID and spam blocking app now with family protection. Download free for iOS and Android",
    "Protect your family from scam calls with our award-winning AI-powered caller identification and smart blocking technology",
    "Rated 4.8 stars by millions of users worldwide. The most comprehensive call protection and family safety app available today",
    "Book a personalized demo today and see how our platform can help your team automate workflows faster than ever before",
    "Read our latest customer success story to learn how enterprise teams cut costs and boosted productivity with our solution",
    "Register now for our exclusive webinar and discover how to unlock more value from your workflow automation stack",
    "Try our new AI assistant today and experience faster onboarding, better outcomes, and premium support from day one",
    "Request pricing now to get a tailored package designed for growing teams that need scalable protection and automation",
]

_POLICY_NEWS_TERMS = {
    "act",
    "bill",
    "commission",
    "compliance",
    "congress",
    "directive",
    "executive order",
    "framework",
    "governance",
    "government",
    "law",
    "laws",
    "parliament",
    "policy",
    "regulation",
    "regulatory",
    "risk assessment",
    "senate",
    "transparency",
}

_PROMOTIONAL_CTA_TERMS = {
    "app store",
    "book a demo",
    "customers",
    "download",
    "enterprise pricing",
    "free trial",
    "get started",
    "ios",
    "join the millions",
    "limited time offer",
    "premium",
    "pricing",
    "request pricing",
    "sign up",
    "subscribe",
    "upgrade",
    "users trust",
    "webinar",
}


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


def _apply_ad_score_adjustments(title: str, gist: str, why_it_matters: str, score: float) -> float:
    combined = " ".join(part for part in [title, gist, why_it_matters] if part).lower()

    policy_hits = sum(1 for term in _POLICY_NEWS_TERMS if term in combined)
    promo_hits = sum(1 for term in _PROMOTIONAL_CTA_TERMS if term in combined)

    # Pure policy/regulation coverage can sit close to corporate PR language.
    # Apply only a small dampening when there are multiple policy cues and no CTA cues.
    if policy_hits >= 2 and promo_hits == 0:
        score -= 0.035

    return round(max(score, 0.0), 3)


def score_ad_likelihood(title: str, gist: str, why_it_matters: str = "") -> float:
    """
    Score how likely an article is promotional/ad content.

    Embeds the article text and queries the ad-reference collection.
    Returns max cosine similarity (0.0–1.0).
    Score >= 0.76 → likely ad/promotional content.
    Score 0.65–0.76 → borderline, logged for review.

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
        return _apply_ad_score_adjustments(title, gist, why_it_matters, max_score)

    except Exception as e:
        print(f"⚠️ Ad-likelihood scoring failed (non-blocking): {e}")
        return 0.0
