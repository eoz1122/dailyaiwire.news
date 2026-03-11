# DailyAIWire Product Roadmap (2026)

## 🎯 Vision

To transition from a "News Aggregator" to an **"Autonomous Intelligence Refinery"**. We do not just report the news; we synthesize signal, adapt our interface to the content's sentiment, and defend against the noise of the dead internet.

---

## ✅ Phase 1: The "Iron Dome" (Completed Q1 '26)

**Objective:** Infrastructure Hardening & Adversarial Defense.

- [x] **Adversarial Spam Filter:** 3-Layer defense (DB Blacklist, Heuristics, AI Sentiment) to filter affiliate microsites.
- [x] **EU AI Act Compliance:** Automated transparency labeling ("Art. 50 Verified") on all AI-synthesized content.
- [x] **Instant Indexing:** Google Indexing API integration for <10min crawl times.
- [x] **Web Indexing:** Sitemap and indexing infrastructure optimized for fast discovery.
- [x] **Resilient Scheduler:** Self-healing social distribution pipeline.
- [x] **Editorial Guidelines (Q1 '26):** Implemented automated "Safety Filters" (Suicide/Murder blocks) and "Quality Thresholds" (Min Score 50).
- [x] **Semantic Search:** Upgraded from SQL `LIKE` to Qdrant vector search with automatic keyword fallback.
- [x] **Editorial Compass (RAG):** `bge-large-en-v1.5` + Qdrant for editorial scoring and semantic deduplication.
- [x] **Smart Deduplication:** Historical dedup sweep using Qdrant vector similarity + admin review dashboard.

## ✅ Phase 2: Generative UI (Shipped Q1 '26)

**Objective:** A "Living" Frontend that adapts to the story.

- [x] **Adaptive CSS Engine:** Frontend consumes `design_tokens` (Intensity, Sentiment) to change colors/fonts per article.
  - *Two-tier CSS variables:* `--genui-brand-*` (always blue) + `--genui-signal-*` (sentiment-driven).
- [x] **Dynamic Components:** AI decides *layout* via `component_triggers`.
  - *Shipped:* `quick_facts_grid`, `market_ticker`. Removed `code_block` (made deep analysis look like raw markdown).
- [x] **Automated Article Visuals (DeepDiagram):** AI-generated mermaid diagrams for technical articles. Gemini decides per-article; rendered client-side with Mermaid.js dark theme.

## 🔮 Phase 3: Agentic Optimization (GEO)

**Objective:** Optimizing for AI Search (Perplexity/SearchGPT) over Google.

- [x] **`llms.txt` Standard:** Deployed to guide AI crawlers.
- [x] **Tavily RAG Research Layer:** (Implemented as DuckDuckGo Deep Research — free, no API key)
  - Deep web enrichment for high-signal articles during fetch pipeline.
  - Finds primary sources, whitepapers, and official docs to cross-reference headlines.
- [x] **Answer-Engine API:** `GET /api/intelligence` + `/api/intelligence/<slug>` JSON endpoints for AI agents (Perplexity, SearchGPT). CORS + Cache-Control. `llms.txt` deployed.
- [x] **"The Signal" Newsletter:** Public archive at `/signal`, web-readable past editions, `--auto` mode for `weekly_curator.py` with trend snapshot injection.

## 🛡️ Phase 4: Administrative Supremacy

**Objective:** Full control from the dashboard.

- [x] **Author-Aware Search:** Admin panel now searches by Author and Title.
- [x] **Source Management UI:** Add/Ban sources directly from the dashboard without SQL scripts.
- [x] **Admin Panel Redesign:** Standalone light-mode interface, fully responsive, decoupled from public site.
- [x] **Trend Intelligence Engine:** SQL-driven trend detection (surging categories, trending hashtags, emerging keywords).
- [x] **Manual Override Mode:** "Emergency Override" — global site kill switch from Admin UI with maintenance page (503), confirmation safety, and Google deindex/re-crawl signals.

## 🏗️ Phase 5: Architectural Refactoring

**Objective:** Reduce tech debt before scaling.

- [x] **R2: Blueprint Split:** `app.py` split from 1,967 lines to 275-line factory + 8 Blueprint modules.
- [x] **R4: Shared DB Layer:** Single `db.py` module with `get_db_connection()`.
- [x] **R5: Cleanup:** Deploy script fixed, test audio removed, requirements deduped.
- [x] **R1: Safety Net:** pytest + 62 smoke tests covering all route groups (public, admin, API, SEO) and helpers. 0% → baseline coverage.
- [x] **R3: Fetcher Decomposition:** Split `fetcher.py` (1,341 lines) into 7 focused modules under `fetcher/` package, with backward-compat shim.

## 🔮 Phase 6: Future Architecture & AdCP

**Objective:** Scaling the ecosystem using Agentic standards.

- [ ] **Infrastructure Upgrade (vibe-to-prod):**
  - **Goal:** Investigate migrating the stack to a production-ready template (Go/Echo + Next.js + Cloud Run).
  - **Why:** To support high-concurrency AdCP agents and robust CI/CD pipelines.
- [ ] **Ad Context Protocol (AdCP) Prototype:**
  - **Status:** *In Planning*.
  - **Goal:** Build the first reference implementation of an AdCP-compliant agent ("AdAgent Alpha").
  - **Tech:** FastMCP + Gemini.

**Objective:** Latent Readiness for a post-ad-tech economy ("Value-Capture" Architecture), aligned with the **Ad Context Protocol (AdCP)**.

- [ ] **Attribution Ledger:** Transition from single-source to multi-source "provenance chains" to track value contribution for future revenue sharing.
- [ ] **Universal Opt-Out Firewall:** Proactive "Ingestion Firewall" that logs and respects `/.well-known/llms.txt` and TDM reservations to ensure "Clean Feed" status.
- [ ] **Contextual Value Injection (AdCP Integration):**
  - **Concept:** Replace programmatic ads with a sovereign `sponsorship_injection` engine.
  - **Mechanic:** Scan text for entities (e.g., "Nvidia") -> Match `sponsor_context` -> Inject "Native Sponsor Card".
  - **Metric:** Optimize for `impression_quality` and relevance, purely server-side.
