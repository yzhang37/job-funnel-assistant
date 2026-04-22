# PLANS.md

## Phase 0: Foundation

- [x] Create repository guidance files
- [x] Import user's analysis template
- [ ] Import user's resume template
- [ ] Confirm first target job sources
- [ ] Confirm preferred notification channel
- [x] Create first standalone job-fit analyzer component
- [x] Build LLM-driven Job Funnel / Resume Fit Analyst runner
- [x] Add config-driven cache policy layer for company/job snapshots

## Phase 1: Data Model

- [ ] Define normalized job schema
- [x] Define Notion database schema
- [x] Import historical Wolai job data into Notion
- [x] Define suitability scoring output shape
- [ ] Decide how to deduplicate repeated job posts
- [x] Define minimal tracker config shape for recurring tracker monitoring

## Phase 2: First End-To-End Flow

- [x] Add tracker scheduler config file for current tracker set
- [x] Add due-run logic for daily/weekly trackers
- [x] Add replaceable tracker scheduler storage boundary with SQLite first
- [ ] Connect tracker scheduler to real browser execution and paging
- [x] Validate LinkedIn tracker discovery flow on a real search-results page: click result card -> derive `currentJobId` -> canonicalize to JD link -> move to `Page 2` when needed
- [x] Validate Indeed tracker discovery flow on a real search-results page: click result card -> derive `vjk`/`jk` -> canonicalize to JD link -> page by search-result pagination
- [ ] Collect jobs from one source
- [ ] Normalize captured data
- [x] Define first browser-capture milestone as `extracted sections -> jd.md`
- [x] Define a generic `company_profile` capture shape for company-level insights and premium pages
- [x] Define LinkedIn company resolution strategy: canonical company link -> cached slug -> direct insights URL -> search fallback
- [x] Validate direct LinkedIn `/company/<slug>/insights/` access on a real company page and confirm block variability across companies
- [x] Define public capture interfaces: `job link -> bundle` and `company name -> bundle`
- [x] Add first bundle/manifest writer for normalized capture artifacts
- [x] Define multi-source company enrichment rule: source-native insights -> LinkedIn insights -> official site / careers -> other public sources
- [x] Upgrade `company_profile` output to preserve maximal evidence instead of only summary fields
- [ ] Run template-based fit analysis
- [ ] Save suitable roles to Notion
- [ ] Send notification summary
- [ ] Validate with dry-run output

## Phase 3: Automation

- [ ] Add recurring execution flow
- [ ] Add retry and failure logging
- [ ] Add manual review checkpoints
- [ ] Add source-specific collectors

## Notes

Recommended initial product shape:

- human-in-the-loop
- notification-first
- no automatic application submission
- modular integrations

Current Notion progress:

- `找工作项目` page created in Notion
- `Stage Policy` database created and seeded
- `Jobs` database created with formulas, relation, and verification views
- Historical Wolai data imported into `Jobs`
- `Mock / Test` checkbox added so test rows stay hidden from normal views
- `待跟进` view adjusted to a gallery-first layout with a human-readable `Follow-up Summary` field

Current analyzer progress:

- `scripts/analyze_job_fit.py` can score one job JSON against a profile JSON
- output includes `decision`, `score`, `hard_requirements_passed`, and `summary`
- current version is rules-based and ready to be aligned with the user's real analysis template
- `prompts/job_funnel_resume_fit_analyst_spec.md` stores the user's analyzer spec without rewriting its framework
- `scripts/run_job_funnel_analysis.py` can run one JD through a profile stack and render the fixed report format
- `profiles/` now separates stable candidate background, preferences, work authorization, and resume patches
- `config/cache_policy.toml` now controls cache TTL defaults and field-level overrides without hardcoding policy in Python
- `src/job_search_assistant/cache/` provides a lightweight SQLite-backed cache store for reusable company/job snapshot data

Current capture progress:

- first capture requirement is intentionally narrow: organize extracted browser content into `jd.md`
- capture text-normalization layer is intended to stay generic across LinkedIn, Indeed, MeeBoss, YC, Glassdoor, and similar sources
- `src/job_search_assistant/capture/jd_markdown.py` now renders structured sections into a reusable markdown JD
- `scripts/render_jd_markdown.py` provides a thin CLI for turning captured section JSON into `jd.md`
- `docs/company-profile-capture.md` now defines a separate company-level capture spec for embedded profile cards and full insights pages
- `docs/linkedin-company-resolution.md` now defines when to jump directly to LinkedIn company insights and when to fall back to company-name search
- real-page validation now confirms `jackandjillai/insights/` is reachable directly and exposes premium metrics such as total employee count and function distribution
- real-page validation also confirms that `Insights` blocks vary by company, so capture should treat openings/alumni/affiliated-pages sections as optional
- `src/job_search_assistant/capture/company_profile.py` now provides a generic `company_profile` schema, markdown renderer, and cache payload split
- `scripts/render_company_profile.py` can turn one loosely structured company profile JSON into markdown and optional cache rows
- `docs/capture-bundle-spec.md` now defines the stable handoff format: bundle directory + manifest + normalized markdown/json artifacts
- `scripts/build_job_capture_bundle.py` and `scripts/build_company_profile_bundle.py` now expose the first standardized output layer for downstream analyzer/storage/notifier usage
- `company_profile` schema now supports `source_snapshots`, so one company profile can preserve site-native signals, LinkedIn insights, and official-site evidence side by side
- `company_profile` schema now also preserves `related_pages`, `available_signals`, `missing_signals`, and `raw_sections`, so the first capture program keeps as much analyzer-relevant evidence as possible

Current tracker scheduler progress:

- `config/trackers.toml` now stores the current tracker set in a minimal config-driven format
- tracker config currently keeps only the scheduler-facing fields: `id`, `label`, `url`, `source_frequency`, `target_new_jobs`, and `enabled`
- `target_new_jobs` is defined as "new job links to discover this run", not "top N jobs on the first page"
- `src/job_search_assistant/tracker_scheduler/` now contains config loading, due logic, and scheduler service code
- storage is intentionally abstracted behind `TrackerStateStore`, with SQLite as the first implementation and room for MySQL/Aurora adapters later
- `scripts/list_due_trackers.py` can list which trackers should run now
- `scripts/record_tracker_discovery.py` can persist one tracker run and record which discovered links were new
- `src/job_search_assistant/tracker_scheduler/platforms.py` now provides adapter-driven canonicalization for LinkedIn and Indeed search-result discovery
- `src/job_search_assistant/tracker_scheduler/linkedin.py` captures the validated LinkedIn rule: convert `search-results?...currentJobId=<id>` or `/jobs/view/<id>/...` into canonical JD links
- `src/job_search_assistant/tracker_scheduler/indeed.py` captures the validated Indeed rule: convert `search` / `viewjob` URLs containing `vjk` or `jk` into canonical Indeed JD links
- `src/job_search_assistant/tracker_scheduler/browser.py` now models one browser discovery session that canonicalizes raw URLs, computes which are new, and stops at JD-link discovery
- `scripts/normalize_job_links.py` now provides a thin CLI bridge from raw browser-collected LinkedIn / Indeed URLs to stable canonical JD links
- `scripts/prepare_tracker_discovery_batch.py` now turns one batch of browser-observed raw URLs into a structured discovery payload
- tracker scheduler explicitly stops at discovery. It does not rank, analyze, or decide fit; those remain in capture/analyzer layers
- real-page experiment on `mid_level_software_engineer_linkedin` confirmed that discovery can stay lightweight: click left result cards, read `currentJobId`, normalize to JD links, and page forward when the first page is exhausted
- real-page experiment on Indeed search results confirmed that discovery can stay lightweight there too: click main result cards, read `vjk`/`jk`, normalize to canonical Indeed JD links, and continue via result pagination
- first-milestone browser discovery now explicitly ignores horizontal carousels, related-job rails, and detail-page recommendation modules; only the primary vertical results list matters
