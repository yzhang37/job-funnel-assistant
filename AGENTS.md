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
- Keep the pipeline modular: collector, analyzer, storage, notifier.
- Design around replaceable integrations. Notion and Telegram are preferred initial targets, but avoid coupling core logic to any one provider.
- When a website has no reliable API, browser automation is acceptable. Prefer robust selectors and explicit retry logic.
- Keep cache policy configuration-driven. TTL and freshness rules should live in config files rather than being hardcoded in Python when practical.
- For the first browser capture milestone, prefer a minimal output: convert extracted page content into `jd.md` before expanding to full packet/attachment workflows.
- Keep browser capture source-agnostic where practical. Avoid assuming LinkedIn-only fields, fixed screenshot counts, or platform-specific packet shapes unless a task explicitly calls for it.
- Preserve the user's templates and wording where possible; avoid rewriting them unless asked.

## Commands

The project may start without a fixed stack. Before adding new tools or dependencies:

1. inspect the repository state
2. document the chosen stack in `README.md`
3. add runnable commands here once they exist

Common expected commands once implemented:

- analyze one job: `python3 scripts/analyze_job_fit.py --job <job.json> --profile <profile.json> --pretty`
- run funnel analysis: `python3 scripts/run_job_funnel_analysis.py --jd-file <jd.txt> --provider <mock|openai>`
- render jd markdown: `python3 scripts/render_jd_markdown.py --input <capture.json> --output <jd.md>`
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
5. build a first end-to-end flow for one target job source
