import os
import json
from google.oauth2 import service_account
from google.auth.transport.requests import Request
import requests

# Scopes required for the Indexing API
SCOPES = ["https://www.googleapis.com/auth/indexing"]
ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"

def get_credentials():
    """Authenticates using the Service Account JSON key."""
    # Look for the key file in the same directory or a secure location
    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
    
    if not os.path.exists(key_path):
        print(f"⚠️ Indexing Skipped: Service account key not found at {key_path}")
        return None

    try:
        creds = service_account.Credentials.from_service_account_file(
            key_path, scopes=SCOPES
        )
        return creds
    except Exception as e:
        print(f"❌ Auth Failed: {e}")
        return None

def notify_google_index(url: str, action="URL_UPDATED"):
    """
    Sends a notification to Google Indexing API.
    
    Args:
        url (str): The URL to update or remove.
        action (str): "URL_UPDATED" or "URL_DELETED".
    """
    creds = get_credentials()
    if not creds:
        return

    # Refresh credentials to get an access token
    try:
        creds.refresh(Request())
    except Exception as e:
        print(f"❌ Failed to refresh credentials: {e}")
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {creds.token}"
    }

    payload = {
        "url": url,
        "type": action
    }

    try:
        response = requests.post(ENDPOINT, headers=headers, json=payload, timeout=10)
        
        if response.status_code == 200:
            print(f"📡 Google Indexing Notified: {url} [{action}]")
        elif response.status_code == 429:
            print(f"⚠️ Query Quota Exceeded (429) for Indexing API. Skipping.")
        else:
            print(f"⚠️ Indexing API Error {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"❌ Indexing Request Failed: {e}")

if __name__ == "__main__":
    # Test
    test_url = "https://dailyaiwire.news/test-indexing"
    notify_google_index(test_url)
