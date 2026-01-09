import os
from google.cloud import texttospeech

def list_all_en_us_voices():
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Users\emreo\Documents\Gemini\gen-lang-client-0316461786-849135b92979.json"
    client = texttospeech.TextToSpeechClient()
    voices = client.list_voices()
    print("Available en-US Voices:")
    for v in voices.voices:
        if 'en-US' in v.name:
            print(f"- {v.name} ({v.ssml_gender.name})")

if __name__ == "__main__":
    list_all_en_us_voices()
