import os
import json
from google.oauth2 import service_account
from google.auth.transport.requests import Request
import requests

from services.indexing_audit import record_indexing_notification

# Scopes required for the Indexing API
SCOPES = ["https://www.googleapis.com/auth/indexing"]
ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def google_indexing_enabled() -> bool:
    """Return whether automatic Google Indexing API notifications are enabled."""
    return _env_truthy("ENABLE_GOOGLE_INDEXING_API")


def _skip_reason(url: str, action: str) -> str | None:
    if _env_truthy("ALLOW_UNSUPPORTED_GOOGLE_INDEXING_API"):
        return None
    return (
        "unsupported Indexing API usage for general article URLs; "
        "Google restricts this API to JobPosting and BroadcastEvent pages"
    )

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
    reason = _skip_reason(url, action)
    if reason:
        print(f"⚠️ Indexing Skipped: {reason} [{url}]")
        _record_indexing_audit(
            url=url,
            action=action,
            status="skipped",
            error=reason,
        )
        return

    creds = get_credentials()
    if not creds:
        _record_indexing_audit(
            url=url,
            action=action,
            status="skipped",
            error="credentials unavailable",
        )
        return

    # Refresh credentials to get an access token
    try:
        creds.refresh(Request())
    except Exception as e:
        print(f"❌ Failed to refresh credentials: {e}")
        _record_indexing_audit(
            url=url,
            action=action,
            status="failed",
            error=f"credential refresh failed: {e}",
        )
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
            _record_indexing_audit(
                url=url,
                action=action,
                status="success",
                status_code=response.status_code,
                response_body=response.text,
            )
        elif response.status_code == 429:
            print(f"⚠️ Query Quota Exceeded (429) for Indexing API. Skipping.")
            _record_indexing_audit(
                url=url,
                action=action,
                status="quota_exceeded",
                status_code=response.status_code,
                response_body=response.text,
            )
        else:
            print(f"⚠️ Indexing API Error {response.status_code}: {response.text}")
            _record_indexing_audit(
                url=url,
                action=action,
                status="failed",
                status_code=response.status_code,
                response_body=response.text,
            )

    except Exception as e:
        print(f"❌ Indexing Request Failed: {e}")
        _record_indexing_audit(
            url=url,
            action=action,
            status="failed",
            error=str(e),
        )


def _record_indexing_audit(**kwargs):
    try:
        record_indexing_notification(**kwargs)
    except Exception as exc:
        print(f"⚠️ Indexing audit write failed: {exc}")

if __name__ == "__main__":
    # Test
    test_url = "https://dailyaiwire.news/test-indexing"
    notify_google_index(test_url)
