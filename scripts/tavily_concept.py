import os
import requests
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Concept: Tavily "Truth Layer" for DailyAIWire
# This module would be imported by fetcher.py to cross-reference headlines before synthesis.

load_dotenv()

class TavilyTruthLayer:
    def __init__(self):
        self.api_key = os.getenv("TAVILY_API_KEY")
        self.base_url = "https://api.tavily.com/search"

    def fact_check_headline(self, headline: str) -> Dict:
        """
        Performs a 'Basic Search' (1 credit) to find corroborating sources.
        Returns a context blob to be appended to the AI synthesis prompt.
        """
        if not self.api_key:
            print("⚠️ Tavily API Key missing. Skipping fact check.")
            return {}

        payload = {
            "api_key": self.api_key,
            "query": f'latest news about "{headline}"',
            "search_depth": "basic",
            "topic": "news",
            "days": 3, # Freshness is key
            "include_answer": False,
            "include_raw_content": False,
            "max_results": 3,
        }

        try:
            response = requests.post(self.base_url, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Extract key URLS and snippets
            results = data.get("results", [])
            context = "\n".join([f"- {r['title']} ({r['url']}): {r['content'][:200]}..." for r in results])
            
            return {
                "verified": bool(results),
                "context": context,
                "sources": [r['url'] for r in results]
            }

        except Exception as e:
            print(f"⚠️ Tavily Check Failed: {e}")
            return {"verified": False, "context": "", "sources": []}

    def deep_dive_research(self, topic: str) -> str:
        """
        Performs an 'Advanced Search' (2 credits) for the 'Deep Analysis' section.
        Used only for 'High Importance' (Score > 80) articles.
        """
        # Logic similar to above but search_depth="advanced" and include_raw_content=True
        pass

# Example Integration in fetcher.py:
# truth_layer = TavilyTruthLayer()
# check = truth_layer.fact_check_headline(article['headline'])
# if check['verified']:
#     prompt += f"\n\nVERIFIED CONTEXT FROM WEB:\n{check['context']}"
