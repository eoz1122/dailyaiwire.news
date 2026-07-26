"""
Read-only SEO and indexability admin panel.
"""
from __future__ import annotations

import csv
import io
from collections import Counter

from flask import Blueprint, Response, render_template, request
from flask_login import login_required

from db import get_db_connection
from services.indexability import SITEMAP_ELIGIBILITY_THRESHOLD, score_article


admin_seo_bp = Blueprint("admin_seo", __name__)

ARTICLE_SCAN_LIMIT = 1000
PAGE_SIZE = 100
VALID_STATUS_FILTERS = {"", "eligible", "not_eligible"}


def _article_select_columns() -> str:
    return """
        id, slug, title, image, social_image, category, gist, why_it_matters, bull_case,
        bear_case, key_details, deep_analysis, source, source_url,
        published_at, importance_score, compass_score, is_published
    """


def _fetch_source_options():
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT source, COUNT(*) AS count
        FROM articles
        WHERE is_published = 1
          AND source IS NOT NULL
          AND TRIM(source) != ''
        GROUP BY source
        ORDER BY count DESC, source ASC
        LIMIT 80
        """
    ).fetchall()
    conn.close()
    return rows


def _fetch_articles(query_text: str, source: str):
    conditions = [
        "is_published = 1",
        "published_at IS NOT NULL",
        "replace(published_at, 'T', ' ') <= datetime('now')",
    ]
    params: list[object] = []

    if query_text:
        conditions.append("(title LIKE ? OR slug LIKE ? OR source LIKE ?)")
        like = f"%{query_text}%"
        params.extend([like, like, like])

    if source:
        conditions.append("source = ?")
        params.append(source)

    where_clause = " AND ".join(conditions)
    params.append(ARTICLE_SCAN_LIMIT)

    conn = get_db_connection()
    rows = conn.execute(
        f"""
        SELECT {_article_select_columns()}
        FROM articles
        WHERE {where_clause}
        ORDER BY replace(published_at, 'T', ' ') DESC, id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    conn.close()
    return rows


def _score_rows(rows):
    scored = []
    for row in rows:
        article = dict(row)
        result = score_article(article)
        article["indexability_score"] = result.score
        article["sitemap_eligible"] = result.sitemap_eligible
        article["blockers"] = list(result.blockers)
        article["strengths"] = list(result.strengths)
        scored.append(article)
    return scored


def _filter_rows(rows, status: str, blocker: str):
    filtered = rows
    if status == "eligible":
        filtered = [row for row in filtered if row["sitemap_eligible"]]
    elif status == "not_eligible":
        filtered = [row for row in filtered if not row["sitemap_eligible"]]

    if blocker:
        filtered = [row for row in filtered if blocker in row["blockers"]]

    return filtered


def _summary(rows):
    total = len(rows)
    eligible = sum(1 for row in rows if row["sitemap_eligible"])
    blocked = total - eligible
    average_score = round(
        sum(row["indexability_score"] for row in rows) / total,
        1,
    ) if total else 0

    blocker_counts = Counter(
        blocker
        for row in rows
        for blocker in row["blockers"]
    )
    rejected_source_counts = Counter(
        row["source"] or "Unknown"
        for row in rows
        if not row["sitemap_eligible"]
    )

    return {
        "total": total,
        "eligible": eligible,
        "blocked": blocked,
        "average_score": average_score,
        "top_blockers": blocker_counts.most_common(10),
        "top_rejected_sources": rejected_source_counts.most_common(8),
        "all_blockers": sorted(blocker_counts.keys()),
    }


def _csv_response(rows):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "slug",
        "title",
        "source",
        "indexability_score",
        "sitemap_eligible",
        "blockers",
        "strengths",
    ])
    for row in rows:
        writer.writerow([
            row["slug"],
            row["title"],
            row["source"],
            row["indexability_score"],
            "yes" if row["sitemap_eligible"] else "no",
            "|".join(row["blockers"]),
            "|".join(row["strengths"]),
        ])

    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=indexability.csv"
    return response


def _get_admin_seo_context():
    query_text = request.args.get("q", "", type=str).strip()
    source = request.args.get("source", "", type=str).strip()
    status = request.args.get("status", "", type=str).strip()
    blocker = request.args.get("blocker", "", type=str).strip()

    if status not in VALID_STATUS_FILTERS:
        status = ""

    scored_rows = _score_rows(_fetch_articles(query_text, source))
    summary = _summary(scored_rows)
    filtered_rows = _filter_rows(scored_rows, status, blocker)

    return {
        "rows": filtered_rows[:PAGE_SIZE],
        "all_rows": filtered_rows,
        "summary": summary,
        "source_options": _fetch_source_options(),
        "filters": {
            "q": query_text,
            "source": source,
            "status": status,
            "blocker": blocker,
        },
        "threshold": SITEMAP_ELIGIBILITY_THRESHOLD,
        "scan_limit": ARTICLE_SCAN_LIMIT,
        "page_size": PAGE_SIZE,
        "filtered_count": len(filtered_rows),
    }


@admin_seo_bp.route("/admin/seo")
@login_required
def admin_seo():
    context = _get_admin_seo_context()
    return render_template("admin/seo.html", **context)


@admin_seo_bp.route("/admin/seo.csv")
@login_required
def admin_seo_csv():
    context = _get_admin_seo_context()
    return _csv_response(context["all_rows"])
