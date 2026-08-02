# DECISIONS.md — Daily AI Wire News
# Architectural Decision Log

Architectural decision log for the Daily AI Wire News project. Every entry includes an ISO 8601 timestamp per §6 of the AI Directives.

---

## 2026-07-21T23:27:56+02:00 - Audit Article Semantics Instead of Display Labels

**Context**: The article layout now labels its summary as `Signal Summary` and its source CTA as `Read Article at Source`, while `qa_monitor.py` still searched for the old literal labels `The Gist` and `Read Full Story`. Every current article therefore produced a false QA failure despite rendering correctly.

**Decision**:
- Validate the summary through the existing `data-article-summary-tone` container and non-empty summary content.
- Validate the source CTA through the existing `data-article-source-link` container and a non-empty link target.
- Retain the old display-label checks as fallbacks for archived layouts.
- Do not change the article template or visible copy for this monitoring fix.

**Verification**:
- RED: representative current article markup failed with `'The Gist' block missing`.
- GREEN: four monitor tests, five persistence tests, and 23 site-health tests passed.
- Both the local and production auditors passed the live RynnBrain article with headline, summary, and source CTA checks.
- `dailyaiwire_fetcher` is running after deployment.

**Rollback**: Restore `qa_monitor.py` from `/home/dailyai/dailyaiwire.news/ops/deploy-backups/qa-monitor-selectors-20260721T213000Z/` and restart `dailyaiwire_fetcher`.

## 2026-07-21T23:21:38+02:00 - Soft-Retire Fuzzy Duplicates and Clean Their Vectors

**Context**: Legacy post-publication fuzzy deduplication hard-deleted article rows without removing their Qdrant points. Production contained one missing-row vector for an earlier RynnBrain article, and retaining retired rows is safer for audit history and database references.

**Decision**:
- Scan only published articles during post-publication fuzzy deduplication.
- Set `is_published = 0` for fuzzy duplicates instead of deleting their database rows.
- Delete retired article points from Qdrant through an explicit point-ID helper.
- Restrict missing-audio generation to published articles so retired duplicates cannot consume TTS.
- Treat Qdrant deletion as non-blocking because semantic deduplication already filters candidates through published database IDs.

**Verification**:
- RED: duplicate rows were deleted, the vector deletion API was absent, unpublished rows influenced fuzzy matching, and unpublished rows reached audio generation.
- GREEN: 51 relevant tests passed in isolated test-file runs, including fuzzy retirement, Qdrant cleanup, ingestion, audio, governance, RSS, and indexing coverage.
- Production Qdrant and the database both contain 10,368 published article IDs, with zero missing-row vectors, zero unpublished-row vectors, and zero published articles lacking vectors.

**Rollback**: Restore `remove_duplicates.py`, `embedding_service.py`, and `generate_missing_audio.py` from `/home/dailyai/dailyaiwire.news/ops/deploy-backups/fuzzy-soft-retire-20260721T212000Z/`, then restart `dailyaiwire_fetcher`. A consistent pre-deployment `news.db` snapshot is stored in the same directory.

## 2026-07-21T23:15:03+02:00 - Disable Redundant Post-Publication AI Dedup by Default

**Context**: Post-publication Gemini deduplication ran 223 times over 14 days, consumed approximately 144,441 logged tokens, created 179 review rows that all remained pending, and missed the observed Hugging Face duplicate. Deterministic and Qdrant semantic checks now run before publication.

**Decision**:
- Keep deterministic and 36-hour Qdrant pre-publication deduplication as the active guards.
- Disable post-publication Gemini deduplication by default.
- Retain the explicit emergency opt-in `ENABLE_POST_PUBLICATION_AI_DEDUP=true`.
- Leave legacy fuzzy deduplication unchanged for this decision; audit its database deletion and Qdrant cleanup separately.

**Verification**:
- RED: the default path called `ai_deduplicate()` after every productive cycle.
- GREEN: the default path skips the Gemini call, while the explicit environment opt-in preserves the legacy behavior.
- `python3 -m pytest tests/test_post_publication_dedup.py tests/test_embedding_service_config.py tests/test_persistence_images.py tests/test_ai_governance.py -q` -> 29 passed.
- Production reports the feature flag as false and `dailyaiwire_fetcher` is running after deployment.

**Rollback**: Restore `/home/dailyai/dailyaiwire.news/ops/deploy-backups/post-publication-ai-dedup-20260721T211346Z/remove_duplicates.py` and restart `dailyaiwire_fetcher`, or set `ENABLE_POST_PUBLICATION_AI_DEDUP=true` to restore the legacy Gemini call without reverting code.

## 2026-07-21T21:45:51+02:00 - Exclude Unpublished Articles from Public RSS

**Context**: The public RSS query filtered future timestamps but omitted `is_published = 1`. A newly unpublished duplicate could therefore remain in RSS until enough newer records pushed it beyond the 20-item limit, even after disappearing from the homepage.

**Decision**: Apply the same publication-state requirement to public RSS that is already used by the homepage and LinkedIn feed.

**Verification**:
- RED: a newly inserted unpublished article appeared in `/rss.xml`.
- GREEN: the same article is absent after adding the publication filter.
- `python3 -m pytest tests/test_indexability.py tests/test_indexing_promotions.py tests/test_rss_visibility.py -q` -> 16 passed.

**Rollback**: Restore `routes/seo.py` from the production deployment backup and restart `dailyaiwire-web.service`.

## 2026-07-21T21:44:07+02:00 - Recognize Verified Single-Document Root Domains

**Context**: The July 19 Reader Pick cites `freefable.org/`, a one-page primary-source open letter that The Atlantic also links directly. The indexability scorer treated every root URL as a generic publisher homepage, incorrectly making this otherwise strong article ineligible under the tightened source rule.

**Decision**:
- Keep rejecting ordinary root publisher URLs.
- Allow only explicitly verified domains whose root page is the primary document itself.
- Begin the narrow allowlist with `freefable.org`; additions require equivalent source verification.

**Verification**:
- RED: the verified single-document regression scored 91 but remained blocked by `generic_source_url`.
- GREEN: the observed root domain passes while `https://example.com/` remains blocked.
- `python3 -m pytest tests/test_indexability.py tests/test_indexing_promotions.py -q` -> 15 passed.

**Rollback**: Restore `services/indexability.py` from the production deployment backup and restart `dailyaiwire_fetcher`.

## 2026-07-21T21:23:56+02:00 - Isolate Qdrant as a Localhost Service

**Context**: Gunicorn semantic search and the fetcher opened the same embedded Qdrant directory. A search request left one web worker holding the exclusive store lock, causing every later fetcher vector write to fail. The VPS already had a shared Qdrant service for legal projects, but its single master key could access all collections and was not an acceptable cross-project boundary.

**Decision**:
- Run a dedicated DailyAIWire Qdrant container on localhost-only ports `6433/6434` with a separate volume and API key.
- Configure `embedding_service.py` through `QDRANT_URL` and `QDRANT_API_KEY`, while retaining embedded mode as the local-development and rollback fallback.
- Keep article generation and deterministic story dedup independent of Qdrant availability.

**Verification**:
- RED: the remote-client configuration test observed the existing embedded `path` argument instead of the configured URL and API key.
- GREEN: `python3 -m pytest tests/test_embedding_service_config.py tests/test_ad_filter_logic.py -q` -> 4 passed.
- Relevant regression suite -> 129 passed.
- Production Qdrant is healthy on localhost-only ports, the old embedded directory has no open handles, and public search returns ten semantic results.
- The production article backfill runs detached at low priority with restricted CPU affinity. Its dedicated key was rotated after an initial wrapper exposed it in process arguments; the replacement wrapper keeps the key out of the process command line.

**Rollback**: Restore `embedding_service.py`, remove the two Qdrant variables from the application environment, restart `dailyaiwire-web.service` and `dailyaiwire_fetcher`, then stop `dailyaiwire-qdrant`. The dedicated volume is retained unless explicitly removed.

## 2026-07-21T21:10:10+02:00 - Add Deterministic Cross-Source Story Deduplication

**Context**: Two homepage lead articles covered the same Hugging Face autonomous-agent breach from different publishers, four hours apart. The later cycle's Gemini headline filter returned HTTP 503 and fell back to ranked candidates. The one-hour post-publication dedup window could not compare the pair, and the fetcher's Qdrant index write was blocked because a Gunicorn worker held the embedded store lock.

**Decision**:
- Reject strong same-event headline matches against the last 36 hours before any LLM analysis.
- Repeat the deterministic title-and-gist comparison against SQLite immediately before publication so LLM and vector-store failures cannot bypass it.
- Require strong token containment with at least five shared event tokens, and preserve distinct numbered versions such as GPT-5 versus GPT-6.
- Keep the existing semantic and AI dedup layers as additional non-blocking signals.

**Verification**:
- RED: the observed Hugging Face pair passed both existing gates and all three new regression checks failed.
- `python3 -m pytest tests/test_source_quality.py tests/test_persistence_images.py tests/test_indexing_promotions.py tests/test_indexability.py tests/test_smoke.py tests/test_fetcher_daily_cap.py tests/test_fetcher_env_loading.py tests/test_indexing_audit.py -q` -> 125 passed.
- `python3 -m py_compile services/story_dedup.py fetcher/sources.py fetcher/persistence.py` -> passed.

**Rollback**: Restore the three runtime files from the timestamped production deployment backup and restart `dailyaiwire_fetcher`. Re-publish any manually corrected article row by setting `is_published = 1`.

---

## 2026-07-21T20:58:40+02:00 - Use Systemd as the Sole DailyAIWire Web Process Owner

**Context**: Production had both `dailyaiwire-web.service` and Supervisor configured to start the same Gunicorn command on port 8000. Systemd kept the public site healthy, while Supervisor repeatedly started a duplicate process that failed on the occupied port and restarted every six seconds.

**Decision**:
- Keep the enabled `dailyaiwire-web.service` unit as the sole owner of the DailyAIWire Gunicorn web process.
- Set Supervisor's duplicate `dailyaiwire` program to `autostart=false` and `autorestart=false`.
- Keep `dailyaiwire_fetcher` under Supervisor without changing its restart policy.

**Verification**:
- Systemd remained active with one Gunicorn master and four workers on `127.0.0.1:8000`.
- Supervisor reports the duplicate web program as `STOPPED Not started` and the fetcher as `RUNNING`.
- Local and public health endpoints return HTTP 200.

**Rollback**: Restore `dailyaiwire.supervisor.conf` from `/home/dailyai/dailyaiwire.news/ops/deploy-backups/reader-picks-20260721T184852Z`, stop and disable `dailyaiwire-web.service`, run `supervisorctl reread && supervisorctl update`, then start Supervisor's `dailyaiwire` program.

---

## 2026-07-21T20:30:22+02:00 - Give Index-Selected Articles Crawlable Reader Picks Links

**Context**: Production had seven articles selected for Google indexing, but none was linked from the homepage and none of their related-article modules linked to another selected page. Some selected articles were buried behind thousands of newer URLs. Selection also favored old all-time view leaders and accepted generic source homepages.

**Decision**:
- Present the three most recently selected pages on the homepage as `Reader Picks`; do not expose internal promotion terminology.
- Prioritize selected pages in same-category and cross-category related links while retaining six total recommendations.
- Prefer quality-eligible articles published within the last 30 days, then fall back to older eligible content when no recent candidate qualifies.
- Require a specific HTTP or HTTPS source article URL for future indexing selection; reject missing, malformed, and homepage-only source URLs.
- Keep the one-new-article-per-UTC-day limit, 24-hour observation window, publishing volume, and existing selections unchanged.

**Verification**:
- RED: four new regression expectations failed before implementation.
- `python3 -m pytest tests/test_indexing_promotions.py tests/test_indexability.py -q` -> 14 passed.
- `python3 -m pytest tests/test_indexing_promotions.py tests/test_indexability.py tests/test_smoke.py tests/test_fetcher_daily_cap.py tests/test_fetcher_env_loading.py tests/test_indexing_audit.py -q` -> 105 passed.
- `python3 -m py_compile routes/public.py services/indexability.py services/indexing_promotions.py` -> passed.
- The full suite retains a pre-existing order-dependent admin fixture error in `test_admin_indexing_page_and_csv`; that test passes independently.

**Rollback**: Remove the Reader Picks query and template section, restore chronological related-article ordering, remove the freshness ordering clause and source URL hard blockers, then restart the web and fetcher services. Existing `google_index_promotions` rows require no database rollback.

---

## 2026-07-15T16:48:28+02:00 - Keep Permanent Pages Outside the Daily Article Limit

**Context**: The one-article-per-day recovery policy applies only to generated article pages. The live core sitemap already contained seven permanent pages, but three useful public pages were indexable without being listed, while the transactional thank-you page was accidentally indexable.

**Decision**:
- Keep permanent site pages independently indexable; they do not consume the daily article promotion allowance.
- Add `/how-it-works`, `/impressum`, and `/subscribe` to `sitemap-core.xml`.
- Give `/how-it-works` unique search and social metadata before sitemap inclusion.
- Mark `/thank-you` as `noindex, follow` in both HTML and the response header, and keep it out of the sitemap.

**Verification**:
- RED tests confirmed the three permanent pages were missing and the thank-you page was indexable.
- `python3 -m pytest tests/test_indexing_promotions.py tests/test_indexability.py tests/test_smoke.py tests/test_fetcher_daily_cap.py tests/test_fetcher_env_loading.py tests/test_indexing_audit.py -q` -> 102 passed.
- `python3 -m py_compile routes/public.py routes/seo.py` -> passed.

**Rollback**: Restore the previous `routes/public.py`, `routes/seo.py`, and `templates/how_it_works.html`; restart the web service. No database rollback is required.

---

## 2026-07-15T16:40:00+02:00 - Observe Articles for 24 Hours Before Google Promotion

**Context**: Daily promotion should use reader demand signals only after an article has had a full day to collect meaningful views. A calendar-day check could promote an article less than 24 hours after publication.

**Decision**:
- Exclude articles published less than 24 hours before the UTC promotion check.
- Apply the cutoff before view-based ranking and quality scoring.
- Keep the existing limit of one new promotion per UTC calendar day.
- Continue evaluating from the two-hour fetch cycle, so actual promotion occurs between 24 and roughly 26 hours after publication.

**Verification**:
- The boundary test failed before implementation because the promotion function did not accept an evaluation time.
- The test now confirms that an article exactly 24 hours old is eligible while one published one second later is excluded, even with much higher views.
- `python3 -m pytest tests/test_indexing_promotions.py tests/test_indexability.py tests/test_smoke.py tests/test_fetcher_daily_cap.py tests/test_fetcher_env_loading.py tests/test_indexing_audit.py -q` -> 100 passed.
- `python3 -m py_compile services/indexing_promotions.py` -> passed.

**Rollback**: Restore the previous `services/indexing_promotions.py`. Existing promotion records remain valid and require no database rollback.

---

## 2026-07-15T16:29:28+02:00 - Promote One Reader-Validated Article Per Day for Google Recovery

**Context**: The 2026-07-15 Search Console export showed zero indexed pages and 1,693 URLs in `Crawled - currently not indexed`. Production published 1,011 articles in the preceding 30 days, while only 225 passed the existing indexability gate. The earlier 500-core plus 400-archive sitemap recovery strategy did not reverse the decline.

**Decision**:
- Keep all published articles available to readers, social channels, newsletters, RSS, and internal navigation.
- Promote at most one new article per UTC calendar day into Google's indexable set.
- Rank unpromoted candidates by `verified_views`, then raw `views`, quality score, publication time, and ID.
- Require the existing indexability threshold before promotion, so bot traffic or popularity alone cannot promote weak content.
- Persist promotions in `google_index_promotions` with unique constraints on both article and day.
- Mark unpromoted article pages `noindex, follow` and exclude them from article sitemaps.
- Keep previously promoted articles indexable and accumulated in `sitemap-core.xml`.
- Stop advertising the legacy archive sitemap; keep its endpoint empty so old Search Console references resolve successfully.
- Run the idempotent promotion check from every two-hour fetch cycle so no separate cron or manual process is required.

**Verification**:
- RED tests failed before implementation because the promotion service and robots behavior did not exist.
- `python3 -m pytest tests/test_indexing_promotions.py tests/test_indexability.py tests/test_smoke.py tests/test_fetcher_daily_cap.py tests/test_fetcher_env_loading.py tests/test_indexing_audit.py -q` -> 99 passed.
- `python3 -m py_compile services/indexing_promotions.py app.py fetcher/__init__.py fetcher/db_init.py routes/public.py routes/seo.py` -> passed.
- Read-only production dry run selected `amazon-jassy-challenges-nvidia-intel-starlink-custom-chips`, with 63 verified views and indexability score 91, as the first candidate.
- The full repository suite retains an unrelated order-dependent admin fixture failure that passes when rerun independently; all indexing, fetcher, smoke, and indexing-audit tests pass together.

**Rollback**: Restore the timestamped deployment backup for `app.py`, `fetcher/__init__.py`, `fetcher/db_init.py`, `routes/public.py`, `routes/seo.py`, and `templates/base.html`; remove `services/indexing_promotions.py`; restart `dailyaiwire` and `dailyaiwire_fetcher`. The `google_index_promotions` table can remain unused or be dropped manually after rollback.

---

## 2026-07-05T14:57:32+02:00 - Normalize HTML-Escaped UTM Query Keys

**Context**: GA4 showed recent `(data not available)` rows for source/medium. Google documents this as an attribution-processing state for recent traffic when UTM or ad identifiers are present, but production logs also showed occasional malformed links with query keys such as `amp;utm_medium`, caused by HTML-escaped URLs being passed through a social/email layer.

**Decision**:
- Add request middleware that redirects GET/HEAD requests containing malformed `amp;utm_*` query keys to clean `utm_*` keys before the page and GA tag render.
- Preserve normal UTM links and do not alter POST requests.
- Keep existing noindex behavior for query-string article URLs.

**Verification**:
- `python3 -m pytest -q tests/test_smoke.py::TestSEORoutes::test_malformed_html_escaped_utm_query_redirects_to_clean_url tests/test_smoke.py::TestSEORoutes::test_rss_feed tests/test_smoke.py::TestSEORoutes::test_linkedin_rss_feed tests/test_smoke.py::TestPublicRoutes::test_article_page tests/test_smoke.py::TestPublicRoutes::test_homepage_analytics_has_client_bot_guard tests/test_smoke.py::TestSEORobotsDirectives::test_article_with_query_params_is_noindex`

**Rollback**: Restore `app.py` from the deployment backup and restart `dailyaiwire`. GA4 `(data not available)` may still appear for recent/intraday data because that is Google-side attribution processing rather than an application error.

---

## 2026-07-05T14:46:35+02:00 - Add Newsletter Unsubscribe and Delivery Audit

**Context**: A Microsoft 365 recipient appeared delayed after the weekly newsletter send. Production logs showed Resend accepted the message, but the app only stored `DELIVERED` and did not expose a working unsubscribe endpoint. Mailbox scanners also requested `/unsubscribe` and received `404`, which is a deliverability and compliance risk.

**Decision**:
- Add tokenized `/unsubscribe/<newsletter_id>/<token>` handling for GET and one-click POST requests.
- Mark unsubscribed subscribers as `UNSUBSCRIBED` and record a subscriber audit event.
- Render per-recipient unsubscribe URLs in newsletter footers.
- Add `List-Unsubscribe` and `List-Unsubscribe-Post` headers to Resend sends.
- Store Resend message IDs and raw provider responses on delivery rows for future troubleshooting.

**Verification**:
- `python3 -m pytest -q tests/test_security_hardening.py -k "send_newsletter_adds_unsubscribe_headers or newsletter_unsubscribe_token or send_newsletter_uses_request_timeout"`
- `python3 -m pytest -q tests/test_security_hardening.py tests/test_subscribe_abuse.py tests/test_admin_subscriber_reconfirmation.py tests/test_confirmation_email_template.py`

**Rollback**: Restore `newsletter_sender.py`, `routes/public.py`, `routes/admin_content.py`, and `templates/email/briefing.html` from the deployment backup. Existing `UNSUBSCRIBED` rows can be reactivated manually with `UPDATE subscribers SET status='ACTIVE' WHERE email='<address>';` if an unsubscribe was accidental.

---

## 2026-06-14T21:10:38+02:00 - Raise Headline Filter Candidate Target to 8

**Context**: The June billing export showed Gemini spend dropped to roughly €0.11/day after article prompts stopped hitting the expensive Flash long-input billing bucket. Article volume also fell, so we can cautiously raise the number of candidates considered per cycle while keeping the strict Flash-Lite triage gate.

**Decision**:
- Increase the headline filter baseline target from 6 to 8 candidates per cycle.
- Keep the maximum target at 12.
- Preserve the heuristic quality floor: do not pad the AI filter prompt with negative-score spam/PR/listicle headlines just to hit the higher target.

**Verification**:
- `python3 -m pytest tests/test_source_quality.py::test_filter_high_signal_headlines_caps_results_to_dynamic_target -q`
- `python3 -m pytest tests/test_source_quality.py -q`
- `python3 -m py_compile fetcher/sources.py`

**Rollback**: Restore `fetcher/sources.py` from the deployment backup and restart `dailyaiwire_fetcher`. If article volume or cost rises too quickly, revert the baseline target from 8 back to 6.

---

## 2026-06-10T22:56:29+02:00 - Tighten Flash-Lite Article Triage

**Context**: Production logs showed Flash-Lite triage was technically working, but it kept 86.8% of candidates on 2026-06-09 and 91.8% on 2026-06-10. That meant most candidates still reached the expensive full `article_analysis` path.

**Decision**:
- Make the triage prompt more selective without adding a hard publishing cap.
- Instruct the model to usually keep 0-1 items per 3-article batch, keep 2 only for clearly major stories, and keep all only when every item is exceptional.
- Default uncertain, vague, local/minor, generic AI adoption, routine integration, PR, listicle, affiliate, and repetitive items to `BLOCK`.
- Log triage block reasons so production keep/block behavior can be audited after deployment.

**Verification**:
- `python3 -m pytest tests/test_ai_governance.py::test_article_triage_prompt_stays_compact_and_english_only -q`
- `python3 -m pytest tests/test_ai_governance.py -q`
- `python3 -m py_compile fetcher/ai_processor.py`

**Rollback**: Restore `fetcher/ai_processor.py` from the deployment backup, or set `GEMINI_ARTICLE_TRIAGE_ENABLED=false` in `.env` and restart `dailyaiwire_fetcher` if the stricter gate suppresses too many articles.

---

## 2026-06-10T21:00:00+02:00 - Route Manual Gemini Scripts Through Gateway

**Context**: Google project-level attribution is not available from the billing report, so future root-cause work depends on making every local DailyAIWire Gemini caller visible. Four manual scripts still used direct `google.generativeai` calls and would bypass `ai_logs` if run.

**Decision**:
- Migrate `scripts/generate_diagrams.py` to `AIGateway.generate_text` with prompt type `diagram_backfill`.
- Migrate `scripts/ingest_manual_urls.py` to `AIGateway.generate_text` with prompt type `manual_url_ingest`.
- Migrate `scripts/generate_lab_metadata.py` to `AIGateway.generate_text` with prompt type `lab_metadata`.
- Migrate `scripts/generate_sample_audio.py` to `AIGateway.generate_text` with prompt type `sample_audio_script`.
- Add a regression test that fails if live `fetcher`, `services`, or `scripts` reintroduce direct Gemini SDK calls outside `services/ai_gateway.py`.

**Verification**:
- `python3 -m pytest tests/test_no_unlogged_gemini.py tests/test_ai_governance.py -q`
- `python3 -m py_compile services/ai_gateway.py scripts/generate_diagrams.py scripts/ingest_manual_urls.py scripts/generate_lab_metadata.py scripts/generate_sample_audio.py`
- VPS compile check for the same deployed scripts.
- VPS grep now finds direct Gemini `generate_content` only inside `services/ai_gateway.py`.

**Rollback**: Restore script files from `/home/dailyai/dailyaiwire.news/ops/deploy-backups/20260610T195748Z-manual-gemini-gateway`, then run the desired manual script again. No Supervisor restart is required for these manual helpers.

---

## 2026-06-10T19:02:00+02:00 - Add AI Log Fallback for SQLite Lock Gaps

**Context**: Billing investigation showed successful Gemini calls were logging token metadata after the recent instrumentation rollout, but historical server logs also showed `database is locked` failures in the AI logging path. A successful model call followed by a failed SQLite write creates a billing blind spot.

**Decision**:
- Keep `ai_logs` as the primary audit table.
- Switch gateway logging to the shared timeout-aware DB helper so SQLite waits longer before failing.
- Add `logs/ai_logs_fallback.jsonl` for failed DB writes, storing model, prompt type, status, token counts, cached tokens, character counts, timestamp, and DB error.
- Do not store full prompt or response text in the fallback file to avoid creating a second sensitive prompt archive.

**Verification**:
- `python3 -m pytest tests/test_ai_governance.py -q`
- `python3 -m py_compile services/ai_gateway.py`
- VPS compile check with `/home/dailyai/dailyaiwire.news/venv/bin/python -m py_compile services/ai_gateway.py`
- Restarted `dailyaiwire_fetcher`, `dailyaiwire`, and `tweet_scheduler` under Supervisor.

**Rollback**: Restore `/home/dailyai/dailyaiwire.news/ops/deploy-backups/20260610T165950Z-ai-log-fallback/services/ai_gateway.py` to `/home/dailyai/dailyaiwire.news/services/ai_gateway.py`, then restart `dailyaiwire_fetcher`, `dailyaiwire`, and `tweet_scheduler`.

---

## 2026-06-09T13:58:38+0200 - Add Flash-Lite Article Triage Before Full Analysis

**Context**: Billing analysis showed `article_analysis` on `gemini-2.5-flash` remained the dominant cost driver. Even after prompt trimming and stricter headline filtering, every prepared article still went straight into the expensive full-analysis path.

**Decision**:
- Added a cheap Flash-Lite triage stage in `fetcher/ai_processor.py` before full article analysis.
- Triage uses a shorter source excerpt (`ARTICLE_TRIAGE_CHAR_LIMIT`, default `500`) and returns `KEEP` or `BLOCK` decisions via a structured `ArticleTriageDecision` schema.
- Full article analysis now runs only on triage-approved records.
- If triage fails, the fetcher falls back to the old behavior and analyzes the full prepared batch to avoid a publishing outage.
- Triage is enabled by default through `GEMINI_ARTICLE_TRIAGE_ENABLED=true`.

**Rationale**: This adds a low-cost gate in front of the expensive Flash synthesis step, which is the only path large enough to move daily spend materially. The fallback keeps operational risk low while we watch the keep/block rate in production.

**Verification**:
- `python3 -m pytest tests/test_ai_governance.py -q`
- `python3 -m py_compile fetcher/ai_processor.py services/ai_schemas.py ai_config.py`

**Rollback**: Restore `fetcher/ai_processor.py`, `services/ai_schemas.py`, and `ai_config.py` from the pre-deploy backup, then restart `dailyaiwire_fetcher`. If needed, set `GEMINI_ARTICLE_TRIAGE_ENABLED=false` in `.env` and restart the fetcher to disable the gate without code changes.

## 2026-06-09T13:01:30+0200 - Shrink Headline Filter Prompt

**Context**: Live instrumentation showed `headline_filter` prompts at roughly 8.7k characters. Most of that payload came from injecting every title published in the last 36 hours, duplicating the candidate headline block, and carrying long examples that did not affect the actual output format.

**Decision**:
- Added a dedicated `_build_headline_filter_prompt(...)` helper in `fetcher/sources.py`.
- Capped recent-title context with `HEADLINE_FILTER_RECENT_TITLES_LIMIT` defaulting to `24`.
- Removed the duplicated `HEADLINES:` block and stripped the long example section.
- Kept the same filter purpose and output contract: comma-separated candidate indices only.
- Updated `get_recent_published_titles()` to return titles ordered by newest first so the prompt cap keeps the most recent duplicate context.

**Rationale**: This cuts routine Flash-Lite prompt size without changing article-analysis logic or the number of published articles. The filter still catches duplicate stories and low-signal launches, but with a much smaller fixed prompt overhead per cycle.

**Verification**:
- `python3 -m pytest tests/test_source_quality.py -q`
- `python3 -m py_compile fetcher/sources.py fetcher/db_init.py`

**Rollback**: Restore `fetcher/sources.py` and `fetcher/db_init.py` from the pre-deploy backup, then restart `dailyaiwire_fetcher`.

## 2026-06-09T12:28:44+0200 - Detailed AI Token Instrumentation

**Context**: Billing still showed Gemini 2.5 Flash long-input as the dominant cost driver, but `ai_logs` only stored a coarse total token value in `cost_estimate`. That was not enough to prove whether the remaining spend came from prompt size, output size, thinking tokens, or another request path.

**Decision**:
- Extended the shared `ai_logs` schema used by `services/ai_gateway.py` and `fetcher/db_init.py`.
- Added nullable per-call audit fields: `prompt_tokens`, `output_tokens`, `thoughts_tokens`, `total_tokens`, `cached_input_tokens`, `prompt_char_count`, `response_char_count`, and `request_status`.
- Kept `cost_estimate` unchanged for backward compatibility with existing queries.

**Rationale**: This adds direct per-call observability for `article_analysis` and every other gateway-backed prompt without changing model behavior, prompt content, or article generation flow. The added character counts make it possible to distinguish token spikes caused by oversized source text from spikes caused by another request path.

**Verification**:
- `python3 -m pytest tests/test_ai_governance.py -q`
- `python3 -m pytest tests/test_fetcher_daily_cap.py -q`
- `python3 -m py_compile services/ai_gateway.py fetcher/db_init.py`

**Rollback**: Restore `services/ai_gateway.py`, `fetcher/db_init.py`, and the matching test schema to the previous version, then restart the fetcher. Existing `ai_logs` rows remain valid because this change only adds nullable columns.

## 2026-05-30T12:20:00+02:00 - Disable General Article Use of Google Indexing API by Default

**Context**: DailyAIWire article publication and X posting were automatically calling `google_indexer.notify_google_index()` for normal article URLs. Google documents the Indexing API for `JobPosting` and `BroadcastEvent` pages, not general news/article URLs. Leaving the calls active created false confidence, noisy audit rows, and unnecessary external requests without solving the real Search Console coverage issue.

**Changes**:
- `google_indexer.py`:
  - Added a default guard that records article URL notifications as `skipped` instead of sending them to Google's Indexing API.
  - Added `ALLOW_UNSUPPORTED_GOOGLE_INDEXING_API` as an explicit escape hatch for legacy or emergency manual use.
- `tests/test_indexing_audit.py`:
  - Added regression coverage proving unsupported article URLs are skipped by default.
  - Preserved success, quota, and missing-credentials coverage behind the explicit env override.

**Verification**:
- `python3 -m pytest tests/test_indexing_audit.py -q` -> passed.
- `python3 -m pytest tests/test_x_posting.py -q` -> passed.
- `python3 -m pytest tests/test_persistence_images.py -q` -> passed.

**Rollback**:
- Revert `google_indexer.py`, `tests/test_indexing_audit.py`, and this `DECISIONS.md` entry.
- If legacy behavior is temporarily needed before a code rollback, set `ALLOW_UNSUPPORTED_GOOGLE_INDEXING_API=1` in the runtime environment, then remove it after the test.

## 2026-05-13T21:47:00+02:00 - Newsletter Subscribe Cooldown for Repeated Blocked Sources

**Context**: The newsletter signup form already used a honeypot field and minimum render-time guard, but production telemetry showed a bot repeatedly tripping the honeypot from the same source. The defense was blocking inserts correctly, yet every repeated hit still generated new DB events and log noise.

**Changes**:
- `routes/public.py`:
  - Added a short server-side cooldown for repeated blocked subscribe sources.
  - If the same IP hash and user-agent pair has a recent blocked subscribe event, the request is silently dropped to the normal review path without writing a new subscriber or a new event.
  - Added an IP-only burst safeguard for unusually noisy blocked traffic from one source.
- `tests/test_subscribe_abuse.py`:
  - Added a regression test proving that a second request from the same blocked source no longer inserts a subscriber or writes a second abuse event.

**Verification**:
- `python3 -m pytest -q tests/test_subscribe_abuse.py` -> passed.
- `python3 -m pytest -q tests/test_security.py -k subscribe` -> passed.
- `python3 -m pytest -q tests/test_smoke.py -k "thank_you_page or subscribe"` -> passed.

**Rollback**:
- Revert `routes/public.py`, `tests/test_subscribe_abuse.py`, and this `DECISIONS.md` entry.
- No schema rollback is needed because this change reuses the existing `subscriber_events` table.

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

---

## 2026-05-04T22:33:58+02:00 - Admin Reconfirmation for Suspicious Subscribers

**Context**: The suspicious May 4 subscriber batch should not receive newsletters, but deleting them immediately would remove the ability to distinguish real users from automated list poisoning.

**Decision**:
1. Keep suspicious subscribers quarantined under `SUSPICIOUS`.
2. Add an admin-only POST action to send reconfirmation emails to all `SUSPICIOUS` subscribers.
3. Move successfully emailed suspicious subscribers to `PENDING` with a new confirmation token.
4. Keep failed sends as `SUSPICIOUS` with a `reconfirmation_failed` audit event.
5. Activate only after the existing double opt-in confirmation link is clicked.
6. Use HTTPS confirmation links explicitly.

**Trigger**: User asked how to check whether the suspicious subscribers are real and approved the reconfirmation workflow.

**Rollback**:
- Revert `routes/admin_content.py`, `templates/admin/subscribers.html`, `services/subscribers.py`, `routes/public.py`, and `tests/test_admin_subscriber_reconfirmation.py`.
- Existing `SUSPICIOUS` rows remain quarantined; no data deletion is required for rollback.

---

## 2026-05-04T22:42:30+02:00 - Pending Subscriber Expiry and Admin Filters

**Context**: Reconfirmation moves suspicious subscribers to `PENDING`; unconfirmed rows should not remain in limbo indefinitely, and admin needs quick visibility by status.

**Decision**:
1. Add admin status filters for `ACTIVE`, `PENDING`, `SUSPICIOUS`, `EXPIRED`, `BOUNCED`, and `COMPLAINED`.
2. Add an admin-only POST action to expire stale `PENDING` subscribers after 14 days.
3. Expiry changes status to `EXPIRED` and clears the confirmation token; it does not delete the row.
4. Each expiry writes a `pending_expired` audit event.
5. Keep fresh `PENDING` rows and `ACTIVE` rows untouched.

**Trigger**: User approved the next abuse-cleanup layer after suspicious subscriber reconfirmation.

**Rollback**:
- Revert `routes/admin_content.py`, `templates/admin/subscribers.html`, `tests/test_admin_subscriber_reconfirmation.py`, and this `DECISIONS.md` entry.
- If any row is incorrectly expired, restore it with `UPDATE subscribers SET status='PENDING' WHERE id=<id>;` and send a new reconfirmation token if needed.

---

## 2026-05-04T23:08:19+02:00 - Branded Confirmation Email Template

**Context**: Double opt-in confirmation emails were sent through inline HTML inside `newsletter_sender.py`, which made the user-facing email harder to review, style, and test.

**Decision**:
1. Move the confirmation email HTML into `templates/email/confirmation.html`.
2. Render the template from `send_confirmation_email()` using the Flask app context.
3. Keep a minimal escaped fallback HTML path if template rendering fails.
4. Add a 10 second timeout to the Resend API call so confirmation sends cannot hang indefinitely.
5. Add tests for both template rendering and sender payload generation.

**Trigger**: User asked whether a click-to-activate confirmation email template existed and approved adding one.

**Rollback**:
- Revert `newsletter_sender.py`, `templates/email/confirmation.html`, `tests/test_confirmation_email_template.py`, and this `DECISIONS.md` entry.

---

## 2026-05-05T04:05:49+02:00 - Stored XSS and Upload Path Hardening

**Context**: The security audit found two active stored-XSS paths and inconsistent upload validation. Public newsletter archive pages rendered newsletter intro HTML unsafely, the admin leads modal injected generated HTML with `innerHTML`, and some upload routes accepted extensions that the article edit flow already blocked.

**Decision**:
1. Render Signal intro text as escaped plaintext with preserved line breaks instead of trusting stored HTML.
2. Sanitize admin lead preview HTML through a small allowlist and render it server-side instead of injecting raw model output in the browser.
3. Generate mailto fallback bodies from sanitized plain text rather than raw HTML.
4. Centralize upload extension validation and apply it consistently to article create, stock manager, and author image uploads.
5. Add regression tests covering Signal XSS, lead-preview XSS, and disallowed upload extensions.

**Trigger**: User approved patching the `P1` and `P2` findings from the full website security review.

**Rollback**:
- Revert `helpers.py`, `routes/signal.py`, `templates/signal_detail.html`, `routes/admin_ops.py`, `templates/admin/leads.html`, `routes/admin_core.py`, `tests/test_security_hardening.py`, and this `DECISIONS.md` entry.

---

## 2026-05-05T12:16:57+02:00 - CSP Nonces, Audio Abuse Dedupe, Request Timeouts, and Local Python 3.12 Upgrade

**Context**: The follow-up security pass still had three open hardening items: outbound email requests could hang without timeouts, `/api/track-audio` could be inflated by repeated calls from the same visitor, and CSP still allowed inline script execution broadly. The local workspace also still relied on Python 3.9.6, which is out of support and produced incomplete dependency-audit results.

**Decision**:
1. Add a shared 10 second timeout constant to the remaining Resend send paths in `newsletter_sender.py` and `services/proposal_agent.py`.
2. Add `audio_play_events` persistence and a 30 minute per-visitor dedupe window so repeated audio play pings do not inflate article metrics.
3. Move CSP to a nonce-based `script-src-elem` policy, remove the stale meta CSP tag, and add per-request nonces to inline script blocks while temporarily keeping `script-src-attr 'unsafe-inline'` for existing `onclick` handlers.
4. Add self-healing Qdrant recovery in `embedding_service.py` so an incompatible persisted local store is backed up and rebuilt automatically during client initialization.
5. Build and verify a new local Python 3.12 virtualenv, then promote it to `.venv` only after the full test suite passes.

**Trigger**: User asked to complete all remaining post-audit hardening items instead of stopping after the initial `P1` and `P2` fixes.

**Rollback**:
- Code rollback: revert `app.py`, `routes/api.py`, `newsletter_sender.py`, `services/proposal_agent.py`, `embedding_service.py`, the touched templates, `tests/test_security_hardening.py`, and this `DECISIONS.md` entry.
- Local runtime rollback: `mv .venv .venv-py312-failed && mv .venv-py39-backup-20260505T121038 .venv`

---

## 2026-05-05T12:28:57+02:00 - Proposal Agent Migration to google.genai Governance Path

**Context**: The local Python upgrade removed the remaining compatibility pressure, but `services/proposal_agent.py` was still the one active business workflow using deprecated `google.generativeai`. That path bypassed the shared AI governance layer, meaning proposal generation did not inherit the project-wide structured-output conventions or explicit routine-task thinking budget controls.

**Decision**:
1. Move `ProposalAgent` from direct SDK calls to the shared `AIGateway`.
2. Treat proposal drafting as a routine-cost task by switching it to `ai_config.ROUTINE_MODEL`.
3. Enforce structured output through a dedicated `ProposalDraft` schema in `services/ai_schemas.py`.
4. Keep budget accounting behavior unchanged by continuing to log prompt and output token counts under `Proposal Gen`.
5. Add governance regression coverage proving proposal generation now goes through the gateway with routine model settings and structured schema validation.

**Trigger**: User approved the remaining `google.generativeai` migration work after the broader security and runtime hardening batch.

## 2026-05-30T17:42:00+02:00 - Low-Risk Runtime Hardening for AI Governance and Path Safety

**Context**: The repo review found three live operational leaks that could be fixed without changing page layout or the heavier analytics architecture: some scheduled AI scripts still bypassed `services/ai_gateway.py`, several live modules still depended on relative `news.db` paths, and newsletter tracking would silently fall back to a built-in secret when `SECRET_KEY` was missing.

**Decision**:
1. Migrate `weekly_curator.py` and `opinion_generator.py` to `AIGateway` with structured schemas so their Gemini calls inherit `ai_logs` auditing and the shared runtime controls.
2. Replace the remaining live relative `news.db` paths in `weekly_curator.py`, `opinion_generator.py`, `tweet_scheduler.py`, and `newsletter_sender.py` with `db.DB_PATH`.
3. Load `.env` from an explicit project-root path in those same live entrypoints instead of relying on the process working directory.
4. Require `SECRET_KEY` for newsletter tracking token generation instead of falling back to a predictable default.
5. Harden the article analytics branch so non-GET requests do not rely on uninitialized analytics variables.

**Trigger**: User approved the low-risk remediation stage first and explicitly wanted the fixes applied without destabilizing the site.

**Rollback**:
- Restore `/home/dailyai/dailyaiwire.news/ops/deploy-backups/20260530T153803Z` on production and restart `dailyaiwire` plus `tweet_scheduler`.
- Full code rollback: revert `weekly_curator.py`, `opinion_generator.py`, `tweet_scheduler.py`, `newsletter_sender.py`, `routes/public.py`, `services/ai_schemas.py`, the related tests, and this `DECISIONS.md` entry.

---

**Rollback**:
- Revert `services/proposal_agent.py`, `services/ai_schemas.py`, `tests/test_ai_governance.py`, and this `DECISIONS.md` entry.

---

## 2026-05-09T15:40:00+02:00 - X Cheap Mode Defaults to URL-Free Posts and 3/Day Cap

**Context**: X usage data showed the scheduler was regularly creating 11-12 paid X write events per day, and official X pricing now charges far more for `Content: Create (with URL)` than plain `Content: Create`. The existing formatter always embedded the article URL, which pushed automated posts into the more expensive bucket and made backlog clearing unnecessarily costly.

**Decision**:
1. Default automated X posts to URL-free copy and keep the article body self-contained with headline, category, gist, `Why it matters`, question, hashtags, and a plain-text DailyAIWire CTA.
2. Add `X_INCLUDE_URL` as an explicit rollback/override switch so URL-bearing posts can still be re-enabled intentionally.
3. Add `X_DAILY_LIMIT` with a default of `3` and enforce it in the scheduler against the current Berlin calendar day.
4. Update the admin social queue X preview to match the new production formatter so manual operators see the same cheaper copy mode.
5. Add regression coverage for URL-free defaults, opt-in URL mode, and Berlin-day X daily limit counting.

**Trigger**: User approved reducing X API cost by switching to longer URL-free posts and capping automated volume at 3 posts per day.

**Rollback**:
- Set `X_INCLUDE_URL=true` and raise `X_DAILY_LIMIT` in the environment if an immediate behavioral rollback is needed without code changes.
- Full code rollback: revert `social_distributor.py`, `tweet_scheduler.py`, `templates/admin/social_queue.html`, `tests/test_x_posting.py`, `tests/test_smoke.py`, and this `DECISIONS.md` entry.

---

## 2026-05-20T11:15:13+02:00 - Male-Only Public Audio Rollout

**Context**: Google Cloud Text-to-Speech spend remained materially above target because every published article generated two premium audio reads. Product direction was to cut recurring TTS cost without deleting legacy female files or breaking public article playback.

**Decision**:
1. Default new generated article audio to male-only by setting `AUDIO_GENERATE_FEMALE` off unless explicitly re-enabled.
2. Treat `audio_male` alone as the completion signal for automated backfill so new articles do not get stuck in a permanent "missing female audio" regeneration loop.
3. Preserve any existing `audio_female` database reference when a legacy article is manually or automatically regenerated under male-only mode.
4. Replace the public male/female selector with one neutral `Listen` control that prefers `audio_male` and falls back to legacy `audio_female` when needed.
5. Leave admin upload fields and historic female files untouched so rollback stays non-destructive.

**Trigger**: User approved option 2: generate male-only for new articles, remove female from the public site, and leave old female assets in place.

**Rollback**:
- Set `AUDIO_GENERATE_FEMALE=true` to resume dual-voice generation without further code changes.
- Full code rollback: revert `audio_generator.py`, `generate_missing_audio.py`, `routes/admin_content.py`, `templates/article.html`, `tests/test_audio_rollout.py`, `tests/test_site_health.py`, and this `DECISIONS.md` entry.

---

## 2026-07-10T23:08:52+02:00 - LinkedIn Distribution Limited to 24 Eastern-Time Slots

**Context**: LinkedIn exported 993 DailyAIWire posts over 30 days, with a median same-day interval of roughly 15 minutes. The active n8n workflow allowed eight RSS items per trigger execution and looped through them with a 15-minute wait, but it had no daily ceiling or overnight pause. It also recorded an article as processed before LinkedIn confirmed successful publication.

**Decision**:
1. Keep LinkedIn scheduling in n8n and leave website article publication unchanged.
2. Replace feed-driven batch execution with 24 schedule slots, spaced 45 minutes apart from 06:00 through 23:15 in the `America/New_York` timezone.
3. Process at most one quality-filtered RSS article per scheduled execution and enforce a second 24-success daily guard in workflow static data.
4. Seed current RSS URLs on the replacement workflow's first execution so historical feed items are not reposted.
5. Record an article as processed and increment the daily counter only after the LinkedIn API call succeeds.
6. Preserve the existing post formatting, image upload, fallback payload, LinkedIn credential references, and LinkedIn API nodes.
7. Deliver the replacement as an inactive import-ready workflow so the current production workflow remains available for rollback.

**Trigger**: User approved starting with a maximum of 24 LinkedIn posts per day and pausing automated posting between midnight and 06:00 US Eastern time.

**Verification**:
- Structural validation confirmed 24 unique schedule slots, the Eastern timezone, an inactive import state, valid graph connections, and preserved LinkedIn credential references.
- Deterministic Code-node tests confirmed first-run seeding, newest-unseen selection, post-success marking, duplicate prevention, the daily cap, and the overnight guard.

**Rollback**:
- Deactivate the replacement workflow and reactivate the original `LinkedIn RSS Trigger Production` workflow.
- The original workflow export remains unchanged; delete the replacement workflow if it is no longer required.

---

## 2026-07-21T23:46:00+02:00 - Meta Blog Extraction and Terminal AI Attempt Accounting

**Context**: Meta's former FAIR RSS endpoint now returns a Facebook error page, while the previous replacement endpoint redirects to an HTML 404. A direct official-blog candidate was also repeatedly eligible because terminal AI rejection outcomes were not written to `processing_attempts`. This could produce repeated token spend without a published article.

**Decision**:
1. Replace both deprecated Meta feed URLs with the official `https://ai.meta.com/blog/` page.
2. Extract current Meta blog posts deterministically from server-rendered HTML and admit only posts published within seven days.
3. Condense Meta article text around model names, measured outcomes, and deployment facts while preserving the existing global 1,400-character source limit.
4. Record `TRIAGE_BLOCKED` and `INSUFFICIENT_DATA` as terminal processing attempts so rejected candidates respect the existing 24-hour cooldown.
5. Do not mark successful analyses or transient API failures at this stage, preserving retries when persistence or an external service fails.

**Verification**:
- Relevant source, environment, daily-cap, and AI governance suites passed with 44 tests.
- Live official Meta extraction returned five posts, with one eligible in the seven-day window.
- The selected Meta context retained named models and measured outcomes without increasing the global prompt limit.

**Rollback**:
- Restore the production files and database from `/home/dailyai/dailyaiwire.news/ops/deploy-backups/meta-blog-extractor-20260721T213500Z/` and restart the fetcher.
- Full code rollback: revert `fetcher/sources.py`, `fetcher/ai_processor.py`, `scripts/repair_source_urls.py`, `scripts/migrate_sources.py`, the related tests, and this entry.

---

## 2026-07-21T23:55:50+02:00 - Restore the Official Microsoft Research Feed

**Context**: Microsoft Research had timed out repeatedly for several days because the repair map replaced its responsive official Research RSS feed with the slow Azure blog feed. Live checks returned the official feed in under one second while the Azure endpoint timed out after 20 seconds.

**Decision**:
1. Map the failing Azure endpoint to `https://www.microsoft.com/en-us/research/feed/`.
2. Use the official Research feed in future source seeds and repair migrations.
3. Leave Hacker News unchanged because its failures are intermittent and its endpoint continues to return valid RSS between upstream 502 responses.

**Verification**:
- Source-quality, environment-loading, and daily-cap suites passed with 25 tests.
- Python compilation and diff checks passed.

**Rollback**:
- Restore the production files and database from `/home/dailyai/dailyaiwire.news/ops/deploy-backups/microsoft-feed-20260721T215550Z/` and restart the fetcher.
- Full code rollback: revert the Microsoft entries in `fetcher/sources.py`, `scripts/repair_source_urls.py`, `scripts/migrate_sources.py`, the related test, and this entry.

---

## 2026-07-22T00:08:33+02:00 - Reduce Aggregator and Research-Paper Dominance

**Context**: The previous 30 days contained 1,029 published articles. Google News produced 195 articles from headline-level wire context, while Hugging Face and ArXiv supplied 394 articles. These three paths represented 57 percent of output and made the site overly dependent on snippets and research-paper coverage.

**Decision**:
1. Disable Google News in production while retaining its database row for immediate rollback.
2. Reduce the default `HF_PAPERS_LIMIT` from 12 to 4 candidates per fetch cycle.
3. Keep direct editorial feeds, ArXiv, Hacker News, and Twitter sources active so important coverage can replace removed aggregator volume.
4. Preserve `HF_PAPERS_LIMIT` as an environment override and avoid introducing a hard daily publishing cap.

**Verification**:
- AI governance, source-quality, environment-loading, daily-cap, and X posting suites passed with 54 tests.
- The Hugging Face default-limit regression test confirmed no more than four extracted candidates.

**Rollback**:
- Set Google News `is_active` back to `1` and set `HF_PAPERS_LIMIT=12` in production, then restart the fetcher.
- Restore production files and database from `/home/dailyai/dailyaiwire.news/ops/deploy-backups/quality-source-policy-20260721T220833Z/`.

---

## 2026-07-22T00:08:33+02:00 - Guarantee Tweet Scheduler Transaction Cleanup

**Context**: Queue maintenance encountered a SQLite commit failure and left its connection open while the scheduler slept. The process retained a write lock, causing article requests to fail and Gunicorn workers to time out.

**Decision**:
1. Roll back queue-maintenance transactions whenever an update or commit fails.
2. Close the SQLite connection in a `finally` block before propagating the error to the scheduler loop.
3. Keep the existing scheduler retry interval and posting behavior unchanged.

**Verification**:
- A regression test reproduces a locked commit and proves both rollback and close occur.
- Restarting only `tweet_scheduler` released the production write lock and restored article reads.

**Rollback**:
- Restore `tweet_scheduler.py` from `/home/dailyai/dailyaiwire.news/ops/deploy-backups/quality-source-policy-20260721T220833Z/` and restart `tweet_scheduler`.

---

## 2026-07-22T01:05:49+02:00 - Enforce Subscriber Recipient Isolation at the Network Boundary

**Context**: A February 2026 newsletter exposed subscriber addresses because the full subscriber list was passed to Resend's `to` field. Individual delivery replaced that implementation, but welcome, confirmation, and two obsolete incident scripts could still call the provider without passing through the same fail-closed guard.

**Decision**:
1. Route every subscriber-facing Resend request through one private gateway.
2. Reject any payload unless `to` contains exactly the expected recipient and neither `cc` nor `bcc` is present.
3. Run the guard immediately before the network request so invalid payloads cannot reach Resend.
4. Remove the obsolete apology senders and deployment patcher to eliminate accidental bypass routes. Git retains their audit history.
5. Keep partnership proposal delivery separate because it does not use the subscriber list or newsletter sender.

**Verification**:
- Regression tests prove unsafe payloads fail before any network call and that the subscriber email module contains only one direct `requests.post` gateway.
- Welcome, confirmation, newsletter delivery, unsubscribe headers, and subscriber reconfirmation tests pass.

**Rollback**:
- Restore `newsletter_sender.py` and the retired scripts from the timestamped production deployment backup, then restart `dailyaiwire-web.service`.

---

## 2026-07-22T01:23:48+02:00 - Make Newsletter Broadcasts Atomic and Idempotent

**Context**: The admin send action started an unreserved background thread. Two clicks could therefore run overlapping workers, and a provider success followed by a local crash could resend an email before its delivery record was committed.

**Decision**:
1. Atomically change eligible newsletters to `SENDING` before starting a worker; a second reservation fails closed.
2. Recover reservations older than two hours while rejecting active overlapping sends.
3. Add a case-insensitive unique index on `(newsletter_id, recipient_email)`.
4. Add a deterministic Resend `Idempotency-Key` for every newsletter-recipient request. Resend retains provider idempotency keys for 24 hours.
5. Require an admin confirmation page showing active, delivered, and remaining recipient counts.
6. Revalidate the confirmed remaining count inside the reserved worker before sending the first email.
7. Add a private test-send action that creates no delivery record and does not change newsletter status.
8. Mark incomplete or crashed broadcasts `PARTIAL` with a bounded error message so they can be inspected and safely resumed.

**Verification**:
- Atomic reservation, duplicate delivery, audience race, provider idempotency, test-send isolation, confirmation UI, and worker startup tests pass.
- Existing newsletter rendering, confirmation, reconfirmation, unsubscribe, timeout, and recipient-isolation tests pass.

**Rollback**:
- Restore the changed application files from the timestamped production deployment backup and restart `dailyaiwire-web.service`.
- The added nullable audit columns and unique index may remain safely; drop `idx_newsletter_delivery_recipient` only if a full schema rollback is required.

---

## 2026-07-22T20:27:10+02:00 - Track Newsletter Delivery from Signed Provider Events

**Context**: A successful Resend API response was stored as `DELIVERED`, although it only confirmed that Resend accepted the request. The tracking pixel then replaced that status with `OPENED`, so delivery, engagement, bounce, complaint, and failure states could not be distinguished reliably.

**Decision**:
1. Record successful send API responses as `ACCEPTED` and update delivery state only from signed Resend webhooks.
2. Verify the raw request body with Resend's Svix signature protocol and reject missing, invalid, stale, or oversized requests.
3. Store each Svix event ID once so provider retries and manual replays are idempotent.
4. Match events only through the Resend message ID already stored for a private one-recipient send. Never trust the webhook recipient field for subscriber updates.
5. Suppress active subscribers after a complaint, provider suppression, or permanent bounce. Keep temporary bounces retryable.
6. Preserve opens, clicks, and unsubscribes as separate timestamps instead of overwriting delivery status.
7. Show accepted, delivered, failed, opened, and unsubscribed counts separately in the admin dashboard and log abnormal provider failure rates.
8. Store event metadata only, not complete webhook payloads, to minimize retained subscriber data.

**Verification**:
- Signature rejection, valid delivery, replay safety, bounce classification, complaint suppression, provider failure, provider suppression, open-state preservation, acceptance state, admin metrics, and unsubscribe timestamp tests pass.
- Python compilation passes for all changed runtime modules.

**Rollback**:
- Restore the changed application files and database from the timestamped production deployment backup, reinstall the prior requirements, and restart `dailyaiwire-web.service`.
- The added nullable delivery columns and `newsletter_provider_events` table may remain safely if only application code is rolled back.

---

## 2026-07-22T22:43:34+02:00 - Add a Privacy-Safe Subscriber Conversion Funnel

**Context**: Newsletter delivery events were available per broadcast, while signup acquisition and confirmation performance remained split across subscriber records and audit events. The application also had no measurement of whether a signup form was actually seen.

**Decision**:
1. Keep delivery, open, bounce, complaint, and unsubscribe details in `/admin/newsletters`.
2. Add 7, 30, and 90-day acquisition funnel views to `/admin/subscribers`, grouped by the existing signup placement taxonomy.
3. Measure signup and confirmation using signup cohorts so later confirmations do not distort the selected acquisition period.
4. Record anonymous form visibility only after a form remains at least 50 percent visible for one second.
5. Exclude likely bots, reject unknown placements, and deduplicate the same hashed IP and placement for 30 minutes so user-agent rotation cannot create extra writes.
6. Never attach an email address to a form-view event, and retain the existing subscriber event schema.
7. Track the hidden site modal only after it has opened and remained open for one second.
8. Calculate view-to-confirm only from subscribers acquired after form-view tracking began, preventing historical confirmations from producing rates above 100 percent.

**Verification**:
- Funnel aggregation, placement breakdown, invalid placement, bot exclusion, request deduplication, cache controls, and admin rendering tests pass.
- The broader subscriber, newsletter, webhook, security, and smoke suite passes with 138 tests.
- Python compilation and scoped whitespace checks pass.

**Rollback**:
- Restore the changed application files and database from the timestamped production deployment backup, then restart `dailyaiwire-web.service`.
- Existing anonymous `form_view` rows can remain safely because older application versions ignore them.

---

## 2026-07-23T01:35:23+02:00 - Separate Cumulative Acceptance from Delivery Outcomes

**Context**: The newsletter dashboard counted `ACCEPTED` as a mutually exclusive current status. Messages later marked delivered, opened, bounced, or failed disappeared from the accepted count, making a 52-recipient broadcast appear to have only 32 accepted messages. Historical delivery was also inferred from opens because provider delivery events were unavailable before July 22, 2026.

**Decision**:
1. Treat every persisted successful send row as cumulatively accepted, regardless of its later provider state.
2. Mark broadcasts sent before signed webhook tracking began as `Legacy/inferred`.
3. Do not present inferred historical delivery as a complete delivery count; state that delivery was not tracked historically.
4. Show historical opened/read counts and rates against total accepted sends.
5. For webhook-era broadcasts, show accepted, provider-confirmed delivered, failed, opened/read, clicked, and unsubscribed metrics separately.
6. Mark webhook-era cards as `Provider-confirmed` only after at least one signed provider event arrives.
7. Show `Awaiting provider events` before the first signed event and warn after 15 minutes without one, so webhook failure is visible during a broadcast.

**Verification**:
- Regression tests cover both historical and provider-era dashboard calculations and labels.
- Newsletter, webhook, confirmation, security, and smoke suites pass with 123 tests.
- Python compilation and scoped whitespace checks pass.

**Rollback**:
- Restore the changed files and database from the timestamped production deployment backup, then restart `dailyaiwire-web.service`.
- No data migration is required because this change only corrects aggregation and presentation.

---

## 2026-07-23T11:39:03+02:00 - Move the Homepage Signup CTA Below the Carousel

**Context**: The subscriber funnel showed complete confirmation for recent signups but very few measured signup-form views. The homepage form was embedded as the second tile in the article grid, below the large carousel and other discovery sections, which limited its visibility while duplicating no functionality not already provided by the desktop exit-intent popup.

**Decision**:
1. Keep the existing desktop exit-intent popup unchanged.
2. Move the single homepage inline signup form directly below the carousel on the unfiltered first page.
3. Preserve the existing `/subscribe` action, CSRF token, abuse guard fields, and `homepage_inline` attribution.
4. Render the CTA as a compact responsive strip rather than an article-grid tile.
5. Keep eight article cards in the first grid so no editorial content is removed.
6. Continue measuring the form only after it remains at least 50 percent visible for one second.

**Verification**:
- A regression test verifies that exactly one homepage inline form appears after the carousel and before the article grid.
- Homepage grid and subscriber funnel tests verify eight article cards plus the separate CTA and unchanged tracking behavior.

**Rollback**:
- Restore `templates/index.html`, remove `templates/partials/homepage_newsletter_cta.html`, restore the prior homepage layout test, and restart `dailyaiwire-web.service`.

---

## 2026-07-24T01:23:01+02:00 - Add Evidence-Based Subscriber Attribution

**Context**: The subscriber funnel measured form visibility, signup, and confirmation, but did not show which acquisition channels or landing pages produced those subscribers. The existing POST flow also stored the internal form-submission referrer instead of the original page-load referrer.

**Decision**:
1. Add aggregate channel, landing-page, and weekly acquisition views to `/admin/subscribers`.
2. Give explicit UTM parameters precedence over referrer evidence.
3. Capture the page-load referrer in the existing signup form payload without adding a cookie or a database column.
4. Keep channel classification fixed and deterministic: LinkedIn, Google Search, Newsletter / Email, X / Twitter, internal navigation, other referral, other campaign, and direct or unattributed.
5. Keep historical unknown acquisition unattributed rather than guessing a source.
6. Strip query parameters from landing-page reporting and show aggregate counts only.
7. Treat Gmail and Outlook webmail referrers as email traffic before applying broad search-engine hostname rules.

**Verification**:
- Regression tests cover UTM precedence, referrer classification, page-load referrer persistence, channel aggregation, landing pages, weekly cohorts, and admin rendering.
- The subscriber, abuse, security, site-health, and smoke suite passes with 143 tests.
- Python compilation and scoped whitespace checks pass.

**Rollback**:
- Restore the changed application files from the timestamped production deployment backup and restart `dailyaiwire-web.service`.
- No schema rollback is required because the implementation reuses existing subscriber metadata columns.

---

## 2026-07-24T01:37:00+02:00 - Separate Explicit Confirmation from Legacy Activation

**Context**: The subscriber dashboard described every activated subscriber as confirmed. Nine recent records have explicit confirmation timestamps, while three older active records have no confirmation timestamp and therefore cannot be presented as explicitly confirmed.

**Decision**:
1. Keep the combined activated total for historical continuity.
2. Split that total into explicit confirmations and legacy activated records.
3. Label the combined total and channel share as activated rather than confirmed.
4. Calculate view-to-confirm using explicit confirmations only.
5. Keep signup-to-activated as the historical cohort metric.
6. Do not modify subscriber statuses, delivery behavior, or stored subscriber data.

**Verification**:
- Regression tests cover explicit confirmation, legacy activation, combined totals, placement metrics, acquisition summaries, and admin labels.
- The subscriber, abuse, security, site-health, and smoke suite passes with 143 tests.
- Python compilation and scoped whitespace checks pass.

**Rollback**:
- Restore the changed application files from the timestamped production deployment backup and restart `dailyaiwire-web.service`.
- No database rollback is required because this is an aggregation and presentation correction only.

---

## 2026-07-24T02:06:14+02:00 - Clarify the Article Sidebar Newsletter Value

**Context**: Form-view tracking recorded 128 deduplicated views over three partial days, including 114 article-sidebar views and no new signups. The sidebar described generic reporting features but did not state the concrete reader outcome.

**Decision**:
1. Change only the article-sidebar newsletter copy and button label.
2. State the weekly value as what changed, why it matters, and original sources.
3. Preserve the existing form action, CSRF token, abuse controls, source attribution, cadence, and layout.
4. Avoid adding A/B infrastructure before sufficient traffic exists.
5. Review conversion after more measured sidebar traffic accumulates.

**Verification**:
- A regression test verifies the new value proposition and unchanged `article_sidebar` attribution.
- The subscriber, abuse, security, site-health, and smoke suite passes with 144 tests.
- Scoped whitespace checks pass.

**Rollback**:
- Restore `templates/article.html`, the subscriber funnel test, and `DECISIONS.md` from the timestamped production deployment backup, then restart `dailyaiwire-web.service`.

---

## 2026-07-24T02:11:57+02:00 - Add a Qualified Submission Funnel Stage

**Context**: The subscriber dashboard measured visible forms and completed signup records but could not distinguish no interaction from a valid form submission that encountered an existing address or later confirmation friction.

**Decision**:
1. Define a qualified submission as a valid email submission that passed cooldown, honeypot, timing, and format checks.
2. Record the event server-side before the existing-subscriber check.
3. Store no email or email hash on the qualified-submission event.
4. Deduplicate by hashed IP and signup placement for 30 minutes.
5. Report qualified submissions, view-to-submit conversion, and submit-to-new-signup conversion by placement and in the aggregate funnel.
6. Preserve existing signup, confirmation, email-delivery, rate-limit, and abuse-control behavior.

**Verification**:
- Tests cover qualified-submission recording, deduplication, absent email hashes, placement attribution, funnel aggregation, conversion rates, and admin labels.
- The subscriber, abuse, security, site-health, and smoke suite passes with 145 tests.
- Python compilation and scoped whitespace checks pass.

**Rollback**:
- Restore the changed application files from the timestamped production deployment backup and restart `dailyaiwire-web.service`.
- No schema rollback is required because the event uses the existing `subscriber_events` table.

---

## 2026-07-24T11:43:25+02:00 - Track Confirmation Provider Acceptance and Retry Pending Signups

**Context**: Confirmation-email failures were logged by the sender but ignored by the signup route. Visitors were always told to check their inbox, and a second submission for the same pending address was treated as an active subscription. This left failed requests pending without a recovery path or measurable delivery event.

**Decision**:
1. Treat `confirmation_sent` as provider acceptance, not proof of inbox delivery.
2. Record `confirmation_sent` or `confirmation_failed` in the existing subscriber event table after each provider request.
3. Show an honest delivery-issue page when the provider does not accept the request.
4. Allow only pending subscribers to request a fresh token and retry the confirmation email.
5. Preserve the existing behavior for active and other non-pending subscribers.
6. Store no provider response body or new sensitive data.
7. Commit the fresh token before the network request so an accepted link is always valid.

**Verification**:
- Tests cover provider acceptance, provider failure, pending-subscriber retry, token replacement, event recording, and delivery-issue messaging.
- The broader subscriber, security, site-health, and smoke regression suite is required before deployment.

**Rollback**:
- Restore `routes/public.py`, `templates/thank_you.html`, the affected test, and `DECISIONS.md` from the timestamped production deployment backup, then restart `dailyaiwire-web.service`.
- No schema rollback is required because the change reuses the existing `subscriber_events` table.

---

## 2026-07-24T11:51:57+02:00 - Expose Confirmation Provider Health in the Subscriber Funnel

**Context**: Confirmation provider acceptance and failure events were recorded but not visible in the admin dashboard. The funnel therefore could not distinguish a signup-quality problem from a confirmation-email provider problem without a direct database query.

**Decision**:
1. Show provider-accepted attempts, provider-failed attempts, provider acceptance rate, and current pending subscribers in the existing acquisition funnel.
2. Calculate provider acceptance as accepted attempts divided by accepted plus failed attempts.
3. Label the values as provider attempts, not delivery or inbox-open results.
4. Show the same metrics by signup placement to identify placement-specific failures.
5. Define current pending as subscribers created during the selected period whose present status is `PENDING`.
6. Reuse the existing subscriber and event tables without a schema change.

**Verification**:
- Tests cover aggregate and placement-level attempt counts, acceptance rates, pending counts, and admin labels.
- The subscriber, abuse, security, site-health, and smoke suite passes with 149 tests.
- Python compilation and scoped whitespace checks are required before deployment.

**Rollback**:
- Restore `services/subscribers.py`, `templates/admin/subscribers.html`, the affected test, and `DECISIONS.md` from the timestamped production deployment backup, then restart `dailyaiwire-web.service`.
- No database rollback is required.

---

## 2026-07-24T12:08:20+02:00 - Match Confirmation Emails to Verified Resend Webhooks

**Context**: Newsletter broadcasts stored their Resend message IDs and could process delivery, bounce, complaint, failure, and suppression webhooks. Confirmation emails retained only a boolean API-acceptance result, so every later provider event was recorded as unmatched. Permanent confirmation bounces therefore left invalid addresses pending and invisible.

**Decision**:
1. Preserve the existing boolean confirmation-sender API by default and return a structured acceptance result only when explicitly requested.
2. Store the Resend message ID, subscriber ID, placement, status, and event timestamps in a dedicated `confirmation_deliveries` table.
3. Do not store copied recipient addresses or complete provider payloads in the new table.
4. Match verified Resend events against newsletter deliveries first, then confirmation deliveries.
5. Keep a delivered confirmation subscriber pending until the recipient clicks the double-opt-in link.
6. Suppress pending or active subscribers only after a permanent bounce, complaint, or provider suppression.
7. Keep temporary delays and ordinary failures retryable.
8. Treat delivery-audit persistence as non-blocking after the provider has accepted the email.

**Verification**:
- RED tests reproduced missing structured results, missing delivery persistence, unmatched delivery webhooks, unmatched permanent bounces, and visitor-facing failures when audit persistence failed.
- GREEN tests cover provider message-ID extraction, signup persistence, verified delivery matching, permanent-bounce suppression, replay safety, and non-blocking audit failures.
- The email, subscriber, privacy, security, site-health, and smoke suite passes with 175 tests.
- Python compilation and scoped whitespace checks pass.

**Rollback**:
- Restore `newsletter_sender.py`, `routes/public.py`, `services/resend_webhooks.py`, the affected tests, and `DECISIONS.md` from the timestamped production deployment backup, then restart `dailyaiwire-web.service`.
- The additive `confirmation_deliveries` table and provider-event column can remain unused after code rollback. Dropping them is optional and should only be done after a database backup.

---

## 2026-07-24T12:38:04+02:00 - Show Actual Confirmation Delivery Separately from Acceptance

**Context**: The subscriber dashboard showed confirmation API acceptance and failure but not the verified delivery states now captured from Resend. This could still make a healthy API request look equivalent to an email reaching the recipient.

**Decision**:
1. Add a separate confirmation-delivery panel to the existing subscriber funnel.
2. Show tracked messages, actual deliveries, webhook-pending messages, delays, delivery issues, and tracked delivery rate.
3. Define actual delivery through a verified `delivered_at` timestamp.
4. Define webhook pending as accepted or sent messages without a later terminal state.
5. Define delivery issues as failed, bounced, complained, or suppressed messages.
6. State explicitly that delivered does not mean confirmed; double opt-in still requires a recipient click.
7. Return zero metrics when the additive delivery table is absent so code rollback remains safe.

**Verification**:
- RED tests confirmed that delivery aggregates and admin labels were absent.
- GREEN tests cover delivery, pending webhook, failure, suppression, rate aggregation, and admin rendering.
- The email, subscriber, privacy, security, site-health, and smoke suite passes with 175 tests.
- Python compilation and scoped whitespace checks pass.

**Rollback**:
- Restore `services/subscribers.py`, `templates/admin/subscribers.html`, the affected test, and `DECISIONS.md` from the timestamped production deployment backup, then restart `dailyaiwire-web.service`.
- No database rollback is required because this change only reads the existing additive table.

---

## 2026-07-24T12:54:04+02:00 - Enforce Daily LinkedIn Content Diversity

**Context**: The LinkedIn RSS feed limited the number of research items visible at one time, but n8n always selected the newest unprocessed article. New research articles could therefore replace older feed items and dominate the daily LinkedIn schedule even though the rolling feed appeared capped.

**Decision**:
1. Keep onsite article publication independent from LinkedIn distribution.
2. Keep the LinkedIn ceiling at 24 successful posts per New York day.
3. Pause LinkedIn selection before 06:00 in `America/New_York`.
4. Limit successful daily LinkedIn posts to 6 research items, 4 items from one source, and 6 items from one category.
5. Count an article and its diversity dimensions only after LinkedIn confirms a successful post.
6. Make success accounting idempotent so an execution replay cannot count one article twice.
7. Expose source and research metadata only in the dedicated LinkedIn RSS feed through additional category elements.
8. Maintain reviewed n8n Code-node sources as standalone files and inject their exact contents into the importable workflow JSON.

**Verification**:
- RED tests confirmed that feed metadata, diversity limits, standalone-script synchronization, and idempotent success accounting were absent.
- GREEN tests cover all four behaviors.
- Both n8n scripts parse successfully when wrapped as Code-node functions.
- The focused LinkedIn workflow test suite passes with 4 tests.
- The broader RSS, indexability, indexing-promotion, smoke, and site-health run passes 121 tests and exposes one unrelated existing author-name assertion failure.

**Activation**:
- Deploy the feed metadata first.
- Import and activate `outputs/linkedin-n8n/linkedin-rss-scheduled-24-daily.json` in n8n.
- Test-execute the imported workflow before disabling the previous workflow.

**Rollback**:
- Restore `routes/seo.py`, `templates/rss.xml`, the n8n source files, workflow JSON, tests, documentation, and `DECISIONS.md` from the timestamped deployment backup.
- Restart `dailyaiwire-web.service`.
- If the n8n workflow was activated, reactivate the prior workflow and disable the diverse workflow.

---

## 2026-07-24T14:31:41+02:00 - Exclude Known Automation from Verified Engagement

**Context**: A 14-day content audit showed implausibly uniform verified engagement across sources and categories. Event-level analysis found that `DailyAIWire-Monitor/1.0` and `Scrapy/2.16.0` were classified as human traffic. The internal monitor alone had generated a verified view across hundreds of distinct articles.

**Decision**:
1. Centralize bot classification for article views, audio plays, and subscriber-form analytics.
2. Explicitly classify DailyAIWire monitoring and Scrapy requests as automated.
3. Preserve raw article request counts while excluding these requests from verified views.
4. Add an idempotent repair that marks existing matching events as bots and subtracts only their previously counted verified views.
5. Keep the repair dry-run by default and require `--apply` to persist changes.
6. Do not classify ordinary browser user agents as bots based only on high article coverage.

**Measured Repair Scope**:
- 2,452 matching historical events across 1,980 articles.
- 2,444 verified views to remove.
- No article would receive a negative verified-view count.

**Verification**:
- RED tests confirmed that the shared traffic-quality module and repair behavior were absent.
- GREEN tests cover the internal monitor, Scrapy, Googlebot, normal browsers, prefetch traffic, and idempotent historical repair.
- The analytics, subscriber-funnel, and smoke suite passes with 97 tests.
- Python compilation and scoped whitespace checks pass.

**Rollback**:
- Restore `routes/public.py`, `routes/api.py`, the traffic-quality service, repair command, tests, and `DECISIONS.md` from the timestamped deployment backup.
- Restore `news.db` from the same backup if the historical repair must be reversed.
- Restart `dailyaiwire-web.service`.

---

## 2026-07-24T14:58:12+02:00 - Observe Browser-Like Traffic Anomalies Before Enforcement

**Context**: After known automation was removed from verified views, one browser-like visitor hash still opened 339 articles within approximately 13 minutes. The user agent alone was not sufficient evidence for permanent bot classification.

**Decision**:
1. Add an observation-only Traffic Quality Monitor to the existing admin dashboard.
2. Flag a visitor-day when it exceeds 20 distinct articles.
3. Flag a fast burst when it reaches at least 10 distinct articles within 15 minutes.
4. Show flagged sessions, high-volume sessions, fast bursts, and views above the proposed daily limit.
5. Display only the first 10 characters of the visitor hash and never display IP hashes.
6. Keep all existing verified-view counts unchanged during the observation period.
7. Do not enforce a behavioral cap until enough production evidence exists to evaluate false-positive risk.

**Verification**:
- RED tests confirmed that anomaly aggregation and dashboard monitoring were absent.
- GREEN tests cover high-volume sessions, fast bursts, normal sessions, truncated identifiers, and admin rendering.
- The analytics, subscriber-funnel, and smoke suite passes with 101 tests.
- Python compilation and scoped whitespace checks pass.

**Rollback**:
- Restore `services/traffic_quality.py`, `app.py`, `templates/admin/index.html`, the affected tests, and `DECISIONS.md` from the timestamped deployment backup.
- Restart `dailyaiwire-web.service`.
- No database rollback is required.

---

## 2026-07-24T15:27:49+02:00 - Deduplicate Research Papers by Canonical Identifier

**Context**: The same DeepSearch-World paper was published from ArXiv and Hugging Face ten days apart. Exact source-URL deduplication could not connect the two URLs, and the second copy was outside the 36-hour deterministic story window.

**Decision**:
1. Normalize modern ArXiv identifiers from ArXiv abstract URLs, ArXiv PDF URLs, and Hugging Face paper URLs.
2. Exclude a known paper during source aggregation before it consumes headline-filter or full-analysis tokens.
3. Track paper identifiers within the current fetch batch so two source representations cannot enter the same analysis run.
4. Repeat the canonical check before database insertion as a second defense.
5. Preserve the existing 36-hour general-story window and all editorial thresholds.
6. Keep historical duplicate URLs published because they were already shared externally; consolidation requires permanent redirects and is separate work.

**Verification**:
- RED tests confirmed that canonical paper identification and cross-source blocking were absent.
- GREEN tests cover ArXiv versions, ArXiv PDF URLs, Hugging Face URLs, existing-database matches, current-batch matches, and a ten-day persistence bypass.
- The focused source and persistence suite passes 29 tests.
- The broader ingestion and AI-governance suite passes 59 tests.
- Python compilation and scoped whitespace checks pass.
- A combined site run exposed an existing test-isolation issue after temporary database mutation; 131 tests passed, while unrelated seeded-article and admin assertions failed.

**Rollback**:
- Restore `services/story_dedup.py`, `fetcher/sources.py`, and `fetcher/persistence.py` from the timestamped deployment backup.
- Restart `dailyaiwire_fetcher`.
- No database rollback is required because the prevention change does not modify existing records.

---

## 2026-07-24T15:42:09+02:00 - Preserve Shared Test Database Fixtures

**Context**: Two AI-governance tests deleted every article from the session-scoped temporary database. Later public-route and admin tests then failed with missing seeded articles, which produced false 410 and template errors in combined runs.

**Decision**:
1. Never clear the shared `articles` table in governance tests.
2. Give every governance article a stable test-only slug.
3. Reset and clean only the rows owned by those tests.
4. Assert that the seeded public-route article survives weekly-curator and opinion-generator tests.
5. Keep the change test-only because production behavior and data were not involved.

**Verification**:
- RED tests confirmed that both governance tests removed `test-article-slug`.
- The minimal governance-to-public-route failure was reproduced before the fix.
- GREEN verification passes the minimal sequence and the exact 163-test sequence that previously failed.
- The complete repository suite passes 378 tests with 1 skipped.

**Rollback**:
- Revert the targeted cleanup fixture and preservation assertions in `tests/test_ai_governance.py`.
- No service restart or database rollback is required.

---

## 2026-07-24T16:30:05+02:00 - Consolidate Proven Duplicates with Permanent Redirects

**Context**: Three proven duplicate article pairs were already shared externally. Unpublishing the copies without redirects would return 410 for existing links, while leaving both records published weakens content quality and duplicate-page signals.

**Decision**:
1. Store article redirects as a source slug mapped to a published canonical article ID.
2. Resolve a valid redirect before article lookup and return HTTP 301 to the internal canonical URL.
3. Serve article pages only when `is_published = 1`; unpublished records without redirects return 410.
4. Consolidate atomically by creating the redirect and unpublishing the duplicate in one transaction.
5. Preserve duplicate records, analytics, and source history rather than deleting them.
6. Remove consolidated copies from carousel slots and mark matching pending duplicate-review entries as consolidated.
7. Apply the operation only to the three manually verified pairs.

**Canonical Selections**:
- Keep Reuters article `11989`; redirect AP article `12024`.
- Keep New York Times article `11823`; redirect TechCrunch article `11826`.
- Keep ArXiv article `11810`; redirect Hugging Face article `12170`.

**Verification**:
- RED tests confirmed that the redirect service was absent and unpublished articles rendered with HTTP 200.
- GREEN tests cover permanent redirects, publication state, and rejection of an unpublished canonical target.
- The redirect, RSS, sitemap, and smoke suite passes 92 tests.
- The complete repository suite passes 381 tests with 1 skipped.
- Python compilation and scoped whitespace checks pass.

**Rollback**:
- Restore `app.py`, `fetcher/db_init.py`, `routes/public.py`, the redirect service, tests, and `DECISIONS.md` from the timestamped deployment backup.
- Restore `news.db` from that backup to republish duplicate records and remove redirect mappings.
- Restart `dailyaiwire-web.service` and `dailyaiwire_fetcher`.

---

## 2026-07-24T16:50:20+02:00 - Reject Ambiguous Article Analysis Mappings

**Context**: A live audit found published articles whose headlines did not match their source URLs. Gemini had returned duplicate `batch_id` values for multiple analysis outputs. The fetcher trusted those IDs, and `INSERT OR REPLACE` allowed a later result to replace the article already stored for that source URL.

**Decision**:
1. Assign contiguous analysis IDs after triage while preserving each source's original batch ID.
2. Require exactly one analysis object for every submitted analysis ID.
3. Retry once with an explicit correction when Gemini returns missing, duplicate, or unexpected IDs.
4. Reject the entire batch after a second invalid mapping rather than risk false attribution.
5. Restore original batch IDs and source hashes only after one-to-one mapping validation succeeds.
6. Skip an article when its source URL already exists and use plain `INSERT`, never `INSERT OR REPLACE`, for new articles.

**Verification**:
- RED tests reproduced duplicate Gemini IDs and source URL replacement.
- GREEN tests verify retry and ID restoration, rejection safety, and collision preservation.
- The complete repository suite passes 383 tests with 1 skipped.
- Python compilation and scoped whitespace checks pass.

**Rollback**:
- Restore `fetcher/ai_processor.py`, `fetcher/persistence.py`, and `DECISIONS.md` from the timestamped deployment backup.
- Restore `news.db` only if production quarantine changes also need to be reversed.
- Restart `dailyaiwire_fetcher`.

---

## 2026-07-24T16:58:08+02:00 - Quarantine Articles with Invalid Source Attribution

**Context**: The source mapping audit covered all `article_analysis` logs from July 10 through July 24, 2026. It found 79 published records whose analysis output was stored against a source position that did not correspond to the article Gemini analyzed. Sixty-eight outputs used an impossible ID. Eleven additional outputs were verified by response order, submitted source title, stored headline, and stored source URL. Reuters article `11989` came from a valid subset of a partially malformed response and was explicitly excluded.

**Decision**:
1. Unpublish the 79 demonstrably misattributed records without deleting their rows, analytics, or AI audit logs.
2. Record `SOURCE_MAPPING_QUARANTINED` in `processing_attempts` for every affected source URL.
3. Close pending duplicate reviews involving quarantined records with the same status.
4. Remove affected records from carousel and pending social queues if present.
5. Preserve valid articles from partially malformed batches when their returned ID and source mapping are verified.

**Verification**:
- Exactly 79 records changed from published to unpublished in one transaction.
- No affected record was a redirect target, carousel item, pending social post, or Google recovery promotion.
- Sample quarantined URLs return HTTP 410, while verified Reuters article `11989` returns HTTP 200.
- None of the 79 affected slugs appears on the homepage, RSS, sitemap index, or core sitemap.
- SQLite `PRAGMA integrity_check` returns `ok`.
- The first post-deployment analysis log returned the exact submitted ID set.

**Rollback**:
- Restore `news.db` from `ops/deploy-backups/source-provenance-20260724T145138Z/news.db`.
- Restore the two fetcher files and `DECISIONS.md` from the same backup if the mapping safeguard must also be reverted.
- Restart `dailyaiwire-web.service` and `dailyaiwire_fetcher`.

---

## 2026-07-24T17:30:50+02:00 - Fail Closed on Invalid Persistence Source IDs

**Context**: The Gemini mapping safeguard validates the primary analysis path, but persistence retained a legacy fallback that mapped an invalid or missing `batch_id` to a slug match or the first source in the batch. A malformed caller could therefore recreate false source attribution even after analysis validation.

**Decision**:
1. Accept only a non-boolean integer `batch_id` within the bounds of `original_batch`.
2. Skip and log malformed records before image, embedding, indexing, social, or database side effects.
3. Remove slug and first-source fallback attribution entirely.

**Verification**:
- RED testing proved that `batch_id=99` published and indexed an article against the first source.
- GREEN testing rejects missing, negative, out-of-range, list, and boolean IDs.
- The persistence suite passes 12 tests.
- The complete repository suite passes 388 tests with 1 skipped.
- Python compilation and scoped whitespace checks pass.

**Rollback**:
- Restore `fetcher/persistence.py` and `DECISIONS.md` from the timestamped deployment backup.
- Restart `dailyaiwire_fetcher`.
- No database restoration is required because the guard does not modify existing rows.

---

## 2026-07-24T17:59:44+02:00 - Report Committed Articles Instead of Analyzed Outputs

**Context**: Fetcher monitoring incremented `articles_saved` by the number of AI outputs, even when persistence rejected every output for blockers, duplicates, quality, or invalid attribution. This produced false “Saved” log entries and could trigger an unnecessary audio scan.

**Decision**:
1. Return both social post count and committed article count from persistence.
2. Increment the committed count immediately after the article transaction commits.
3. Use the committed count for per-batch logs, cycle totals, and audio-generation limits.
4. Do not change any filtering, ranking, publication, or social-post behavior.

**Verification**:
- RED tests showed successful and rejected persistence calls returned the same integer-only result.
- GREEN tests distinguish one committed article from zero committed articles.
- Persistence and fetcher governance suites pass 15 tests.
- The complete repository suite passes 388 tests with 1 skipped.
- Python compilation and scoped whitespace checks pass.

**Rollback**:
- Restore `fetcher/__init__.py`, `fetcher/persistence.py`, and `DECISIONS.md` from the timestamped deployment backup.
- Restart `dailyaiwire_fetcher`.
- No database restoration is required.

---

## 2026-07-24T18:06:49+02:00 - Reject Incomplete Article Triage Decisions

**Context**: A live Flash-Lite triage response returned one decision for a three-candidate batch. The fetcher treated the two omitted candidates as blocked, which could silently suppress valid articles and reduce publishing volume.

**Decision**:
1. Require exactly one triage decision for every submitted candidate ID.
2. Reject missing, duplicate, or unexpected IDs and retry once with an explicit correction.
3. If the corrected response is still malformed, send all candidates to full analysis instead of recording false triage blocks.
4. Record `TRIAGE_BLOCKED` only after a complete and valid decision set.

**Verification**:
- RED tests reproduced the omitted-decision suppression and false block recording.
- GREEN tests verify successful correction on retry and fail-open full-analysis fallback after two invalid responses.
- Five focused triage and analysis-mapping tests pass.
- The complete repository suite passes 390 tests with 1 skipped.
- Python compilation passes.

**Rollback**:
- Restore `fetcher/ai_processor.py` and `DECISIONS.md` from the timestamped deployment backup.
- Restart `dailyaiwire_fetcher`.
- No database restoration is required.

---

## 2026-07-24T21:54:51+02:00 - Replace Paid X API Posting with Browser Heartbeat

**Context**: Automated X posting was functioning, but posting article links through the X API incurred material recurring charges. The in-app browser has an authenticated `@DailyAIWireNews` session that can publish through the web interface without X API write charges.

**Decision**:
1. Run browser-based X posting in a dedicated Codex task three times per day.
2. Require account verification, duplicate checking, visible publication confirmation, and database marking after each successful post.
3. Never call the X API from the browser task.
4. Keep `tweet_scheduler` running for weekly-newsletter duties, but disable its X credentials in production so it cannot make paid API calls or duplicate browser posts.

**Verification**:
- The dedicated heartbeat `post-dailyaiwire-to-x` is active against task `019f95b0-6596-73e2-a5d1-4744d7bd5e1d`.
- The in-app browser is authenticated as `@DailyAIWireNews`.
- The previous API scheduler had three accepted posts on July 24, confirming the issue was cost rather than credentials or uptime.

**Rollback**:
- Restore `.env` and `DECISIONS.md` from the timestamped deployment backup.
- Restart `tweet_scheduler`.
- Pause or delete the `post-dailyaiwire-to-x` heartbeat before restoring API posting to prevent duplicates.

---

## 2026-07-25T00:44:23+02:00 - Remove Obsolete Instagram Re-Enable Cron

**Context**: A root cron entry changed `IG_ENABLED=false` to `true` and restarted `tweet_scheduler` every night at 22:30 UTC. Meta posting is intentionally disabled, and this stale job caused unexplained scheduler restarts and configuration drift after browser-based X posting replaced API posting.

**Decision**:
1. Remove `/etc/cron.d/ig_reenable`.
2. Restore `IG_ENABLED=false`.
3. Keep `tweet_scheduler` running for weekly-newsletter generation with all X API credentials disabled.

**Verification**:
- Supervisor logs identified the restart at exactly the cron schedule on consecutive days.
- No X API post succeeded after the browser-posting cutover.
- The browser heartbeat remains active and its manual end-to-end post was confirmed publicly and recorded in the database.

**Rollback**:
- Restore `.env` and `ig_reenable` from the timestamped deployment backup.
- Restart `tweet_scheduler`.

---

## 2026-07-25T01:03:57+02:00 - Retire Social Scheduler and Isolate Weekly Newsletter Generation

**Context**: Browser-based X posting replaced paid X API posting, but `tweet_scheduler`
remained active solely because its ten-minute loop also generated the weekly newsletter.
That left an obsolete social process, paid-API code ownership in deployment, and no
structured audit trail for browser posts.

**Decision**:
1. Retire `tweet_scheduler` from Supervisor, the deployment script, GitHub Actions,
   and production documentation.
2. Generate the weekly draft through a dedicated persistent systemd timer on Sunday
   at 18:05 Europe/Berlin.
3. Skip weekly generation when a newsletter was created in the previous 24 hours,
   and propagate generation failures so systemd records a failed run.
4. Select browser X candidates through a tested CLI using the last 48 hours,
   importance ranking, and recent-category diversity.
5. Record confirmed and failed browser attempts in `x_browser_post_audit`; update
   `articles.shared_on_x` only in the same transaction as a confirmed X status URL.

**Verification**:
- The new tests failed before implementation and pass after implementation.
- The complete repository suite passes 395 tests with 1 skipped.
- Bash syntax and Python compilation checks pass.

**Rollback**:
- Restore the production files and database from the timestamped deployment backup.
- Restore `/etc/supervisor/conf.d/tweet_scheduler.conf` and run `supervisorctl update`.
- Disable and remove `dailyaiwire-weekly-newsletter.timer` before restarting the old
  scheduler to prevent duplicate weekly generation.

---

## 2026-07-25T01:11:06+02:00 - Disable DailyOrbitalWire

**Context**: DailyOrbitalWire had returned after an earlier manual stop because its
Supervisor program still used `autostart=true` and `autorestart=true`.

**Decision**:
1. Stop `dailyorbitalwire`.
2. Remove its active Supervisor definition so it cannot restart after a process
   failure, Supervisor reload, or server reboot.
3. Preserve the original definition under `/etc/supervisor/disabled`.

**Verification**:
- Supervisor reports no such process for `dailyorbitalwire`.
- No process under `/home/dailyorbital/dailyorbitalwire.news` remains.
- DailyAIWire's public health endpoint still returns HTTP 200.

**Rollback**:
- Restore `/etc/supervisor/disabled/dailyorbitalwire.conf.disabled-20260724T231053Z`
  to `/etc/supervisor/conf.d/dailyorbitalwire.conf`.
- Run `supervisorctl reread`, `supervisorctl update`, and
  `supervisorctl start dailyorbitalwire`.

---

## 2026-07-25T01:25:48+02:00 - Establish Single Process Owners for Web, Fetcher, and Newsletter

**Context**: DailyAIWire's live Gunicorn process was healthy under
`dailyaiwire-web.service`, but an obsolete disabled Supervisor web definition made
Supervisor report the app as stopped. Root cron also retained an hourly
DailyOrbital fetcher and an older weekly-newsletter generator.

**Decision**:
1. Use systemd `dailyaiwire-web.service` as the sole DailyAIWire web owner.
2. Use Supervisor `dailyaiwire_fetcher` as the sole DailyAIWire fetcher owner.
3. Use systemd `dailyaiwire-weekly-newsletter.timer` as the sole weekly draft owner.
4. Remove the obsolete Supervisor web definition and both superseded root cron jobs.
5. Make `deploy_to_vps.sh` restart the web through systemd and restart only the
   fetcher through Supervisor when explicitly requested.

**Verification**:
- The systemd web unit is enabled and active with the same Gunicorn master PID that
  serves port 8000.
- DailyAIWire health returns HTTP 200 after cleanup.
- The fetcher remains running under Supervisor.
- No DailyOrbital process or cron entry remains.
- The weekly systemd timer remains active and the old weekly cron is absent.
- The complete repository suite passes 396 tests with 1 skipped.

**Rollback**:
- Restore the Supervisor and root crontab files from
  `/home/dailyai/dailyaiwire.news/ops/deploy-backups/process-owner-cleanup-20260724T232318Z`.
- Run `supervisorctl reread` and `supervisorctl update`.
- Do not enable both the restored weekly cron and weekly systemd timer together.

---

## 2026-07-25T01:35:00+02:00 - Consolidate Historical Cura 1T Duplicate

**Context**: A seven-day content audit found two published articles for the same
research paper, `arxiv:2607.15314`, sourced separately from ArXiv and Hugging Face.
The pair predates the deployed cross-source research-paper guardrail.

**Decision**:
1. Keep article `12116`, which was published first and had more verified views.
2. Unpublish article `12129`.
3. Permanently redirect the retired slug to article `12116` so existing links retain
   continuity and SEO value.

**Verification**:
- The canonical article returns HTTP 200.
- The retired URL returns HTTP 301 to the canonical slug.
- Database state shows article `12116` published and article `12129` unpublished.
- The redirect is recorded in `article_redirects`.
- No other seven-day research-ID duplicate group or deterministic story match exists.

**Rollback**:
- Restore `news.db` from
  `/home/dailyai/dailyaiwire.news/ops/deploy-backups/cura-duplicate-consolidation-20260724T233451Z/news.db`.

---

## 2026-07-25T01:39:01+02:00 - Balance Research Aggregators in Headline Candidate Pools

**Context**: ArXiv and Hugging Face supplied 16 of 33 articles in the latest 24-hour
window. Research remained useful, but seven-day verified engagement was stronger
for Business and Policy content, and strict score ordering gave generic research
terms a structural advantage before full analysis.

**Decision**:
1. Limit ArXiv, Hugging Face Papers, and Papers with Code to 40% of the
   pre-analysis candidate pool when enough qualified non-research candidates exist.
2. Preserve ranking order within research and non-research groups.
3. Backfill all unused pool slots with research candidates so the rule cannot reduce
   analysis or publishing volume.
4. Ask the headline ranker to maintain category and format balance when qualified
   options exist.

**Verification**:
- RED tests confirmed no diversity control existed.
- GREEN tests verify both the 40% preference and full-volume research backfill.
- All 25 source-quality tests pass.
- The complete repository suite passes 398 tests with 1 skipped.

**Rollback**:
- Restore `fetcher/sources.py` from the timestamped production deployment backup.
- Restart only `dailyaiwire_fetcher`.
- No database restoration is required.

---

## 2026-07-25T01:51:29+02:00 - Cool Down Rejected X Candidates

**Context**: Rejecting a browser-posting candidate recorded a `FAILED` audit row,
but the selector did not read those rows. The same stale or unsuitable article could
therefore be returned immediately on the next selection attempt.

**Decision**:
1. Exclude articles with a `FAILED` browser-posting attempt in the previous 24 hours.
2. Allow older failures to become eligible again so temporary browser errors do not
   permanently suppress otherwise suitable articles.
3. Keep `shared_on_x` unchanged for failed attempts.

**Verification**:
- A RED test reproduced immediate reselection of a recently failed article.
- The GREEN test verifies recent failures are skipped and failures older than 24
  hours can be retried.
- All X browser queue tests pass.

**Rollback**:
- Restore `services/x_browser_queue.py` from the timestamped production deployment
  backup.
- No service restart or database restoration is required.

---

## 2026-07-26T14:52:14+02:00 - Move Weekly Newsletter Draft to Sunday 14:00

**Context**: The weekly newsletter draft was generated on Sunday at 18:05
Europe/Berlin, leaving too little time for review before the scheduled evening
delivery.

**Decision**:
1. Run the dedicated weekly newsletter timer on Sunday at 14:00 Europe/Berlin.
2. Keep `Persistent=true` so a missed run is recovered after downtime.
3. Keep the existing five-minute randomized delay to avoid synchronized load.

**Verification**:
- Both the repository timer and installed systemd timer use
  `OnCalendar=Sun *-*-* 14:00:00 Europe/Berlin`.
- The timer is enabled and active.
- The next regular trigger is Sunday, August 2, at approximately 14:00
  Europe/Berlin.
- Restarting the persistent timer after today's window triggered the missed run.
- The service exited successfully and created newsletter draft `37`.

**Rollback**:
- Restore the timer files and `DECISIONS.md` from
  `ops/deploy-backups/newsletter-schedule-20260726T122500Z`.
- Run `systemctl daemon-reload` and restart
  `dailyaiwire-weekly-newsletter.timer`.

---

## 2026-07-26T15:38:27+02:00 - Enforce Weekly Newsletter Freshness, Diversity, and Editorial Validation

**Context**: The weekly generator selected the seven highest importance scores
before the AI writing step. This allowed category clustering, old source stories,
overlong copy, unsupported certainty, and sensational wording to reach a draft.
The prompt did not receive category, source, source URL, or source-date context.

**Decision**:
1. Rank a pool of up to 35 recent live articles, exclude dated source URLs older
   than 14 days, give each available category one slot, and cap categories at two.
2. Supply category, source, source URL, inferred source date, site publication
   date, and existing article context to the weekly writing prompt.
3. Enforce a 60-character subject, an 80-120 word editor's note, 20-40 word
   blurbs, exact article-ID coverage, attribution for risky claims, explicit
   projection wording for future financial figures, and a neutral-language gate.
4. Allow one AI repair attempt. If the repair still fails validation, create no
   newsletter draft and report the validation error.
5. Provide `scripts/run_weekly_newsletter.py --dry-run` to generate and validate
   a preview without creating a newsletter row.

**Verification**:
- Eleven focused newsletter tests pass, including real SQLite row handling.
- The live selector returned seven articles from seven distinct categories.
- A real dry run required one repair and then passed all editorial gates.
- The newsletter row count remained 29 before and after the dry run.
- The canonical test directory completed with 320 passing tests and nine
  unrelated pre-existing failures.

**Rollback**:
- Restore `weekly_curator.py` and `scripts/run_weekly_newsletter.py` from
  `ops/deploy-backups/weekly-curator-quality-20260726T131500Z`.
- Remove `tests/test_weekly_curator.py` if rolling back the feature entirely.
- No service restart or database restoration is required because the weekly
  systemd service starts a fresh Python process for each run.

---

## 2026-08-01T17:30:39+02:00 - Schedule Browser-Only Instagram Feed Publishing

**Context**: DailyAIWire needs regular Instagram distribution without restoring
the retired Meta API worker. Existing square social cards crop poorly in Instagram
feed previews, and publication state must only change after visible confirmation.
Instagram's signed-in desktop web UI exposes feed-post creation but does not expose
Story creation or an "Add to story" destination in the complete Share dialog.

**Decision**:
1. Publish through the signed-in in-app browser as `@dailyaiwirenews` at 12:00 and
   18:00 Europe/Berlin. Never call the Instagram or Meta API.
2. Select only live, recent, source-fresh, important, unshared articles, with a
   24-hour failed-attempt cooldown and recent-category diversity.
3. Generate versioned 1080 x 1350 portrait cards with protected title and footer
   areas for Instagram's 4:5 feed presentation.
4. Mark an article shared only after a confirmed canonical Instagram post URL is
   visible. Record blocked attempts without changing the share state.
5. Do not automate Stories until the in-app browser exposes a visible creation and
   publication-confirmation flow. Keep this limitation explicit instead of using
   the retired API worker or claiming an unverified Story publication.

**Verification**:
- Seven focused queue and card tests pass.
- The CLI compiles and exposes `next`, `posted`, and `failed` commands.
- The signed-in browser account is `@dailyaiwirenews` and shows the Professional
  Dashboard.
- Browser inspection confirms feed-post creation is available and the full Share
  dialog has no Story destination.

**Rollback**:
- Pause or delete the Instagram browser automation.
- Remove the three new deployed code files and restore `news.db` from
  `/home/dailyai/dailyaiwire.news/ops/deploy-backups/instagram-browser-20260801T153127Z/news.db`.
- No legacy Instagram API worker needs to be restarted.

---

## 2026-08-01T18:41:16+02:00 - Preserve Complete Instagram Card Summaries and Repost Audit State

**Context**: The portrait card generator wrapped the article summary and then
blindly kept its first three visual lines. This could cut a sentence halfway
through in the published Instagram image. Replacing an affected post also left
the browser-post audit pointing at the deleted permalink because the safe CLI
only supported first publication.

**Decision**:
1. Version portrait cards as `instagram-v2` so corrected images do not reuse a
   cached or already-published `instagram-v1` asset.
2. Fit complete summary sentences into the three-line area, reduce the summary
   font from 29 to no less than 22 pixels when necessary, and omit the summary
   when even its first complete sentence cannot fit.
3. Add a `replaced` CLI command that validates the new Instagram permalink and
   atomically updates the latest confirmed audit row. It must not create a
   duplicate publication event or accept an unconfirmed article.

**Verification**:
- Eleven focused generator and queue tests pass, including regressions for a
  multi-sentence summary and an unfit single sentence.
- The queue CLI compiles and exposes `next`, `posted`, `replaced`, and `failed`.
- The corrected 1080 x 1350 card and replacement audit flow were verified on
  the live post at `https://www.instagram.com/p/DbgQ65mAjmn/`.

**Rollback**:
- Revert this decision's implementation commit to restore `instagram-v1` card
  generation and remove the `replaced` CLI command.
- Existing `instagram-v2` image files can remain as immutable media or be
  removed after confirming that no published Instagram post references them.
- The last working production commit before the hotfix was
  `35dfb1d37ac9b5230cc7c2a2d34f36d9e8493ea0`.

---

## 2026-08-02T02:57:58+02:00 - Expand Browser-only Instagram Publishing Formats

**Context**: Three daily static posts provide consistent output but do not test
the carousel saves/shares or Reel discovery surfaces that can improve
non-follower reach. The existing publication audit is safe, but the queue only
returns one portrait PNG.

**Decision**:
1. Keep browser-only publication and leave the retired Instagram and Meta API
   workers disabled.
2. Assign static posts to 09:00, five-slide carousels to 14:00, and silent
   Reel-ready videos to 19:00 Europe/Berlin.
3. Generate carousel copy only from stored article headline, gist, impact,
   bull-case, and bear-case fields. Produce a 1080 x 1920 H.264 Reel from the
   same verified fields with no synthetic voiceover.
   Fit only complete sentences, limit Reel analysis blocks to one sentence for
   mobile readability, and version the corrected assets as carousel v2 and
   Reel v2 so cached v1 files cannot be reused.
4. Return explicit format and media URL fields from the safe queue CLI. Continue
   marking an article shared only after a canonical Instagram permalink is
   visibly confirmed.
5. Add the Instagram profile to organization structured data, the public
   footer, article follow controls, and the weekly newsletter footer.
6. Review Instagram insights weekly. Require enough posts per format before
   recommending a schedule rebalance.

**Verification**:
- The complete repository suite passes with 432 tests and one FFmpeg-dependent
  test skipped only when the binary is unavailable.
- Visual QA confirms all five carousel slides retain their complete text,
  header, and footer inside the 1080 x 1350 canvas.
- Reel validation confirms H.264 video at 1080 x 1920, `yuv420p`, and about 12
  seconds. All analysis frames use complete, mobile-readable sentences.
  Production provides both `/usr/bin/ffmpeg` and `/usr/bin/ffprobe`.
- Production browser upload and live route smoke checks remain deployment gates.

**Rollback**:
- Restore the deployment backup recorded during rollout.
- Return the Instagram automation to static-only
  `next --lookback-hours 48`.
- Keep already-published versioned media files until no live post references
  them.
