# AGENTS.md

## Project Purpose

This repository is for building a personal job-search assistant focused on:

1. Collecting job opportunities from target websites
2. Using analysis templates to decide whether a role fits the user
3. Saving promising roles into Notion for review and tracking
4. Sending a message notification so the user can decide whether to apply
5. Supporting browser-based automation when APIs are unavailable

The user is Chinese-speaking. Prefer concise Chinese in user-facing docs and outputs unless a task clearly requires English.

## Repo Structure

- `README.md`: human-readable overview and setup notes
- `PLANS.md`: active roadmap and phased execution plan
- `config/`: runtime configuration such as cache policy and future pipeline settings
- `templates/`: reusable prompt, analysis, and resume templates
- `scripts/`: lightweight utility scripts and automation entrypoints
- `src/`: application code
- `data/cache/`: SQLite cache files and reusable capture/analyzer snapshots
- `data/raw/`: raw job capture artifacts
- `data/processed/`: normalized or scored job records
- `docs/`: supporting design notes and integration decisions
- `automations/`: automation-related notes or exported configs

## Working Style

- Prefer incremental delivery over large one-shot builds.
- Keep the pipeline modular: tracker scheduler, capture, analyzer, storage, notifier.
- Design around replaceable integrations. Notion and Telegram are preferred initial targets, but avoid coupling core logic to any one provider.
- When a website has no reliable API, browser automation is acceptable. Prefer robust selectors and explicit retry logic.
- Keep cache policy configuration-driven. TTL and freshness rules should live in config files rather than being hardcoded in Python when practical.
- Treat job trackers as the first discovery layer. The scheduler should only discover new job links from configured tracker URLs; it must not perform fit analysis or ranking.
- Keep tracker configuration minimal and config-driven. Stable fields currently expected are `id`, `label`, `url`, `source_frequency`, `target_new_jobs`, and `enabled`.
- `target_new_jobs` means "keep paging internally until this many previously unseen job links are found, or the source is exhausted." Pagination is an implementation detail, not a user-facing config field.
- State storage for tracker scheduling should remain driver-abstracted. SQLite is the first implementation, but the service boundary should stay portable to MySQL/Aurora later.
- For LinkedIn tracker discovery, treat the canonical output as JD links only. Current validated path is: click a result card -> read `currentJobId` from the search-results URL -> normalize to `https://www.linkedin.com/jobs/view/<job_id>/`.
- LinkedIn tracker discovery should not depend on reading the right-side JD body. Right-side content is for later capture, not for discovery.
- For the first browser capture milestone, prefer a minimal output: convert extracted page content into `jd.md` before expanding to full packet/attachment workflows.
- Company profile capture should remain source-agnostic. The stable output should be `company_profile.json` / `company_profile.md`, while source-specific behavior such as LinkedIn Premium Insights belongs in optional capture strategies rather than the core schema.
- Public capture should converge on two entrypoints: `job link -> bundle` and `company name -> bundle`. Bundle output is the stable handoff format for analyzer, storage, and notification layers.
- For LinkedIn enrichment, prefer canonical company links already exposed on the page. Recommended resolution order: company URL from current page -> cached slug/url mapping -> direct `/company/<slug>/insights/` URL -> LinkedIn search fallback.
- If the source site itself exposes company-level insights, capture those first, then enrich with LinkedIn when available, then official site / careers. Preserve source attribution instead of flattening everything into one unlabeled blob.
- Do not over-prune company profile output before it reaches the analyzer. Prefer maximal evidence preservation: normalized summary fields plus rich tables, time series, related pages, source snapshots, available signals, missing signals, and raw sections whenever they exist.
- LinkedIn `Insights` pages are high-value but not uniform. Treat blocks such as `Total employee count`, `Employee distribution by function`, `Total job openings`, `Notable alumni`, and `Affiliated pages` as optional sections rather than guaranteed fields.
- Keep browser capture source-agnostic where practical. Avoid assuming LinkedIn-only fields, fixed screenshot counts, or platform-specific packet shapes unless a task explicitly calls for it.
- Preserve the user's templates and wording where possible; avoid rewriting them unless asked.

## Commands

The project may start without a fixed stack. Before adding new tools or dependencies:

1. inspect the repository state
2. document the chosen stack in `README.md`
3. add runnable commands here once they exist

Common expected commands once implemented:

- list due trackers: `python3 scripts/list_due_trackers.py --config config/trackers.toml --db data/cache/tracker_scheduler.sqlite3`
- record tracker discovery: `python3 scripts/record_tracker_discovery.py --config config/trackers.toml --db data/cache/tracker_scheduler.sqlite3 --tracker-id <tracker_id> --job-url <job_url>`
- normalize raw LinkedIn tracker URLs to JD links: `python3 scripts/normalize_linkedin_job_links.py --url <linkedin_search_or_view_url>`
- analyze one job: `python3 scripts/analyze_job_fit.py --job <job.json> --profile <profile.json> --pretty`
- run funnel analysis: `python3 scripts/run_job_funnel_analysis.py --jd-file <jd.txt> --provider <mock|openai>`
- render jd markdown: `python3 scripts/render_jd_markdown.py --input <capture.json> --output <jd.md>`
- render company profile markdown: `python3 scripts/render_company_profile.py --input <profile.json> --output <company_profile.md>`
- build job capture bundle: `python3 scripts/build_job_capture_bundle.py --job-input <job.json> --output-dir <bundle_dir>`
- build company profile bundle: `python3 scripts/build_company_profile_bundle.py --input <company_profile.json> --output-dir <bundle_dir>`
- validate cache layer: `python3 -m py_compile src/job_search_assistant/cache/*.py`
- run app: `TBD`
- run automation: `TBD`
- test: `TBD`
- lint: `TBD`

## Guardrails

- Do not send real applications without explicit user approval.
- Do not auto-submit forms on job sites unless the user asks for that workflow.
- Notifications should summarize and link; they should not trigger irreversible actions.
- Treat resumes, credentials, and personal data as sensitive.
- Prefer dry-run support for scraping, analysis, and notification steps.

## Definition Of Done

A task is complete only when all relevant items are true:

1. Code or docs are updated
2. Any new workflow is documented in `README.md`
3. The changed path is validated with the best available check
4. Limitations, assumptions, and next steps are recorded if something is unfinished

## Current Direction

Initial focus:

1. establish the project structure
2. ingest the user's existing analysis and resume templates
3. define the Notion schema
4. choose and wire a message notification channel
5. build a tracker-first discovery loop: trackers -> new job links -> capture -> analyzer
6. validate the first real LinkedIn tracker execution path: click result cards, derive canonical JD links, and keep analysis out of the scheduler
