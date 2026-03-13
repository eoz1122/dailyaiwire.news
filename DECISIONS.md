# DECISIONS.md — Daily AI Wire News
# Architectural Decision Log

Architectural decision log for the Daily AI Wire News project. Every entry includes an ISO 8601 timestamp per §6 of the AI Directives.

---

## 2026-03-12T14:51:00+01:00 — Curated LinkedIn RSS Feed (`/rss/linkedin`)

**Decision**: Created a separate, quality-filtered RSS feed endpoint for the n8n → LinkedIn pipeline. Rather than posting all ~48 articles/day, the LinkedIn feed serves ≤20 top-signal articles with category diversity and time-window filtering.

**Filters applied**:
- `importance_score >= 80` (quality gate)
- `ROW_NUMBER() OVER (PARTITION BY category)` with max 3 per category (diversity)
- `LIMIT 20` (hard cap)
- Excludes articles published between 02:00-08:00 CET (EU+US dead zone)

**Changes**:
- `routes/seo.py`: New `linkedin_rss_feed()` route at `/rss/linkedin`. Reuses existing `rss.xml` template and `clean_summary` builder logic. No Lab posts — news-only.
- `tests/conftest.py`: Added third seed article (`importance_score=90`, category `Research`) for LinkedIn feed test coverage.
- `tests/test_smoke.py`: New `test_linkedin_rss_feed` in `TestSEORoutes`.

**Tests**: 84/84 passing (83 existing + 1 new).

**Next step**: Deploy to VPS and update n8n workflow to point from `/rss` → `/rss/linkedin`.

**Rollback**: Remove `linkedin_rss_feed()` from `routes/seo.py`. Remove seed article and test from `tests/`. Original `/rss` feed is completely untouched.

---

## 2026-03-11T22:07:00+01:00 — Instagram Distribution Worker

**Decision**: Added Instagram Graph API publishing to the social distribution pipeline. Follows the same architecture as the existing X/Twitter poster (two-step container → publish flow). Worker is "credential-gated" — gracefully skips when `IG_USER_ID` / `IG_ACCESS_TOKEN` are not set, so deployment is safe before Meta App Review is approved.

**Changes**:
- `social_distributor.py`: New `post_to_instagram()` method — image URL normalization (relative→absolute), caption builder (headline + gist + question + hashtags + link, 2,200 char limit), container status polling with retry, rate-limit re-raise for scheduler backoff. Added to `distribute()` chain.
- `tweet_scheduler.py`: Passes `image` field in article dict, calls `post_to_instagram()` independently with `shared_on_ig` tracking, new `mark_as_shared_ig()` helper.
- `scripts/migrate_instagram.py` [NEW]: Idempotent migration adding `shared_on_ig BOOLEAN DEFAULT 0` to articles table.
- `.env.example`: Added `IG_USER_ID` and `IG_ACCESS_TOKEN` placeholders.
- `tests/test_instagram.py` [NEW]: 6 unit tests (credential skip, no-image skip, relative→absolute URL, absolute URL passthrough, caption content validation, 2,200 char limit enforcement).

**Prerequisites** (manual, human-only): Instagram Business/Creator account, Facebook Page link, Meta Developer App with `instagram_business_content_publish` permission, long-lived access token.

**Tests**: 83/83 passing (77 existing + 6 new). Migration verified on local DB.

**Rollback**: Remove `post_to_instagram()` from `social_distributor.py` and `distribute()` chain. Remove IG block from `tweet_scheduler.py`. Delete `scripts/migrate_instagram.py` and `tests/test_instagram.py`. Run `ALTER TABLE articles DROP COLUMN shared_on_ig` (SQLite 3.35+).

---

## 2026-03-11T10:30:00+01:00 — Bare Except Cleanup (19 fixes across 12 files)

**Decision**: Replaced all 19 remaining bare `except:` statements with specific exception types. Routes were cleaned in the previous session; this pass covers scripts/, services/, fetcher/, and utility files. All replacements are behavior-preserving (catches the same runtime errors) but now properly propagate `SystemExit`, `KeyboardInterrupt`, and `GeneratorExit`.

**Changes**:
- `deploy_email_feature.py`: `except:` → `except Exception:`
- `services/proposal_agent.py`: `except:` → `except (json.JSONDecodeError, ValueError):`
- `services/lead_extractor.py`: `except:` → `except Exception:`
- `scripts/backfill_last_10_audio.py`: `except:` → `except (json.JSONDecodeError, ValueError, TypeError):`
- `scripts/generate_diagrams.py` (×2): `except:` → `except (json.JSONDecodeError, ValueError, TypeError):`
- `scripts/create_intro.py` (×3): `except:` → `except Exception:`
- `scripts/publish_backlog.py`: `except:` → `except Exception:`
- `scripts/convert_killed_to_leads.py`: `except:` → `except (ValueError, AttributeError):`
- `audio_generator.py` (×2): `except:` → `except OSError:` and `except Exception:`
- `scripts/recover_missing_audio.py`: `except:` → `except (json.JSONDecodeError, ValueError, TypeError):`
- `fetcher/db_init.py`: `except:` → `except sqlite3.OperationalError:`
- `fetcher/sources.py`: `except:` → `except (ValueError, AttributeError):`
- `fetcher/persistence.py`: `except:` → `except (sqlite3.OperationalError, TypeError):`
- `generate_missing_audio.py`: `except:` → `except (json.JSONDecodeError, ValueError, TypeError):`
- `tweet_scheduler.py`: `except:` → `except (ValueError, TypeError):`

**Tests**: 77/77 passing. Zero bare `except:` remaining (verified via grep).

**Rollback**: `git diff HEAD` shows only `except:` → `except SpecificType:` changes. `git checkout -- <file>` for any individual file, or `git revert <commit>` for the full batch.

---

## 2026-03-11T02:50:00+01:00 — Lighthouse Performance Optimization

**Decision**: Performance pass per AI Rules §5 (target 90+ mobile). Focused on render-blocking resources, cache policy, and image loading. Performance score improved from **58 → 70** (+20%), with FCP **5.5s → 3.4s** (−38%) and LCP **12.2s → 5.3s** (−57%).

**Changes**:
- `templates/base.html`: Google Fonts swapped from sync `<link>` to `preload`+`onload` pattern. AdSense `<script>` moved from `<head>` to before `</body>`. Duplicate preconnect comment removed. Added `cdn.jsdelivr.net` preconnect.
- `app.py`: `Cache-Control: no-store` on all responses replaced with content-type-aware policy: HTML → no-store, static assets → 1yr immutable, everything else → 1hr.
- `templates/index.html`: Added `decoding="async"` to carousel and grid images.

**Note**: True 90+ requires replacing Tailwind CDN (JIT compiles in-browser) with a pre-built CSS file — a larger refactor for a future pass.

**Rollback**: Revert `base.html` font/AdSense changes. Restore `Cache-Control: no-store` in `app.py`. Remove `decoding="async"` from `index.html`.

---

## 2026-03-11T02:35:00+01:00 — Error Handling Hardening

**Decision**: Comprehensive error handling pass — registered Flask error handlers, created branded error pages, protected admin CRUD, cleaned bare `except:` in production routes, and fixed CSP for Mermaid.js CDN.

**Changes**:
- `app.py`: Registered `@app.errorhandler` for 404, 500, 403, 429. Added `cdn.jsdelivr.net` to CSP `script-src`. Imported `render_template`.
- `templates/403.html` [NEW]: Branded "Access Denied" page with lock icon.
- `templates/429.html` [NEW]: Branded "Rate Limited" page with clock icon.
- `templates/500.html` [EXISTING]: Already existed, now wired to handler.
- `templates/404.html` [EXISTING]: Already existed, now wired to handler.
- `routes/admin_core.py`: Wrapped article create/edit/delete in try/except with `sqlite3.IntegrityError` handling.
- `routes/public.py`: Replaced 10 bare `except:` with specific exception types.
- `tests/test_smoke.py`: 3 new tests (77 total).

**Rollback**: Remove error handlers from `app.py`. Delete `403.html`, `429.html`. Revert `admin_core.py` and `public.py` try/except changes.

---

## 2026-03-11T01:57:00+01:00 — Phase 2: DeepDiagram (Automated Article Visuals)

**Decision**: Added AI-powered mermaid diagram generation for technical articles. Gemini generates Mermaid.js syntax during article ingestion; diagrams render client-side with dark theme matching brand colors. Progressive enhancement — articles without diagrams are unaffected.

**Changes**:
- `fetcher/ai_processor.py`: Added `mermaid_diagram` field to Gemini prompt JSON schema. AI decides per-article whether a diagram adds value (null for opinion/non-visual pieces).
- `routes/public.py`: Extracts `mermaid_diagram` from `full_json` column on article detail pages.
- `templates/article.html`: Conditional Mermaid.js CDN load, "Visual Intelligence" section between Deep Analysis and Impact Assessment, dark-theme Mermaid.js initialization with brand color variables.
- `scripts/generate_diagrams.py` [NEW]: Backfill CLI for existing high-value articles (`--limit`, `--min-score`, `--dry-run` flags).
- `tests/conftest.py`: Added test article with diagram fixture.
- `tests/test_smoke.py`: 2 new tests (74 total) — diagram rendering positive and negative paths.
- `ROADMAP.md`: Removed "Audio-First Experience" item (per Architect directive).

**Rollback**: Remove `mermaid_diagram` field from `ai_processor.py` prompt. Revert `routes/public.py` extraction block. Remove Mermaid.js CDN, Visual Intelligence section, and init script from `article.html`. Delete `scripts/generate_diagrams.py`.

---

## 2026-03-11T00:13:00+01:00 — Phase 3: Agentic Optimization (GEO)

**Decision**: Shipped all three Phase 3 items: Deep Research (DuckDuckGo, free), Answer-Engine API, and "The Signal" Newsletter.

**Changes**:
- `tavily_research.py` [NEW]: Deep web research using DuckDuckGo Search (free, no API key). Enriches high-signal article prompts with primary sources, whitepapers, and official docs.
- `routes/api.py`: Added `GET /api/intelligence` (feed with category/score/date filters, CORS, Cache-Control) and `GET /api/intelligence/<slug>` (full article detail).
- `static/llms.txt` [UPDATED]: AI crawler guidance file documenting all endpoints and content structure.
- `routes/seo.py`: Added `/llms.txt` and `/.well-known/llms.txt` routes.
- `routes/signal.py` [NEW]: Public newsletter archive (`/signal`) and detail (`/signal/<id>`) pages.
- `templates/signal.html` [NEW]: Archive page with subscribe CTA. `templates/signal_detail.html` [NEW]: Web view of individual editions.
- `templates/base.html`: Added "The Signal" to desktop and mobile navigation.
- `weekly_curator.py`: Added `--auto` flag for unattended curation with trend snapshot injection.
- `fetcher/ai_processor.py`: Deep research enrichment for high-signal headlines (keyword heuristic trigger).
- `requirements.txt`: Added `duckduckgo-search`.
- `app.py`: Registered `signal_bp` Blueprint.
- `tests/test_smoke.py`: 10 new tests (72 total): Answer-Engine API (7), Signal (2), llms.txt (1).

**Rollback**: Delete `tavily_research.py`, `routes/signal.py`, `templates/signal*.html`. Revert `routes/api.py`, `routes/seo.py`, `fetcher/ai_processor.py`, `weekly_curator.py`, `templates/base.html`, `app.py`.

---

## 2026-03-10T23:48:00+01:00 — Phase 4: Emergency Override (Manual Kill Switch)

**Decision**: Added a global "Emergency Override" that takes the entire public site offline with a branded maintenance page (HTTP 503). Admin panel remains fully accessible during override.

**Changes**:
- `routes/admin_emergency.py` [NEW]: Toggle endpoint with `CONFIRM` safety parameter. Google deindex/re-crawl signals via `notify_google_index()`.
- `templates/maintenance.html` [NEW]: Standalone dark-themed maintenance page with animated grid + pulsing status badge. Returns 503 + `Retry-After`.
- `app.py`: `before_request` middleware checks `metadata.emergency_mode`. Allows `/admin`, `/login`, `/logout`, `/static` through. New Blueprint registered.
- `templates/admin/index.html`: Emergency Override banner at the top of dashboard. Expandable `<details>` panel with text confirmation. Active state shows pulsing red alert with one-click lift button.

**Rollback**: Remove `routes/admin_emergency.py`, `templates/maintenance.html`. Revert `app.py` (remove `before_request` hook and Blueprint registration). Revert `admin/index.html` emergency banner block.

---

## 2026-03-10T23:48:00+01:00 — Phase 5 R3: Fetcher Decomposition

**Decision**: Decomposed the 1,341-line `fetcher.py` monolith into 7 focused modules inside a `fetcher/` package.

**Changes**:
- `fetcher/__init__.py` [NEW]: Orchestrator with `main()` and `main_loop()` re-exports.
- `fetcher/db_init.py` [NEW]: Schema creation, lazy migrations, scan metadata helpers.
- `fetcher/sources.py` [NEW]: RSS fetching, fuzzy dedup, AI headline filter.
- `fetcher/content.py` [NEW]: URL content extraction + SSRF protection.
- `fetcher/spam.py` [NEW]: Keyword/heuristic/blocklist spam defense.
- `fetcher/ai_processor.py` [NEW]: Gemini batch processing + prompt template.
- `fetcher/persistence.py` [NEW]: `save_to_db()`, social queue, Google/Qdrant indexing.
- `fetcher.py`: Replaced 1,341 lines with 14-line backward-compat shim. `python fetcher.py --loop` still works.

**Rollback**: Delete `fetcher/` directory, restore original `fetcher.py` from git.

---

## 2026-03-10T23:48:00+01:00 — Phase 5 R1: Safety Net (pytest Smoke Tests)

**Decision**: Added pytest and 62 smoke tests to establish baseline test coverage (previously 0%).

**Changes**:
- `requirements.txt`: Added `pytest`.
- `tests/__init__.py` [NEW]: Package marker.
- `tests/conftest.py` [NEW]: Shared fixtures — temporary SQLite DB, seeded test article, `client` (unauthenticated) and `auth_client` (authenticated) Flask test clients.
- `tests/test_smoke.py` [NEW]: 40 smoke tests across 6 classes — `TestAppBoot` (3), `TestPublicRoutes` (12), `TestAuthGuard` (5), `TestAdminRoutesAuthenticated` (6), `TestAPIRoutes` (5), `TestSEORoutes` (4).
- `tests/test_helpers.py` [NEW]: 22 unit tests for `slugify`, `remove_emojis`, `time_ago`, `add_utm_to_html`.

**Rollback**: Delete `tests/` directory, remove `pytest` from `requirements.txt`.

---

## 2026-03-10T22:25:00+01:00 — Restored Newsletter Subscription Popup

**Decision**: Restored the 5-second delayed newsletter popup that was accidentally removed during the Blueprint refactor (Phase 5). Recovered original code from git history.

**Features**: 5s `setTimeout` trigger, 30-day `localStorage` suppression after close, backdrop blur dismiss, close button (44px min touch target), glassmorphism card design, form action `/subscribe`.

**Rollback**: Remove the `newsletter-modal` div and its `<script>` from `templates/base.html`.

---

## 2026-03-10T22:10:00+01:00 — Trend Engine Keyword Filtering + Category Cleanup

**Decision**: Expanded keyword stopwords from ~120 to ~200+ words to filter generic news verbs ("unveils", "reveals") and broad nouns ("public", "company"). Raised minimum keyword frequency from 2→4. Fixed category pills to hide categories with 0 published articles.

**Changes**:
- `trend_engine.py`: Added generic news headline verbs, broad nouns, and AI-site-generic terms to STOPWORDS.
- `routes/public.py`: Category query now uses `WHERE is_published = 1 HAVING cnt > 0`.

**Rollback**: Revert STOPWORDS in `trend_engine.py` and the category query in `routes/public.py`.

---

## 2026-03-10T16:35:00+01:00 — Carousel Management Feature (Manual Ordering + Timers)

**Decision**: Added editorial control over the homepage carousel. Editors can pin articles, set display order, and define expiry timers (1h, 4h, 12h, 24h, 48h, 1w, custom, or no expiry). Pinned articles appear first in the carousel; auto-selected articles fill remaining slots.

**Changes**:
- `app.py`: `carousel_slots` table migration, Blueprint registration, `carousel_pinned_ids` passed to dashboard.
- `routes/admin_carousel.py` [NEW]: Pin, unpin, reorder, update-timer endpoints.
- `routes/public.py`: Pinned-first hybrid carousel query (expiry checked at query time — no cron needed).
- `templates/admin/carousel.html` [NEW]: Management UI with sortable slots, timer controls, quick-pin panel.
- `templates/admin/base_admin.html`: "Carousel" link in sidebar.
- `templates/admin/index.html`: Pin/unpin buttons on article rows.

**Rollback**: Remove `carousel_slots` table, `admin_carousel_bp` Blueprint, and revert template changes.

---

## 2026-03-10T16:32:00+01:00 — Phase 5: Architectural Refactoring (Blueprint Split + Shared DB)

**Decision**: Split the 1,967-line `app.py` monolith into 8 Flask Blueprints + slim app factory. Created shared `db.py` database module. Cleaned up stale files and synced ROADMAP.md.

**Changes**:
- `app.py`: Reduced from 1,967 → 275 lines. Now contains only app setup, Flask-Admin dashboard view, context processor, security headers, and Blueprint registration.
- `db.py` [NEW]: Shared `get_db_connection()` with Row factory + `DB_PATH`.
- `helpers.py` [NEW]: Extracted template filters (`time_ago`, `remove_emojis`, `add_utm_to_html`, `slugify`).
- `routes/public.py` [NEW]: Homepage, article, static pages, subscribe (9 routes).
- `routes/api.py` [NEW]: Search, trends, audio tracking, newsletter tracking (4 routes).
- `routes/auth.py` [NEW]: Login, logout, user management, Flask-Login init (5 routes).
- `routes/seo.py` [NEW]: Sitemap, robots, RSS feed, favicon (6 routes).
- `routes/lab.py` [NEW]: Lab index, lab post (2 routes).
- `routes/admin_core.py` [NEW]: Article CRUD, file manager, author profile (5 routes).
- `routes/admin_content.py` [NEW]: Newsletters, editorials, social queue, audio/video gen, subscribers (15 routes).
- `routes/admin_ops.py` [NEW]: Sources, leads, duplicates, budget, kill article (14 routes).
- All 32 template files: `url_for()` calls updated with Blueprint prefixes.
- `fetcher.py`: Removed duplicate `get_db_connection()`, now imports from `db.py`.
- `deploy_to_vps.sh`: Fixed branch from `iron-judo-v1` → `main`.
- `ROADMAP.md`: Synced 12+ shipped features, added Phase 5 section.
- `requirements.txt`: Removed 4 duplicate entries.
- Deleted 4 stale test audio files.

**Rationale**: `app.py` at 1,967 lines was untenable for development velocity — no IDE could navigate it efficiently, and new contributors would be overwhelmed. Blueprint split enables per-module ownership, parallel development, and cleaner git diffs. Shared `db.py` eliminates 2 conflicting `get_db_connection()` implementations.

**Rollback**: `git revert` the refactoring commit. The old monolithic `app.py` will restore all route registrations inline. Templates' `url_for()` calls will need reverting (remove Blueprint prefixes).

---

## 2026-03-10T13:04:00+01:00 — Phase 2: Generative UI — Adaptive CSS Engine

**Decision**: Implemented the Adaptive CSS Engine that consumes AI-generated `design_tokens` (intensity, sentiment_pallet, component_triggers) to dynamically theme article pages. Uses CSS Custom Properties architecture for maintainability.

**Changes**:
- `article.html`: CSS custom properties engine with 3 sentiment palettes (crisis/red, warning/amber, optimist/blue), intensity badge with critical pulse animation, hero overlay gradient, gist box, section borders, CTA buttons, audio player, all themed adaptively. Dynamic components: `quick_facts_grid`, `code_block` terminal aesthetic, `market_ticker` scrolling bar.
- `index.html`: Homepage cards show left-border accent + intensity badge for critical/high articles.
- `app.py`: `index()` route now parses `design_tokens` JSON for homepage articles.

**Rationale**: design_tokens were already being generated by Gemini and stored in the DB since Phase 0, but never consumed by the frontend. This closes that gap with zero backend changes needed.

**Rollback**: Revert commits to `article.html`, `index.html`, and `app.py`. Articles without design_tokens render identically to the pre-change state (progressive enhancement).

---

## 2026-03-10T10:25:00+01:00 — Admin Panel: Light Mode + Responsiveness + Decoupled from Public Site

**Decision**: Redesigned the admin panel to be a standalone light-mode interface, fully decoupled from the public `base.html`. Improved responsiveness by switching breakpoints from `md` (768px) to `lg` (1024px).

**Changes**:
- `templates/admin/base_admin.html`: Made standalone HTML (no longer extends `base.html`). Removed sliding ticker, WIRE/LAB/TERMINAL/REPORTS tabs, footer, and theme toggle. Converted all colors from dark mode (zinc-800/900) to light mode (white/gray-50).
- `templates/admin/index.html`: Converted all dashboard content (stats cards, table, mobile cards, pagination) to light mode. Changed card/table layout breakpoint from `md` to `lg` so tablets get the card layout.

**Rollback**: Revert commits `ee769a7`, `5fbbc86`, `e17774c`. Restore `base_admin.html` to extend `base.html` with `{% extends "base.html" %}`.

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
