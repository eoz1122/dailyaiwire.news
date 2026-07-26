#!/usr/bin/env python3
"""Generate the weekly DailyAIWire newsletter draft once."""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.weekly_newsletter_runner import run_weekly_newsletter


def main() -> int:
    if "--dry-run" in sys.argv:
        from weekly_curator import generate_newsletter_draft

        result = generate_newsletter_draft(dry_run=True)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(run_weekly_newsletter())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
