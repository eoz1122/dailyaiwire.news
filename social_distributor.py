import os
import sys
import logging

# Patch for Python 3.13+ where imghdr was removed (tweepy depends on it)
if sys.version_info >= (3, 13):
    import types
    imghdr = types.ModuleType("imghdr")
    imghdr.what = lambda filename, h=None: None
    sys.modules["imghdr"] = imghdr

import tweepy
import requests
from dotenv import load_dotenv
from google_indexer import notify_google_index
from url_shortener import shorten
from helpers import clean_markdown

load_dotenv()

logger = logging.getLogger('social')


def _env_int(name, default):
    try:
        return max(0, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


class XPostingPause(Exception):
    def __init__(self, reason, retry_after_seconds, message):
        super().__init__(message)
        self.reason = reason
        self.retry_after_seconds = retry_after_seconds


def classify_x_exception(exc):
    message = str(exc)
    message_lower = message.lower()

    if (
        "402" in message
        or "payment required" in message_lower
        or "does not have any credits" in message_lower
    ):
        return XPostingPause(
            "billing",
            _env_int("X_BILLING_BACKOFF_SECONDS", 21600),
            message,
        )

    if "429" in message or "too many requests" in message_lower:
        return XPostingPause(
            "rate_limit",
            _env_int("X_RATE_LIMIT_BACKOFF_SECONDS", 3600),
            message,
        )

    return None


class SocialDistributor:
    def __init__(self):
        # X (Twitter) Credentials
        self.x_api_key = os.getenv("X_API_KEY")
        self.x_api_secret = os.getenv("X_API_SECRET")
        self.x_access_token = os.getenv("X_ACCESS_TOKEN")
        self.x_access_secret = os.getenv("X_ACCESS_SECRET")
        self.x_bearer_token = os.getenv("X_BEARER_TOKEN")
        
        # Instagram Graph API Credentials
        self.ig_user_id = os.getenv("IG_USER_ID")
        self.ig_access_token = os.getenv("IG_ACCESS_TOKEN")
        
        # LinkedIn Credentials (Optional/Planned)
        self.linkedin_access_token = os.getenv("LINKEDIN_ACCESS_TOKEN")
        
        # Facebook Page API Credentials
        self.fb_page_id = os.getenv("FB_PAGE_ID")
        self.fb_page_access_token = os.getenv("FB_PAGE_ACCESS_TOKEN")
        
        # Base URL for links
        self.base_url = "https://dailyaiwire.news"

    def post_to_x(self, article):
        """Posts article gist, question, and link to X (Twitter)."""
        if not all([self.x_api_key, self.x_api_secret, self.x_access_token, self.x_access_secret]):
            logger.warning("⚠️ X (Twitter) credentials missing. Skipping post.")
            return

        try:
            client = tweepy.Client(
                bearer_token=self.x_bearer_token,
                consumer_key=self.x_api_key,
                consumer_secret=self.x_api_secret,
                access_token=self.x_access_token,
                access_token_secret=self.x_access_secret
            )
            
            headline = article.get('headline', 'New Intelligence')
            gist = article.get('gist', '')
            question = article.get('thought_provoking_question', '')
            slug = article.get('seo_slug')
            link = shorten(f"{self.base_url}/article/{slug}?utm_source=twitter&utm_medium=social&utm_campaign=auto_post")
            hashtags = article.get('hashtags', [])
            
            # Use provided hashtags only - NO generic fallbacks
            tags_str = " ".join(hashtags) if hashtags else ""
            
            # Clean markdown bolding
            gist_clean = clean_markdown(gist)
            
            source = article.get('source', '')
            
            # Construct richer tweet
            # We have a Blue Tick (Premium X) - NO TRIMMING needed.
            if source:
                tweet_text = f"{headline} (Source: {source})\n\n"
            else:
                tweet_text = f"{headline}\n\n"
            
            tweet_text += f"{gist_clean}\n\n"
            
            if tags_str:
                tweet_text += f"{tags_str}\n\n"
                
            if question:
                tweet_text += f"🤔 {question}\n\n"
                
            tweet_text += link
            
            logger.info("🐦 X (Twitter) Preview:")
            logger.info("-" * 30)
            logger.info(tweet_text)
            logger.info("-" * 30)
            
            # Send the tweet
            response = client.create_tweet(text=tweet_text)
            logger.info("✅ Posted to X! ID: %s", response.data['id'])
            
            # TRIGGER GOOGLE INDEXING (Instant Crawl)
            notify_google_index(link)
            
            return True
        except Exception as e:
            pause = classify_x_exception(e)
            if pause:
                raise pause
            logger.error("❌ Error posting to X: %s", e)
            return False

    def post_to_instagram(self, article):
        """Posts article image with caption to Instagram via Graph API.
        
        Two-step flow:
        1. POST /{ig-user-id}/media → creates a media container
        2. POST /{ig-user-id}/media_publish → publishes the container
        """
        if not all([self.ig_user_id, self.ig_access_token]):
            logger.warning("⚠️ Instagram credentials missing. Skipping post.")
            return False

        try:
            slug = article.get('seo_slug')
            headline = article.get('headline', 'New Intelligence')
            gist = article.get('gist', '')
            question = article.get('thought_provoking_question', '')
            hashtags = article.get('hashtags', [])
            link = shorten(f"{self.base_url}/article/{slug}?utm_source=instagram&utm_medium=social&utm_campaign=auto_post")

            # Generate branded card image
            try:
                from ig_card_generator import generate_card
                card_path = generate_card(headline=headline, slug=slug, gist=gist)
                image_url = f"{self.base_url}/static/img/social/{slug}.png"
                logger.info("🎨 Using branded card: %s", image_url)
            except Exception as card_err:
                logger.warning("⚠️ Card generation failed: %s, falling back to article image", card_err)
                image_path = article.get('image', '')
                if image_path and not image_path.startswith('http'):
                    image_url = f"{self.base_url}{image_path}"
                elif image_path:
                    image_url = image_path
                else:
                    logger.warning("⚠️ No image found for article. Instagram requires an image. Skipping.")
                    return False

            # Clean markdown formatting
            gist_clean = clean_markdown(gist)

            # Build caption (Instagram limit: 2,200 chars, 30 hashtags)
            caption_parts = [
                f"📡 {headline}",
                "",
                gist_clean,
            ]

            if question:
                caption_parts.extend(["", f"🤔 {question}"])

            caption_parts.extend(["", f"🔗 Full Analysis: {link}"])

            if hashtags:
                tags_str = " ".join(hashtags[:30])  # Instagram max 30 hashtags
                caption_parts.extend(["", tags_str])

            caption_parts.extend(["", "#DailyAIWire #AINews #HybridIntelligence"])

            caption = "\n".join(caption_parts)

            # Trim to Instagram's 2,200 char limit
            if len(caption) > 2200:
                caption = caption[:2197] + "..."

            logger.info("📸 Instagram Preview:")
            logger.info("-" * 30)
            logger.info("Image: %s", image_url)
            logger.info(caption[:200] + "..." if len(caption) > 200 else caption)
            logger.info("-" * 30)

            api_base = "https://graph.facebook.com/v22.0"

            # Step 1: Create media container
            container_resp = requests.post(
                f"{api_base}/{self.ig_user_id}/media",
                data={
                    "image_url": image_url,
                    "caption": caption,
                    "access_token": self.ig_access_token,
                },
                timeout=30,
            )
            container_data = container_resp.json()

            if "error" in container_data:
                err = container_data["error"]
                logger.error("❌ Instagram Container Error: %s", err.get('message', err))
                # Re-raise rate limit errors for scheduler backoff
                if err.get("code") == 4 or err.get("code") == 32:
                    raise Exception(f"Instagram Rate Limit: {err.get('message')}")
                return False

            creation_id = container_data.get("id")
            if not creation_id:
                logger.error("❌ No container ID returned: %s", container_data)
                return False

            logger.info("📦 Container created: %s", creation_id)

            # Step 2: Wait for container to be ready (poll status)
            # R2-05: Hard wall clock timeout (45s) in addition to retry limit
            import time as _time
            poll_deadline = _time.monotonic() + 45
            for attempt in range(10):
                if _time.monotonic() > poll_deadline:
                    logger.error("❌ Container processing hard-timeout (45s).")
                    return False
                status_resp = requests.get(
                    f"{api_base}/{creation_id}",
                    params={
                        "fields": "status_code",
                        "access_token": self.ig_access_token,
                    },
                    timeout=15,
                )
                status_data = status_resp.json()
                status_code = status_data.get("status_code", "UNKNOWN")

                if status_code == "FINISHED":
                    break
                elif status_code == "ERROR":
                    logger.error("❌ Container processing failed: %s", status_data)
                    return False
                else:
                    logger.info("⏳ Container status: %s (attempt %d/10)", status_code, attempt + 1)
                    _time.sleep(3)
            else:
                logger.error("❌ Container processing timed out after 30s.")
                return False

            # Step 3: Publish the container
            publish_resp = requests.post(
                f"{api_base}/{self.ig_user_id}/media_publish",
                data={
                    "creation_id": creation_id,
                    "access_token": self.ig_access_token,
                },
                timeout=30,
            )
            publish_data = publish_resp.json()

            if "error" in publish_data:
                err = publish_data["error"]
                logger.error("❌ Instagram Publish Error: %s", err.get('message', err))
                if err.get("code") == 4 or err.get("code") == 32:
                    raise Exception(f"Instagram Rate Limit: {err.get('message')}")
                return False

            media_id = publish_data.get("id")
            logger.info("✅ Posted to Instagram! Media ID: %s", media_id)
            return True

        except requests.exceptions.RequestException as e:
            logger.error("❌ Instagram network error: %s", e)
            return False
        except Exception as e:
            if "Rate Limit" in str(e):
                raise e
            logger.error("❌ Error posting to Instagram: %s", e)
            return False

    def post_to_facebook(self, article):
        """Posts article link with message to Facebook Page via Graph API.
        
        Single-step: POST /{page-id}/feed with message + link
        """
        if not all([self.fb_page_id, self.fb_page_access_token]):
            logger.warning("⚠️ Facebook Page credentials missing. Skipping post.")
            return False

        try:
            slug = article.get('seo_slug')
            headline = article.get('headline', 'New Intelligence')
            gist = article.get('gist', '')
            question = article.get('thought_provoking_question', '')
            hashtags = article.get('hashtags', [])
            link = shorten(f"{self.base_url}/article/{slug}?utm_source=facebook&utm_medium=social&utm_campaign=auto_post")

            # Clean markdown formatting
            gist_clean = clean_markdown(gist)

            # Build Facebook post message
            msg_parts = [
                f"📡 {headline}",
                "",
                gist_clean,
            ]

            if question:
                msg_parts.extend(["", f"🤔 {question}"])

            if hashtags:
                tags_str = " ".join(hashtags[:30])
                msg_parts.extend(["", tags_str])

            msg_parts.extend(["", "#DailyAIWire #AINews #HybridIntelligence"])

            message = "\n".join(msg_parts)

            logger.info("📘 Facebook Preview:")
            logger.info("-" * 30)
            logger.info(message[:200] + "..." if len(message) > 200 else message)
            logger.info("Link: %s", link)
            logger.info("-" * 30)

            api_base = "https://graph.facebook.com/v22.0"

            # Generate branded card for Facebook photo post
            image_url = None
            try:
                from ig_card_generator import generate_card
                card_path = generate_card(headline=headline, slug=slug, gist=gist)
                image_url = f"{self.base_url}/static/img/social/{slug}.png"
                logger.info("🎨 Using branded card for FB: %s", image_url)
            except Exception as card_err:
                logger.warning("⚠️ Card generation failed: %s, posting without image", card_err)

            # Post as photo if card available, otherwise as link
            if image_url:
                resp = requests.post(
                    f"{api_base}/{self.fb_page_id}/photos",
                    data={
                        "url": image_url,
                        "caption": message + f"\n\n🔗 {link}",
                        "access_token": self.fb_page_access_token,
                    },
                    timeout=30,
                )
            else:
                resp = requests.post(
                    f"{api_base}/{self.fb_page_id}/feed",
                    data={
                        "message": message,
                        "link": link,
                        "access_token": self.fb_page_access_token,
                    },
                    timeout=30,
                )
            resp_data = resp.json()

            if "error" in resp_data:
                err = resp_data["error"]
                logger.error("❌ Facebook Post Error: %s", err.get('message', err))
                # Re-raise rate limit errors for scheduler backoff
                if err.get("code") in (4, 32, 368):
                    raise Exception(f"Facebook Rate Limit: {err.get('message')}")
                return False

            post_id = resp_data.get("id")
            logger.info("✅ Posted to Facebook! Post ID: %s", post_id)
            return True

        except requests.exceptions.RequestException as e:
            logger.error("❌ Facebook network error: %s", e)
            return False
        except Exception as e:
            if "Rate Limit" in str(e):
                raise e
            logger.error("❌ Error posting to Facebook: %s", e)
            return False

    def post_to_linkedin(self, article):
        """Posts deep analysis summary to LinkedIn (Placeholder for API integration)."""
        headline = article.get('headline', 'Intelligence Update')
        analysis = article.get('deep_analysis', '')
        slug = article.get('seo_slug')
        link = shorten(f"{self.base_url}/article/{slug}")
        
        # Clean markdown
        analysis_clean = clean_markdown(analysis).replace('\n', ' ')
        
        li_text = f"📢 AI-First Intelligence Analysis: {headline}\n\n{analysis_clean[:400]}...\n\nFull Investigation: {link}\n\n#AI #DailyAIWire #HybridIntelligence #Innovation"
        
        if not self.linkedin_access_token:
            logger.info("📝 LinkedIn Preview (Token missing):")
            logger.info("-" * 30)
            logger.info(li_text)
            logger.info("-" * 30)
            return
            
        logger.info("✅ LinkedIn Automation: Sent analysis for '%s'", headline)
        # Logic for LinkedIn API (POST /ugcPosts) would go here
        
    def distribute(self, article):
        """Run the active distribution channels."""
        self.post_to_x(article)
        self.post_to_linkedin(article)

if __name__ == "__main__":
    # Test block
    distributor = SocialDistributor()
    dummy_article = {
        "headline": "AI Genesis Mission Meeting",
        "gist": "White House convenes top leaders to discuss AI safety.",
        "seo_slug": "ai-genesis-mission",
        "deep_analysis": "Full analysis here..."
    }
    # distributor.distribute(dummy_article)
    # distributor.distribute(dummy_article)
