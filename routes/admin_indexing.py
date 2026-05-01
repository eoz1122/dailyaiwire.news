"""
Read-only Google Indexing API audit panel.
"""
from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, render_template, request
from flask_login import login_required

from services.indexing_audit import (
    VALID_STATUSES,
    fetch_indexing_notifications,
    summarize_indexing_notifications,
)


admin_indexing_bp = Blueprint("admin_indexing", __name__)

PAGE_SIZE = 100


def _get_indexing_context():
    status = request.args.get("status", "", type=str).strip()
    query = request.args.get("q", "", type=str).strip()

    if status not in VALID_STATUSES:
        status = ""

    rows = fetch_indexing_notifications(status=status, query=query, limit=PAGE_SIZE)
    return {
        "rows": rows,
        "summary": summarize_indexing_notifications(),
        "statuses": sorted(VALID_STATUSES),
        "filters": {
            "status": status,
            "q": query,
        },
        "page_size": PAGE_SIZE,
    }


def _csv_response(rows):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["url", "action", "status", "status_code", "error", "attempted_at"])
    for row in rows:
        writer.writerow([
            row["url"],
            row["action"],
            row["status"],
            row["status_code"] if row["status_code"] is not None else "",
            row["error"] or "",
            row["attempted_at"],
        ])

    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=indexing-notifications.csv"
    return response


@admin_indexing_bp.route("/admin/indexing")
@login_required
def admin_indexing():
    return render_template("admin/indexing.html", **_get_indexing_context())


@admin_indexing_bp.route("/admin/indexing.csv")
@login_required
def admin_indexing_csv():
    context = _get_indexing_context()
    return _csv_response(context["rows"])
