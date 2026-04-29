"""
Indexability scoring for sitemap eligibility.

This is intentionally conservative: it does not decide whether an article is
published or visible to users. It only decides whether the URL deserves crawl
budget in XML sitemaps.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping


SITEMAP_ELIGIBILITY_THRESHOLD = 88

HIGH_AUTHORITY_SOURCES = {
    "TechCrunch",
    "MIT Technology Review",
    "The Verge",
    "Wired",
    "NVIDIA Dev",
    "BBC News",
    "CNBC",
    "Fortune",
    "Arstechnica",
    "Theregister",
    "Theguardian",
    "Forbes",
}

RESEARCH_SOURCES = {
    "ArXiv cs.AI",
    "ArXiv Research",
    "ArXiv Computation and Language (cs.CL)",
    "Hugging Face Papers",
    "Zenodo",
}

LOW_CONTEXT_SOURCES = {
    "GitHub",
    "News",
    "Blog",
}


@dataclass(frozen=True)
class IndexabilityResult:
    score: int
    sitemap_eligible: bool
    strengths: tuple[str, ...]
    blockers: tuple[str, ...]


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _word_count(*values: Any) -> int:
    text = " ".join(_as_text(value) for value in values)
    return len(re.findall(r"\b[\w'-]+\b", text))


def _number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _list_count(value: Any) -> int:
    if isinstance(value, list):
        return len([item for item in value if _as_text(item)])
    if isinstance(value, tuple):
        return len([item for item in value if _as_text(item)])
    raw = _as_text(value)
    if not raw or raw == "[]":
        return 0
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return 1
    if isinstance(parsed, list):
        return len([item for item in parsed if _as_text(item)])
    return 1 if _as_text(parsed) else 0


def _image_points(image: Any) -> tuple[int, str | None]:
    image_text = _as_text(image)
    if not image_text:
        return 0, "image"
    if "/fallbacks/" in image_text or "fallback" in image_text.lower():
        return 2, "fallback_image"
    return 7, None


def _source_points(source: Any) -> tuple[int, str | None]:
    source_text = _as_text(source)
    if not source_text:
        return 0, "source"
    if source_text in HIGH_AUTHORITY_SOURCES:
        return 10, None
    if source_text in RESEARCH_SOURCES:
        return 9, None
    if source_text in LOW_CONTEXT_SOURCES:
        return 2, "low_context_source"
    return 6, None


def _existing_quality_points(article: Mapping[str, Any]) -> int:
    importance = _number(article.get("importance_score"), 50.0)
    compass = _number(article.get("compass_score"), 0.7)
    composite = max(0.0, min(100.0, importance * compass))
    return round(min(24.0, composite / 80.0 * 24.0))


def score_article(article: Mapping[str, Any]) -> IndexabilityResult:
    score = 0
    strengths: list[str] = []
    blockers: list[str] = []

    title = _as_text(article.get("title"))
    gist = _as_text(article.get("gist"))
    why_it_matters = _as_text(article.get("why_it_matters"))
    bull_case = _as_text(article.get("bull_case"))
    bear_case = _as_text(article.get("bear_case"))
    deep_analysis = _as_text(article.get("deep_analysis"))

    body_words = _word_count(gist, why_it_matters, bull_case, bear_case, deep_analysis)
    if body_words >= 650:
        score += 24
        strengths.append("deep_analysis")
    elif body_words >= 450:
        score += 18
        strengths.append("solid_depth")
    elif body_words >= 300:
        score += 12
    elif body_words >= 180:
        score += 6
        blockers.append("thin_analysis")
    else:
        blockers.append("deep_analysis")

    if len(title) >= 35:
        score += 4
    else:
        blockers.append("title")

    if len(gist) >= 80:
        score += 6
        strengths.append("gist")
    elif gist:
        score += 2
    else:
        blockers.append("gist")

    if len(why_it_matters) >= 80:
        score += 10
        strengths.append("why_it_matters")
    elif why_it_matters:
        score += 4
    else:
        blockers.append("why_it_matters")

    detail_count = _list_count(article.get("key_details"))
    if detail_count >= 3:
        score += 8
        strengths.append("key_details")
    elif detail_count >= 1:
        score += 4
    else:
        blockers.append("key_details")

    if len(bull_case) >= 40 and len(bear_case) >= 40:
        score += 8
        strengths.append("tradeoffs")
    elif bull_case or bear_case:
        score += 3
    else:
        blockers.append("tradeoffs")

    if _as_text(article.get("source_url")):
        score += 5
    else:
        blockers.append("source_url")

    source_score, source_blocker = _source_points(article.get("source"))
    score += source_score
    if source_blocker:
        blockers.append(source_blocker)

    image_score, image_blocker = _image_points(article.get("image"))
    score += image_score
    if image_blocker:
        blockers.append(image_blocker)

    score += _existing_quality_points(article)

    final_score = max(0, min(100, score))
    return IndexabilityResult(
        score=final_score,
        sitemap_eligible=final_score >= SITEMAP_ELIGIBILITY_THRESHOLD,
        strengths=tuple(dict.fromkeys(strengths)),
        blockers=tuple(dict.fromkeys(blockers)),
    )


def is_sitemap_eligible(article: Mapping[str, Any]) -> bool:
    return score_article(article).sitemap_eligible
