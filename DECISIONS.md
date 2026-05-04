# DECISIONS.md — Daily AI Wire News
# Architectural Decision Log

Architectural decision log for the Daily AI Wire News project. Every entry includes an ISO 8601 timestamp per §6 of the AI Directives.

---

## 2026-05-01T17:43:24+02:00 - Migrate Shared Gemini Gateway to Google GenAI with Thinking Controls

**Context**: The emergency cost brake moved routine deduplication to Flash-Lite, but the shared `services/ai_gateway.py` still used the deprecated `google.generativeai` SDK. That SDK path did not expose explicit thinking-budget controls, leaving Gemini 2.5 structured calls vulnerable to billable dynamic thinking tokens.

**Changes**:
- Migrated `services/ai_gateway.py` from `google.generativeai` to `google.genai`.
- Added per-call `thinking_budget` support through `types.ThinkingConfig`.
- Added `AIGateway.generate_text()` so non-JSON decision calls can use the same model routing, logging, timeout, and thinking controls.
- Set `ARTICLE_THINKING_BUDGET` and `ROUTINE_THINKING_BUDGET` env-controlled defaults in `ai_config.py`, both defaulting to `0`.
- Applied `ARTICLE_THINKING_BUDGET` to article analysis.
- Moved headline filtering in `fetcher/sources.py` from direct `google.generativeai` + article model usage to the shared gateway with the routine model.
- Applied `ROUTINE_THINKING_BUDGET` to semantic deduplication and legacy dedup.
- Moved lead extraction to the routine model path and routine thinking budget.
- Preserved legacy timeout behavior by translating old second-based `request_options.timeout` to Google GenAI millisecond `HttpOptions.timeout`.

**Verification**:
- `python3 -m pytest tests/test_ai_governance.py -q` -> passed.
- `python3 -m pytest tests/test_ai_governance.py tests/test_source_quality.py -q` -> passed.
- `python3 -m py_compile ai_config.py services/ai_gateway.py fetcher/ai_processor.py fetcher/sources.py remove_duplicates.py ai_dedup.py services/lead_extractor.py tests/test_ai_governance.py tests/test_source_quality.py` -> passed.
- `git diff --check` -> passed.
- `python3 -m pytest -q` -> passed, `200 passed, 1 skipped`.

**Rollback**:
- Revert the code commit.
- If article quality drops, set `GEMINI_ARTICLE_THINKING_BUDGET` to a positive budget before reverting the full migration.

---

## 2026-05-01T17:30:53+02:00 - AI Cost Brake for Dedup and Validation Retries

**Context**: Google AI billing jumped sharply in the final week of April 2026. Production logs showed article volume increased, but not enough to explain the spend. The larger issue was that `tweet_scheduler.py` ran semantic duplicate review every 10 minutes, and after source throughput recovered this repeatedly called `gemini-2.5-flash` for recent headline sets. Article analysis also retried paid calls when `INSUFFICIENT_DATA` responses left fields empty, even though those rows were intended to be skipped.

**Changes**:
- Added `GEMINI_ARTICLE_MODEL` and `GEMINI_ROUTINE_MODEL` routing in `ai_config.py`.
- Kept article synthesis on `gemini-2.5-flash`.
- Moved semantic duplicate review to `gemini-2.5-flash-lite`.
- Added `ai_dedup_runs` prompt-signature caching so the scheduler does not pay for the same recent headline set every 10 minutes.
- Updated `ArticleAnalysis` validation so `INSUFFICIENT_DATA` can carry empty fields and be skipped without paid retries.
- Updated `ai_logs.cost_estimate` to prefer `total_token_count` and include `thoughts_token_count` when available, improving visibility into billed Gemini 2.5 usage.

**Verification**:
- `python3 -m pytest tests/test_ai_governance.py -q` -> passed.
- `python3 -m py_compile ai_config.py services/ai_gateway.py services/ai_schemas.py remove_duplicates.py ai_dedup.py tests/test_ai_governance.py` -> passed.
- `python3 -m pytest -q` -> passed, `200 passed, 1 skipped`.

**Rollback**:
- Revert the code commit.
- If `ai_dedup_runs` exists in production, it can remain unused. It only stores prompt hashes and article counts.

---

## 2026-05-01T16:58:02+02:00 - Curated Fallback Images for Onsite Article Cards

**Context**: Science article cards could use `/static/fallbacks/science_1.jpg`, an anatomical heart image that is irrelevant for generic AI research and cognitive-decline coverage. AI Agents fallbacks also pointed at missing `agents_*.jpg` files, which forced browser-level image fallback behavior and made onsite thumbnails inconsistent.

**Changes**:
- Added `services/image_fallbacks.py` as the shared source of truth for onsite fallback images.
- Removed the anatomical heart image from the Science fallback pool.
- Replaced missing AI Agents and Ethics fallback paths with existing neutral technology, society, policy, and security assets.
- Updated fetcher persistence to use the shared fallback selector for future articles.
- Updated `scripts/backfill_social_images.py` to repair existing rows that use disallowed or missing fallback images while preserving `social_image` previews.

**Verification**:
- `python3 -m pytest tests/test_image_fallbacks.py tests/test_backfill_social_images.py tests/test_persistence_images.py -q` -> passed.
- `python3 -m py_compile services/image_fallbacks.py fetcher/persistence.py scripts/backfill_social_images.py` -> passed.
- `git diff --check` -> passed.
- `python3 -m pytest -q` -> passed, `196 passed, 1 skipped`.

**Rollback**:
- Revert the code commit.
- If the production backfill has run, restore specific article `image` values manually only where needed. `social_image` does not need rollback because it remains the correct social preview field.

---

## 2026-05-01T16:31:45+02:00 - Separate Onsite Thumbnails from Social Preview Cards

**Context**: Recent article listing cards were showing generated social cards with oversized headline text, then repeating the same headline in the article card body. This made the homepage look templated and reduced editorial trust. X previews were also unreliable because posted X URLs used UTM query strings that rendered with `noindex`, and static social images were served with `X-Robots-Tag: noindex`.

**Changes**:
- Added `articles.social_image` for OG/Twitter preview assets.
- Kept `articles.image` for onsite thumbnails and article hero display.
- Updated fetcher persistence so generated text cards go to `social_image`; source images remain onsite thumbnails; missing source images use category fallbacks onsite.
- Updated article meta tags and `NewsArticle` structured data to prefer `social_image` for social previews while keeping the visible article image separate.
- Updated X post text to use the canonical article URL without UTM parameters, improving card crawler compatibility.
- Added `/social-image/<file>` as a non-static social preview image route so crawlers can fetch generated preview cards without inheriting Nginx static asset headers.
- Removed static `X-Robots-Tag: noindex` from `nginx_optimized.conf` so social preview images can be fetched cleanly.
- Added `scripts/backfill_social_images.py` to move existing `/static/img/social/...` values out of onsite `image` and into `social_image`.

**Verification**:
- `python3 -m pytest tests/test_persistence_images.py tests/test_x_posting.py tests/test_social_images.py tests/test_backfill_social_images.py tests/test_smoke.py::TestAppBoot -q` -> passed.
- `python3 -m pytest -q` -> passed, `192 passed, 1 skipped`.
- `python3 -m py_compile fetcher/persistence.py social_distributor.py scripts/backfill_social_images.py app.py fetcher/db_init.py` -> passed.
- `git diff --check` -> passed.

**Rollback**:
- Revert the code commit.
- Restore Nginx from `/etc/nginx/sites-available/dailyaiwire.pre-social-image-fix-*` if deployed.
- If the DB backfill was run, reverse only rows where `social_image` starts with `/static/img/social/` and `image` starts with `/static/fallbacks/` by copying `social_image` back into `image`.

---

## 2026-05-01T14:56:42+02:00 - Google Indexing API Audit Trail

**Context**: Article publication already calls Google Indexing API after database insert, but the result was only printed to process logs. That made it hard to prove which article URLs were notified, which attempts failed, and which failures should be retried.

**Changes**:
- Added `indexing_notifications` as a durable audit table for URL, action, status, status code, response body, error, and attempt timestamp.
- Added `services/indexing_audit.py` as the single audit helper for schema creation, recording, summary metrics, admin listing, and retry candidate selection.
- Updated `google_indexer.notify_google_index()` to record `success`, `failed`, `quota_exceeded`, and `skipped` attempts without blocking article publication if audit storage fails.
- Added `/admin/indexing` and `/admin/indexing.csv` as read-only admin visibility for recent Google Indexing API attempts.
- Added `scripts/retry_indexing_notifications.py` to retry latest failed or quota-limited URL/action pairs without retrying older failures that later succeeded.

**Verification**:
- `./.venv/bin/python -m pytest tests/test_indexing_audit.py -q` -> passed.
- `./.venv/bin/python -m pytest tests/test_smoke.py::TestAppBoot tests/test_indexing_audit.py -q` -> passed.

**Rollback**:
- Revert `services/indexing_audit.py`, `routes/admin_indexing.py`, `templates/admin/indexing.html`, `scripts/retry_indexing_notifications.py`, and related edits in `google_indexer.py`, `app.py`, `fetcher/db_init.py`, `templates/admin/base_admin.html`, and tests.
- The rollback does not require data deletion. The `indexing_notifications` table can remain unused if the code is reverted.

---

## 2026-04-29T13:49:18+02:00 - Sitemap Indexability Gate for Quality-First Crawl Budget

**Context**: Article pages already expose source attribution, source links, deep analysis, impact assessment, key details, related links, and `NewsArticle` structured data. The remaining Search Console problem is not missing page sections, but scale: Google sees thousands of similarly structured aggregation pages and indexes only a small subset. A production dry run showed an initial permissive score would mark `6,029` of `6,060` published articles as sitemap-eligible, which would not solve crawl-budget dilution.

**Changes**:
- `services/indexability.py`:
  - Added a reusable `score_article()` engine with `SITEMAP_ELIGIBILITY_THRESHOLD = 88`.
  - Scores article depth, summary quality, impact text, key details, bull/bear tradeoffs, source URL, source class, image quality, and existing `importance_score * compass_score`.
  - Returns explicit strengths and blockers for future admin visibility.
- `routes/seo.py`:
  - Core and archive sitemaps now select more candidates than needed, then include only articles that pass the indexability gate.
  - Sitemap URLs remain capped at `500` core and `400` archive, but weak/high-importance-thin pages no longer enter just because their numeric importance is high.
- `tests/test_indexability.py`:
  - Added RED/GREEN coverage for accepting strong original articles, rejecting thin low-signal articles, and excluding thin high-importance articles from the core sitemap.

**Production Dry Run**:
- Published articles evaluated: `6,060`.
- Sitemap-eligible after threshold `88`: `937`.
- Estimated sitemap output remains `500` core + `400` archive, but from the strongest eligible set.
- Top exclusion signals: `low_context_source`, `fallback_image`, `thin_analysis`, `key_details`.

**Verification**:
- `python3 -m pytest tests/test_indexability.py -q` -> passed.
- `python3 -m pytest tests/test_indexability.py tests/test_smoke.py -q` -> passed.
- `python3 -m py_compile services/indexability.py routes/seo.py` -> passed.

**Rollback**:
- Revert `services/indexability.py`, `routes/seo.py`, and `tests/test_indexability.py`.
- If the threshold proves too strict in Search Console after recrawl, lower `SITEMAP_ELIGIBILITY_THRESHOLD` in small steps and verify sitemap counts before deployment.

---

## 2026-04-29T13:07:11+02:00 - Search Console Coverage Recovery: Smaller Archive Sitemap and Robots Cleanup

**Context**: Google Search Console coverage export on 2026-04-29 showed `1,676` pages in `Crawled - currently not indexed`, `116` 404s, `42` canonical alternatives, `36` other 4xx, and only `23` indexed pages. Live checks showed the site was technically reachable, query URLs were correctly `noindex, follow`, missing article URLs returned `410 Gone`, and most recent 404s were bot/security probes. The main controllable issue was still crawl-budget dilution from too many archive URLs.

**Changes**:
- `routes/seo.py`:
  - Reduced `ARCHIVE_SITEMAP_LIMIT` from `1200` to `400`.
  - Reduced `ARCHIVE_RECENCY_DAYS` from `180` to `45`.
  - Kept `ARCHIVE_MIN_QUALITY_SCORE = 65`.
  - Added `/apple-touch-icon.png` and `/apple-touch-icon-precomposed.png` aliases to the existing favicon asset to reduce repeated icon discovery 404s.
- `static/robots.txt`:
  - Kept only `Sitemap: https://dailyaiwire.news/sitemap.xml`, so the sitemap index remains the single source of truth.
- `tests/test_smoke.py`:
  - Added regression coverage for single sitemap index exposure in `robots.txt`.
  - Added coverage for the apple-touch icon aliases.
  - Added recovery-limit assertions for archive sitemap contraction.

**Verification**:
- `python3 -m pytest tests/test_smoke.py -k "robots_txt or touch_icon_aliases or sitemap_archive_is_contracted or sitemap_archive_returns_200 or sitemap_core_returns_200 or sitemap_index_cache_header" -q` -> passed.
- `python3 -m pytest tests/test_smoke.py -q` -> passed.
- `python3 -m py_compile routes/seo.py` -> passed.

**Rollback**:
- Revert `routes/seo.py`, `static/robots.txt`, and `tests/test_smoke.py`.
- If Search Console indexing improves and crawl budget stabilizes, archive size can be increased gradually in small steps rather than restoring the full `1200` URL archive immediately.

---

## 2026-04-28T17:42:58+02:00 - Deploy Script Restarts X Scheduler for Social Posting Changes

**Context**: Production was on the correct commit, but `tweet_scheduler.py` continued running an old in-memory process after deployment. The deploy script restarted `dailyaiwire` and optional `dailyaiwire_fetcher`, but did not restart the decoupled `tweet_scheduler` Supervisor program, so X posts kept using the old copy formatter until the process was manually restarted.

**Changes**:
- `deploy_to_vps.sh`:
  - Added `--with-scheduler` for explicit `tweet_scheduler` restarts.
  - Auto-detects scheduler-impacting changes in `tweet_scheduler.py`, `social_distributor.py`, `url_shortener.py`, and `requirements.txt`.
  - Restarts `tweet_scheduler` automatically when those files change.
  - Falls back to sending `TERM` to the owned scheduler process if limited sudo does not yet include `tweet_scheduler`, relying on Supervisor autorestart.
  - Includes scheduler restart intent in rollback command output when relevant.
- `.github/workflows/deploy-production.yml`:
  - Added a manual `restart_scheduler` input.
  - Passes `--with-scheduler` to the deploy script when requested.
- `DEPLOYMENT.md`:
  - Updated the production baseline to include `tweet_scheduler`.
  - Documented limited sudoers entries and monitoring commands for `tweet_scheduler`.
- `tests/test_deploy_script.py`:
  - Added regression coverage for the scheduler deploy option and scheduler-related auto-restart detection.

**Verification**:
- `bash -n deploy_to_vps.sh` -> passed.
- `python3 -m pytest tests/test_deploy_script.py -q` -> passed.
- `python3 -m pytest tests/test_x_posting.py -q` -> passed.
- `python3 -m py_compile social_distributor.py tweet_scheduler.py` -> passed.

**Rollback**:
- Revert `deploy_to_vps.sh`, `.github/workflows/deploy-production.yml`, `DEPLOYMENT.md`, and `tests/test_deploy_script.py`.
- If the scheduler restart fallback causes trouble, deploy with the previous script version and manually restart `tweet_scheduler` with Supervisor after social posting changes.

---

## 2026-04-28T00:08:00+02:00 - X Post Quality: Direct Article Cards and LinkedIn-Style Structure

**Context**: Automated X posts were lower quality than LinkedIn posts and used `s.dailyaiwire.news` short links. The shortener reduced the chance of X rendering the article card image, and the X copy lacked the editorial structure already used in the LinkedIn pipeline.

**Changes**:
- `social_distributor.py`:
  - Added `build_x_post_text()` as a reusable, tested X composer.
  - Replaced short links with direct `https://dailyaiwire.news/article/<slug>?utm_source=twitter...` URLs.
  - Kept Google indexing notifications on the canonical article URL without UTM parameters.
  - Added LinkedIn-style structure without a top source line: headline, category, gist, `Why it matters`, canonical article URL, question, and normalized hashtags.
  - Normalized malformed hashtags such as `AI Governance` into `#AIGovernance`.
- `tweet_scheduler.py`:
  - Added `category` and `why_it_matters` to the X scheduler payload.
  - Bumped scheduler version to `2.5.2`.
- `templates/admin/social_queue.html`:
  - Updated the manual X copy preview to use the same direct URL and editorial structure.
- `tests/test_x_posting.py`:
  - Added coverage for direct article URLs, no shortener usage, editorial structure, and hashtag normalization.
- `tests/test_smoke.py`:
  - Added admin social queue render coverage to verify direct X article URLs.

**Verification**:
- `python3 -m pytest -q tests/test_x_posting.py` -> passed.
- `python3 -m pytest -q tests/test_smoke.py -k "admin_social_queue or admin_newsletter_preview"` -> passed.
- `python3 -m py_compile social_distributor.py tweet_scheduler.py routes/admin_content.py` -> passed.

**Rollback**:
- Revert `social_distributor.py`, `tweet_scheduler.py`, `templates/admin/social_queue.html`, `tests/test_x_posting.py`, and `tests/test_smoke.py`.
- If direct URLs create an unexpected X card issue, restore the old `shorten(...)` call in `post_to_x()` while keeping the rest of the copy formatter.

---

## 2026-04-27T23:32:00+02:00 - X Scheduler Resilience: Billing-Aware Backoff for 402 and 429

**Context**: X posting resumed once credits were restored, but the scheduler previously treated `402 Payment Required` as a generic failure and retried again later without explicit billing state. That behavior was noisy and opaque, and the old X failure path also used a blocking `sleep(3600)` that paused the scheduler loop instead of keeping heartbeats visible.

**Changes**:
- `social_distributor.py`:
  - Added `XPostingPause` to represent scheduler-level pause signals for X posting.
  - Added `classify_x_exception()` to map:
    - `402 Payment Required` / no-credit responses -> `billing` pause
    - `429 Too Many Requests` -> `rate_limit` pause
  - `post_to_x()` now raises the pause signal for classified X API errors instead of flattening them into a generic `False`.
- `tweet_scheduler.py`:
  - Added `_build_x_backoff_window()` helper for deterministic backoff windows and labels.
  - Replaced the blocking X-side `time.sleep(3600)` failure path with non-blocking scheduler state:
    - `x_backoff_until`
    - `x_backoff_reason`
  - Scheduler now logs active X backoff state and continues heartbeats cleanly while paused.
  - Added `X_FAILURE_BACKOFF_SECONDS` env-configurable generic X failure backoff (default `3600`).
  - Bumped scheduler version to `2.5.1`.
- `tests/test_x_posting.py` [NEW]:
  - Added unit coverage for X billing pause classification, rate-limit pause classification, `post_to_x()` raising billing pause signals, and deterministic X backoff window construction.

**Verification**:
- `python3 -m pytest -q tests/test_x_posting.py` -> passed.
- `python3 -m pytest -q tests/test_smoke.py -k "editorial_share or admin_newsletter_preview"` -> passed.
- `python3 -m py_compile social_distributor.py tweet_scheduler.py` -> passed.

**Rollback**:
- Revert `social_distributor.py`, `tweet_scheduler.py`, and `tests/test_x_posting.py`.
- If needed, restore the old generic X failure behavior by removing `XPostingPause` classification and the scheduler-level X backoff state.

---

## 2026-04-27T23:15:00+02:00 - Social Distribution Simplification: Remove Meta Posting, Keep X Only

**Context**: Instagram and Facebook posting had been failing repeatedly in production due to invalid Meta session/account state, while X posting resumed after credits were restored. Continuing to expose Meta posting controls created noise in logs, unnecessary scheduler work, and operational ambiguity.

**Changes**:
- `tweet_scheduler.py`:
  - Added `META_POSTING_ENABLED` gate defaulting to `false`.
  - Scheduler now logs Meta as disabled and skips both Instagram and Facebook posting blocks unless explicitly re-enabled.
- `routes/admin_content.py`:
  - Restricted `/admin/editorial/share/<id>` to accept only platform `x`.
  - Removed manual editorial Instagram/Facebook publishing branches.
- `templates/admin/edit_editorial.html`:
  - Social share panel now exposes only `Post to X`.
  - Removed Instagram/Facebook button handling from the client-side share helper.
- `social_distributor.py`:
  - `distribute()` now runs the active X + LinkedIn flow only, with Meta excluded from the aggregate dispatch path.
- `tests/test_smoke.py`:
  - Added coverage to verify the editorial admin page only shows X sharing and that Meta platforms are rejected at the route boundary.

**Verification**:
- `python3 -m pytest -q tests/test_smoke.py -k "editorial_share or admin_newsletter_preview"` -> passed.
- `python3 -m pytest -q tests/test_instagram.py tests/test_facebook.py` -> passed.
- `python3 -m py_compile tweet_scheduler.py routes/admin_content.py social_distributor.py` -> passed.

**Rollback**:
- Set `META_POSTING_ENABLED=true` and restore the removed Instagram/Facebook branches in `routes/admin_content.py` and `templates/admin/edit_editorial.html`.
- Re-add Meta calls to the scheduler and `SocialDistributor.distribute()` if Meta publishing is intentionally brought back.

---

## 2026-04-25T20:56:00+02:00 - Fetcher Throughput Recovery: Source Auto-Repair + Google Wire Fallback

**Context**: Production logs showed a sharp drop in saved articles despite fetcher uptime. Root causes were (1) stale/broken source feed URLs, (2) non-RSS endpoints returning HTML, (3) Google News consent/redirect pages causing low-content skips, and (4) fixed-size headline filtering (top 8) under high candidate volume.

**Changes**:
- `fetcher/sources.py`:
  - Added source URL auto-repair for known broken endpoints (Cambridge, DeepMind legacy URL, Meta legacy URL), with DB persistence.
  - Added feed-shape validation (`_looks_like_feed_response`) to skip HTML/non-feed responses early.
  - Added retry wrapper for unstable feeds (`_fetch_feed_response`) with targeted retries for Google News and Hacker News.
  - Added Google News wire fallback context (`_build_google_news_context`) and set it as `pre_extracted_content` to bypass consent-page scraping failures.
  - Added source health counters to log scan quality (`scanned`, `added`, `connection_errors`, `non_feed`, `empty_feed`).
  - Switched headline filter output from fixed top 8 to dynamic target (`min(16, max(8, len(batch)//3))`) with safer fallback behavior.
- `tests/test_source_quality.py`:
  - Added tests for source URL repair persistence, Google News context generation, and dynamic filter-cap behavior.
- `scripts/repair_source_urls.py` [NEW]:
  - Added idempotent one-off utility to repair known source URLs in DB.

**Verification**:
- `python3 -m pytest -q tests/test_source_quality.py` -> passed (9 passed).
- `python3 -m pytest -q tests/test_smoke.py -k "admin_sources"` -> passed (2 passed).
- `python3 -m py_compile fetcher/sources.py scripts/repair_source_urls.py` -> passed.

**Rollback**:
- Revert files: `fetcher/sources.py`, `tests/test_source_quality.py`, `scripts/repair_source_urls.py`.
- If URL repairs were persisted in DB and rollback is needed, run:
  - `UPDATE sources SET url='https://www.cam.ac.uk/topics/artificial-intelligence/feed' WHERE name='Cambridge University AI';`
  - `UPDATE sources SET url='https://deepmind.com/blog/feed/basic/' WHERE name='DeepMind';`
  - `UPDATE sources SET url='https://ai.meta.com/blog/rss.xml' WHERE name='Meta AI (FAIR)';`

---

## 2026-04-19T16:55:00+02:00 — Indexing Recovery Mode: Query Noindex + Archive Sitemap Contraction

**Context**: Search Console showed a high excluded/indexed gap on a young domain with fast URL growth. Root cause was crawl-budget dilution from query-string variants and a very large archive sitemap.

**Changes**:
- `templates/base.html`: Unified robots policy to **noindex, follow** for any URL carrying query parameters (`request.args`), while keeping clean canonical URLs indexable.
- `templates/index.html`: Removed duplicate homepage robots meta block to eliminate conflicting directives.
- `app.py`: Added `X-Robots-Tag: noindex, follow` on HTML responses with query params (header-level enforcement for UTM/debug/filter variants).
- `routes/seo.py`: Introduced recovery constraints for `sitemap-archive.xml`:
  - cap to `ARCHIVE_SITEMAP_LIMIT = 1200`,
  - include only recent (`ARCHIVE_RECENCY_DAYS = 180`) or high-quality (`ARCHIVE_MIN_QUALITY_SCORE = 65`) URLs,
  - keep `CORE_SITEMAP_LIMIT = 500` for top-tier pages.
- `tests/test_smoke.py`: Added SEO robots tests to verify deterministic single-tag behavior and query noindex enforcement.

**Verification**:
- `pytest -q tests/test_smoke.py -k "SEORobotsDirectives or TestSEORoutes or TestSitemapCaching"` passed.
- `pytest -q tests/test_helpers.py tests/test_site_health.py` passed.
- Local checks confirmed:
  - query URLs emit `meta robots = noindex, follow`,
  - query URLs emit `X-Robots-Tag: noindex, follow`,
  - clean article URLs remain indexable,
  - `sitemap-archive.xml` reduced to 1200 URLs.

**Rollback**: Revert commit affecting `templates/base.html`, `templates/index.html`, `app.py`, `routes/seo.py`, and `tests/test_smoke.py`. This restores prior indexability behavior and full archive sitemap breadth.

---

## 2026-03-20T11:27:00+01:00 — Penetration Test Remediation Final Batch (7 Findings, 10 Files)

**Context**: Final sweep to close all 23 pentest findings (23/23 complete).

**Changes**:
- `deploy_email_feature.py`: F-08 — `shell=True` → `shell=False` with list-based subprocess args. Prevents shell injection.
- `routes/api.py`: F-09 — CORS narrowed from `*` to `https://dailyaiwire.news` on intelligence API endpoints.
- `routes/auth.py`: F-11 — `FailedLoginTracker` rewritten from in-memory dict to SQLite-backed table (`failed_logins`). Persists across Gunicorn restarts and shares state across all workers. F-16 — Logout changed from GET to POST, added audit log entry.
- `templates/admin/base_admin.html`: F-16 — Logout link → POST form with CSRF token.
- `app.py`: F-14 — Documented that `unsafe-eval` is required by Tailwind CDN JIT mode and will be removable after Tailwind migration to pre-built CSS.
- `nginx_optimized.conf`: F-15 — Added `limit_req_zone` (10r/s general, 5r/s login), `client_max_body_size 10m` (1m for login), dedicated `/login` location block with stricter limit.
- `tweet_scheduler.py`: F-20 — Centralized 7 constants to env vars (`SCHEDULER_INTERVAL_SECONDS`, `SCHEDULER_QUIET_START/END`, `SCHEDULER_TIMEZONE`, `FB_DAILY_LIMIT`, `FB_BACKOFF_MAX_HOURS`). Version bumped to 2.4.0.
- `fetcher/__init__.py`: F-20 — `MAX_ARTICLES_PER_CYCLE` and `batch_size` now read from `FETCHER_MAX_ARTICLES` and `FETCHER_BATCH_SIZE` env vars.
- `tests/test_smoke.py`: Updated CORS assertion from `*` to domain-specific.
- `tests/test_security.py`: Updated brute-force test to create `failed_logins` table in test DB and clean up after.

**Tests**: 102/102 passing (1 skipped).

**Rollback**: `git revert <commit>`. For F-11: `DROP TABLE IF EXISTS failed_logins` and restore the class to dict-based. For F-15: nginx rate limits are graceful (burst allows normal usage), but `sudo nginx -t && sudo systemctl reload nginx` needed after any config change.

---

## 2026-03-20T11:02:00+01:00 — Penetration Test Remediation Batch 2 (5 Findings, 7 Files)

**Context**: Second pass addressing remaining pentest findings from F-03 (critical PII leak), F-10, F-12, F-20/F-22 (code quality).

**Changes**:
- `newsletter_sender.py`: F-03 — HMAC tracking tokens replace raw email in newsletter tracking URLs. New `_tracking_token()` generates 16-char HMAC hex. `_ensure_tracking_columns()` adds lazy migration for `tracking_token` + `opened_at` columns. Token stored in `newsletter_deliveries` at delivery time.
- `routes/api.py`: F-03 — Tracking endpoint now matches by `tracking_token` instead of `recipient_email`. URL pattern changed from `/t/nl/<id>/<email>` to `/t/nl/<id>/<token>`.
- `services/lead_extractor.py`: F-10 — Replaced hardcoded `DB_PATH = "news.db"` with `from db import DB_PATH`.
- `.env.example`: F-12 — Removed duplicate `SECRET_KEY` entry (was on lines 12 and 19).
- `helpers.py`: F-22 — Added shared `clean_markdown()` function.
- `social_distributor.py`: F-22 — Replaced 4 inline `.replace('**', '')` calls with `clean_markdown()` import.

**Tests**: 102/102 passing (1 skipped).

**Rollback**: `git revert <commit>`. For F-03: the tracking endpoint change means previously-sent newsletters with old-style email URLs will return 200 (no DB match → no update). This is safe — it just means old tracking pixels stop working, which is an acceptable tradeoff for eliminating PII from server logs.

---

## 2026-03-20T10:48:00+01:00 — Penetration Test Remediation (12 Findings, 11 Files)

**Context**: Full static-analysis penetration test identified 23 findings (F-01 through F-23) across OWASP Top 10 categories. This commit remediates 12 of the highest-priority findings.

**Changes**:
- `app.py`: F-01 security headers (HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy), F-02 session cookie hardening (Secure/HttpOnly/SameSite), F-13 removed default admin credentials fallback, F-23 `/health` endpoint.
- `db.py`: F-18 added `timeout=10` to SQLite connection.
- `tweet_scheduler.py`: F-18 added `timeout=10` to local SQLite connection.
- `routes/api.py`: F-05 rate limit on audio tracking (5/min), F-07 sanitized trend API error.
- `routes/auth.py`: F-07 sanitized user creation error, F-21 dedicated auth audit log (`logs/auth_audit.log`).
- `routes/admin_content.py`: F-04 changed 4 destructive routes from GET to POST (newsletter delete/generate/send, editorial generate), F-07 sanitized error messages.
- `routes/admin_core.py`: F-06 file upload extension whitelist (jpg/jpeg/png/webp/gif/mp3/wav/ogg), F-07 sanitized error messages.
- `routes/admin_ops.py`: F-07 sanitized source-blocking error.
- `fetcher/sources.py`: F-17 added `request_options={'timeout': 120}` to Gemini API call.
- `fetcher/persistence.py`: F-19 replaced silent `except ImportError: pass` with debug logging.
- `templates/admin/newsletters.html`: F-04 converted GET links to POST forms with CSRF tokens.

**Tests**: 102/102 passing (1 skipped).

**Rollback**: `git revert <commit>`. All changes are additive (headers, config, timeouts) or tightening (GET→POST, error sanitization), so reverting restores the previous behavior without data loss.

---

## 2026-03-18T12:00:00+01:00 — Facebook Pipeline Fix: Missing Column + Scheduler Isolation

**Context**: Facebook posting stopped ~17 hours ago. Root cause: `shared_on_fb` column was never added to the database (migrations existed for `shared_on_x` and `shared_on_ig` but not `shared_on_fb`). Additionally, the scheduler's IG/FB distribution blocks were not error-isolated — a crash in `mark_as_shared_fb` could cascade into the main loop's catch-all.

**Changes**:
- `scripts/migrate_facebook.py` [NEW]: Idempotent migration to add `shared_on_fb BOOLEAN DEFAULT 0` to the articles table.
- `fetcher/db_init.py`: Added `shared_on_ig` and `shared_on_fb` to both the CREATE TABLE statement (for fresh DBs) and as lazy migrations (for existing DBs).
- `tweet_scheduler.py`: Wrapped Instagram and Facebook distribution blocks in isolated try/except so a failure in one platform never crashes the scheduler or blocks the other.

**Rollback**: Remove `shared_on_fb` and `shared_on_ig` lazy migrations from `db_init.py`. Remove try/except wrappers from scheduler distribution blocks. Delete `scripts/migrate_facebook.py`.

---

## 2026-03-18T02:45:00+01:00 — System Hardening: CSRF, Rate Limiting, and Brute-Force Defenses

**Context**: Addressed critical security vulnerabilities identified during the architecture audit (P0 Priorities): absence of CSRF protection on forms, no rate limiting on public/admin endpoints, and exposure to brute-force credential stuffing.

**Changes (Security & Stability)**:
- `extensions.py` [NEW]: Centralized global registry to prevent cyclic dependency initialization of `flask_wtf.csrf.CSRFProtect` and `flask_limiter.Limiter`.
- `app.py`: Integrated `CSRFProtect` and `Flask-Limiter`. Uses `key_func=get_remote_address` to actively trust `X-Forwarded-For` headers from the Nginx proxy.
- `templates/**/*.html`: Injected `{{ csrf_token() }}` into all 18+ `<form method="POST">` nodes across the admin and public UI.
- `routes/api.py`: Exempted programmatic API/AJAX endpoints (`/api/track-audio`, `/api/search`) using `@csrf.exempt`.
- `routes/auth.py`: Replaced login logic with `FailedLoginTracker` for local memory credential tracking. Locks out accounts for 15 minutes after 5 failures. Enforced POST rate limiting of `10/min`.
- `routes/public.py`: Rate limited `/subscribe` POST submissions to `5/min` to defend against email bombing.
- `tests/test_smoke.py`: Refactored unit tests to correctly expect `410 Gone` on removed articles, preventing Google Search Console soft-404 dilution.

**Rollback**: Uninstall `flask-wtf` and `flask-limiter`. Delete `extensions.py` and remove initialization imports from `app.py`. Strip `@csrf.exempt` and `@limiter` decorators from route modules.

---

## 2026-03-16T18:55:00+01:00 — SEO Indexing Audit: Tiered Sitemap + Crawl Budget Optimization

**Context**: Google Search Console showed 46/4,150 pages indexed (~1%). 3,179 "Discovered – not indexed", 919 "Crawled – not indexed", 41 returning 404. Technical SEO (canonical, OG, JSON-LD, www→non-www) was correct — root cause was crawl budget saturation from a single massive sitemap on a young domain.

**Changes**:
- `routes/seo.py`: `sitemap.xml` is now a **sitemap index** pointing to `sitemap-core.xml` (7 static + top 500 articles by `importance_score * compass_score` + lab posts = 512 URLs) and `sitemap-archive.xml` (remaining 3,611 articles at `priority: 0.4`). Concentrates Google's crawl budget on highest-quality content.
- `templates/sitemap_index.xml` [NEW]: Sitemap index template.
- `routes/public.py`: Missing article slugs now return `410 Gone` instead of `404 Not Found`. Google drops 410 URLs permanently (vs retrying 404s for weeks).
- `templates/index.html`: Added `?q=` search pages to `noindex, follow` meta directive.
- `nginx_optimized.conf`: Added `X-Robots-Tag: noindex` on all `/static` locations.

**Rollback**: Revert `routes/seo.py` to single `sitemap()` function. Delete `templates/sitemap_index.xml`. Revert `routes/public.py` from `abort(410)` → `abort(404)`. Revert `index.html` noindex condition. Revert nginx config to remove `X-Robots-Tag` headers.

---

## 2026-03-15T11:03:00+01:00 — Structured Logging, CI/CD Pipeline, and Content Provenance Chain

**Context**: Jules' codebase analysis identified 3 still-relevant improvements: `print()` calls in production code, no CI/CD pipeline, and no audit trail for AI-processed content. This decision addresses all three.

**Changes (Structured Logging)**:
- `logging_config.py` [NEW]: Centralized logging setup with console + optional `RotatingFileHandler` (5 MB × 3 rotations, enabled via `LOG_TO_FILE=true`). Quiets noisy third-party loggers.
- `app.py`: `print()` → `logger = logging.getLogger('app')`. Calls `setup_logging()` on boot.
- `fetcher/__init__.py`: `print()` → `logging.getLogger('fetcher')`. Calls `setup_logging()` on boot.
- `fetcher/ai_processor.py`: `print()` → `logging.getLogger('fetcher.ai')`.
- `fetcher/persistence.py`: `print()` → `logging.getLogger('fetcher.persistence')`.
- `fetcher/sources.py`: `print()` → `logging.getLogger('fetcher.sources')`.
- `fetcher/content.py`: `print()` → `logging.getLogger('fetcher.content')`.
- `fetcher/spam.py`: `print()` → `logging.getLogger('fetcher.spam')`.
- `fetcher/db_init.py`: `print()` → `logging.getLogger('fetcher.db')`.
- `tweet_scheduler.py`: `print()` → `logging.getLogger('scheduler')`. Hardcoded `DEBUG:` boot prefixes converted to `logger.debug()`. Version bumped to 2.3.0.
- `social_distributor.py`: `print()` → `logging.getLogger('social')`.
- `budget_tracker.py`: `print()` → `logging.getLogger('budget')`.
- `tests/test_facebook.py`: `capsys` → `caplog` for credential-missing test.
- `tests/test_instagram.py`: `capsys` → `caplog` for credential-missing test.

**Changes (CI/CD)**:
- `.github/workflows/ci.yml` [NEW]: GitHub Actions workflow running `pytest tests/ -v --tb=short` on every push/PR to `main`. Python 3.12, pip cache enabled, zero secrets needed.

**Changes (Content Provenance Chain)**:
- `scripts/migrate_provenance.py` [NEW]: Idempotent migration adding `source_content_hash TEXT` and `ai_model_used TEXT` to articles table.
- `fetcher/db_init.py`: Lazy migration for provenance columns (runs on fetcher boot).
- `fetcher/ai_processor.py`: Computes SHA-256 of scraped content, attaches `source_content_hash` and `ai_model_used` to each processed article.
- `fetcher/persistence.py`: Stores provenance fields in INSERT statement (2 new bind params).
- `tests/conftest.py`: Added `source_content_hash` and `ai_model_used` columns to test schema.

**Tests**: 91/91 passing (89 existing + 2 fixed `capsys` → `caplog`).

**Rollback**: `git revert` the commit. For provenance columns: `ALTER TABLE articles DROP COLUMN source_content_hash; ALTER TABLE articles DROP COLUMN ai_model_used;` (SQLite 3.35+). Delete `.github/workflows/ci.yml` and `logging_config.py`.

---

## 2026-03-14T18:42:00+01:00 — SEO Indexing Crisis Recovery (127→1,900+ target)

**Context**: Google Search Console showed indexed pages dropped from ~1,200 to 127 (of 3,863 discovered), with 1,310+ pages in "Crawled - currently not indexed" status. Traffic dropped massively since late Jan 2026.

**Root Causes Identified**:
1. **www/non-www duplication** (Critical): Nginx served identical content on both `dailyaiwire.news` and `www.dailyaiwire.news`, doubling perceived content and triggering duplicate content penalties.
2. **`Cache-Control: no-store` on all HTML** (Critical): Told Google content was ephemeral/not worth caching.
3. **Category URLs in sitemap** (High): `/?category=AI Agents` (with unescaped spaces) created invalid XML and wasted crawl budget on thin filter pages.
4. **Paginated canonicals** (Medium): `/?category=X&page=2` canonicals diluted link equity.

**Changes**:
- `nginx_optimized.conf`: New HTTPS server block for `www.dailyaiwire.news` → 301 redirect to `dailyaiwire.news`. HTTP block simplified to always redirect to non-www HTTPS.
- `app.py`: HTML `Cache-Control` changed from `no-store` → `public, max-age=60, s-maxage=300`.
- `routes/public.py`: Removed explicit `no-cache, no-store, must-revalidate` override on homepage.
- `routes/seo.py`: Removed 12+ `/?category=X` URLs from sitemap. Added `/signal` to static pages.
- `templates/index.html`: Canonical always points to `https://dailyaiwire.news/`. Added `<meta name="robots" content="noindex, follow">` for paginated + category-filtered pages.

**Tests**: 52/52 passing. No regressions.

**Required manual steps**: Deploy to VPS, reload nginx (`sudo nginx -t && sudo systemctl reload nginx`), resubmit sitemap in GSC, click "Validate Fix" on "Crawled - currently not indexed" issue.

**Rollback**: Revert `nginx_optimized.conf` to include `www.dailyaiwire.news` in main server block. Restore `no-store` in `app.py` and `public.py`. Restore category URLs in `seo.py` sitemap. Restore pagination canonicals in `index.html`.

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

---

## 2026-03-22T21:44:00+01:00 — Logging Migration: print() → structured logging

**Decision**: Migrated all ad-hoc `print()` calls in production code to Python's `logging` module.

**Files changed**:
- `weekly_curator.py` — 8 calls → `logging.getLogger('weekly_curator')`
- `services/lead_extractor.py` — 10 calls → `logging.getLogger('lead_extractor')`
- `services/proposal_agent.py` — 3 calls → `logging.getLogger('proposal_agent')`
- `tavily_research.py` — 4 calls → `logging.getLogger('tavily_research')` (library pattern, no setup_logging)
- `video_renderer.py` — 7 calls → `logging.getLogger('video_renderer')` (library pattern, no setup_logging)
- `tests/test_logging.py` — new test file (6 tests covering idempotency, level control, named loggers)

**Log level mapping**:
- DEBUG: noisy heuristic hits, pipeline misses (high frequency, low signal)
- INFO: business events (lead captured, draft created, render start)
- WARNING: non-blocking failures, config fallbacks
- ERROR + exc_info=True: exceptions with full stack traces

**Not migrated**: one-off CLI scripts in `scripts/` (print() is correct operator UX there).

**Trigger**: Closed Jules PR #1 (CODE_ANALYSIS.md / IMPROVEMENT_IDEAS.md). Logging was the only actionable item.

**Rollback**: `git revert` the commit. No DB or config changes.

---

## 2026-03-29T17:21:00+02:00 - Content Extraction Resilience (Scrapling & RSS Fallback)

**Decision**: Replaced the basic `requests` fallback in the content extraction pipeline with `Scrapling` to bypass anti-bot protections (e.g., Cloudflare 403s on `fiercehealthcare.com`). Additionally, implemented a universal RSS summary fallback to rescue articles when full-page scraping fails.

**Changes**:
- `fetcher/sources.py`: Extracts raw `summary` or `content` from RSS feeds as `rss_summary` for every article. Merged PR #2 logic to use `pre_extracted_content` for Twitter sources.
- `fetcher/ai_processor.py`: Falls back to `rss_summary` if `trafilatura` yields `< 300` characters, skipping the block entirely if the RSS provides `>= 150` characters. Lowered minimum floor for tweets to 50 chars.
- `fetcher/content.py`: Replaced `requests.get` fallback with `scrapling.Fetcher(auto_match=True)` to mimic real browser TLS fingerprints on protected sites.
- `requirements.txt`: Added `scrapling`, `curl_cffi`, `playwright`, `browserforge`.

**Trigger**: Articles were being dropped due to "Insufficient Data" because scrapers were increasingly blocked by WAFs. 

**Rollback**: Remove `scrapling` from `fetcher/content.py` and restore `requests.get()`. Remove the `rss_summary` logic from `fetcher/sources.py` and `fetcher/ai_processor.py`.

---

## 2026-03-29T19:27:00+02:00 - Self-Hosted RSS-Bridge for Twitter

**Decision**: Replaced all unreliable external Nitter mirrors (which Twitter actively blocks) with a self-hosted `RSS-Bridge` Docker container running locally on the VPS. 

**Changes**:
- `docker-compose.yml` (VPS only): Spun up `rssbridge/rss-bridge:latest` tracking on `127.0.0.1:8333`.
- `scripts/seed_twitter_sources.py`: Removed public mirror scraper and rewritten to generate bridge URLs (`/?action=display&bridge=Twitter...`) pointing to `127.0.0.1:8333`. Emptied the DB of old Nitter URLs and inserted 12 local bridge URLs.

**Rollback**: Tear down the Docker container `docker compose down`, restore the Nitter check block in `seed_twitter_sources.py`, and re-run to repopulate the DB with public mirrors.

---

## 2026-03-30T00:25:00+02:00 - RSS-Bridge Scraper Bypass & Semantic Deduplication Fix

**Decision**: The `dailyaiwire_fetcher` was failing to insert Twitter articles because the new RSS-Bridge endpoints didn't trigger the `pre_extracted_content` bypass logic, routing tweets to `trafilatura` (which failed on the generic Atom feed UI). Additionally, the semantic deduplication engine was throwing 404 errors due to calling a deprecated Gemini 1.5 API.

**Changes**:
- `fetcher/sources.py`: Appended `bridge=Twitter` to the `if 'nitter' in url...` condition. Tweets are now safely routed around the HTML scraper and use their RSS text directly.
- `remove_duplicates.py`: Bumped `gemini-1.5-flash` to `gemini-2.5-flash` in the explicit model instantiation block.

**Trigger**: Articles successfully found by RSS-Bridge were being dropped by the AI filter due to "Insufficient Data". Deduplication was crashing.

**Rollback**: Revert `fetcher/sources.py` and `remove_duplicates.py` to previous git state.

---

## 2026-04-16T13:15:00+02:00 - Production Baseline Reconciled After VPS Cleanup

**Context**: Repository history, VPS state, and deployment docs had drifted apart after repeated direct local-to-VPS deploys. Production had to be reconciled against the live server before any branch or cleanup decisions could be trusted.

**Decision**:
1. Treat `/home/dailyai/dailyaiwire.news` as the sole active app root for DailyAIWire.
2. Treat Supervisor as the runtime source of truth for production. Verified active services are `dailyaiwire` and `dailyaiwire_fetcher`.
3. Move the active Google credential out of the repo and into `/home/dailyai/.secrets/google-cloud.json`, with `.env` pointing to the external secret path.
4. Quarantine the extra `n8n-indexting` key outside the repo and keep it separate from the app credential path.
5. Archive production cleanup artifacts under `/home/dailyai/vps-cleanup-backups/` instead of deleting them in place.
6. Collapse stale Git branches. GitHub now keeps only `main`. The older environment ref, `deploy`, `iron-judo-v1`, AI scratch branches, and other stale refs were removed after confirming their history was either redundant or preserved locally.
7. Update `DEPLOYMENT.md` to document the real production model: committed Git deploys, Supervisor-managed fetcher, and external secret storage.

**Trigger**: VPS audit and branch cleanup performed on 2026-04-15 and 2026-04-16.

**Rollback**:
- Restore the app credential path by moving `/home/dailyai/.secrets/google-cloud.json` back into the repo only if an emergency rollback absolutely requires it, then update `.env` accordingly and restart Supervisor services.
- Restore archived VPS files from `/home/dailyai/vps-cleanup-backups/` if a moved artifact turns out to be needed.
- Recreate deleted Git branches from their last known commit hashes if a removed historical branch is needed again.

---

## 2026-04-16T00:23:00+02:00 - Non-Production DailyAIWire Environment Retired

**Context**: A stopped non-production clone and its leftover process definition were still present on the VPS even after the production line, deploy flow, and branch history had been simplified around `main`.

**Decision**:
1. Archive the non-production checkout into a dated VPS backup directory instead of deleting it in place.
2. Archive the leftover Supervisor config in the same dated backup directory and remove the live registration so no unused non-production process remains on the server.
3. Remove the final non-production remote branch and keep `main` as the only remaining remote branch.
4. Treat any future secondary environment as an explicit new setup task rather than an inherited leftover clone.

**Trigger**: Final environment cleanup after confirming the non-production process was stopped, unwired from nginx, and no longer part of the operating model.

**Rollback**:
- Move the archived checkout and archived Supervisor config back into their former locations, then run `supervisorctl reread && supervisorctl update`.
- Recreate the deleted remote branch from its archived commit hash if that environment ever needs to be revived.

---

## 2026-04-16T13:45:00+02:00 - Production Deploy Standardized Around Exact Refs and Web-Only Defaults

**Context**: The existing VPS deploy script only pulled `main`, restarted `dailyaiwire`, and relied on manual operator judgement. It had no health verification, no explicit rollback path, and no CI-backed production deploy entrypoint.

**Decision**:
1. Harden `deploy_to_vps.sh` to deploy an exact git ref or commit SHA instead of implicitly deploying "whatever main is now".
2. Make web-only deploys the default operational mode. `dailyaiwire_fetcher` is restarted only when explicitly requested with `--with-fetcher`.
3. Add a `/health` verification step to the deploy flow so a deploy fails fast if the app does not come back cleanly.
4. Block accidental non-fast-forward deploys unless the operator explicitly passes `--allow-reset` for an intentional rollback.
5. Add a manual GitHub Actions workflow, `Deploy Production`, that streams the hardened deploy script to the VPS over SSH and records a repeatable deploy path around exact refs.

**Trigger**: Deployment process review after branch cleanup and VPS reconciliation exposed that the old deploy path was still below standard operational practice.

**Rollback**:
- Revert `deploy_to_vps.sh` and `.github/workflows/deploy-production.yml` to the prior simpler deploy model if the new workflow proves incompatible.
- Use `./deploy_to_vps.sh --ref <previous-sha> --allow-reset` for application rollback on the VPS.

---

## 2026-04-16T14:20:00+02:00 - DailyAIWire Deploy User Gets Narrow Supervisor Sudoers

**Context**: The first live run of the hardened deploy script updated production code but failed at the restart step because `dailyai` could not run `sudo supervisorctl` non-interactively and also could not talk to the root-owned Supervisor socket directly. That left the deploy path short of the intended one-command standard.

**Decision**:
1. Keep the shared VPS least-privilege model and do not grant `dailyai` broad sudo or unrestricted `supervisorctl` access.
2. Add a dedicated `/etc/sudoers.d/dailyaiwire-supervisor` rule that allows only these four commands without a password:
   - `/usr/bin/supervisorctl restart dailyaiwire`
   - `/usr/bin/supervisorctl status dailyaiwire`
   - `/usr/bin/supervisorctl restart dailyaiwire_fetcher`
   - `/usr/bin/supervisorctl status dailyaiwire_fetcher`
3. Update `deploy_to_vps.sh` to probe Supervisor access before touching Git and to use `sudo -n` so a missing sudoers rule fails fast instead of prompting mid-deploy.
4. Document the exact sudoers contract in `DEPLOYMENT.md` so future deploys do not depend on remembered shell state.

**Trigger**: First live production deploy of the hardened script on 2026-04-16 exposed that the previous restart assumption was incompatible with the actual VPS permissions model.

**Rollback**:
- Remove `/etc/sudoers.d/dailyaiwire-supervisor` with `visudo` or delete the file and revalidate sudoers if the rule needs to be withdrawn.
- Revert the `deploy_to_vps.sh` permission probe if the VPS is later restructured around direct Supervisor access for the deploy user.

---

## 2026-04-16T01:50:32+02:00 - Semantic Search Stack Pinned for Reproducible Deploys

**Context**: Production semantic search and Qdrant indexing were working only because `qdrant-client`, `sentence-transformers`, `transformers`, and `huggingface_hub` had been installed manually on the VPS. They were not declared in `requirements.txt`, and the production venv had drifted into `pip check` mismatches through newer transitive installs of `grpcio-tools` and `typer`.

**Decision**:
1. Add the semantic-search runtime packages the app imports to `requirements.txt`:
   - `qdrant-client==1.12.1`
   - `sentence-transformers==5.2.3`
   - `transformers==5.3.0`
   - `huggingface-hub==1.6.0`
   - `torch==2.10.0`
2. Pin the previously drifting transitive packages that were causing `pip check` failures while keeping the existing `click`, `grpcio`, and `protobuf` pins intact:
   - `grpcio-tools==1.71.2`
   - `typer==0.23.1`
3. Validate the full candidate file in an isolated Python 3.12 venv on the VPS before changing the live environment.
4. Align the production venv to the validated candidate and require `pip check` to return clean before considering the dependency baseline fixed.

**Trigger**: Post-cleanup dependency audit on 2026-04-16 showed that the repo could not reproduce production semantic-search features and that the live venv contained stale dependency drift even after the invalid-distribution cleanup.

**Rollback**:
- Reinstall the previous package versions explicitly if the new semantic-search pin set causes runtime regressions, especially `grpcio-tools` and `typer`.
- Restore the previous `requirements.txt` and rerun `venv/bin/python -m pip install -r requirements.txt` if this pin set proves incompatible with future deploys.

---

## 2026-04-16T17:20:32+02:00 - Site Health Hardening for Lab, RSS, and Public Metadata

**Context**: Live verification on 2026-04-15 found that `/lab` and `/rss` were returning `500` in production, while the public HTML referenced a missing `/static/schema.json` asset and article JSON-LD pointed to a missing `/static/logo.png`. The editorial data flow also had schema drift: some code paths assumed `blog_posts.is_published` existed, while older databases did not have that column.

**Decision**:
1. Add a shared editorial loader in `services/editorials.py` to centralize `blog_posts` reads and make them resilient to schema drift.
2. Filter public editorial surfaces down to complete, publishable records only:
   - require `slug`
   - require `title`
   - require `published_at`
   - require `is_published = 1` only when that column exists
3. Use the shared loader for:
   - `/lab`
   - `/rss` and `/rss.xml`
   - homepage editorial ingestion
4. Harden public output so incomplete editorial records cannot crash templates:
   - guard `published_at` rendering in `templates/lab_index.html`
   - fall back from `subtitle` to `meta_description`
5. Restore machine-facing assets and metadata consistency:
   - add `static/schema.json`
   - repoint organization/article logo URLs to `static/img/brand/logo_nodes.png`
   - change `ai-content-declaration` from `human-created` to `ai-assisted-human-reviewed`
   - standardize public RSS references on `/rss.xml`
6. Add regression tests covering:
   - unpublished editorials not breaking `/lab`
   - unpublished editorials not leaking into `/rss`
   - `static/schema.json` being served

**Trigger**: Production route audit and Lighthouse preparation on 2026-04-15 surfaced a cluster of site-health issues that were all rooted in schema drift, unsafe editorial assumptions, and missing machine-facing assets.

**Rollback**:
- Revert `services/editorials.py` and restore the previous route-local editorial queries if the shared loader causes unexpected editorial visibility changes.
- Remove `static/schema.json` and revert logo/meta changes if external consumers depend on the previous metadata contract.
- Revert `tests/test_site_health.py` only if the public contract for drafts and schema assets is intentionally changed in a future redesign.

---

## 2026-04-16T17:33:14+02:00 - Public AI Disclosure Copy Standardized to One Phrase

**Context**: After switching the machine-readable `ai-content-declaration` tag to `ai-assisted-human-reviewed`, the visible copy still mixed several older labels such as `expert curated`, `expert-vetted`, `AI-orchestration`, and `machine-generated`. That made the public disclosure story inconsistent across the homepage footer, `/about`, and `/how-it-works`.

**Decision**:
1. Standardize visible disclosure copy on the phrase `AI-assisted, human-reviewed`.
2. Apply that phrase across:
   - homepage footer copy
   - `/about`
   - `/how-it-works`
3. Remove older wording that implied a different review standard or a fully machine-generated output path.
4. Add regression tests that verify:
   - the homepage keeps the `ai-assisted-human-reviewed` meta tag
   - public disclosure pages render `AI-assisted, human-reviewed`
   - legacy disclosure phrases do not reappear

**Trigger**: Manual review on 2026-04-16 showed that the machine-readable disclosure had already been corrected, but visible copy had not been brought into alignment.

**Rollback**:
- Revert the disclosure-copy updates in `templates/base.html`, `templates/about.html`, and `templates/how_it_works.html` if the editorial team wants a different public wording.
- Update `tests/test_site_health.py` in the same change if the disclosure phrase is intentionally renamed in the future.

---

## 2026-04-16T18:03:05+02:00 - Homepage Grid Budget Fixed at Nine Visible Tiles

**Context**: The homepage uses a 3-column grid with a newsletter subscribe tile injected into page 1. The route was also injecting editorial cards into the same grid without reducing the number of regular article cards, which produced a 10th tile and broke the layout. The same route still had an older `_fetch_editorials(conn)` call on the `Editorial` category path, causing `/?category=Editorial` to return `500`.

**Decision**:
1. Treat homepage page 1 as a fixed 9-tile layout:
   - 1 subscribe tile
   - 8 content-card slots total
2. Reduce homepage page-1 regular article fetches by the number of injected editorial cards so the content-card budget stays capped at 8.
3. Keep page-2 and later offsets aligned with the number of real article rows actually shown on page 1 to avoid skipping article records.
4. Fix the stale `Editorial` category route call by using `_fetch_editorials()` with its current signature.
5. Add regressions covering:
   - homepage page-1 grid staying within the 9-tile layout
   - `/?category=Editorial` returning `200`

**Trigger**: Local reproduction and live screenshots on 2026-04-16 showed the homepage rendering an extra card row and confirmed that the live `/lab` and editorial surfaces were still inconsistent with the branch fixes.

**Rollback**:
- Revert the homepage slot-budget logic in `routes/public.py` if the product intentionally moves back to a denser front-page layout.
- Revert the new tests in `tests/test_site_health.py` and `tests/test_smoke.py` only if the homepage grid contract or editorial category behavior is deliberately changed later.

---

## 2026-04-19T17:38:09+02:00 - Centralized Gemini Gateway, Schema Validation, and Non-Destructive AI Dedup

**Context**: The AI audit found three high-risk failure modes in the live intelligence pipeline: (1) raw scraped text was being passed into lead extraction without a hardened policy layer or local schema validation, (2) article processing could mark a URL as processed before a valid Gemini response had been parsed, causing silent content loss, and (3) AI-driven dedup scripts could execute direct `DELETE` statements from model output with no review gate.

**Decision**:
1. Add a shared Gemini gateway in `services/ai_gateway.py` to centralize:
   - Gemini invocation
   - JSON fence cleanup
   - Pydantic validation
   - best-effort `ai_logs` persistence
2. Add shared output schemas in `services/ai_schemas.py` for:
   - article analysis
   - lead extraction
   - duplicate review payloads
3. Extend `ai_config.py` with specialized roles for:
   - `LeadExtractor`
   - `Deduplicator`
4. Move `fetcher/ai_processor.py` onto the shared gateway and validated article schema.
5. Remove the premature `SENT_TO_API` state update from `fetcher/ai_processor.py` so a malformed model response no longer blacklists a fresh URL before validation succeeds.
6. Move `services/lead_extractor.py` onto the shared gateway and validated lead-extraction schema, while explicitly treating page text as untrusted data in the prompt.
7. Replace destructive AI dedup writes with review queue inserts:
   - add `duplicate_review_queue`
   - update `remove_duplicates.py` and `ai_dedup.py` so AI semantic duplicates are flagged for review instead of deleted
8. Keep the existing fuzzy dedup pass unchanged in this slice to avoid changing the live site’s duplicate-suppression behavior too broadly in one release.
9. Add focused regression tests covering:
   - structured Gemini validation
   - removal of the premature `SENT_TO_API` status
   - AI dedup review-queue behavior

**Trigger**: Security and architecture audit on 2026-04-19 identified prompt-injection exposure in lead extraction, destructive AI autonomy in deduplication, and weak state handling around Gemini output validation.

**Rollback**:
- Revert `services/ai_gateway.py`, `services/ai_schemas.py`, and `services/duplicate_review.py` if the shared gateway introduces unexpected provider behavior.
- Revert `fetcher/ai_processor.py` and `services/lead_extractor.py` if schema validation is found to reject too many valid outputs in production.
- Revert `remove_duplicates.py`, `ai_dedup.py`, and the `duplicate_review_queue` schema if the team explicitly decides to return to destructive semantic deduplication.
- Revert `tests/test_ai_governance.py` and `tests/conftest.py` only alongside the production-code rollback so the tests stay aligned with the actual AI contract.

---

## 2026-04-29T22:34:09+02:00 - Read-Only Admin Indexability Control Panel

**Context**: Google Search Console showed a large `Crawled - currently not indexed` backlog. The sitemap now uses an indexability gate, but the admin UI had no way to inspect why specific articles were eligible or excluded without querying the database manually.

**Decision**:
1. Add a read-only `/admin/seo` panel for authenticated admins.
2. Reuse `services.indexability.score_article()` so admin diagnostics match sitemap behavior exactly.
3. Cap each admin scan at the latest 1,000 published articles to keep the route cheap on SQLite.
4. Support filters for search, source, sitemap status, and blocker code.
5. Add `/admin/seo.csv` export for the current filtered view.
6. Add regression tests for authentication, score visibility, filtering, CSV export, and blueprint registration.

**Trigger**: SEO recovery work on 2026-04-29 identified that the next useful operational tool is visibility into sitemap eligibility and blocker reasons before changing fetcher or generation rules.

**Rollback**:
- Revert `routes/admin_seo.py`, `templates/admin/seo.html`, the sidebar link in `templates/admin/base_admin.html`, and the blueprint registration in `app.py` if the admin panel causes performance issues.
- Revert `tests/test_admin_seo.py` and the `admin_seo` blueprint assertion in `tests/test_smoke.py` with the production rollback.

---

## 2026-04-30T00:17:18+02:00 - GitHub Repo Quality Gate Fails Closed on Unknown Stars

**Context**: Production analysis showed the GitHub star gate is active with `GITHUB_MIN_STARS=10`, but low-star repositories can still pass when GitHub API lookup fails or is rate-limited because the gate previously failed open.

**Decision**:
1. Keep the existing configurable `GITHUB_MIN_STARS` threshold.
2. Keep non-GitHub URLs unaffected by the GitHub-specific gate.
3. Reject GitHub repository URLs when star count cannot be verified and no fresh cache value exists.
4. Preserve cache behavior for verified repos, including low-star cache entries.
5. Add a regression test for unknown-star GitHub repos.

**Trigger**: SEO and source-quality review on 2026-04-29/2026-04-30 identified low-reputation GitHub repo stories as a content-quality risk for a young domain.

**Rollback**:
- Revert `fetcher/sources.py` and `tests/test_source_quality.py` if GitHub API availability causes too many legitimate GitHub stories to be skipped.
- Alternatively set up a valid `GITHUB_TOKEN` in production to reduce unknown-star cases without weakening the gate.

---

## 2026-04-30T00:27:50+02:00 - Generate Branded Article Cards Before Stock Fallback Images

**Context**: Production SEO audit showed `fallback_image` is the largest recent sitemap blocker. In the latest 1,000 published articles, 368 used stock fallback images, with ArXiv and research sources accounting for most cases because they often lack usable Open Graph images.

**Decision**:
1. Keep scraped source images as the first choice when they are valid.
2. When the scraped image is missing or generic, generate a branded article card via `ig_card_generator.generate_card()`.
3. Store generated cards as `/static/img/social/<slug>.png` article images so they are web-addressable and unique per article.
4. Keep stock `/static/fallbacks/...` images only as the last-resort path when card generation fails.
5. Treat `/static/img/social/...` as a usable image in persistence checks while stock fallback paths remain generic for indexability.
6. Add regression tests for both generated-card success and fallback-on-generation-failure behavior.

**Trigger**: SEO recovery work on 2026-04-30 identified fallback-image volume as the highest-impact content-quality blocker after the GitHub source gate was tightened.

**Rollback**:
- Revert `fetcher/persistence.py` and `tests/test_persistence_images.py` if card generation causes fetcher latency, image-write errors, or unacceptable visual output.
- Existing source images and stock fallback behavior remain available as safe fallback paths.

---

## 2026-05-04T22:11:53+02:00 - Newsletter Signup Abuse Guard and Double Opt-In

**Context**: A sudden May 4 subscriber spike showed many Gmail addresses with identical signup timing and request signatures, but no matching GA users. The existing `/subscribe` route immediately inserted `ACTIVE` subscribers and stored only email/status/timestamp, leaving no reliable audit trail.

**Decision**:
1. Normalize subscriber emails to lowercase before insert and dedupe with `lower(email)`.
2. Add honeypot, minimum form-age, email-format validation, and subscriber event logging for blocked attempts.
3. Add subscriber audit metadata: hashed IP, user-agent, referrer, source path, accept-language, and fingerprint hash.
4. Use `ProxyFix` so Flask-Limiter keys on the real client IP behind nginx.
5. Change new subscribers to `PENDING` with a one-time confirmation token; only confirmed subscribers become `ACTIVE`.
6. Send a confirmation email instead of immediately activating the feed.
7. Track GA conversion only after `status=confirmed`, not on pending or blocked requests.

**Trigger**: User reported many new subscriber emails appearing in a short window without corresponding Google Analytics traffic.

**Rollback**:
- Revert `routes/public.py`, `newsletter_sender.py`, `templates/thank_you.html`, the subscribe-form partial, subscribe-form includes, `app.py`, and `tests/test_subscribe_abuse.py`.
- To reactivate quarantined May 4 addresses if needed: `UPDATE subscribers SET status='ACTIVE' WHERE id BETWEEN 59 AND 76;`
