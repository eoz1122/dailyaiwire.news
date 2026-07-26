import sqlite3
import json
import os
import logging
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

from dotenv import load_dotenv
from logging_config import setup_logging
import ai_config
from db import DB_PATH
from services.ai_gateway import AIGateway
from services.ai_schemas import WeeklyNewsletterDraft

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))
setup_logging()

logger = logging.getLogger('weekly_curator')

ARTICLE_LIMIT = 7
CANDIDATE_POOL_LIMIT = 35
MAX_ARTICLES_PER_CATEGORY = 2
MAX_SOURCE_AGE_DAYS = 14
SUBJECT_MAX_CHARACTERS = 60
INTRO_MIN_WORDS = 80
INTRO_MAX_WORDS = 120
BLURB_MIN_WORDS = 20
BLURB_MAX_WORDS = 40
MAX_GENERATION_ATTEMPTS = 2

SENSATIONAL_PHRASES = (
    "breaking free",
    "catastrophic",
    "loss of control",
    "profoundly",
    "revolutionizing",
    "unleashes",
    "unprecedented",
)

SOURCE_DATE_PATTERN = re.compile(
    r"(?<!\d)(20\d{2})[/-](0?[1-9]|1[0-2])[/-](0?[1-9]|[12]\d|3[01])(?!\d)"
)
MONEY_PATTERN = re.compile(
    r"\$\s?\d[\d,.]*(?:\s*(?:million|billion|trillion)|[mbt]\b)?",
    re.IGNORECASE,
)
FUTURE_HORIZON_PATTERN = re.compile(
    r"\b(?:by|through)\s+20\d{2}\b",
    re.IGNORECASE,
)
COMMITMENT_PATTERN = re.compile(
    r"\bcommit(?:ment|ments|s|ted|ting)?\b",
    re.IGNORECASE,
)
PROJECTION_QUALIFIER_PATTERN = re.compile(
    r"\b(?:project(?:ed|ion|ions)?|plan(?:ned|s)?|expect(?:ed|s)?|"
    r"estimat(?:e|ed|es|ion|ions))\b",
    re.IGNORECASE,
)
RISKY_HEADLINE_PATTERN = re.compile(
    r"\b(?:alleg(?:e|es|ed|edly|ation)|claim(?:s|ed|ing)?|"
    r"breach(?:es|ed|ing)?|kill rates?|loss[- ]of[- ]control)\b",
    re.IGNORECASE,
)
ATTRIBUTION_PATTERN = re.compile(
    r"\b(?:alleged|allegedly|claim(?:s|ed)?|says|said|reported|"
    r"reportedly|according to|during (?:an? )?(?:internal )?"
    r"(?:evaluation|test|testing))\b",
    re.IGNORECASE,
)


def _as_utc(now):
    """Return a timezone-aware UTC datetime without changing the instant."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def extract_source_date(source_url):
    """Extract a publication date from common dated URL path formats."""
    if not source_url:
        return None

    path = urlparse(source_url).path
    match = SOURCE_DATE_PATTERN.search(path)
    if not match:
        return None

    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def _is_stale_source(article, *, now, max_age_days=MAX_SOURCE_AGE_DAYS):
    source_date = extract_source_date(article.get("source_url"))
    if source_date is None:
        return False
    return source_date < (_as_utc(now).date() - timedelta(days=max_age_days))


def _published_sort_value(article):
    raw_value = article.get("published_at") or ""
    try:
        parsed = datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
        return _as_utc(parsed).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _article_rank(article):
    return (
        float(article.get("importance_score") or 0),
        _published_sort_value(article),
        int(article.get("id") or 0),
    )


def select_diverse_articles(candidates, *, limit=ARTICLE_LIMIT, now=None):
    """Select fresh, high-scoring articles while limiting category clustering."""
    normalized = [dict(article) for article in candidates]
    ranked = sorted(
        (
            article
            for article in normalized
            if not _is_stale_source(article, now=now)
        ),
        key=_article_rank,
        reverse=True,
    )

    selected = []
    selected_ids = set()
    category_counts = Counter()

    # First pass gives each available category one slot before any repeats.
    for article in ranked:
        category = (article.get("category") or "Uncategorized").strip()
        if category_counts[category] or len(selected) >= limit:
            continue
        selected.append(article)
        selected_ids.add(article["id"])
        category_counts[category] += 1

    # Second pass fills the issue by score while enforcing the category cap.
    for article in ranked:
        if len(selected) >= limit:
            break
        if article["id"] in selected_ids:
            continue
        category = (article.get("category") or "Uncategorized").strip()
        if category_counts[category] >= MAX_ARTICLES_PER_CATEGORY:
            continue
        selected.append(article)
        selected_ids.add(article["id"])
        category_counts[category] += 1

    return selected


def get_top_articles(days=7, limit=ARTICLE_LIMIT, now=None):
    """Retrieve a larger candidate pool, then apply freshness and diversity."""
    now = _as_utc(now)
    threshold_date = now - timedelta(days=days)
    candidate_limit = max(CANDIDATE_POOL_LIMIT, limit * 5)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                id, title, gist, why_it_matters, importance_score,
                category, source, source_url, published_at
            FROM articles
            WHERE datetime(replace(published_at, 'T', ' ')) >= datetime(?)
              AND datetime(replace(published_at, 'T', ' ')) <= datetime(?)
              AND is_published = 1
            ORDER BY importance_score DESC, published_at DESC, id DESC
            LIMIT ?
            """,
            (threshold_date.isoformat(), now.isoformat(), candidate_limit),
        ).fetchall()
    finally:
        conn.close()

    return select_diverse_articles(rows, limit=limit, now=now)


def build_newsletter_prompt(articles, *, week_ending, now=None):
    """Build the grounded editorial contract supplied to the AI writer."""
    article_blocks = []
    for article in articles:
        source_date = extract_source_date(article.get("source_url"))
        article_blocks.append(
            "\n".join(
                (
                    f"ID: {article['id']}",
                    f"TITLE: {article['title']}",
                    f"CATEGORY: {article.get('category') or 'Uncategorized'}",
                    f"SOURCE: {article.get('source') or 'Unknown'}",
                    f"SOURCE URL: {article.get('source_url') or 'Not provided'}",
                    f"SOURCE DATE: {source_date.isoformat() if source_date else 'Unknown'}",
                    f"SITE PUBLISHED: {article.get('published_at') or 'Unknown'}",
                    f"GIST: {article.get('gist') or 'Not provided'}",
                    (
                        "EXISTING WHY IT MATTERS: "
                        f"{article.get('why_it_matters') or 'Not provided'}"
                    ),
                    f"IMPORTANCE: {article.get('importance_score') or 0}",
                )
            )
        )

    articles_context = "\n---\n".join(article_blocks)
    return f"""
You are the Editor-in-Chief of DailyAIWire.
Write the AI Weekly Wrap for the week ending {week_ending}.

SELECTED ARTICLES:
{articles_context}

EDITORIAL CONTRACT:
1. SUBJECT
   - Format: "AI Weekly Wrap: [specific themes from the selected articles]".
   - Maximum 60 characters including the prefix.
   - Be direct and factual. Avoid sensational or apocalyptic language.
   - Do not use hype words such as "unprecedented", "profoundly", or
     "revolutionizing".
   - Do not use abstract filler such as "Nexus", "Paradigm", or "Quantum Leap".

2. EDITOR'S NOTE
   - Write exactly two short paragraphs totaling 80-120 words.
   - Synthesize the issue across several categories instead of repeating headlines.
   - Preserve attribution such as "says", "claims", "alleges", "reported", or
     "according to" when the supplied context uses it.
   - Distinguish projections from commitments, plans from completed actions,
     and reported results from independently verified results.
   - Treat future financial figures from third-party reporting as reported
     projections or plans, never as commitments. Use explicit projection
     language such as "projected", "planned", "expected", or "estimated".
   - Do not present a story as current if its supplied source date is old.
   - Never invent facts, forecasts, motives, deadlines, or consequences.

3. WHY IT MATTERS
   - Return one sentence for every selected article, mapped by article ID.
   - Keep every sentence to 20-40 words.
   - State who is affected, what concretely changes, and why it matters now.
   - Use only the supplied context and do not strengthen its level of certainty.
   - If a headline describes an allegation, claim, breach, reported kill rate,
     or loss-of-control framing, keep explicit attribution in its blurb.
   - Avoid generic filler such as "signifies", "underscores", or "highlights".

OUTPUT:
Return only a JSON object with this exact shape:
{{
  "subject": "AI Weekly Wrap: [specific themes]",
  "intro_text": "Two paragraphs separated by a blank line",
  "article_blurbs": {{
    "ARTICLE_ID": "One grounded 20-40 word sentence"
  }}
}}

TONE: Professional, concise, evidence-led, and tech-forward.
""".strip()


def _word_count(value):
    return len(re.findall(r"\b[\w$%'-]+\b", value or ""))


def validate_newsletter_draft(draft, articles):
    """Return editorial contract violations without mutating generated copy."""
    errors = []
    subject = (draft.subject or "").strip()
    intro_text = (draft.intro_text or "").strip()
    blurbs = {str(key): value for key, value in (draft.article_blurbs or {}).items()}

    if not subject.startswith("AI Weekly Wrap:"):
        errors.append('Subject must start with "AI Weekly Wrap:".')
    if len(subject) > SUBJECT_MAX_CHARACTERS:
        errors.append("Subject must be no more than 60 characters.")

    intro_words = _word_count(intro_text)
    if not INTRO_MIN_WORDS <= intro_words <= INTRO_MAX_WORDS:
        errors.append("Editor's note must contain 80-120 words.")

    expected_ids = {str(article["id"]) for article in articles}
    actual_ids = set(blurbs)
    if actual_ids != expected_ids:
        errors.append(
            "Article blurbs must match selected IDs exactly: "
            f"expected {sorted(expected_ids)}, received {sorted(actual_ids)}."
        )

    for article_id, blurb in blurbs.items():
        word_count = _word_count(blurb)
        if not BLURB_MIN_WORDS <= word_count <= BLURB_MAX_WORDS:
            errors.append(
                f"Article {article_id} blurb must contain 20-40 words; "
                f"received {word_count}."
            )

    articles_by_id = {str(article["id"]): article for article in articles}
    for article_id, blurb in blurbs.items():
        article = articles_by_id.get(article_id)
        if (
            article
            and RISKY_HEADLINE_PATTERN.search(article.get("title") or "")
            and not ATTRIBUTION_PATTERN.search(blurb or "")
        ):
            errors.append(
                f"Article {article_id} blurb requires explicit attribution "
                "because its headline contains a claim or risky incident framing."
            )

    generated_text = f"{subject}\n{intro_text}\n" + "\n".join(blurbs.values())
    lowered_text = generated_text.lower()
    normalized_text = re.sub(r"[-_]+", " ", lowered_text)
    found_phrases = [
        phrase for phrase in SENSATIONAL_PHRASES if phrase in normalized_text
    ]
    if found_phrases:
        errors.append(
            "Generated copy contains sensational language: "
            + ", ".join(sorted(found_phrases))
            + "."
        )

    sentences = re.split(r"(?<=[.!?])\s+|\n+", generated_text)
    future_financial_sentences = [
        sentence
        for sentence in sentences
        if MONEY_PATTERN.search(sentence)
        and FUTURE_HORIZON_PATTERN.search(sentence)
    ]
    if any(COMMITMENT_PATTERN.search(sentence) for sentence in future_financial_sentences):
        errors.append(
            "Describe future financial projections as reported projections or "
            "plans, not commitments."
        )
    if any(
        not PROJECTION_QUALIFIER_PATTERN.search(sentence)
        for sentence in future_financial_sentences
    ):
        errors.append(
            "Future financial figures require explicit projection language such "
            "as projected, planned, expected, or estimated."
        )

    return errors


def _draft_as_dict(draft):
    if hasattr(draft, "model_dump"):
        return draft.model_dump()
    return {
        "subject": draft.subject,
        "intro_text": draft.intro_text,
        "article_blurbs": draft.article_blurbs,
    }


def _build_repair_prompt(base_prompt, draft, errors):
    return (
        f"{base_prompt}\n\n"
        "REVISION REQUIRED:\n"
        + "\n".join(f"- {error}" for error in errors)
        + "\n\nPREVIOUS OUTPUT:\n"
        + json.dumps(_draft_as_dict(draft), ensure_ascii=False)
        + "\nReturn a corrected JSON object that satisfies every contract rule."
    )


def _log_usage(budget, response):
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return
    budget.log_request(
        getattr(usage, "prompt_token_count", 0) or 0,
        getattr(usage, "candidates_token_count", 0) or 0,
        category="Weekly Digest",
    )


def _dry_run_payload(draft, articles):
    return {
        "dry_run": True,
        "subject": draft.subject,
        "intro_text": draft.intro_text,
        "article_ids": [article["id"] for article in articles],
        "article_blurbs": {
            str(key): value for key, value in draft.article_blurbs.items()
        },
        "articles": [
            {
                "id": article["id"],
                "title": article["title"],
                "category": article.get("category"),
                "source": article.get("source"),
                "source_date": (
                    source_date.isoformat()
                    if (source_date := extract_source_date(article.get("source_url")))
                    else None
                ),
                "importance_score": article.get("importance_score"),
            }
            for article in articles
        ],
    }


def generate_newsletter_draft(
    *,
    dry_run=False,
    now=None,
    gateway=None,
    budget=None,
):
    """Synthesize a validated weekly draft, optionally without saving it."""
    now = _as_utc(now)
    top_articles = get_top_articles(now=now)

    if not top_articles:
        logger.info("📭 No high-signal articles found this week. Skipping draft generation.")
        return None

    try:
        if budget is None:
            from budget_tracker import BudgetTracker
            budget = BudgetTracker()

        if gateway is None:
            gateway = AIGateway(
                model_name=ai_config.DEFAULT_MODEL,
                generation_config={"response_mime_type": "application/json"},
                logger_name='weekly_curator',
            )

        logger.info(
            "🔬 Synthesizing %d diverse, fresh stories into a weekly wrap...",
            len(top_articles),
        )
        week_ending = now.strftime('%B %d, %Y')
        base_prompt = build_newsletter_prompt(
            top_articles,
            week_ending=week_ending,
            now=now,
        )
        prompt = base_prompt
        draft = None

        for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
            draft, response = gateway.generate_structured(
                prompt,
                WeeklyNewsletterDraft,
                prompt_type="weekly_digest",
            )
            _log_usage(budget, response)
            errors = validate_newsletter_draft(draft, top_articles)
            if not errors:
                break
            if attempt == MAX_GENERATION_ATTEMPTS:
                raise ValueError(
                    "Weekly newsletter failed editorial validation after "
                    f"{MAX_GENERATION_ATTEMPTS} attempts: {'; '.join(errors)}"
                )
            logger.warning(
                "Weekly draft failed editorial validation; requesting one repair: %s",
                "; ".join(errors),
            )
            prompt = _build_repair_prompt(base_prompt, draft, errors)

        if dry_run:
            logger.info("Dry run complete; no newsletter row was created.")
            return _dry_run_payload(draft, top_articles)

        # Save to DB
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Serialize article IDs for reference
        article_ids = json.dumps([a['id'] for a in top_articles])

        # Serialize Metadata (Why It Matters)
        article_metadata = json.dumps(draft.article_blurbs)

        # Schedule for TODAY at 18:00 - newsletter covers last 7 days and should
        # be ready for immediate review and sending, not queued for next Sunday.
        scheduled_date = now.replace(hour=18, minute=0, second=0, microsecond=0)

        cursor.execute('''
            INSERT INTO newsletters (subject, intro_text, article_ids, article_metadata, status, scheduled_date)
            VALUES (?, ?, ?, ?, 'DRAFT', ?)
        ''', (draft.subject, draft.intro_text, article_ids, article_metadata, scheduled_date.isoformat()))
        newsletter_id = cursor.lastrowid

        conn.commit()
        conn.close()

        logger.info("✅ Newsletter Draft Created: '%s'", draft.subject)
        logger.info("📅 Status: DRAFT | Scheduled for: %s", scheduled_date.strftime('%Y-%m-%d %H:%M'))
        return newsletter_id

    except Exception as e:
        logger.error("❌ Failed to generate weekly wrap: %s", e, exc_info=True)
        raise

if __name__ == "__main__":
    import sys

    if "--dry-run" in sys.argv:
        print(
            json.dumps(
                generate_newsletter_draft(dry_run=True),
                ensure_ascii=False,
                indent=2,
            )
        )
    elif "--auto" in sys.argv:
        # Unattended mode: include trend data in the curation
        logger.info("🤖 Running in --auto mode (unattended weekly curation)...")

        # Inject trend snapshot into the prompt
        try:
            from trend_engine import get_trend_snapshot
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            snapshot = get_trend_snapshot(conn)
            conn.close()

            if snapshot.get('has_trends'):
                hot_cats = [c['category'] for c in snapshot.get('hot_categories', [])[:3]]
                hot_tags = [h['hashtag'] for h in snapshot.get('hot_hashtags', [])[:5]]
                logger.debug("📊 Trend context: categories=%s, hashtags=%s", hot_cats, hot_tags)
        except Exception as e:
            logger.warning("⚠️ Trend injection skipped: %s", e)

        generate_newsletter_draft()
    else:
        generate_newsletter_draft()
