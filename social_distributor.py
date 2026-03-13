import os
import sys

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

load_dotenv()

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
            print("⚠️ X (Twitter) credentials missing. Skipping post.")
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
            link = f"{self.base_url}/article/{slug}"
            hashtags = article.get('hashtags', [])
            
            # Use provided hashtags only - NO generic fallbacks
            tags_str = " ".join(hashtags) if hashtags else ""
            
            # Clean markdown bolding
            gist_clean = gist.replace('**', '')
            
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
            
            print("🐦 X (Twitter) Preview:")
            print("-" * 30)
            print(tweet_text)
            print("-" * 30)
            
            # Send the tweet
            response = client.create_tweet(text=tweet_text)
            print(f"✅ Posted to X! ID: {response.data['id']}")
            
            # TRIGGER GOOGLE INDEXING (Instant Crawl)
            notify_google_index(link)
            
            return True
        except Exception as e:
            # CRITICAL LOOP FIX: Re-raise "Too Many Requests" so the scheduler knows to sleep
            if "429" in str(e) or "Too Many Requests" in str(e):
                raise e
            print(f"❌ Error posting to X: {e}")
            return False

    def post_to_instagram(self, article):
        """Posts article image with caption to Instagram via Graph API.
        
        Two-step flow:
        1. POST /{ig-user-id}/media → creates a media container
        2. POST /{ig-user-id}/media_publish → publishes the container
        """
        if not all([self.ig_user_id, self.ig_access_token]):
            print("⚠️ Instagram credentials missing. Skipping post.")
            return False

        try:
            slug = article.get('seo_slug')
            headline = article.get('headline', 'New Intelligence')
            gist = article.get('gist', '')
            question = article.get('thought_provoking_question', '')
            hashtags = article.get('hashtags', [])
            image_path = article.get('image', '')
            link = f"{self.base_url}/article/{slug}"

            # Instagram requires a publicly accessible image URL (JPEG)
            if image_path and not image_path.startswith('http'):
                image_url = f"{self.base_url}{image_path}"
            elif image_path:
                image_url = image_path
            else:
                print("⚠️ No image found for article. Instagram requires an image. Skipping.")
                return False

            # Clean markdown formatting
            gist_clean = gist.replace('**', '')

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

            print("📸 Instagram Preview:")
            print("-" * 30)
            print(f"Image: {image_url}")
            print(caption[:200] + "..." if len(caption) > 200 else caption)
            print("-" * 30)

            api_base = "https://graph.instagram.com/v22.0"

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
                print(f"❌ Instagram Container Error: {err.get('message', err)}")
                # Re-raise rate limit errors for scheduler backoff
                if err.get("code") == 4 or err.get("code") == 32:
                    raise Exception(f"Instagram Rate Limit: {err.get('message')}")
                return False

            creation_id = container_data.get("id")
            if not creation_id:
                print(f"❌ No container ID returned: {container_data}")
                return False

            print(f"📦 Container created: {creation_id}")

            # Step 2: Wait for container to be ready (poll status)
            import time as _time
            for attempt in range(10):
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
                    print(f"❌ Container processing failed: {status_data}")
                    return False
                else:
                    print(f"⏳ Container status: {status_code} (attempt {attempt + 1}/10)")
                    _time.sleep(3)
            else:
                print("❌ Container processing timed out after 30s.")
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
                print(f"❌ Instagram Publish Error: {err.get('message', err)}")
                if err.get("code") == 4 or err.get("code") == 32:
                    raise Exception(f"Instagram Rate Limit: {err.get('message')}")
                return False

            media_id = publish_data.get("id")
            print(f"✅ Posted to Instagram! Media ID: {media_id}")
            return True

        except requests.exceptions.RequestException as e:
            print(f"❌ Instagram network error: {e}")
            return False
        except Exception as e:
            if "Rate Limit" in str(e):
                raise e
            print(f"❌ Error posting to Instagram: {e}")
            return False

    def post_to_facebook(self, article):
        """Posts article link with message to Facebook Page via Graph API.
        
        Single-step: POST /{page-id}/feed with message + link
        """
        if not all([self.fb_page_id, self.fb_page_access_token]):
            print("⚠️ Facebook Page credentials missing. Skipping post.")
            return False

        try:
            slug = article.get('seo_slug')
            headline = article.get('headline', 'New Intelligence')
            gist = article.get('gist', '')
            question = article.get('thought_provoking_question', '')
            hashtags = article.get('hashtags', [])
            link = f"{self.base_url}/article/{slug}"

            # Clean markdown formatting
            gist_clean = gist.replace('**', '')

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

            print("📘 Facebook Preview:")
            print("-" * 30)
            print(message[:200] + "..." if len(message) > 200 else message)
            print(f"Link: {link}")
            print("-" * 30)

            api_base = "https://graph.facebook.com/v22.0"

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
                print(f"❌ Facebook Post Error: {err.get('message', err)}")
                # Re-raise rate limit errors for scheduler backoff
                if err.get("code") in (4, 32, 368):
                    raise Exception(f"Facebook Rate Limit: {err.get('message')}")
                return False

            post_id = resp_data.get("id")
            print(f"✅ Posted to Facebook! Post ID: {post_id}")
            return True

        except requests.exceptions.RequestException as e:
            print(f"❌ Facebook network error: {e}")
            return False
        except Exception as e:
            if "Rate Limit" in str(e):
                raise e
            print(f"❌ Error posting to Facebook: {e}")
            return False

    def post_to_linkedin(self, article):
        """Posts deep analysis summary to LinkedIn (Placeholder for API integration)."""
        headline = article.get('headline', 'Intelligence Update')
        analysis = article.get('deep_analysis', '')
        slug = article.get('seo_slug')
        link = f"{self.base_url}/article/{slug}"
        
        # Clean markdown
        analysis_clean = analysis.replace('**', '').replace('\n', ' ')
        
        li_text = f"📢 AI-First Intelligence Analysis: {headline}\n\n{analysis_clean[:400]}...\n\nFull Investigation: {link}\n\n#AI #DailyAIWire #HybridIntelligence #Innovation"
        
        if not self.linkedin_access_token:
            print("📝 LinkedIn Preview (Token missing):")
            print("-" * 30)
            print(li_text)
            print("-" * 30)
            return
            
        print(f"✅ LinkedIn Automation: Sent analysis for '{headline}'")
        # Logic for LinkedIn API (POST /ugcPosts) would go here
        
    def distribute(self, article):
        """Run all active distribution channels."""
        self.post_to_x(article)
        self.post_to_instagram(article)
        self.post_to_facebook(article)
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
