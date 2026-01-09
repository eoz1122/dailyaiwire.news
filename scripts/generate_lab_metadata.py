import google.generativeai as genai
import os
import sys
from dotenv import load_dotenv

# Load env from parent dir
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def generate_social_metadata(title, content_snippet):
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = f"""
    You are a social media strategist. Generate two metadata fields for a new blog post.
    
    TITLE: {title}
    CONTENT SAMPLE: {content_snippet[:2000]}
    
    Output Format:
    "thought_provoking_question": "Your question here?",
    "hashtags": ["#Tag1", "#Tag2", "#Tag3", "#Tag4", "#Tag5"]
    
    Instructions:
    1. Question: Engaging, challenges the reader, or highlights a key insight. Max 20 words.
    2. Hashtags: 3-5 relevant, high-traffic tech/AI hashtags.
    3. Output ONLY the two lines above, ready to paste into a Python dict.
    """
    
    response = model.generate_content(prompt)
    print("\n--- COPY PASTE BELOW INTO lab_posts.py ---\n")
    print(response.text.strip().replace('```', ''))
    print("\n------------------------------------------\n")

if __name__ == "__main__":
    print("Simply paste the Title and a chunk of Content below.")
    title = input("Title: ")
    print("Content (paste and press Enter, then Ctrl+Z/D to finish):")
    lines = sys.stdin.read()
    
    generate_social_metadata(title, lines)
