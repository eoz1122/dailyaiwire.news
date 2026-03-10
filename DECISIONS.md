# DECISIONS.md — Daily AI Wire News
# Architectural Decision Log

Architectural decision log for the Daily AI Wire News project. Every entry includes an ISO 8601 timestamp per §6 of the AI Directives.

---

## 2026-03-10T09:38:00+01:00 — Removed "Trusted Intelligence Sources" Section

**Decision**: Removed the "Trusted Intelligence Sources" grid from the homepage. The section displayed source logos/icons (GitHub, TechCrunch, Wired, etc.) with a paginated grid. Per the Architect's directive, this section is no longer needed.

**Changes**: 
- Removed 40-line HTML block from `templates/index.html` (former lines 501–541).
- Removed the SQL query fetching top 12 sources from `app.py` `index()` route.
- Removed `sources=sources` from the `render_template()` call.

**Rollback**: Re-add the `{% if sources %}` block in `index.html` after the article grid. Restore the `sources_raw` SQL query and `sources` variable in `app.py` `index()`. Add `sources=sources` back to `render_template()`.

---

## 2026-03-10T01:22:00+01:00 — Phase 4: Trend Intelligence Engine

**Decision**: Added SQL-driven trend detection comparing 7-day rolling windows. Surfaces surging categories, trending hashtags, and emerging keywords on the homepage.

**Stack**: New `trend_engine.py` module (pure SQL, zero dependencies). `/api/trends` JSON endpoint. Horizontal scroll glass-cards on homepage.

**Rollback**: Remove `trend_engine.py`. Remove `/api/trends` route. Remove trending section from `index.html`. Remove `trends` from `render_template()` call.

---

## 2026-03-10T01:12:00+01:00 — Phase 2: Smart Deduplication (Historical Sweep)

**Decision**: Added a one-time historical dedup sweep using Qdrant vector similarity + admin review dashboard. Non-destructive design: articles are unpublished (`is_published=0`), never deleted.

**Stack**: `find_all_duplicates()` in `embedding_service.py` uses union-find clustering over Qdrant `scroll()`. `scripts/dedup_sweep.py` writes clusters to `duplicate_clusters` SQLite table. Admin dashboard at `/admin/duplicates` with merge/dismiss actions.

**How it works**:
- CLI: `python scripts/dedup_sweep.py --threshold 0.88` (runs on VPS)
- Scans all vectors, finds neighbors > threshold, groups into clusters
- Writes to `duplicate_clusters` table (pending status)
- Admin reviews at `/admin/duplicates` → Merge (unpublish older) or Dismiss (false positive)

**Rollback**: Drop `duplicate_clusters` table. Remove routes from `app.py`. Delete `scripts/dedup_sweep.py` and `templates/admin/duplicates.html`.

---

## 2026-03-10T00:56:00+01:00 — Phase 1: Semantic Search (Qdrant-Powered)

**Decision**: Upgraded the public search from SQL `LIKE` keyword matching to **Qdrant vector semantic search** with automatic keyword fallback.

**Stack**: Reuses Phase 0 infrastructure (`bge-large-en-v1.5` + Qdrant local disk). New `search_articles()` function in `embedding_service.py` uses the BGE query prefix for asymmetric retrieval.

**How it works**:
- User types query in search bar → `/?q=...`
- `app.py` `index()` route calls `embedding_service.search_articles(q)`
- Qdrant returns ranked article IDs by cosine similarity
- Full articles fetched from SQLite preserving Qdrant rank order
- If Qdrant unavailable (`ImportError` or error) → silent fallback to SQL `LIKE`
- UI shows "Semantic Search" (purple badge) or "Keyword Search" (grey badge)
- New `/api/search` JSON endpoint for programmatic access / future typeahead
- Mobile search bar added to `base.html` header

**Rollback**: Revert the `index()` route in `app.py` to the simple `LIKE` query block. Remove `search_articles()` from `embedding_service.py`. Remove `/api/search` route.

---

## 2026-03-09T23:21:00+01:00 — Phase 0: Editorial Compass (RAG Infrastructure)

**Decision**: Integrated a vector-based Editorial Compass into the article fetcher.

**Stack**: `bge-large-en-v1.5` (HuggingFace, 1024-dim, local CPU) + Qdrant (local disk persistence).

**How it works**:
- 3,780 existing articles embedded into Qdrant vector collection
- New articles scored against corpus at ingestion time in `save_to_db()`
- Score > 0.75 → auto-publish, 0.55–0.75 → review, < 0.55 → auto-kill → Iron Judo leads
- Semantic dedup: > 0.92 cosine similarity → rejected as duplicate
- Post-save: new articles auto-indexed into Qdrant (compass self-improves)
- All hooks are non-blocking with graceful ImportError fallback

**Rollback**: Remove the "2.5 EDITORIAL COMPASS" and "INDEX INTO QDRANT" blocks from `fetcher.py`. Delete `qdrant_data/` directory on VPS.

---

## 2026-03-09T21:05:00+01:00 — AI Rules Cleanup (v2.8 → v3.0)

**Context**: The AI assistant directives (`GEMINI.md`) had accumulated project-specific rules mixed with universal principles and existed as triple-duplicated copies, creating a drift risk.

**Decisions**:
1. Restructured to **Option B** — Split into Universal and Project-Specific rules.
2. Removed YouTube Shorts rule and Daily AI Wire branding from universal directives.
3. `GEMINI.md` is the single source of truth. Bumped to v3.0.

**Rollback**: Restore from `MEMORY[airules.md]` snapshot.

---

## 2026-03-09T21:16:00+01:00 — Investor-Ready Codebase Cleanup

**Context**: Codebase had ~200 files with one-off debug scripts, orphaned binaries, and stale docs. Not investor-ready.

**Decisions**:
1. Phased deletion on `cleanup/investor-ready-v2` branch — 6 phases, each with its own commit.
2. Removed ~80 files across 6 categories: root debug scripts (22), orphaned media (8), stale docs (8), one-off scripts (35), orphaned dirs (6 items).
3. Preserved all production code.

**Rollback**: `git checkout main` to return to pre-cleanup state.

---

## 2026-03-09T21:53:00+01:00 — Git Resync (Local → VPS)

**Context**: Local `main` diverged from `origin/main` by 457/407 commits due to a forgotten `filter-branch` rewrite. VPS declared as source of truth.

**Decisions**:
1. Reset local `main` to `origin/main` (`575fe28`).
2. Re-applied all cleanup phases on fresh `cleanup/investor-ready-v2` branch from the correct VPS history.
3. Deleted old diverged `cleanup/investor-ready` branch (superseded).

**Rollback**: N/A — the diverged local history was corrupted and had no unique production value.
