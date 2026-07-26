"""
Newsletter subscriber persistence helpers.

Keeps signup confirmation, audit metadata, and abuse events consistent across
public and admin flows.
"""
import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import parse_qs, urlsplit


SUBSCRIBE_PLACEMENTS = frozenset({
    "article_inline",
    "article_sidebar",
    "homepage_inline",
    "signal_archive",
    "signal_issue",
    "site_modal",
    "subscribe_page",
})
SUBSCRIBE_PLACEMENT_LABELS = {
    "homepage_inline": "Homepage inline",
    "article_inline": "Article inline",
    "article_sidebar": "Article sidebar",
    "site_modal": "Site modal",
    "subscribe_page": "Subscribe page",
    "signal_archive": "Signal archive",
    "signal_issue": "Signal issue",
    "unknown": "Unknown",
}
FUNNEL_PERIODS = (7, 30, 90)
CONFIRMED_SUBSCRIBER_STATUSES = frozenset({
    "ACTIVE",
    "UNSUBSCRIBED",
    "BOUNCED",
    "COMPLAINED",
    "SUPPRESSED",
})
CHANNEL_LABELS = {
    "linkedin": "LinkedIn",
    "google_search": "Google Search",
    "newsletter_email": "Newsletter / Email",
    "x_twitter": "X / Twitter",
    "internal": "Internal navigation",
    "other_referral": "Other referral",
    "other_campaign": "Other campaign",
    "direct_unattributed": "Direct / Unattributed",
}


def hash_value(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def normalize_subscribe_placement(value: str) -> str:
    placement = (value or "").strip().lower()[:50]
    return placement if placement in SUBSCRIBE_PLACEMENTS else "unknown"


def _normalized_hostname(url: str) -> str:
    try:
        return (urlsplit(url or "").hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def classify_subscriber_channel(source_path: str, referrer: str) -> tuple[str, str]:
    """Classify acquisition using explicit campaign data before referrer evidence."""
    try:
        query = parse_qs(urlsplit(source_path or "").query)
    except ValueError:
        query = {}

    source = (query.get("utm_source") or [""])[0].strip().lower()
    medium = (query.get("utm_medium") or [""])[0].strip().lower()
    campaign_value = f"{source} {medium}"

    if "email" in medium or "newsletter" in medium or any(
        token in campaign_value for token in ("newsletter", "weekly_signal", "convertkit")
    ):
        channel = "newsletter_email"
    elif any(token in source for token in ("linkedin", "lnkd")):
        channel = "linkedin"
    elif source in {"google", "google_search", "google-search"}:
        channel = "google_search"
    elif source in {"x", "twitter", "t.co"}:
        channel = "x_twitter"
    elif source or medium:
        channel = "other_campaign"
    else:
        hostname = _normalized_hostname(referrer)
        if hostname == "linkedin.com" or hostname.endswith(".linkedin.com") or hostname == "lnkd.in":
            channel = "linkedin"
        elif hostname in {"mail.google.com", "outlook.live.com"}:
            channel = "newsletter_email"
        elif hostname == "google.com" or hostname.startswith("google.") or ".google." in hostname:
            channel = "google_search"
        elif hostname in {"x.com", "twitter.com", "t.co"} or hostname.endswith(
            (".x.com", ".twitter.com")
        ):
            channel = "x_twitter"
        elif hostname == "dailyaiwire.news" or hostname.endswith(".dailyaiwire.news"):
            channel = "internal"
        elif hostname:
            channel = "other_referral"
        else:
            channel = "direct_unattributed"

    return channel, CHANNEL_LABELS[channel]


def _subscriber_is_confirmed(row: Any) -> bool:
    return bool(
        _row_value(row, "confirmed_at", 5)
        or _row_value(row, "status", 1) in CONFIRMED_SUBSCRIBER_STATUSES
    )


def _subscriber_confirmation_counts(row: Any) -> tuple[int, int, int]:
    explicit_confirmed = int(bool(_row_value(row, "confirmed_at", 5)))
    activated = int(_subscriber_is_confirmed(row))
    legacy_activated = int(activated and not explicit_confirmed)
    return activated, explicit_confirmed, legacy_activated


def _landing_page(source_path: str) -> tuple[str, str]:
    try:
        path = urlsplit(source_path or "").path
    except ValueError:
        path = ""
    if not path.startswith("/"):
        path = "/"
    path = path[:160] or "/"
    return path, "Homepage" if path == "/" else path


def _week_start(created_at: Any) -> str:
    try:
        parsed = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        parsed = datetime.utcnow()
    return (parsed.date() - timedelta(days=parsed.weekday())).isoformat()


def get_subscriber_acquisition(conn: sqlite3.Connection, days: int = 30) -> dict:
    """Aggregate privacy-safe signup attribution from existing subscriber metadata."""
    if days not in FUNNEL_PERIODS:
        days = 30
    ensure_subscribers_schema(conn)
    rows = conn.execute(
        """
        SELECT signup_source_path, signup_referrer, signup_placement, created_at,
               status, confirmed_at
        FROM subscribers
        WHERE datetime(created_at) >= datetime('now', ?)
        ORDER BY datetime(created_at) ASC
        """,
        (f"-{days} days",),
    ).fetchall()

    channel_totals = {}
    landing_totals = {}
    weekly_totals = {}
    total_confirmed = 0
    total_explicit_confirmed = 0
    total_legacy_activated = 0

    for row in rows:
        source_path = _row_value(row, "signup_source_path", 0) or ""
        referrer = _row_value(row, "signup_referrer", 1) or ""
        channel, label = classify_subscriber_channel(source_path, referrer)
        landing_path, landing_label = _landing_page(source_path)
        week = _week_start(_row_value(row, "created_at", 3))
        confirmed, explicit_confirmed, legacy_activated = _subscriber_confirmation_counts(row)
        total_confirmed += int(confirmed)
        total_explicit_confirmed += explicit_confirmed
        total_legacy_activated += legacy_activated

        channel_row = channel_totals.setdefault(
            channel,
            {
                "channel": channel,
                "label": label,
                "signups": 0,
                "confirmed": 0,
                "explicit_confirmed": 0,
                "legacy_activated": 0,
            },
        )
        channel_row["signups"] += 1
        channel_row["confirmed"] += int(confirmed)
        channel_row["explicit_confirmed"] += explicit_confirmed
        channel_row["legacy_activated"] += legacy_activated

        landing_row = landing_totals.setdefault(
            landing_path,
            {
                "path": landing_path,
                "label": landing_label,
                "signups": 0,
                "confirmed": 0,
                "explicit_confirmed": 0,
                "legacy_activated": 0,
            },
        )
        landing_row["signups"] += 1
        landing_row["confirmed"] += int(confirmed)
        landing_row["explicit_confirmed"] += explicit_confirmed
        landing_row["legacy_activated"] += legacy_activated

        week_row = weekly_totals.setdefault(
            week,
            {
                "week_start": week,
                "signups": 0,
                "confirmed": 0,
                "explicit_confirmed": 0,
                "legacy_activated": 0,
            },
        )
        week_row["signups"] += 1
        week_row["confirmed"] += int(confirmed)
        week_row["explicit_confirmed"] += explicit_confirmed
        week_row["legacy_activated"] += legacy_activated

    channels = sorted(
        channel_totals.values(),
        key=lambda item: (-item["confirmed"], -item["signups"], item["label"]),
    )
    for row in channels:
        row["confirmed_share"] = _conversion_rate(row["confirmed"], total_confirmed)

    landing_pages = sorted(
        landing_totals.values(),
        key=lambda item: (-item["confirmed"], -item["signups"], item["path"]),
    )[:10]

    return {
        "days": days,
        "channels": channels,
        "landing_pages": landing_pages,
        "weeks": sorted(weekly_totals.values(), key=lambda item: item["week_start"]),
        "summary": {
            "signups": len(rows),
            "confirmed": total_confirmed,
            "explicit_confirmed": total_explicit_confirmed,
            "legacy_activated": total_legacy_activated,
        },
    }


def ensure_subscribers_schema(conn: sqlite3.Connection) -> None:
    conn.execute('''
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            status TEXT DEFAULT 'ACTIVE',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    existing = set()
    for row in conn.execute("PRAGMA table_info(subscribers)").fetchall():
        existing.add(row["name"] if hasattr(row, "keys") else row[1])
    migrations = {
        "signup_ip_hash": "ALTER TABLE subscribers ADD COLUMN signup_ip_hash TEXT",
        "signup_user_agent": "ALTER TABLE subscribers ADD COLUMN signup_user_agent TEXT",
        "signup_referrer": "ALTER TABLE subscribers ADD COLUMN signup_referrer TEXT",
        "signup_source_path": "ALTER TABLE subscribers ADD COLUMN signup_source_path TEXT",
        "signup_placement": "ALTER TABLE subscribers ADD COLUMN signup_placement TEXT",
        "signup_accept_language": "ALTER TABLE subscribers ADD COLUMN signup_accept_language TEXT",
        "signup_fingerprint_hash": "ALTER TABLE subscribers ADD COLUMN signup_fingerprint_hash TEXT",
        "confirmation_token_hash": "ALTER TABLE subscribers ADD COLUMN confirmation_token_hash TEXT",
        "confirmed_at": "ALTER TABLE subscribers ADD COLUMN confirmed_at TIMESTAMP",
    }
    for column, sql in migrations.items():
        if column not in existing:
            conn.execute(sql)


def ensure_subscriber_events_schema(conn: sqlite3.Connection) -> None:
    conn.execute('''
        CREATE TABLE IF NOT EXISTS subscriber_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_hash TEXT,
            event_type TEXT NOT NULL,
            reason TEXT,
            ip_hash TEXT,
            user_agent TEXT,
            referrer TEXT,
            source_path TEXT,
            placement TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    existing = {
        row["name"] if hasattr(row, "keys") else row[1]
        for row in conn.execute("PRAGMA table_info(subscriber_events)").fetchall()
    }
    if "placement" not in existing:
        conn.execute("ALTER TABLE subscriber_events ADD COLUMN placement TEXT")


def record_subscriber_event(
    conn: sqlite3.Connection,
    *,
    email: str,
    event_type: str,
    reason: str,
    ip_hash: Optional[str],
    user_agent: str,
    referrer: str,
    source_path: str,
    placement: str = "unknown",
) -> None:
    ensure_subscriber_events_schema(conn)
    conn.execute(
        '''
        INSERT INTO subscriber_events (
            email_hash, event_type, reason, ip_hash, user_agent, referrer, source_path,
            placement
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            hash_value(normalize_email(email)) if email else None,
            event_type,
            reason,
            ip_hash,
            user_agent,
            referrer,
            source_path,
            placement,
        ),
    )


def _row_value(row: Any, key: str, index: int) -> Any:
    if hasattr(row, "keys"):
        return row[key]
    return row[index]


def _conversion_rate(numerator: int, denominator: int) -> float:
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def get_subscriber_funnel(conn: sqlite3.Connection, days: int = 30) -> dict:
    """Return anonymous form views and signup-cohort conversion metrics."""
    if days not in FUNNEL_PERIODS:
        days = 30

    ensure_subscribers_schema(conn)
    ensure_subscriber_events_schema(conn)
    window = f"-{days} days"
    tracking_row = conn.execute(
        "SELECT MIN(created_at) AS started_at FROM subscriber_events WHERE event_type = 'form_view'"
    ).fetchone()
    tracking_started_at = _row_value(tracking_row, "started_at", 0) if tracking_row else None

    views_by_placement = {}
    for row in conn.execute(
        '''
        SELECT COALESCE(NULLIF(placement, ''), 'unknown') AS placement,
               COUNT(*) AS count
        FROM subscriber_events
        WHERE event_type = 'form_view'
          AND datetime(created_at) >= datetime('now', ?)
        GROUP BY COALESCE(NULLIF(placement, ''), 'unknown')
        ''',
        (window,),
    ).fetchall():
        views_by_placement[_row_value(row, "placement", 0)] = int(
            _row_value(row, "count", 1)
        )

    submissions_by_placement = {}
    for row in conn.execute(
        '''
        SELECT COALESCE(NULLIF(placement, ''), 'unknown') AS placement,
               COUNT(*) AS count
        FROM subscriber_events
        WHERE event_type = 'qualified_submit'
          AND datetime(created_at) >= datetime('now', ?)
        GROUP BY COALESCE(NULLIF(placement, ''), 'unknown')
        ''',
        (window,),
    ).fetchall():
        submissions_by_placement[_row_value(row, "placement", 0)] = int(
            _row_value(row, "count", 1)
        )

    blocked_by_placement = {}
    for row in conn.execute(
        '''
        SELECT COALESCE(NULLIF(placement, ''), 'unknown') AS placement,
               COUNT(*) AS count
        FROM subscriber_events
        WHERE event_type = 'blocked'
          AND datetime(created_at) >= datetime('now', ?)
        GROUP BY COALESCE(NULLIF(placement, ''), 'unknown')
        ''',
        (window,),
    ).fetchall():
        blocked_by_placement[_row_value(row, "placement", 0)] = int(
            _row_value(row, "count", 1)
        )

    confirmation_by_placement = {}
    for row in conn.execute(
        '''
        SELECT COALESCE(NULLIF(placement, ''), 'unknown') AS placement,
               SUM(CASE WHEN event_type = 'confirmation_sent' THEN 1 ELSE 0 END)
                   AS confirmation_sent,
               SUM(CASE WHEN event_type = 'confirmation_failed' THEN 1 ELSE 0 END)
                   AS confirmation_failed
        FROM subscriber_events
        WHERE event_type IN ('confirmation_sent', 'confirmation_failed')
          AND datetime(created_at) >= datetime('now', ?)
        GROUP BY COALESCE(NULLIF(placement, ''), 'unknown')
        ''',
        (window,),
    ).fetchall():
        confirmation_by_placement[_row_value(row, "placement", 0)] = {
            "confirmation_sent": int(
                _row_value(row, "confirmation_sent", 1) or 0
            ),
            "confirmation_failed": int(
                _row_value(row, "confirmation_failed", 2) or 0
            ),
        }

    signup_by_placement = {}
    for row in conn.execute(
        '''
        SELECT COALESCE(NULLIF(signup_placement, ''), 'unknown') AS placement,
               COUNT(*) AS signups,
               SUM(
                   CASE
                       WHEN confirmed_at IS NOT NULL
                         OR status IN (
                             'ACTIVE', 'UNSUBSCRIBED', 'BOUNCED',
                             'COMPLAINED', 'SUPPRESSED'
                         )
                       THEN 1
                       ELSE 0
                   END
               ) AS confirmed,
               SUM(CASE WHEN confirmed_at IS NOT NULL THEN 1 ELSE 0 END)
                   AS explicit_confirmed,
               SUM(
                   CASE
                       WHEN confirmed_at IS NULL
                         AND status IN (
                             'ACTIVE', 'UNSUBSCRIBED', 'BOUNCED',
                             'COMPLAINED', 'SUPPRESSED'
                         )
                       THEN 1
                       ELSE 0
                   END
               ) AS legacy_activated,
               SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) AS pending
        FROM subscribers
        WHERE datetime(created_at) >= datetime('now', ?)
        GROUP BY COALESCE(NULLIF(signup_placement, ''), 'unknown')
        ''',
        (window,),
    ).fetchall():
        signup_by_placement[_row_value(row, "placement", 0)] = {
            "signups": int(_row_value(row, "signups", 1)),
            "confirmed": int(_row_value(row, "confirmed", 2) or 0),
            "explicit_confirmed": int(
                _row_value(row, "explicit_confirmed", 3) or 0
            ),
            "legacy_activated": int(
                _row_value(row, "legacy_activated", 4) or 0
            ),
            "pending": int(_row_value(row, "pending", 5) or 0),
        }

    tracked_confirmed_by_placement = {}
    if tracking_started_at:
        for row in conn.execute(
            '''
            SELECT COALESCE(NULLIF(signup_placement, ''), 'unknown') AS placement,
                   SUM(CASE WHEN confirmed_at IS NOT NULL THEN 1 ELSE 0 END)
                       AS confirmed
            FROM subscribers
            WHERE datetime(created_at) >= datetime('now', ?)
              AND datetime(created_at) >= datetime(?)
            GROUP BY COALESCE(NULLIF(signup_placement, ''), 'unknown')
            ''',
            (window, tracking_started_at),
        ).fetchall():
            tracked_confirmed_by_placement[_row_value(row, "placement", 0)] = int(
                _row_value(row, "confirmed", 1) or 0
            )

    confirmation_delivery = {
        "tracked": 0,
        "delivered": 0,
        "webhook_pending": 0,
        "delayed": 0,
        "issues": 0,
    }
    confirmation_table = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = 'confirmation_deliveries'
        LIMIT 1
        """
    ).fetchone()
    if confirmation_table:
        row = conn.execute(
            """
            SELECT COUNT(*) AS tracked,
                   SUM(CASE WHEN delivered_at IS NOT NULL THEN 1 ELSE 0 END)
                       AS delivered,
                   SUM(CASE WHEN status IN ('ACCEPTED', 'SENT') THEN 1 ELSE 0 END)
                       AS webhook_pending,
                   SUM(CASE WHEN status = 'DELAYED' THEN 1 ELSE 0 END)
                       AS delayed,
                   SUM(
                       CASE
                           WHEN status IN (
                               'FAILED', 'BOUNCED', 'COMPLAINED', 'SUPPRESSED'
                           )
                           THEN 1
                           ELSE 0
                       END
                   ) AS issues
            FROM confirmation_deliveries
            WHERE datetime(accepted_at) >= datetime('now', ?)
            """,
            (window,),
        ).fetchone()
        confirmation_delivery = {
            "tracked": int(_row_value(row, "tracked", 0) or 0),
            "delivered": int(_row_value(row, "delivered", 1) or 0),
            "webhook_pending": int(_row_value(row, "webhook_pending", 2) or 0),
            "delayed": int(_row_value(row, "delayed", 3) or 0),
            "issues": int(_row_value(row, "issues", 4) or 0),
        }

    discovered = (
        set(views_by_placement)
        | set(submissions_by_placement)
        | set(blocked_by_placement)
        | set(confirmation_by_placement)
        | set(signup_by_placement)
    )
    ordered_placements = [
        placement
        for placement in SUBSCRIBE_PLACEMENT_LABELS
        if placement in discovered
    ]
    ordered_placements.extend(sorted(discovered - set(ordered_placements)))

    placements = []
    for placement in ordered_placements:
        views = views_by_placement.get(placement, 0)
        qualified_submissions = submissions_by_placement.get(placement, 0)
        signups = signup_by_placement.get(placement, {}).get("signups", 0)
        confirmed = signup_by_placement.get(placement, {}).get("confirmed", 0)
        explicit_confirmed = signup_by_placement.get(placement, {}).get(
            "explicit_confirmed",
            0,
        )
        legacy_activated = signup_by_placement.get(placement, {}).get(
            "legacy_activated",
            0,
        )
        pending = signup_by_placement.get(placement, {}).get("pending", 0)
        confirmation_sent = confirmation_by_placement.get(placement, {}).get(
            "confirmation_sent",
            0,
        )
        confirmation_failed = confirmation_by_placement.get(placement, {}).get(
            "confirmation_failed",
            0,
        )
        tracked_confirmed = tracked_confirmed_by_placement.get(placement, 0)
        placements.append({
            "placement": placement,
            "label": SUBSCRIBE_PLACEMENT_LABELS.get(
                placement,
                placement.replace("_", " ").title(),
            ),
            "views": views,
            "qualified_submissions": qualified_submissions,
            "signups": signups,
            "confirmed": confirmed,
            "explicit_confirmed": explicit_confirmed,
            "legacy_activated": legacy_activated,
            "confirmation_sent": confirmation_sent,
            "confirmation_failed": confirmation_failed,
            "provider_acceptance_rate": _conversion_rate(
                confirmation_sent,
                confirmation_sent + confirmation_failed,
            ),
            "pending": pending,
            "blocked": blocked_by_placement.get(placement, 0),
            "view_to_submit_rate": _conversion_rate(
                qualified_submissions,
                views,
            ),
            "submission_to_signup_rate": _conversion_rate(
                signups,
                qualified_submissions,
            ),
            "view_to_confirm_rate": _conversion_rate(tracked_confirmed, views),
            "signup_to_confirm_rate": _conversion_rate(confirmed, signups),
        })

    views = sum(row["views"] for row in placements)
    qualified_submissions = sum(
        row["qualified_submissions"] for row in placements
    )
    signups = sum(row["signups"] for row in placements)
    confirmed = sum(row["confirmed"] for row in placements)
    explicit_confirmed = sum(row["explicit_confirmed"] for row in placements)
    legacy_activated = sum(row["legacy_activated"] for row in placements)
    confirmation_sent = sum(row["confirmation_sent"] for row in placements)
    confirmation_failed = sum(row["confirmation_failed"] for row in placements)
    pending = sum(row["pending"] for row in placements)
    tracked_confirmed = sum(tracked_confirmed_by_placement.values())
    blocked = sum(row["blocked"] for row in placements)

    return {
        "days": days,
        "tracking_started_at": tracking_started_at,
        "summary": {
            "views": views,
            "qualified_submissions": qualified_submissions,
            "signups": signups,
            "confirmed": confirmed,
            "explicit_confirmed": explicit_confirmed,
            "legacy_activated": legacy_activated,
            "confirmation_sent": confirmation_sent,
            "confirmation_failed": confirmation_failed,
            "provider_acceptance_rate": _conversion_rate(
                confirmation_sent,
                confirmation_sent + confirmation_failed,
            ),
            "pending": pending,
            "confirmation_tracked": confirmation_delivery["tracked"],
            "confirmation_delivered": confirmation_delivery["delivered"],
            "confirmation_webhook_pending": confirmation_delivery["webhook_pending"],
            "confirmation_delayed": confirmation_delivery["delayed"],
            "confirmation_delivery_issues": confirmation_delivery["issues"],
            "confirmation_delivery_rate": _conversion_rate(
                confirmation_delivery["delivered"],
                confirmation_delivery["tracked"],
            ),
            "blocked": blocked,
            "view_to_submit_rate": _conversion_rate(
                qualified_submissions,
                views,
            ),
            "submission_to_signup_rate": _conversion_rate(
                signups,
                qualified_submissions,
            ),
            "view_to_confirm_rate": _conversion_rate(tracked_confirmed, views),
            "signup_to_confirm_rate": _conversion_rate(confirmed, signups),
        },
        "placements": placements,
    }


def confirmation_token_hash(token: str) -> str:
    return hash_value(token)


def create_confirmation_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, confirmation_token_hash(token)
