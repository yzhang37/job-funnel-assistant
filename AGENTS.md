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
- Keep the pipeline modular around five named components:
  - `Tracker`
  - `Manual Intake`
  - `Capture`
  - `Analyzer`
  - `Output`
- Design around replaceable integrations. Notion and Telegram are preferred initial targets, but avoid coupling core logic to any one provider.
- Distinguish clearly between background intake and manual intake. Background intake is tracker-driven and scheduled; manual intake is user-driven and should accept arbitrary job links, JD text, and attachments.
- Treat Telegram as the preferred manual intake channel for mobile-first use. Email forward is a secondary/manual fallback rather than the primary interactive surface.
- Additional manual intake surfaces such as share sheet shortcuts and a lightweight web form are valid complements when they reduce friction, but they should map into the same internal request shape.
- When a website has no reliable API, browser automation is acceptable. Prefer robust selectors and explicit retry logic.
- In the current planned system, both `Tracker` execution and `Capture` execution depend on `Computer Use`. Tracker needs it to open search-result pages, click result cards, and paginate; Capture needs it to open job/company pages, expand content, and collect JD/company evidence.
- Keep cache policy configuration-driven. TTL and freshness rules should live in config files rather than being hardcoded in Python when practical.
- Treat job trackers as the first discovery layer. The scheduler should only discover new job links from configured tracker URLs; it must not perform fit analysis or ranking.
- Keep tracker configuration minimal and config-driven. Stable fields currently expected are `id`, `label`, `url`, `source_frequency`, `target_new_jobs`, and `enabled`.
- `target_new_jobs` means "keep paging internally until this many previously unseen job links are found, or the source is exhausted." Pagination is an implementation detail, not a user-facing config field.
- State storage for tracker scheduling should remain driver-abstracted. SQLite is the first implementation, but the service boundary should stay portable to MySQL/Aurora later.
- Treat scheduler discovery as platform-adapter driven. LinkedIn and Indeed are the first supported search-result sources; future sites should plug in through the same canonical JD-link boundary.
- For LinkedIn tracker discovery, treat the canonical output as JD links only. Current validated path is: click a result card -> read `currentJobId` from the search-results URL -> normalize to `https://www.linkedin.com/jobs/view/<job_id>/`.
- For Indeed tracker discovery, treat the canonical output as JD links only. Current validated path is: click a result card -> read `vjk`/`jk` from the search/search-result URL -> normalize to `https://www.indeed.com/viewjob?jk=<id>`.
- LinkedIn tracker discovery should not depend on reading the right-side JD body. Right-side content is for later capture, not for discovery.
- Scheduler browser discovery should only consume the primary vertical result list. Ignore horizontal carousels, related-job rails, and detail-page recommendation modules in the first milestone.
- For the first browser capture milestone, prefer a minimal output: convert extracted page content into `jd.md` before expanding to full packet/attachment workflows.
- Company profile capture should remain source-agnostic. The stable output should be `company_profile.json` / `company_profile.md`, while source-specific behavior such as LinkedIn Premium Insights belongs in optional capture strategies rather than the core schema.
- Public capture should converge on two entrypoints: `job link -> bundle` and `company name -> bundle`. Bundle output is the stable handoff format for analyzer, storage, and notification layers.
- System-level node model should stay explicit:
  - `Tracker / Manual Intake -> Capture -> Analyzer -> Output`
  - More precisely:
    - `(Tracker)` / `(Manual Intake)` -> `Capture (outputs bundle)` -> `Analyzer` -> `Output`
- Manual intake should expose one user-facing entry that accepts multiple payload types: `job_url`, `jd_text`, optional `attachments`, optional `company_name`, and optional `notes`. Different channels should not fork the downstream pipeline.
- `Output` is a first-class system component. It receives analyzer results and decides how to render and route them, for example:
  - write/update the Notion analysis page
  - send the Telegram short reply
  - attach the Notion page link in the Telegram response
- Telegram manual intake should behave like an owner-only control surface. Only messages from the configured owner chat/user should be processed; bot-authored replies and messages from other chats/users must be ignored.
- `Output` is not responsible for tracker dedupe, capture retries, or analyzer caching. Those belong to upstream execution layers.
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
- normalize raw tracker URLs to JD links: `python3 scripts/normalize_job_links.py --url <raw_search_or_view_url>`
- prepare one browser discovery batch: `python3 scripts/prepare_tracker_discovery_batch.py --config config/trackers.toml --db data/cache/tracker_scheduler.sqlite3 --tracker-id <tracker_id> --raw-url <raw_url>`
- analyze one job: `python3 scripts/analyze_job_fit.py --job <job.json> --profile <profile.json> --pretty`
- run funnel analysis: `python3 scripts/run_job_funnel_analysis.py --jd-file <jd.txt> --provider <auto|codex|openai|mock>`
- render jd markdown: `python3 scripts/render_jd_markdown.py --input <capture.json> --output <jd.md>`
- render company profile markdown: `python3 scripts/render_company_profile.py --input <profile.json> --output <company_profile.md>`
- build job capture bundle: `python3 scripts/build_job_capture_bundle.py --job-input <job.json> --output-dir <bundle_dir>`
- build company profile bundle: `python3 scripts/build_company_profile_bundle.py --input <company_profile.json> --output-dir <bundle_dir>`
- run one manual intake end-to-end: `python3 scripts/run_manual_intake_once.py --text-file <input.txt> --source-channel telegram --provider auto --write-notion --send-telegram`
- process Telegram manual-intake updates: `python3 scripts/process_telegram_manual_intake.py --provider auto`
- send one Telegram message from `.env.local`: `python3 scripts/send_telegram_message.py --text "hello"`
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
- TODO: 当前本地开发可使用 `.env.local` 一类本地 secrets 文件；未来如需长期运行或多机部署，应迁移到更安全的 secrets 管理方案，例如 AWS Secrets Manager。
- 当前 analyzer 默认应优先使用本机已登录的 `Codex` CLI；`OPENAI_API_KEY` 路径只作为可选 fallback，不应作为本地单机工作流的默认前提。
- 当前 Telegram manual intake 第一版已支持：`JD 文本` 与 `岗位链接 + JD 文本`。
- 当前 Telegram manual intake 第一版仍未支持：`纯 job_url` 直接触发 live browser capture。
- 当前 Telegram manual intake 第一版只处理配置好的 owner 消息：优先校验 `TELEGRAM_USER_ID`，若未配置则退回到私聊场景下的 `TELEGRAM_CHAT_ID`；bot 自己发出的消息不应进入 intake 流程。

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
4. define the intake layer clearly:
   - scheduled tracker intake
   - manual intake (`job_url`, `jd_text`, attachments, company name)
   - preferred channels: Telegram first, email forward second, share sheet/web intake later
5. choose and wire a message notification channel
6. build a tracker-first discovery loop: trackers -> new job links -> capture -> analyzer
7. validate the first real LinkedIn tracker execution path: click result cards, derive canonical JD links, and keep analysis out of the scheduler
8. keep the five-component framing stable across docs and code:
   - `Tracker`
   - `Manual Intake`
   - `Capture`
   - `Analyzer`
   - `Output`
