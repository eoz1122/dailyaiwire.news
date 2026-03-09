# DECISIONS.md — Daily AI Wire News

# Architectural Decision Log

Architectural decision log for the Daily AI Wire News project. Every entry includes an ISO 8601 timestamp per §6 of the AI Directives.

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
