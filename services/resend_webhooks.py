"""Verified, idempotent processing for Resend newsletter events."""

import logging
import sqlite3
from typing import Any, Mapping

from svix.webhooks import Webhook

from db import get_db_connection
from services.subscribers import ensure_subscribers_schema, record_subscriber_event


logger = logging.getLogger("resend_webhooks")

RESEND_WEBHOOK_TRACKING_STARTED_AT = "2026-07-22 20:27:10"
DELIVERY_EVENT_COLUMNS = {
    "email.sent": ("SENT", "sent_at"),
    "email.delivery_delayed": ("DELAYED", "delayed_at"),
    "email.delivered": ("DELIVERED", "delivered_at"),
    "email.bounced": ("BOUNCED", "bounced_at"),
    "email.complained": ("COMPLAINED", "complained_at"),
    "email.failed": ("FAILED", "failed_at"),
    "email.suppressed": ("SUPPRESSED", "suppressed_at"),
}
STATUS_RANK = {
    "ACCEPTED": 10,
    "SENT": 20,
    "DELAYED": 25,
    "DELIVERED": 30,
    "FAILED": 40,
    "SUPPRESSED": 50,
    "BOUNCED": 60,
    "COMPLAINED": 70,
}
SUPPRESSING_STATUSES = {"BOUNCED", "COMPLAINED", "SUPPRESSED"}


def ensure_resend_webhook_schema(conn: sqlite3.Connection) -> None:
    """Add provider state fields without storing complete webhook payloads."""
    ensure_subscribers_schema(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS newsletter_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            newsletter_id INTEGER,
            recipient_email TEXT,
            status TEXT,
            tracking_token TEXT,
            opened_at TIMESTAMP,
            resend_message_id TEXT,
            provider_response TEXT
        )
        """
    )
    delivery_columns = {
        row["name"] if hasattr(row, "keys") else row[1]
        for row in conn.execute("PRAGMA table_info(newsletter_deliveries)").fetchall()
    }
    migrations = {
        "sent_at": "ALTER TABLE newsletter_deliveries ADD COLUMN sent_at TIMESTAMP",
        "delivered_at": "ALTER TABLE newsletter_deliveries ADD COLUMN delivered_at TIMESTAMP",
        "delayed_at": "ALTER TABLE newsletter_deliveries ADD COLUMN delayed_at TIMESTAMP",
        "clicked_at": "ALTER TABLE newsletter_deliveries ADD COLUMN clicked_at TIMESTAMP",
        "bounced_at": "ALTER TABLE newsletter_deliveries ADD COLUMN bounced_at TIMESTAMP",
        "complained_at": "ALTER TABLE newsletter_deliveries ADD COLUMN complained_at TIMESTAMP",
        "failed_at": "ALTER TABLE newsletter_deliveries ADD COLUMN failed_at TIMESTAMP",
        "suppressed_at": "ALTER TABLE newsletter_deliveries ADD COLUMN suppressed_at TIMESTAMP",
        "last_event_at": "ALTER TABLE newsletter_deliveries ADD COLUMN last_event_at TIMESTAMP",
        "last_event_type": "ALTER TABLE newsletter_deliveries ADD COLUMN last_event_type TEXT",
        "bounce_type": "ALTER TABLE newsletter_deliveries ADD COLUMN bounce_type TEXT",
        "unsubscribed_at": "ALTER TABLE newsletter_deliveries ADD COLUMN unsubscribed_at TIMESTAMP",
    }
    for column, ddl in migrations.items():
        if column not in delivery_columns:
            conn.execute(ddl)

    # Legacy rows recorded API acceptance as delivery. An observed open proves
    # delivery; all other legacy rows become ACCEPTED until a provider event arrives.
    conn.execute(
        """
        UPDATE newsletter_deliveries
        SET status = 'DELIVERED', delivered_at = COALESCE(delivered_at, opened_at)
        WHERE status = 'OPENED' AND opened_at IS NOT NULL
        """
    )
    conn.execute(
        """
        UPDATE newsletter_deliveries
        SET delivered_at = COALESCE(delivered_at, opened_at)
        WHERE status = 'DELIVERED' AND opened_at IS NOT NULL
        """
    )
    conn.execute(
        """
        UPDATE newsletter_deliveries
        SET status = 'ACCEPTED'
        WHERE status = 'DELIVERED'
          AND delivered_at IS NULL
          AND last_event_type IS NULL
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS newsletter_provider_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            resend_message_id TEXT,
            matched_delivery_id INTEGER,
            processing_result TEXT NOT NULL,
            event_created_at TIMESTAMP,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    provider_event_columns = {
        row["name"] if hasattr(row, "keys") else row[1]
        for row in conn.execute("PRAGMA table_info(newsletter_provider_events)").fetchall()
    }
    if "matched_confirmation_delivery_id" not in provider_event_columns:
        conn.execute(
            """
            ALTER TABLE newsletter_provider_events
            ADD COLUMN matched_confirmation_delivery_id INTEGER
            """
        )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS confirmation_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscriber_id INTEGER NOT NULL,
            resend_message_id TEXT,
            status TEXT NOT NULL DEFAULT 'ACCEPTED',
            placement TEXT,
            accepted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sent_at TIMESTAMP,
            delivered_at TIMESTAMP,
            delayed_at TIMESTAMP,
            opened_at TIMESTAMP,
            clicked_at TIMESTAMP,
            bounced_at TIMESTAMP,
            complained_at TIMESTAMP,
            failed_at TIMESTAMP,
            suppressed_at TIMESTAMP,
            last_event_at TIMESTAMP,
            last_event_type TEXT,
            bounce_type TEXT,
            FOREIGN KEY (subscriber_id) REFERENCES subscribers(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_newsletter_delivery_resend_message
        ON newsletter_deliveries (resend_message_id)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_confirmation_delivery_resend_message
        ON confirmation_deliveries (resend_message_id)
        WHERE resend_message_id IS NOT NULL
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_confirmation_delivery_subscriber
        ON confirmation_deliveries (subscriber_id, accepted_at)
        """
    )
    conn.commit()


def record_confirmation_delivery(
    conn: sqlite3.Connection,
    *,
    subscriber_id: int,
    resend_message_id: str | None,
    placement: str,
) -> None:
    """Persist provider acceptance without storing recipient or payload copies."""
    ensure_resend_webhook_schema(conn)
    conn.execute(
        """
        INSERT INTO confirmation_deliveries (
            subscriber_id, resend_message_id, status, placement
        ) VALUES (?, ?, 'ACCEPTED', ?)
        """,
        (subscriber_id, resend_message_id or None, placement),
    )


def verify_resend_webhook(
    raw_body: bytes,
    headers: Mapping[str, str],
    webhook_secret: str,
) -> dict[str, Any]:
    """Verify timestamp and signature using Resend's Svix protocol."""
    verified = Webhook(webhook_secret).verify(raw_body, dict(headers))
    if not isinstance(verified, dict):
        raise ValueError("Webhook payload must be a JSON object")
    return verified


def _event_time(payload: Mapping[str, Any]) -> str | None:
    value = payload.get("created_at")
    return str(value)[:64] if value else None


def _record_provider_suppression(
    conn: sqlite3.Connection,
    recipient_email: str,
    subscriber_status: str,
    reason: str,
) -> None:
    result = conn.execute(
        """
        UPDATE subscribers
        SET status = ?, confirmation_token_hash = NULL
        WHERE lower(email) = lower(?) AND status = 'ACTIVE'
        """,
        (subscriber_status, recipient_email),
    )
    if result.rowcount:
        record_subscriber_event(
            conn,
            email=recipient_email,
            event_type="provider_suppressed",
            reason=reason,
            ip_hash=None,
            user_agent="resend-webhook",
            referrer="",
            source_path="/api/webhooks/resend",
            placement="provider",
        )


def _record_confirmation_suppression(
    conn: sqlite3.Connection,
    *,
    subscriber_id: int,
    recipient_email: str,
    subscriber_status: str,
    reason: str,
    placement: str,
) -> None:
    result = conn.execute(
        """
        UPDATE subscribers
        SET status = ?, confirmation_token_hash = NULL
        WHERE id = ? AND status IN ('PENDING', 'ACTIVE')
        """,
        (subscriber_status, subscriber_id),
    )
    if result.rowcount:
        record_subscriber_event(
            conn,
            email=recipient_email,
            event_type="provider_suppressed",
            reason=reason,
            ip_hash=None,
            user_agent="resend-webhook",
            referrer="",
            source_path="/api/webhooks/resend",
            placement=placement or "unknown",
        )


def _process_confirmation_delivery_event(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    event_type: str,
    data: Mapping[str, Any],
    event_time: str | None,
    delivery,
) -> dict[str, Any]:
    delivery_id = delivery["id"]
    current_status = delivery["status"] or "ACCEPTED"
    processing_result = "PROCESSED"

    if event_type == "email.opened":
        conn.execute(
            """
            UPDATE confirmation_deliveries
            SET opened_at = COALESCE(opened_at, ?),
                last_event_at = ?, last_event_type = ?
            WHERE id = ?
            """,
            (event_time, event_time, event_type, delivery_id),
        )
    elif event_type == "email.clicked":
        conn.execute(
            """
            UPDATE confirmation_deliveries
            SET clicked_at = COALESCE(clicked_at, ?),
                last_event_at = ?, last_event_type = ?
            WHERE id = ?
            """,
            (event_time, event_time, event_type, delivery_id),
        )
    elif event_type in DELIVERY_EVENT_COLUMNS:
        new_status, timestamp_column = DELIVERY_EVENT_COLUMNS[event_type]
        bounce_type = None
        if event_type == "email.bounced":
            bounce = data.get("bounce")
            if isinstance(bounce, Mapping):
                bounce_type = str(bounce.get("type") or "")[:40] or None
            if bounce_type != "Permanent":
                new_status = "DELAYED"

        status_to_store = current_status
        if STATUS_RANK.get(new_status, 0) >= STATUS_RANK.get(current_status, 0):
            status_to_store = new_status
        delivered_evidence_time = (
            event_time
            if event_type in {"email.delivered", "email.complained"}
            else None
        )
        conn.execute(
            f"""
            UPDATE confirmation_deliveries
            SET status = ?,
                {timestamp_column} = COALESCE({timestamp_column}, ?),
                delivered_at = COALESCE(delivered_at, ?),
                last_event_at = ?, last_event_type = ?,
                bounce_type = COALESCE(?, bounce_type)
            WHERE id = ?
            """,
            (
                status_to_store,
                event_time,
                delivered_evidence_time,
                event_time,
                event_type,
                bounce_type,
                delivery_id,
            ),
        )

        should_suppress = (
            event_type == "email.complained"
            or event_type == "email.suppressed"
            or (event_type == "email.bounced" and bounce_type == "Permanent")
        )
        if should_suppress:
            _record_confirmation_suppression(
                conn,
                subscriber_id=delivery["subscriber_id"],
                recipient_email=delivery["recipient_email"],
                subscriber_status=new_status,
                reason=f"resend_confirmation_{event_type.removeprefix('email.').replace('.', '_')}",
                placement=delivery["placement"],
            )

        if event_type == "email.delivered":
            record_subscriber_event(
                conn,
                email=delivery["recipient_email"],
                event_type="confirmation_delivered",
                reason="resend_delivered",
                ip_hash=None,
                user_agent="resend-webhook",
                referrer="",
                source_path="/api/webhooks/resend",
                placement=delivery["placement"] or "unknown",
            )
        elif event_type == "email.failed":
            record_subscriber_event(
                conn,
                email=delivery["recipient_email"],
                event_type="confirmation_delivery_failed",
                reason="resend_failed",
                ip_hash=None,
                user_agent="resend-webhook",
                referrer="",
                source_path="/api/webhooks/resend",
                placement=delivery["placement"] or "unknown",
            )
    else:
        processing_result = "IGNORED_UNSUPPORTED"

    conn.execute(
        """
        UPDATE newsletter_provider_events
        SET matched_confirmation_delivery_id = ?, processing_result = ?
        WHERE event_id = ?
        """,
        (delivery_id, processing_result, event_id[:255]),
    )
    conn.commit()
    return {"duplicate": False, "matched": True}
def _log_abnormal_failure_rate(conn: sqlite3.Connection, newsletter_id: int) -> None:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status IN ('BOUNCED', 'COMPLAINED', 'FAILED', 'SUPPRESSED')
                     THEN 1 ELSE 0 END) AS failures
        FROM newsletter_deliveries
        WHERE newsletter_id = ?
        """,
        (newsletter_id,),
    ).fetchone()
    total = int(row["total"] or 0)
    failures = int(row["failures"] or 0)
    if total >= 5 and failures >= 3 and failures / total >= 0.20:
        logger.critical(
            "Newsletter %s has abnormal provider failures: %s/%s",
            newsletter_id,
            failures,
            total,
        )


def process_resend_event(event_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Persist one verified provider event and apply it at most once."""
    event_type = str(payload.get("type") or "")[:80]
    data = payload.get("data")
    if not event_id or not event_type or not isinstance(data, Mapping):
        raise ValueError("Invalid Resend webhook event")

    resend_message_id = str(data.get("email_id") or "")[:255]
    event_time = _event_time(payload)
    conn = get_db_connection()
    try:
        ensure_resend_webhook_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        inserted = conn.execute(
            """
            INSERT OR IGNORE INTO newsletter_provider_events (
                event_id, event_type, resend_message_id, processing_result,
                event_created_at
            ) VALUES (?, ?, ?, 'RECEIVED', ?)
            """,
            (event_id[:255], event_type, resend_message_id or None, event_time),
        )
        if inserted.rowcount == 0:
            conn.rollback()
            return {"duplicate": True, "matched": False}

        delivery = None
        if resend_message_id:
            delivery = conn.execute(
                """
                SELECT id, newsletter_id, recipient_email, status
                FROM newsletter_deliveries
                WHERE resend_message_id = ?
                LIMIT 1
                """,
                (resend_message_id,),
            ).fetchone()

        confirmation_delivery = None
        if resend_message_id and not delivery:
            confirmation_delivery = conn.execute(
                """
                SELECT c.id, c.subscriber_id, c.status, c.placement, s.email
                    AS recipient_email
                FROM confirmation_deliveries c
                JOIN subscribers s ON s.id = c.subscriber_id
                WHERE c.resend_message_id = ?
                LIMIT 1
                """,
                (resend_message_id,),
            ).fetchone()

        if not delivery and not confirmation_delivery:
            conn.execute(
                """
                UPDATE newsletter_provider_events
                SET processing_result = 'UNMATCHED'
                WHERE event_id = ?
                """,
                (event_id[:255],),
            )
            conn.commit()
            logger.warning(
                "Verified Resend event %s had no matching newsletter delivery",
                event_type,
            )
            return {"duplicate": False, "matched": False}

        if confirmation_delivery:
            return _process_confirmation_delivery_event(
                conn,
                event_id=event_id,
                event_type=event_type,
                data=data,
                event_time=event_time,
                delivery=confirmation_delivery,
            )

        delivery_id = delivery["id"]
        current_status = delivery["status"] or "ACCEPTED"
        processing_result = "PROCESSED"

        if event_type == "email.opened":
            conn.execute(
                """
                UPDATE newsletter_deliveries
                SET opened_at = COALESCE(opened_at, ?),
                    last_event_at = ?, last_event_type = ?
                WHERE id = ?
                """,
                (event_time, event_time, event_type, delivery_id),
            )
        elif event_type == "email.clicked":
            conn.execute(
                """
                UPDATE newsletter_deliveries
                SET clicked_at = COALESCE(clicked_at, ?),
                    last_event_at = ?, last_event_type = ?
                WHERE id = ?
                """,
                (event_time, event_time, event_type, delivery_id),
            )
        elif event_type in DELIVERY_EVENT_COLUMNS:
            new_status, timestamp_column = DELIVERY_EVENT_COLUMNS[event_type]
            bounce_type = None
            if event_type == "email.bounced":
                bounce = data.get("bounce")
                if isinstance(bounce, Mapping):
                    bounce_type = str(bounce.get("type") or "")[:40] or None
                if bounce_type != "Permanent":
                    new_status = "DELAYED"

            status_to_store = current_status
            if STATUS_RANK.get(new_status, 0) >= STATUS_RANK.get(current_status, 0):
                status_to_store = new_status
            delivered_evidence_time = (
                event_time
                if event_type in {"email.delivered", "email.complained"}
                else None
            )

            conn.execute(
                f"""
                UPDATE newsletter_deliveries
                SET status = ?,
                    {timestamp_column} = COALESCE({timestamp_column}, ?),
                    delivered_at = COALESCE(delivered_at, ?),
                    last_event_at = ?, last_event_type = ?,
                    bounce_type = COALESCE(?, bounce_type)
                WHERE id = ?
                """,
                (
                    status_to_store,
                    event_time,
                    delivered_evidence_time,
                    event_time,
                    event_type,
                    bounce_type,
                    delivery_id,
                ),
            )

            should_suppress = (
                event_type == "email.complained"
                or event_type == "email.suppressed"
                or (event_type == "email.bounced" and bounce_type == "Permanent")
            )
            if should_suppress:
                _record_provider_suppression(
                    conn,
                    delivery["recipient_email"],
                    new_status,
                    f"resend_{event_type.removeprefix('email.').replace('.', '_')}",
                )
        else:
            processing_result = "IGNORED_UNSUPPORTED"

        conn.execute(
            """
            UPDATE newsletter_provider_events
            SET matched_delivery_id = ?, processing_result = ?
            WHERE event_id = ?
            """,
            (delivery_id, processing_result, event_id[:255]),
        )
        _log_abnormal_failure_rate(conn, delivery["newsletter_id"])
        conn.commit()
        return {"duplicate": False, "matched": True}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
