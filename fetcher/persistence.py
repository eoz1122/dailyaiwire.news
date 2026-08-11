"""
Fetcher — Persistence & Post-Processing
Save articles to DB, social queue processing, Google indexing, Qdrant indexing.
"""
import json
import os
import uuid
import time
import sqlite3
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timedelta, timezone
from typing import Dict, List, NamedTuple

from slugify import slugify

from db import DB_PATH, get_db_connection
from social_distributor import SocialDistributor
from google_indexer import google_indexing_enabled, notify_google_index
from qa_monitor import run_post_publication_audit
from services.image_fallbacks import select_category_fallback
from services.story_dedup import canonical_research_paper_id, likely_same_story

logger = logging.getLogger('fetcher.persistence')

# R2-03: Whitelist of valid categories to prevent garbage data in DB
VALID_CATEGORIES = {
    'LLMs', 'Robotics', 'Business', 'Tools', 'Policy',
    'Science', 'Security', 'Society', 'Ethics', 'AI Agents'
}

_EMBEDDING_TIMEOUT = 30  # R2-04: Max seconds for embedding service calls


# DRIP-FEED: Minutes to add per subsequent article from the same source in one batch.
_SOURCE_SPREAD_MINUTES = 150

_GENERIC_IMAGE_MARKERS = ("google", "placeholder", "logo", "icon", "pixel")


class SaveResult(NamedTuple):
    posts_count: int
    articles_saved: int


def _is_generic_image_url(image_url) -> bool:
    image_text = str(image_url or "")
    if image_text.startswith("/static/img/social/"):
        return True
    return (
        not image_text
        or not image_text.startswith("http")
        or any(marker in image_text.lower() for marker in _GENERIC_IMAGE_MARKERS)
    )


def _generated_card_web_path(card_path):
    if not card_path:
        return None

    normalized = str(card_path).replace(os.sep, "/")
    if normalized.startswith("/static/"):
        return normalized
    if normalized.startswith("static/"):
        return f"/{normalized}"

    static_index = normalized.find("/static/")
    if static_index >= 0:
        return normalized[static_index:]

    return None


def _generate_branded_article_image(headline, slug, gist):
    try:
        from ig_card_generator import generate_card

        card_path = generate_card(headline or "DailyAIWire Analysis", slug, gist or "")
        web_path = _generated_card_web_path(card_path)
        if web_path:
            return web_path
        logger.warning("Generated card path is not web-addressable: %s", card_path)
    except Exception as exc:
        logger.warning("Article card generation failed for %s: %s", slug, exc)
    return None


def _find_recent_story_duplicate(cursor, title, gist, hours=36):
    rows = cursor.execute(
        """
        SELECT id, title, gist
        FROM articles
        WHERE is_published = 1
          AND datetime(replace(published_at, 'T', ' ')) >= datetime('now', ?)
        ORDER BY published_at DESC, id DESC
        LIMIT 200
        """,
        (f"-{int(hours)} hours",),
    ).fetchall()
    for article_id, published_title, published_gist in rows:
        if likely_same_story(title, published_title, gist, published_gist or ""):
            return {
                "id": article_id,
                "title": published_title,
            }
    return None


def _find_research_paper_duplicate(cursor, source_url):
    paper_id = canonical_research_paper_id(source_url)
    if not paper_id:
        return None

    rows = cursor.execute(
        """
        SELECT id, title, source_url
        FROM articles
        WHERE is_published = 1
          AND (source_url LIKE ? OR source_url LIKE ?)
        ORDER BY id DESC
        """,
        ("%arxiv.org/%", "%huggingface.co/papers/%"),
    ).fetchall()
    for article_id, title, published_url in rows:
        if canonical_research_paper_id(published_url) == paper_id:
            return {
                "id": article_id,
                "title": title,
                "paper_id": paper_id,
            }
    return None


def save_to_db(processed_articles: List[Dict], original_batch: List[Dict], distributor=None, social_limit=2, posts_count=0, audio_gen=None):
    """Persist processed articles to the database with all post-save hooks."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    articles_saved = 0

    # DRIP-FEED: Track how many articles from each source we have saved in this batch.
    # Offset 0 = publish now (or original time), offset 1 = +150 min, etc.
    source_publish_offsets: dict = {}

    for art in processed_articles:
        # 1. Status Check (New 2026 Guardrail)
        if art.get('status') == "INSUFFICIENT_DATA":
            logger.info("Skipping '%s' - AI flagged as Insufficient Data.", art.get('headline'))
            continue

        # 1.5 Score Filter (New 2026 Guardrail)
        imp_score = int(art.get('importance_score', 0) or 0)
        if imp_score < 50:
            logger.info("Skipping '%s' - Score %d < 50.", art.get('headline'), imp_score)
            continue

        # Skip articles where AI failed to find content or hit a paywall/blocker
        gist = str(art.get('gist', '')).lower()
        impact = str(art.get('why_it_matters', '')).lower()
        headline = str(art.get('headline', '')).lower()
        analysis = str(art.get('deep_analysis', ''))

        # EU AI Act transparency: displayed in-page UI only, not in metadata/schema

        blacklist = [
            "source content missing",
            "javascript is disabled",
            "enable javascript",
            "article unavailable",
            "content access",
            "access denied",
            "please enable js",
            "browser to continue"
        ]

        if any(b in gist for b in blacklist) or \
           any(b in impact for b in blacklist) or \
           any(b in headline for b in blacklist) or \
           any(b in analysis for b in blacklist):
            logger.info("Skipping '%s' due to content blocker signal (JS/Access Denied).", art.get('headline'))
            continue

        batch_id = art.get('batch_id')
        if (
            isinstance(batch_id, bool)
            or not isinstance(batch_id, int)
            or not 0 <= batch_id < len(original_batch)
        ):
            logger.error(
                "Skipping '%s' due to invalid source mapping: batch_id=%r, batch_size=%d",
                art.get('headline'),
                batch_id,
                len(original_batch),
            )
            continue
        original = original_batch[batch_id]

        source_url = (original.get('link') or '').strip()
        if source_url:
            source_duplicate = cursor.execute(
                """
                SELECT id, title
                FROM articles
                WHERE source_url = ?
                LIMIT 1
                """,
                (source_url,),
            ).fetchone()
            if source_duplicate:
                logger.info(
                    "Exact source URL duplicate blocked before publication: '%s' "
                    "already belongs to '%s' (article %s)",
                    art.get('headline'),
                    source_duplicate[1],
                    source_duplicate[0],
                )
                continue

        paper_duplicate = _find_research_paper_duplicate(
            cursor,
            source_url,
        )
        if paper_duplicate:
            logger.info(
                "Research paper duplicate blocked before publication: '%s' matches '%s' "
                "(article %s, paper %s)",
                art.get('headline'),
                paper_duplicate['title'],
                paper_duplicate['id'],
                paper_duplicate['paper_id'],
            )
            continue

        recent_duplicate = _find_recent_story_duplicate(
            cursor,
            art.get('headline', ''),
            art.get('gist', ''),
        )
        if recent_duplicate:
            logger.info(
                "Recent story duplicate blocked before publication: '%s' matches '%s' (article %s)",
                art.get('headline'),
                recent_duplicate['title'],
                recent_duplicate['id'],
            )
            continue

        # 2.5 EDITORIAL COMPASS — Semantic Scoring, Dedup & Ad Detection
        compass_score = 0.7  # Default for articles where compass unavailable
        try:
            from embedding_service import score_article, find_duplicates, index_article, score_ad_likelihood

            with ThreadPoolExecutor(max_workers=1) as executor:
                # AD SHIELD: Semantic ad/promotional content detection (R2-04: timeout)
                ad_future = executor.submit(
                    score_ad_likelihood,
                    art.get('headline', ''),
                    art.get('gist', ''),
                    art.get('why_it_matters', '')
                )
                try:
                    ad_score = ad_future.result(timeout=_EMBEDDING_TIMEOUT)
                except FuturesTimeout:
                    logger.warning("⏱️ AD SHIELD timeout for '%s'. Allowing through.", art.get('headline'))
                    ad_score = 0.0

                if ad_score >= 0.76:
                    logger.info("🛡️ AD SHIELD: Blocked '%s' — ad-likelihood %s (threshold: 0.76)", art.get('headline'), ad_score)
                    continue
                elif ad_score >= 0.65:
                    logger.warning("🛡️ AD SHIELD: REVIEW '%s' — ad-likelihood %s (borderline)", art.get('headline'), ad_score)

                # Semantic Dedup: Check if near-duplicate exists (>0.92 cosine) (R2-04: timeout)
                dup_future = executor.submit(
                    find_duplicates,
                    art.get('headline', ''),
                    art.get('gist', ''),
                    0.92,
                    art.get('why_it_matters', '')
                )
                try:
                    dup = dup_future.result(timeout=_EMBEDDING_TIMEOUT)
                except FuturesTimeout:
                    logger.warning("⏱️ Dedup timeout for '%s'. Skipping dedup check.", art.get('headline'))
                    dup = None

                if dup:
                    logger.info("🧬 Semantic Duplicate Detected: '%s' matches '%s' (score: %s)", art.get('headline'), dup['title'], dup['score'])
                    continue

                # Editorial Compass: Score relevance to existing corpus (R2-04: timeout)
                compass_future = executor.submit(
                    score_article,
                    art.get('headline', ''),
                    art.get('gist', ''),
                    art.get('why_it_matters', '')
                )
                try:
                    compass_score, similar = compass_future.result(timeout=_EMBEDDING_TIMEOUT)
                except FuturesTimeout:
                    logger.warning("⏱️ Compass timeout for '%s'. Using default score.", art.get('headline'))
                    compass_score, similar = 0.7, []

            if compass_score > 0:
                if compass_score >= 0.75:
                    logger.info("🧭 Compass: HIGH MATCH (%s) — '%s'", compass_score, art.get('headline'))
                elif compass_score >= 0.55:
                    logger.info("🧭 Compass: REVIEW (%s) — '%s'", compass_score, art.get('headline'))
                else:
                    logger.info("🧭 Compass: LOW MATCH (%s) — '%s' → Auto-kill candidate", compass_score, art.get('headline'))
                    try:
                        from services.lead_extractor import LeadExtractor
                        lead_extractor = LeadExtractor()
                        lead_extractor.extract_and_log(original.get('link', ''), art.get('headline', ''))
                        logger.info("🥋 Iron Judo: Low-compass article routed to leads.")
                    except Exception as le:
                        logger.warning("   ⚠️ Lead extraction failed: %s", le)
                    continue
        except ImportError:
            logger.debug("Embedding service not installed — skipping compass scoring")
        except Exception as compass_err:
            logger.warning("⚠️ Editorial Compass error (non-blocking): %s", compass_err)

        # 3. Robust Slug Generation
        final_slug = art.get('seo_slug')
        if not final_slug or final_slug == "None" or len(final_slug) < 2:
            final_slug = slugify(art.get('headline', ''))
        if not final_slug:
            final_slug = slugify(original.get('title', 'article'))
        if not final_slug:
            final_slug = f"article-{uuid.uuid4().hex[:8]}"

        # R2-02: Cap slug at 120 chars to prevent absurdly long URLs
        art['seo_slug'] = final_slug[:120]
        final_slug = art['seo_slug']

        # R2-03: Validate category against whitelist
        cat = art.get('category', 'Tools')
        if cat not in VALID_CATEGORIES:
            logger.warning("Invalid category '%s' for '%s'. Defaulting to 'Tools'.", cat, art.get('headline'))
            art['category'] = 'Tools'

        # Onsite image and social preview image are deliberately separate.
        # Text-heavy social cards make poor listing thumbnails, but work well
        # as controlled OG/Twitter preview assets.
        source_image_url = original.get('scraped_image')
        image_url = source_image_url if not _is_generic_image_url(source_image_url) else None
        source_name = original.get('source', '')
        is_generic = _is_generic_image_url(source_image_url)

        if source_name == "Google News" and is_generic:
            logger.info("⚠️ Google News article '%s' has no unique image. Using AI fallback.", art.get('headline'))

        social_image_url = _generate_branded_article_image(
            art.get('headline', ''),
            final_slug,
            art.get('gist', ''),
        )
        if not social_image_url:
            social_image_url = image_url

        # Fall back to category stock images for onsite display only.
        if _is_generic_image_url(image_url):
            cat = art.get('category', 'Tools')
            # Check the most recently saved article's image to avoid repetition.
            try:
                last_img_row = cursor.execute("SELECT image FROM articles ORDER BY id DESC LIMIT 1").fetchone()
                last_img = last_img_row[0] if last_img_row else None
            except (sqlite3.OperationalError, TypeError):
                last_img = None

            image_url = select_category_fallback(cat, avoid=last_img)

        if not social_image_url:
            social_image_url = image_url

        try:
            # --- DRIP-FEED: Calculate spread published_at ---
            _source_key = (original.get('source') or 'unknown').strip().lower()
            _offset_count = source_publish_offsets.get(_source_key, 0)
            source_publish_offsets[_source_key] = _offset_count + 1

            _now_utc = datetime.now(timezone.utc)
            _original_published_str = original.get('published')
            try:
                _orig_dt = datetime.fromisoformat(_original_published_str.replace('Z', '+00:00')) if _original_published_str else _now_utc
                if _orig_dt.tzinfo is None:
                    _orig_dt = _orig_dt.replace(tzinfo=timezone.utc)
            except (ValueError, AttributeError):
                _orig_dt = _now_utc

            # Base time is the later of: original publish time or now (never backdate)
            _base_dt = max(_orig_dt, _now_utc)
            _final_published_dt = _base_dt + timedelta(minutes=_SOURCE_SPREAD_MINUTES * _offset_count)
            _final_published = _final_published_dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')

            if _offset_count > 0:
                logger.info(
                    "🗓️ Drip-feed: '%s' from '%s' scheduled +%dh (offset %d)",
                    art.get('headline'), _source_key,
                    (_SOURCE_SPREAD_MINUTES * _offset_count) // 60, _offset_count
                )
            # --- END DRIP-FEED ---

            # Generate Audio Reads
            am, af = None, None
            if audio_gen:
                key_details_text = ". ".join(art.get('key_details', []))
                text_to_read = (
                    f"Headline: {art.get('headline')}. "
                    f"The Gist: {art.get('gist')}. "
                    f"Why It Matters: {art.get('why_it_matters')}. "
                    f"Optimistic Outlook: {art.get('optimistic_outlook')}. "
                    f"Risk Factors: {art.get('pessimistic_outlook')}. "
                    f"Key Details: {key_details_text}. "
                )
                am, af = audio_gen.generate_audio_reads(final_slug, text_to_read)

            cursor.execute('''
                INSERT INTO articles
                (slug, title, image, social_image, category, gist, why_it_matters, bull_case, bear_case, key_details, eli5, deep_analysis, source, source_url, full_json, published_at, audio_male, audio_female, hashtags, original_author, narration_script, thought_provoking_question, importance_score, design_tokens, compass_score, source_content_hash, ai_model_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                final_slug,
                art.get('headline'),
                image_url,
                social_image_url,
                art.get('category'),
                art.get('gist'),
                art.get('why_it_matters'),
                art.get('optimistic_outlook'),
                art.get('pessimistic_outlook'),
                json.dumps(art.get('key_details', [])),
                art.get('eli5'),
                art.get('deep_analysis'),
                original.get('source'),
                original.get('link'),
                json.dumps(art),
                _final_published,
                am,
                af,
                json.dumps(art.get('hashtags', [])),
                original.get('original_author'),
                art.get('narration_script'),
                art.get('thought_provoking_question'),
                int(art.get('importance_score', 50) or 50),
                json.dumps(art.get('design_tokens', {})),
                round(compass_score, 3),
                art.get('source_content_hash'),
                art.get('ai_model_used'),
            ))

            # Release the write lock before post-publish hooks open their own DB connections.
            conn.commit()
            articles_saved += 1

            local_url = f"https://dailyaiwire.news/article/{final_slug}"
            # Automatic Google Indexing API notifications are opt-in. General
            # article URLs are not supported by that API; sitemap discovery is
            # the normal indexing path.
            if google_indexing_enabled():
                notify_google_index(local_url)

            # RUN QA AUDIT (Self-Correction)
            run_post_publication_audit(local_url)

            # INDEX INTO QDRANT (Editorial Compass — Phase 0)
            try:
                from embedding_service import index_article
                new_id = cursor.execute("SELECT id FROM articles WHERE slug = ?", (final_slug,)).fetchone()
                if new_id:
                    index_article(
                        article_id=new_id[0],
                        title=art.get('headline', ''),
                        gist=art.get('gist', ''),
                        why_it_matters=art.get('why_it_matters', ''),
                        category=art.get('category', ''),
                        source=original.get('source', ''),
                        importance_score=imp_score
                    )
                    logger.info("📦 Indexed into Qdrant: %s", art.get('headline'))
            except ImportError:
                logger.debug("Embedding service not installed — skipping Qdrant indexing")
            except Exception as idx_err:
                logger.warning("⚠️ Qdrant indexing error (non-blocking): %s", idx_err)

            # STAGGERED SOCIAL QUEUING - DISABLED
            pass

        except Exception as e:
            logger.error("Error saving article %s: %s", art.get('headline'), e)

    conn.close()
    return SaveResult(posts_count=posts_count, articles_saved=articles_saved)


def process_social_queue():
    """Checks for pending social posts that are due."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, slug, headline FROM social_queue 
        WHERE status='PENDING' AND scheduled_time <= ?
    ''', (datetime.utcnow().isoformat(),))

    pending = cursor.fetchall()

    if not pending:
        conn.close()
        return

    distributor = SocialDistributor()

    for row in pending:
        queue_id, slug, headline = row
        logger.info("🚀 Processing scheduled post: %s", headline)

        cursor.execute('''
            SELECT a.full_json, a.source FROM articles a
            JOIN social_queue sq ON sq.slug = a.slug
            WHERE sq.id = ?
        ''', (queue_id,))
        art_row = cursor.fetchone()

        if art_row:
            try:
                article_data = json.loads(art_row[0])
                article_data['seo_slug'] = slug
                article_data['source'] = art_row[1]
                distributor.distribute(article_data)

                cursor.execute("UPDATE social_queue SET status='SENT' WHERE id=?", (queue_id,))
                cursor.execute("UPDATE articles SET shared_on_x=1, shared_at=? WHERE slug=?", (datetime.utcnow().isoformat(), slug))
                logger.info("✅ Successfully posted: %s", headline)
            except Exception as e:
                logger.error("❌ Failed to post %s: %s", headline, e)
                cursor.execute("UPDATE social_queue SET status='FAILED' WHERE id=?", (queue_id,))
        else:
            logger.warning("⚠️ Article data missing for slug: %s", slug)
            cursor.execute("UPDATE social_queue SET status='FAILED_MISSING_DATA' WHERE id=?", (queue_id,))

    conn.commit()
    conn.close()
