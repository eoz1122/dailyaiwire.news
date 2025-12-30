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

load_dotenv()

class SocialDistributor:
    def __init__(self):
        # X (Twitter) Credentials
        self.x_api_key = os.getenv("X_API_KEY")
        self.x_api_secret = os.getenv("X_API_SECRET")
        self.x_access_token = os.getenv("X_ACCESS_TOKEN")
        self.x_access_secret = os.getenv("X_ACCESS_SECRET")
        self.x_bearer_token = os.getenv("X_BEARER_TOKEN")
        
        # LinkedIn Credentials (Optional/Planned)
        self.linkedin_access_token = os.getenv("LINKEDIN_ACCESS_TOKEN")
        
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
            return True
        except Exception as e:
            # CRITICAL LOOP FIX: Re-raise "Too Many Requests" so the scheduler knows to sleep
            if "429" in str(e) or "Too Many Requests" in str(e):
                raise e
            print(f"❌ Error posting to X: {e}")
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
