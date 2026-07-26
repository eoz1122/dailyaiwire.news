"""Deterministic recent-story duplicate detection for ingestion guardrails."""

import difflib
import re
from urllib.parse import urlparse


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_MODERN_ARXIV_ID_RE = re.compile(r"^(\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?/?$")
_STOPWORDS = {
    "a", "an", "and", "as", "at", "by", "for", "from", "in", "into",
    "is", "of", "on", "the", "to", "with",
}


def canonical_research_paper_id(source_url: str) -> str | None:
    """Return one stable identifier for the same paper across supported sources."""
    try:
        parsed = urlparse((source_url or "").strip())
    except (TypeError, ValueError):
        return None

    host = (parsed.hostname or "").lower()
    path = parsed.path.strip("/")
    candidate = ""

    if host in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
        if path.startswith("abs/") or path.startswith("pdf/"):
            candidate = path.split("/", 1)[1]
    elif host in {"huggingface.co", "www.huggingface.co"} and path.startswith("papers/"):
        candidate = path.split("/", 1)[1]

    match = _MODERN_ARXIV_ID_RE.fullmatch(candidate)
    if not match:
        return None
    return f"arxiv:{match.group(1)}"


def _stem_token(token: str) -> str:
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


def _story_tokens(text: str) -> set[str]:
    return {
        _stem_token(token)
        for token in _TOKEN_RE.findall((text or "").lower())
        if token not in _STOPWORDS
    }


def _number_tokens(text: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall((text or "").lower()) if token.isdigit()}


def _overlap(left: set[str], right: set[str]) -> tuple[int, float]:
    if not left or not right:
        return 0, 0.0
    shared = len(left & right)
    return shared, shared / min(len(left), len(right))


def likely_same_story(
    candidate_title: str,
    published_title: str,
    candidate_gist: str = "",
    published_gist: str = "",
) -> bool:
    """Return True for strong same-event matches without an LLM or vector store."""
    candidate_title = (candidate_title or "").strip()
    published_title = (published_title or "").strip()
    if not candidate_title or not published_title:
        return False

    candidate_numbers = _number_tokens(candidate_title)
    published_numbers = _number_tokens(published_title)
    if candidate_numbers and published_numbers and candidate_numbers != published_numbers:
        return False

    title_ratio = difflib.SequenceMatcher(
        None,
        candidate_title.lower(),
        published_title.lower(),
    ).ratio()
    if title_ratio >= 0.85:
        return True

    candidate_tokens = _story_tokens(candidate_title)
    published_tokens = _story_tokens(published_title)
    title_shared, title_containment = _overlap(candidate_tokens, published_tokens)
    if title_shared >= 5 and title_containment >= 0.70:
        return True

    candidate_gist_tokens = _story_tokens(candidate_gist)
    published_gist_tokens = _story_tokens(published_gist)
    gist_shared, gist_containment = _overlap(candidate_gist_tokens, published_gist_tokens)
    return (
        title_shared >= 3
        and gist_shared >= 5
        and gist_containment >= 0.72
    )
