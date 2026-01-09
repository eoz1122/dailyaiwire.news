
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("❌ Error: GEMINI_API_KEY not found.")
    exit(1)

genai.configure(api_key=api_key)


print("Listing available models...")
with open("models_output.txt", "w") as f:
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(f"- {m.name}")
                f.write(f"{m.name}\n")
    except Exception as e:
        print(f"Error listing models: {e}")
        f.write(f"Error: {e}\n")

