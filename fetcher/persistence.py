"""
Fetcher — Persistence & Post-Processing
Save articles to DB, social queue processing, Google indexing, Qdrant indexing.
"""
import json
import uuid
import time
import random
import sqlite3
from datetime import datetime
from typing import List, Dict

from slugify import slugify

from db import DB_PATH, get_db_connection
from social_distributor import SocialDistributor
from google_indexer import notify_google_index
from qa_monitor import run_post_publication_audit


def save_to_db(processed_articles: List[Dict], original_batch: List[Dict], distributor=None, social_limit=2, posts_count=0, audio_gen=None):
    """Persist processed articles to the database with all post-save hooks."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for art in processed_articles:
        # 1. Status Check (New 2026 Guardrail)
        if art.get('status') == "INSUFFICIENT_DATA":
            print(f"Skipping '{art.get('headline')}' - AI flagged as Insufficient Data.")
            continue

        # 1.5 Score Filter (New 2026 Guardrail)
        imp_score = int(art.get('importance_score', 0) or 0)
        if imp_score < 50:
            print(f"Skipping '{art.get('headline')}' - Score {imp_score} < 50.")
            continue

        # Skip articles where AI failed to find content or hit a paywall/blocker
        gist = str(art.get('gist', '')).lower()
        impact = str(art.get('why_it_matters', '')).lower()
        headline = str(art.get('headline', '')).lower()
        analysis = str(art.get('deep_analysis', ''))

        # 2. Transparency & Attribution Injection (EU AI Act)
        footer = "\n\n_Context: This intelligence report was compiled by the DailyAIWire Strategy Engine. Verified for Art. 50 Compliance._"
        if footer not in analysis:
            art['deep_analysis'] = analysis + footer
            analysis = art['deep_analysis'].lower()

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
            print(f"Skipping '{art.get('headline')}' due to content blocker signal (JS/Access Denied).")
            continue

        # 2.5 EDITORIAL COMPASS — Semantic Scoring, Dedup & Ad Detection
        compass_score = 0.7  # Default for articles where compass unavailable
        try:
            from embedding_service import score_article, find_duplicates, index_article, score_ad_likelihood

            # AD SHIELD: Semantic ad/promotional content detection
            ad_score = score_ad_likelihood(
                art.get('headline', ''),
                art.get('gist', ''),
                art.get('why_it_matters', '')
            )
            if ad_score >= 0.76:
                print(f"🛡️ AD SHIELD: Blocked '{art.get('headline')}' — ad-likelihood {ad_score} (threshold: 0.76)")
                continue
            elif ad_score >= 0.65:
                print(f"🛡️ AD SHIELD: REVIEW '{art.get('headline')}' — ad-likelihood {ad_score} (borderline)")

            # Semantic Dedup: Check if near-duplicate exists (>0.92 cosine)
            dup = find_duplicates(
                art.get('headline', ''),
                art.get('gist', ''),
                threshold=0.92
            )
            if dup:
                print(f"🧬 Semantic Duplicate Detected: '{art.get('headline')}' matches '{dup['title']}' (score: {dup['score']})")
                continue

            # Editorial Compass: Score relevance to existing corpus
            compass_score, similar = score_article(
                art.get('headline', ''),
                art.get('gist', ''),
                art.get('why_it_matters', '')
            )

            if compass_score > 0:
                if compass_score >= 0.75:
                    print(f"🧭 Compass: HIGH MATCH ({compass_score}) — '{art.get('headline')}'")
                elif compass_score >= 0.55:
                    print(f"🧭 Compass: REVIEW ({compass_score}) — '{art.get('headline')}'")
                else:
                    print(f"🧭 Compass: LOW MATCH ({compass_score}) — '{art.get('headline')}' → Auto-kill candidate")
                    try:
                        from services.lead_extractor import LeadExtractor
                        lead_extractor = LeadExtractor()
                        lead_extractor.extract_and_log(original.get('link', ''), art.get('headline', ''))
                        print(f"🥋 Iron Judo: Low-compass article routed to leads.")
                    except Exception as le:
                        print(f"   ⚠️ Lead extraction failed: {le}")
                    continue
        except ImportError:
            pass  # Compass not installed, skip gracefully
        except Exception as compass_err:
            print(f"⚠️ Editorial Compass error (non-blocking): {compass_err}")

        # Determine the article identifier
        lookup_slug = art.get('seo_slug') or slugify(art.get('headline', ''))

        # Find original source info
        batch_id = art.get('batch_id')
        if isinstance(batch_id, list) and batch_id:
            batch_id = batch_id[0]

        if batch_id is not None and isinstance(batch_id, int) and 0 <= batch_id < len(original_batch):
            original = original_batch[batch_id]
        else:
            source_map = {slugify(it['title']): it for it in original_batch}
            original = source_map.get(lookup_slug, original_batch[0])

        # 1. Prioritize scraped image
        image_url = original.get('scraped_image')

        # 2. Use image_query if scraped image is missing
        source_name = original.get('source', '')
        is_generic = not image_url or not image_url.startswith('http') or any(x in image_url.lower() for x in ["google", "placeholder", "logo", "icon", "pixel"])

        if source_name == "Google News" and is_generic:
            print(f"⚠️ Google News article '{art.get('headline')}' has no unique image. Using AI fallback.")

        if is_generic:
            cat = art.get('category', 'Tools')
            cat_map = {
                "LLMs": [
                    "/static/fallbacks/llms_0.jpg",
                    "/static/fallbacks/llms_1.jpg",
                    "/static/fallbacks/llms_2.jpg",
                    "/static/fallbacks/llms_3.jpg"
                ],
                "Robotics": [
                    "/static/fallbacks/robotics_0.jpg",
                    "/static/fallbacks/robotics_1.jpg",
                    "/static/fallbacks/robotics_2.jpg",
                    "/static/fallbacks/robotics_3.jpg",
                    "/static/fallbacks/robotics_4.jpg",
                    "/static/fallbacks/robotics_5.jpg",
                    "/static/fallbacks/robotics_6.jpg",
                    "/static/fallbacks/robotics_7.jpg"
                ],
                "Business": [
                    "/static/fallbacks/business_0.jpg",
                    "/static/fallbacks/business_1.jpg",
                    "/static/fallbacks/business_2.jpg",
                    "/static/fallbacks/business_3.jpg",
                    "/static/fallbacks/business_4.jpg",
                    "/static/fallbacks/business_5.jpg",
                    "/static/fallbacks/business_6.jpg",
                    "/static/fallbacks/business_7.jpg",
                    "/static/fallbacks/business_8.jpg"
                ],
                "Tools": [
                    "/static/fallbacks/tools_0.jpg",
                    "/static/fallbacks/tools_1.jpg",
                    "/static/fallbacks/tools_2.jpg"
                ],
                "Policy": [
                    "/static/fallbacks/policy_0.jpg",
                    "/static/fallbacks/policy_1.jpg",
                    "/static/fallbacks/policy_2.jpg",
                    "/static/fallbacks/policy_3.jpg",
                    "/static/fallbacks/policy_4.jpg",
                    "/static/fallbacks/policy_5.jpg",
                    "/static/fallbacks/policy_6.jpg",
                    "/static/fallbacks/policy_7.jpg"
                ],
                "Science": [
                    "/static/fallbacks/science_0.jpg",
                    "/static/fallbacks/science_1.jpg",
                    "/static/fallbacks/science_2.jpg",
                    "/static/fallbacks/science_3.jpg",
                    "/static/fallbacks/science_4.jpg",
                    "/static/fallbacks/science_5.jpg",
                    "/static/fallbacks/science_6.jpg",
                    "/static/fallbacks/science_7.jpg"
                ],
                "Security": [
                    "/static/fallbacks/security_0.jpg",
                    "/static/fallbacks/security_1.jpg",
                    "/static/fallbacks/security_2.jpg",
                    "/static/fallbacks/security_3.jpg"
                ],
                "Society": [
                    "/static/fallbacks/society_0.jpg",
                    "/static/fallbacks/society_1.jpg",
                    "/static/fallbacks/society_2.jpg",
                    "/static/fallbacks/society_3.jpg",
                    "/static/fallbacks/society_4.jpg"
                ],
                "Ethics": [
                    "/static/fallbacks/policy_0.jpg",
                    "/static/fallbacks/policy_1.jpg",
                    "/static/fallbacks/policy_2.jpg",
                    "/static/fallbacks/policy_3.jpg"
                ],
                "AI Agents": [
                    "/static/fallbacks/tools_0.jpg",
                    "/static/fallbacks/tools_1.jpg",
                    "/static/fallbacks/tools_2.jpg",
                    "/static/fallbacks/robotics_0.jpg",
                    "/static/fallbacks/robotics_1.jpg"
                ]
            }
            images = cat_map.get(cat, cat_map["Tools"])

            # Check the most recently saved article's image to avoid repetition
            try:
                last_img_row = cursor.execute("SELECT image FROM articles ORDER BY id DESC LIMIT 1").fetchone()
                last_img = last_img_row[0] if last_img_row else None
            except (sqlite3.OperationalError, TypeError):
                last_img = None

            available_images = [img for img in images if img != last_img]
            if not available_images:
                available_images = images

            image_url = random.choice(available_images)

        # 3. Robust Slug Generation
        final_slug = art.get('seo_slug')
        if not final_slug or final_slug == "None" or len(final_slug) < 2:
            final_slug = slugify(art.get('headline', ''))
        if not final_slug:
            final_slug = slugify(original.get('title', 'article'))
        if not final_slug:
            final_slug = f"article-{uuid.uuid4().hex[:8]}"

        art['seo_slug'] = final_slug

        try:
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
                INSERT OR REPLACE INTO articles 
                (slug, title, image, category, gist, why_it_matters, bull_case, bear_case, key_details, eli5, deep_analysis, source, source_url, full_json, published_at, audio_male, audio_female, hashtags, original_author, narration_script, thought_provoking_question, importance_score, design_tokens, compass_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                final_slug,
                art.get('headline'),
                image_url,
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
                original.get('published'),
                am,
                af,
                json.dumps(art.get('hashtags', [])),
                original.get('original_author'),
                art.get('narration_script'),
                art.get('thought_provoking_question'),
                int(art.get('importance_score', 50) or 50),
                json.dumps(art.get('design_tokens', {})),
                round(compass_score, 3)
            ))

            # TRIGGER GOOGLE INDEXING (Instant Crawl)
            local_url = f"https://dailyaiwire.news/article/{final_slug}"
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
                    print(f"📦 Indexed into Qdrant: {art.get('headline')}")
            except ImportError:
                pass  # Compass not installed
            except Exception as idx_err:
                print(f"⚠️ Qdrant indexing error (non-blocking): {idx_err}")

            # STAGGERED SOCIAL QUEUING - DISABLED
            pass

        except Exception as e:
            print(f"Error saving article {art.get('headline')}: {e}")

    conn.commit()
    conn.close()
    return posts_count


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
        print(f"🚀 Processing scheduled post: {headline}")

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
                print(f"✅ Successfully posted: {headline}")
            except Exception as e:
                print(f"❌ Failed to post {headline}: {e}")
                cursor.execute("UPDATE social_queue SET status='FAILED' WHERE id=?", (queue_id,))
        else:
            print(f"⚠️ Article data missing for slug: {slug}")
            cursor.execute("UPDATE social_queue SET status='FAILED_MISSING_DATA' WHERE id=?", (queue_id,))

    conn.commit()
    conn.close()
