"""
DeepDiagram Backfill — Generate mermaid diagrams for existing high-value articles.

Usage:
    python scripts/generate_diagrams.py                  # Process top 10 articles
    python scripts/generate_diagrams.py --limit 50       # Process top 50
    python scripts/generate_diagrams.py --dry-run        # Preview without saving
    python scripts/generate_diagrams.py --min-score 80   # Only articles scoring 80+
"""
import os
import sys
import json
import argparse
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

from db import DB_PATH

DIAGRAM_PROMPT = """You are a technical diagram expert. Given an article's headline and deep analysis, generate a Mermaid.js diagram that visually represents the key flow, process, or relationship described.

RULES:
- Output ONLY valid Mermaid.js syntax (no markdown fences, no explanation)
- Use flowchart LR (left-to-right) for processes, sequence diagrams for interactions, mindmap for concept overviews
- Keep node labels concise (max 6 words per node)
- Use 5-10 nodes maximum
- If the article is an opinion piece, minor update, or has no clear visual flow, respond with exactly: null

ARTICLE HEADLINE: {headline}

ARTICLE CONTENT:
{analysis}

Generate the Mermaid.js diagram:"""


def backfill_diagrams(limit=10, min_score=75, dry_run=False):
    """Generate diagrams for high-value articles that don't have one yet."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Find articles without diagrams
    rows = conn.execute('''
        SELECT id, slug, title, deep_analysis, full_json, importance_score
        FROM articles
        WHERE is_published = 1 AND importance_score >= ?
        ORDER BY importance_score DESC, published_at DESC
        LIMIT ?
    ''', (min_score, limit * 3)).fetchall()  # Fetch extra to filter

    # Filter out articles that already have a diagram
    candidates = []
    for row in rows:
        try:
            full = json.loads(row['full_json'] or '{}')
            if full.get('mermaid_diagram'):
                continue  # Already has a diagram
        except:
            pass
        candidates.append(dict(row))
        if len(candidates) >= limit:
            break

    if not candidates:
        print("✅ No articles need diagrams. All high-value articles already have one.")
        conn.close()
        return

    print(f"📊 Found {len(candidates)} articles to process (min_score={min_score})")

    if dry_run:
        for c in candidates:
            print(f"  [DRY RUN] Would process: [{c['importance_score']}] {c['title']}")
        conn.close()
        return

    # Initialize Gemini
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY not set")
        conn.close()
        return

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    generated = 0
    skipped = 0

    for c in candidates:
        prompt = DIAGRAM_PROMPT.format(
            headline=c['title'],
            analysis=(c['deep_analysis'] or '')[:2000]
        )

        try:
            response = model.generate_content(prompt)
            diagram = response.text.strip()

            # Clean up: remove markdown fences if AI added them
            if diagram.startswith("```mermaid"):
                diagram = diagram[len("```mermaid"):].strip()
            if diagram.startswith("```"):
                diagram = diagram[3:].strip()
            if diagram.endswith("```"):
                diagram = diagram[:-3].strip()

            if diagram.lower() == "null" or not diagram:
                print(f"  ⏭️  Skipped (no visual flow): {c['title'][:60]}")
                skipped += 1
                continue

            # Update full_json with the diagram
            try:
                full = json.loads(c['full_json'] or '{}')
            except:
                full = {}
            full['mermaid_diagram'] = diagram

            conn.execute(
                'UPDATE articles SET full_json = ? WHERE id = ?',
                (json.dumps(full), c['id'])
            )
            conn.commit()

            generated += 1
            print(f"  ✅ [{c['importance_score']}] {c['title'][:60]}...")

            # Rate limiting
            time.sleep(1)

        except Exception as e:
            print(f"  ❌ Error processing '{c['title'][:40]}': {e}")
            time.sleep(2)

    conn.close()
    print(f"\n📊 Done: {generated} diagrams generated, {skipped} skipped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill mermaid diagrams for existing articles")
    parser.add_argument("--limit", type=int, default=10, help="Max articles to process (default: 10)")
    parser.add_argument("--min-score", type=int, default=75, help="Minimum importance score (default: 75)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    args = parser.parse_args()

    backfill_diagrams(limit=args.limit, min_score=args.min_score, dry_run=args.dry_run)
