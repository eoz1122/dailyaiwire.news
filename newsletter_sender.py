import sqlite3
import json
import os
import hmac
import hashlib
import logging
import re
import requests
import time
from datetime import datetime
from dotenv import load_dotenv
from markupsafe import escape
from db import DB_PATH

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

logger = logging.getLogger('newsletter')

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
SENDER_EMAIL = "briefing@dailyaiwire.news"  # Verified Domain Sender
RESEND_API_URL = "https://api.resend.com/emails"
RESEND_TIMEOUT_SECONDS = 10
NEWSLETTER_LOCK_TIMEOUT_HOURS = 2
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _tracking_token(newsletter_id, email):
    """Generate a one-way HMAC token for newsletter open tracking (F-03).
    Replaces raw PII (email) in tracking URLs with an opaque token."""
    secret = os.getenv('SECRET_KEY')
    if not secret:
        raise RuntimeError("SECRET_KEY is required for newsletter tracking tokens.")
    msg = f"{newsletter_id}:{email}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()[:16]


def _newsletter_issue_context(newsletter_row):
    """Build display-friendly issue/date labels for the weekly briefing masthead."""
    raw_date = (
        newsletter_row["scheduled_date"]
        or newsletter_row["created_at"]
        or ""
    )
    try:
        parsed = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
    except Exception:
        parsed = datetime.utcnow()

    iso_week = parsed.isocalendar().week
    return {
        "newsletter_date_display": parsed.strftime("%d %b %Y").upper(),
        "newsletter_issue_label": f"W{iso_week:02d} · {parsed.year}",
    }


def ensure_newsletter_delivery_safety_schema(conn):
    """Add broadcast locking, audit fields, and recipient idempotency."""
    newsletter_columns = {
        row["name"] if hasattr(row, "keys") else row[1]
        for row in conn.execute("PRAGMA table_info(newsletters)").fetchall()
    }
    newsletter_migrations = {
        "broadcast_started_at": "ALTER TABLE newsletters ADD COLUMN broadcast_started_at TIMESTAMP",
        "broadcast_finished_at": "ALTER TABLE newsletters ADD COLUMN broadcast_finished_at TIMESTAMP",
        "last_send_error": "ALTER TABLE newsletters ADD COLUMN last_send_error TEXT",
    }
    for column, ddl in newsletter_migrations.items():
        if column not in newsletter_columns:
            logger.info("MIGRATION: Adding newsletters.%s...", column)
            conn.execute(ddl)

    delivery_columns = {
        row["name"] if hasattr(row, "keys") else row[1]
        for row in conn.execute("PRAGMA table_info(newsletter_deliveries)").fetchall()
    }
    delivery_migrations = {
        "tracking_token": "ALTER TABLE newsletter_deliveries ADD COLUMN tracking_token TEXT",
        "opened_at": "ALTER TABLE newsletter_deliveries ADD COLUMN opened_at TIMESTAMP",
        "resend_message_id": "ALTER TABLE newsletter_deliveries ADD COLUMN resend_message_id TEXT",
        "provider_response": "ALTER TABLE newsletter_deliveries ADD COLUMN provider_response TEXT",
    }
    for column, ddl in delivery_migrations.items():
        if column not in delivery_columns:
            logger.info("MIGRATION: Adding newsletter_deliveries.%s...", column)
            conn.execute(ddl)

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_newsletter_delivery_recipient
        ON newsletter_deliveries (newsletter_id, recipient_email COLLATE NOCASE)
        """
    )
    from services.resend_webhooks import ensure_resend_webhook_schema
    ensure_resend_webhook_schema(conn)
    conn.commit()


def _ensure_tracking_columns(conn):
    """Compatibility wrapper for callers that need delivery audit columns."""
    ensure_newsletter_delivery_safety_schema(conn)


def reserve_newsletter_send(newsletter_id):
    """Atomically reserve one newsletter for one broadcast worker."""
    conn = sqlite3.connect(DB_PATH, timeout=RESEND_TIMEOUT_SECONDS)
    try:
        ensure_newsletter_delivery_safety_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        result = conn.execute(
            f"""
            UPDATE newsletters
            SET status = 'SENDING',
                broadcast_started_at = CURRENT_TIMESTAMP,
                broadcast_finished_at = NULL,
                last_send_error = NULL
            WHERE id = ?
              AND (
                    status IN ('DRAFT', 'PARTIAL', 'SCHEDULED')
                    OR (
                        status = 'SENDING'
                        AND datetime(broadcast_started_at) <= datetime('now', '-{NEWSLETTER_LOCK_TIMEOUT_HOURS} hours')
                    )
                  )
            """,
            (newsletter_id,),
        )
        conn.commit()
        return result.rowcount == 1
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def finalize_newsletter_send(newsletter_id, status, error=None):
    """Release a broadcast reservation with an auditable terminal status."""
    conn = sqlite3.connect(DB_PATH, timeout=RESEND_TIMEOUT_SECONDS)
    try:
        ensure_newsletter_delivery_safety_schema(conn)
        conn.execute(
            """
            UPDATE newsletters
            SET status = ?, broadcast_finished_at = CURRENT_TIMESTAMP, last_send_error = ?
            WHERE id = ? AND status = 'SENDING'
            """,
            (status, (error or "")[:2000] or None, newsletter_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_newsletter_audience_summary(newsletter_id):
    conn = sqlite3.connect(DB_PATH, timeout=RESEND_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    try:
        ensure_newsletter_delivery_safety_schema(conn)
        newsletter = conn.execute(
            "SELECT * FROM newsletters WHERE id = ?",
            (newsletter_id,),
        ).fetchone()
        if not newsletter:
            return None

        active_count = conn.execute(
            "SELECT COUNT(*) FROM subscribers WHERE status = 'ACTIVE'"
        ).fetchone()[0]
        delivered_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM subscribers s
            WHERE s.status = 'ACTIVE'
              AND EXISTS (
                    SELECT 1
                    FROM newsletter_deliveries d
                    WHERE d.newsletter_id = ?
                      AND lower(d.recipient_email) = lower(s.email)
              )
            """,
            (newsletter_id,),
        ).fetchone()[0]
        return {
            "newsletter": dict(newsletter),
            "active_count": active_count,
            "delivered_count": delivered_count,
            "remaining_count": max(active_count - delivered_count, 0),
        }
    finally:
        conn.close()


def _unsubscribe_url(newsletter_id, email):
    token = _tracking_token(newsletter_id, email)
    return f"https://dailyaiwire.news/unsubscribe/{newsletter_id}/{token}"


def _provider_message_id(response):
    try:
        payload = response.json()
    except Exception:
        try:
            payload = json.loads(response.text or "{}")
        except Exception:
            payload = {}
    if isinstance(payload, dict):
        return payload.get("id") or payload.get("message_id")
    return None


def _assert_recipient_isolation(payload, expected_email):
    recipients = payload.get("to")
    has_copy_fields = "cc" in payload or "bcc" in payload
    if has_copy_fields or recipients != [expected_email]:
        raise ValueError(
            "CRITICAL PRIVACY ERROR: Newsletter payload must contain exactly "
            "one matching recipient and no cc or bcc fields."
        )


def _post_private_email(payload, expected_email, idempotency_key=None):
    """Send only after enforcing the subscriber-recipient privacy invariant."""
    _assert_recipient_isolation(payload, expected_email)
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return requests.post(
        RESEND_API_URL,
        headers=headers,
        json=payload,
        timeout=RESEND_TIMEOUT_SECONDS,
    )

def send_welcome_email(recipient_email):
    """Sends a transactional welcome email to a new subscriber."""
    if not RESEND_API_KEY:
        logger.error("❌ ERROR: RESEND_API_KEY missing.")
        return False
        
    logger.info("🚀 Sending welcome email to %s...", recipient_email)
    
    # Simple HTML for the welcome email (inline for reliability if file read fails, or read from file)
    # Ideally reuse template logic, but keep it robust here.
    try:
        from flask import render_template
        from app import app
        with app.app_context():
            html_content = render_template('email/welcome.html')
    except Exception as e:
        logger.warning("⚠️ Template render failed (%s), using fallback HTML.", e)
        html_content = "<h1>Welcome to the Wire.</h1><p>You are subscribed.</p>"

    payload = {
        "from": f"DailyAIWire <{SENDER_EMAIL}>",
        "to": [recipient_email],
        "subject": "Connection Established // DailyAIWire",
        "html": html_content
    }

    try:
        response = _post_private_email(payload, recipient_email)
        if response.status_code in [200, 201]:
            logger.info("✅ Welcome email sent successfully.")
            return True
        else:
            logger.error("❌ Welcome email failed: %s - %s", response.status_code, response.text)
            return False
    except Exception as e:
        logger.error("❌ Network error sending email: %s", e)
        return False


def send_confirmation_email(recipient_email, confirmation_url, *, include_result=False):
    """Send a double opt-in confirmation email before activating a subscriber."""
    def result(accepted, message_id=None):
        if include_result:
            return {"accepted": accepted, "message_id": message_id}
        return accepted

    if not RESEND_API_KEY:
        logger.error("❌ ERROR: RESEND_API_KEY missing.")
        return result(False)

    try:
        from flask import render_template
        from app import app
        with app.app_context():
            html_content = render_template(
                'email/confirmation.html',
                confirmation_url=confirmation_url,
            )
    except Exception as e:
        logger.warning("⚠️ Confirmation template render failed (%s), using fallback HTML.", e)
        safe_url = escape(confirmation_url)
        html_content = f"""
        <h1>Confirm your DailyAIWire subscription</h1>
        <p>Click the link below to confirm that you requested DailyAIWire updates.</p>
        <p><a href="{safe_url}">Confirm subscription</a></p>
        <p>If you did not request this, ignore this email and you will not be added to the active newsletter list.</p>
        """

    payload = {
        "from": f"DailyAIWire <{SENDER_EMAIL}>",
        "to": [recipient_email],
        "subject": "Confirm your DailyAIWire subscription",
        "html": html_content,
    }
    try:
        response = _post_private_email(payload, recipient_email)
        if response.status_code in [200, 201]:
            logger.info("✅ Confirmation email sent successfully.")
            return result(True, _provider_message_id(response))
        logger.error("❌ Confirmation email failed: %s - %s", response.status_code, response.text)
        return result(False)
    except Exception as e:
        logger.error("❌ Network error sending confirmation email: %s", e)
        return result(False)

def get_active_subscribers():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM subscribers WHERE status = 'ACTIVE'")
    subs = [row[0] for row in cursor.fetchall()]
    conn.close()
    return subs

def build_email_html(newsletter_id, template='email/briefing.html', recipient_email=None):
    from flask import render_template
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get newsletter
    cursor.execute("SELECT * FROM newsletters WHERE id = ?", (newsletter_id,))
    nl = cursor.fetchone()
    
    if not nl:
        conn.close()
        return None
        
    article_ids = json.loads(nl['article_ids'])
    articles = []
    if article_ids:
        placeholders = ', '.join(['?'] * len(article_ids))
        cursor.execute(f"SELECT * FROM articles WHERE id IN ({placeholders})", article_ids)
        articles = [dict(row) for row in cursor.fetchall()]
        
    try:
        article_metadata = json.loads(nl['article_metadata']) if nl['article_metadata'] else {}
    except Exception:
        article_metadata = {}
    
    conn.close()

    issue_context = _newsletter_issue_context(nl)
    
    tracking_url = ""
    unsubscribe_url = "https://dailyaiwire.news/unsubscribe"
    if recipient_email:
        token = _tracking_token(newsletter_id, recipient_email)
        tracking_url = f"https://dailyaiwire.news/t/nl/{newsletter_id}/{token}"
        unsubscribe_url = _unsubscribe_url(newsletter_id, recipient_email)
    
    # Render using the requested Jinja2 template
    from app import app
    with app.app_context():
        return render_template(template, 
                               subject=nl['subject'], 
                               intro_text=nl['intro_text'].replace('\n', '<br>'), 
                               articles=articles,
                               article_metadata=article_metadata,
                               newsletter_date_display=issue_context['newsletter_date_display'],
                               newsletter_issue_label=issue_context['newsletter_issue_label'],
                               tracking_pixel_url=tracking_url,
                               unsubscribe_url=unsubscribe_url)

def send_test_newsletter(newsletter_id, recipient_email):
    """Send a private preview without changing broadcast or delivery state."""
    recipient_email = (recipient_email or "").strip().lower()
    if not RESEND_API_KEY or not EMAIL_PATTERN.fullmatch(recipient_email):
        return False

    conn = sqlite3.connect(DB_PATH, timeout=RESEND_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    try:
        newsletter = conn.execute(
            "SELECT subject FROM newsletters WHERE id = ?",
            (newsletter_id,),
        ).fetchone()
    finally:
        conn.close()
    if not newsletter:
        return False

    html_content = build_email_html(newsletter_id)
    if not html_content:
        return False
    payload = {
        "from": f"DailyAIWire <{SENDER_EMAIL}>",
        "to": [recipient_email],
        "subject": f"[TEST] {newsletter['subject']}",
        "html": html_content,
    }
    try:
        response = _post_private_email(payload, recipient_email)
        return response.status_code in (200, 201)
    except Exception as exc:
        logger.error("Test newsletter send failed: %s", exc)
        return False


def send_newsletter(
    newsletter_id,
    is_apology=False,
    reservation_held=False,
    expected_recipient_count=None,
):
    if not RESEND_API_KEY:
        logger.error("ERROR: RESEND_API_KEY not found in environment.")
        if reservation_held:
            finalize_newsletter_send(newsletter_id, "PARTIAL", "RESEND_API_KEY missing")
        return False

    if not reservation_held and not reserve_newsletter_send(newsletter_id):
        logger.warning("Newsletter %d is already sending or is not eligible.", newsletter_id)
        return False

    conn = sqlite3.connect(DB_PATH, timeout=RESEND_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    try:
        ensure_newsletter_delivery_safety_schema(conn)
        newsletter = conn.execute(
            "SELECT * FROM newsletters WHERE id = ? AND status = 'SENDING'",
            (newsletter_id,),
        ).fetchone()
        if not newsletter:
            logger.warning("Newsletter %d has no active send reservation.", newsletter_id)
            return False

        subscribers = get_active_subscribers()
        if not subscribers:
            conn.execute(
                """
                UPDATE newsletters
                SET status = 'PARTIAL', broadcast_finished_at = CURRENT_TIMESTAMP,
                    last_send_error = 'No active subscribers'
                WHERE id = ? AND status = 'SENDING'
                """,
                (newsletter_id,),
            )
            conn.commit()
            return False

        logger.info(
            "Processing broadcast for '%s' to %d active subscribers...",
            newsletter["subject"],
            len(subscribers),
        )
        template = 'email/apology_briefing.html' if is_apology else 'email/briefing.html'
        success_count = 0
        pending_subscribers = []
        for sub_email in subscribers:
            delivered = conn.execute(
                """
                SELECT id FROM newsletter_deliveries
                WHERE newsletter_id = ? AND lower(recipient_email) = lower(?)
                """,
                (newsletter_id, sub_email),
            ).fetchone()
            if not delivered:
                pending_subscribers.append(sub_email)

        if (
            expected_recipient_count is not None
            and len(pending_subscribers) != expected_recipient_count
        ):
            error = (
                "Audience changed after reservation: expected "
                f"{expected_recipient_count}, found {len(pending_subscribers)}"
            )
            conn.execute(
                """
                UPDATE newsletters
                SET status = 'PARTIAL', broadcast_finished_at = CURRENT_TIMESTAMP,
                    last_send_error = ?
                WHERE id = ? AND status = 'SENDING'
                """,
                (error, newsletter_id),
            )
            conn.commit()
            logger.warning("Newsletter %d %s", newsletter_id, error)
            return False

        skip_count = len(subscribers) - len(pending_subscribers)
        fail_count = 0
        errors = []

        for sub_email in pending_subscribers:
            try:
                html_content = build_email_html(
                    newsletter_id,
                    template=template,
                    recipient_email=sub_email,
                )
                unsubscribe_url = _unsubscribe_url(newsletter_id, sub_email)
                payload = {
                    "from": f"DailyAIWire <{SENDER_EMAIL}>",
                    "to": [sub_email],
                    "subject": newsletter["subject"],
                    "html": html_content,
                    "headers": {
                        "List-Unsubscribe": f"<{unsubscribe_url}>",
                        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                    },
                }
                response = _post_private_email(
                    payload,
                    sub_email,
                    idempotency_key=(
                        f"newsletter-{newsletter_id}-"
                        f"{_tracking_token(newsletter_id, sub_email)}"
                    ),
                )
                if response.status_code not in (200, 201):
                    raise RuntimeError(f"Resend returned HTTP {response.status_code}")

                conn.execute(
                    """
                    INSERT INTO newsletter_deliveries (
                        newsletter_id, recipient_email, status, tracking_token,
                        resend_message_id, provider_response
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        newsletter_id,
                        sub_email,
                        "ACCEPTED",
                        _tracking_token(newsletter_id, sub_email),
                        _provider_message_id(response),
                        (response.text or "")[:2000],
                    ),
                )
                conn.commit()
                success_count += 1
            except Exception as exc:
                logger.error("Newsletter delivery failed for %s: %s", sub_email, exc)
                errors.append(str(exc))
                fail_count += 1

            time.sleep(2.0)

        final_status = "SENT" if fail_count == 0 else "PARTIAL"
        error_summary = "; ".join(errors[:5])[:2000] if errors else None
        conn.execute(
            """
            UPDATE newsletters
            SET status = ?, broadcast_finished_at = CURRENT_TIMESTAMP, last_send_error = ?
            WHERE id = ? AND status = 'SENDING'
            """,
            (final_status, error_summary, newsletter_id),
        )
        conn.commit()
        logger.info(
            "Broadcast complete. Sent: %d | Skipped: %d | Failed: %d | Status: %s",
            success_count,
            skip_count,
            fail_count,
            final_status,
        )
        return True
    except Exception as exc:
        conn.rollback()
        logger.exception("Fatal newsletter broadcast error for id=%s", newsletter_id)
        try:
            conn.execute(
                """
                UPDATE newsletters
                SET status = 'PARTIAL', broadcast_finished_at = CURRENT_TIMESTAMP,
                    last_send_error = ?
                WHERE id = ? AND status = 'SENDING'
                """,
                (str(exc)[:2000], newsletter_id),
            )
            conn.commit()
        except Exception:
            logger.exception("Could not release newsletter reservation for id=%s", newsletter_id)
        return False
    finally:
        conn.close()
