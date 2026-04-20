#!/usr/bin/env python3
"""
Storage housekeeping for DailyAIWire.

Safe defaults:
- Dry-run by default.
- Deletes only audio files that are not referenced by DB or code
  and older than a configurable age threshold.
- Truncates only large active log files.
- Deletes only old rotated/backup logs.
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable


TEXT_EXTENSIONS = {
    ".py",
    ".html",
    ".md",
    ".txt",
    ".sh",
    ".yml",
    ".yaml",
    ".toml",
    ".json",
}

SKIP_DIRS = {".git", "venv", ".venv", "__pycache__", "qdrant_data", ".pytest_cache"}

# Captures file name part from static/audio/foo.mp3 and /static/audio/foo.mp3.
# Allows spaces in file names.
STATIC_AUDIO_REF_PATTERN = re.compile(r'(?:/)?static/audio/([^"\'<>\)\]]+)')
ROTATED_LOG_PATTERN = re.compile(r"\.log\.\d+$")


@dataclass
class FileCandidate:
    path: Path
    size_bytes: int


def _safe_stat(path: Path):
    try:
        return path.stat()
    except OSError:
        return None


def _iter_text_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        st = _safe_stat(path)
        if st is None or st.st_size > 2_000_000:
            continue
        yield path


def collect_db_audio_refs(db_path: Path) -> set[str]:
    refs: set[str] = set()
    if not db_path.exists():
        return refs

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    for col in ("audio_male", "audio_female"):
        query = f"""
            SELECT {col}
            FROM articles
            WHERE {col} IS NOT NULL
              AND LENGTH(TRIM({col})) > 0
        """
        for (value,) in cur.execute(query):
            if value and "/static/audio/" in value:
                refs.add(value.split("/static/audio/", 1)[1])

    try:
        for (value,) in cur.execute(
            """
            SELECT audio_path
            FROM podcasts
            WHERE audio_path IS NOT NULL
              AND LENGTH(TRIM(audio_path)) > 0
            """
        ):
            if value and "/static/audio/" in value:
                refs.add(value.split("/static/audio/", 1)[1])
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()

    return refs


def collect_code_audio_refs(root: Path) -> set[str]:
    refs: set[str] = set()
    for path in _iter_text_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        refs.update(STATIC_AUDIO_REF_PATTERN.findall(text))
    return refs


def audio_orphan_candidates(
    root: Path,
    keep_set: set[str],
    min_age_days: int,
) -> list[FileCandidate]:
    candidates: list[FileCandidate] = []
    audio_dir = root / "static" / "audio"
    if not audio_dir.exists():
        return candidates

    cutoff = datetime.now() - timedelta(days=min_age_days)
    for path in audio_dir.iterdir():
        if not path.is_file():
            continue
        if path.name in keep_set:
            continue
        st = _safe_stat(path)
        if st is None:
            continue
        mtime = datetime.fromtimestamp(st.st_mtime)
        if mtime > cutoff:
            continue
        candidates.append(FileCandidate(path=path, size_bytes=st.st_size))
    return candidates


def log_candidates(
    root: Path,
    retention_days: int,
    truncate_mb: int,
) -> tuple[list[FileCandidate], list[FileCandidate]]:
    delete_list: list[FileCandidate] = []
    truncate_list: list[FileCandidate] = []

    logs_dir = root / "logs"
    if not logs_dir.exists():
        return delete_list, truncate_list

    old_cutoff = datetime.now() - timedelta(days=retention_days)
    truncate_bytes = truncate_mb * 1024 * 1024

    for path in logs_dir.iterdir():
        if not path.is_file():
            continue
        st = _safe_stat(path)
        if st is None:
            continue
        mtime = datetime.fromtimestamp(st.st_mtime)
        name = path.name

        if (".bak" in name or ROTATED_LOG_PATTERN.search(name)) and mtime < old_cutoff:
            delete_list.append(FileCandidate(path=path, size_bytes=st.st_size))
            continue

        if name.endswith((".log", ".lo", ".err", ".out")) and st.st_size > truncate_bytes:
            truncate_list.append(FileCandidate(path=path, size_bytes=st.st_size))

    return delete_list, truncate_list


def _mb(total_bytes: int) -> float:
    return round(total_bytes / 1024 / 1024, 1)


def apply_actions(delete_audio: list[FileCandidate], delete_logs: list[FileCandidate], truncate_logs: list[FileCandidate]) -> tuple[int, int]:
    reclaimed = 0
    failures = 0

    for item in delete_audio + delete_logs:
        try:
            os.remove(item.path)
            reclaimed += item.size_bytes
        except OSError:
            failures += 1

    for item in truncate_logs:
        try:
            with open(item.path, "w", encoding="utf-8"):
                pass
            reclaimed += item.size_bytes
        except OSError:
            failures += 1

    return reclaimed, failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DailyAIWire storage housekeeping")
    parser.add_argument("--root", default=".", help="Project root path")
    parser.add_argument("--audio-min-age-days", type=int, default=2, help="Only delete orphan audio older than this age")
    parser.add_argument("--log-retention-days", type=int, default=30, help="Delete rotated/backup logs older than this age")
    parser.add_argument("--log-truncate-mb", type=int, default=50, help="Truncate active logs above this size")
    parser.add_argument("--apply", action="store_true", help="Apply cleanup (default: dry-run)")
    parser.add_argument("--verbose", action="store_true", help="Print top candidates")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()

    db_refs = collect_db_audio_refs(root / "news.db")
    code_refs = collect_code_audio_refs(root)
    keep = db_refs | code_refs

    audio_candidates = audio_orphan_candidates(
        root=root,
        keep_set=keep,
        min_age_days=args.audio_min_age_days,
    )
    log_delete, log_truncate = log_candidates(
        root=root,
        retention_days=args.log_retention_days,
        truncate_mb=args.log_truncate_mb,
    )

    audio_bytes = sum(x.size_bytes for x in audio_candidates)
    log_delete_bytes = sum(x.size_bytes for x in log_delete)
    log_truncate_bytes = sum(x.size_bytes for x in log_truncate)
    potential = audio_bytes + log_delete_bytes + log_truncate_bytes

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"== Storage Housekeeping ({mode}) ==")
    print(f"root: {root}")
    print(f"db_audio_refs: {len(db_refs)}")
    print(f"code_audio_refs: {len(code_refs)}")
    print(f"audio_orphans: {len(audio_candidates)} ({_mb(audio_bytes)} MB)")
    print(f"delete_logs: {len(log_delete)} ({_mb(log_delete_bytes)} MB)")
    print(f"truncate_logs: {len(log_truncate)} ({_mb(log_truncate_bytes)} MB)")
    print(f"potential_reclaim: {_mb(potential)} MB")

    if args.verbose:
        print("\nTop audio orphans:")
        for item in sorted(audio_candidates, key=lambda x: x.size_bytes, reverse=True)[:15]:
            print(f"- {_mb(item.size_bytes)} MB\t{item.path.name}")

        print("\nTop logs to truncate:")
        for item in sorted(log_truncate, key=lambda x: x.size_bytes, reverse=True)[:10]:
            print(f"- {_mb(item.size_bytes)} MB\t{item.path.name}")

    if not args.apply:
        return 0

    reclaimed, failures = apply_actions(audio_candidates, log_delete, log_truncate)
    print(f"\nreclaimed: {_mb(reclaimed)} MB")
    print(f"failures: {failures}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
