# Architecture Draft

## Proposed Pipeline

1. `Tracker`
2. `Manual Intake`
3. `Capture`
4. `Analyzer`
5. `Output`

Canonical chain:

- `Tracker / Manual Intake -> Capture -> Analyzer -> Output`

More precise chain:

- `(Tracker)` / `(Manual Intake)` -> `Capture (outputs bundle)` -> `Analyzer` -> `Output`

Current first runnable manual chain:

1. `Manual intake (JD text or URL + JD text)`
2. `Capture (outputs bundle)`
3. `Analyzer`
4. `Output`
   - `Notion writer`
   - `Telegram short-result sender`

## Intake Layer

The system should expose two top-level intake families:

1. `Scheduled tracker intake`
2. `Manual intake`

### Scheduled tracker intake

- background-only
- driven by configured tracker URLs
- outputs only new canonical JD links
- no fit analysis
- no company-value judgment
- requires `Computer Use` in the current design

### Manual intake

- user-driven
- mobile-first
- should accept arbitrary incoming job material

Preferred payloads:

- `job_url`
- `jd_text`
- attachments
- `company_name`
- notes

Preferred channel priority:

1. Telegram
2. Email forward
3. Share sheet / shortcuts
4. Lightweight web intake page

All manual channels should map into the same internal request shape. Channel differences should not fork the downstream capture/analyzer logic.

Current first implemented manual-intake constraint:

- supported:
  - `jd_text`
  - `job_url + jd_text`
- not yet supported:
  - `job_url` only, when that would require live browser capture

## Node Boundary

The system-level node model should stay explicit:

- `Tracker / Manual Intake -> Capture -> Analyzer -> Output`

More precisely:

- `(Tracker)` / `(Manual Intake)` -> `Capture (outputs bundle)` -> `Analyzer` -> `Output`

Interpretation:

- `Tracker` discovers links
- `Manual Intake` accepts arbitrary incoming job material
- `Capture` is one node: it fetches, normalizes, and emits the bundle
- `Analyzer` is one node: it consumes evidence and decides fit
- `Output` is one node: it renders analyzer results into user-facing artifacts and routes them to the chosen delivery surfaces

## Collector Strategy

- Treat configured job trackers as the first discovery layer. The scheduler should periodically revisit tracker URLs and discover previously unseen job links.
- Scheduler scope is intentionally narrow: discover new job links, persist run state, and hand links off to capture. Do not do fit analysis or ranking in this stage.
- Scheduled tracker execution currently requires `Computer Use`: open search-result pages, click cards, and paginate until enough new canonical JD links are collected.
- Capture should remain the first layer that turns discovered input into durable evidence (`jd.md`, `job_posting.json`, `company_profile.json`, `manifest.json`).
- Capture execution also currently requires `Computer Use`: open job pages, expand content, traverse company/insights pages, and gather JD/company evidence before writing the bundle.
- Analyzer should remain the only layer that decides fit / priority (`主攻 / 备胎 / 放弃`).
- Tracker config should stay minimal and user-owned. Current stable fields are `id`, `label`, `url`, `source_frequency`, `target_new_jobs`, and `enabled`.
- `target_new_jobs` means "discover this many new job links for the current run, or stop early if the source is exhausted." Internal paging should stay inside the capture/scheduler runtime, not inside user config.
- Tracker scheduling state should remain portable across storage backends. SQLite is the first driver, but the service boundary should remain compatible with future MySQL/Aurora adapters.
- Current scheduler discovery should be adapter-driven rather than LinkedIn-only. LinkedIn and Indeed are the first validated search-result sources.
- Current LinkedIn tracker experiment validated a lightweight discovery path: click a left-side result card, read `currentJobId` from the search-results URL, normalize it to `https://www.linkedin.com/jobs/view/<job_id>/`, and page forward only when more new links are needed.
- Current Indeed search-results experiment validated the sibling path: click a main result card, read `vjk` / `jk` from the URL, normalize it to `https://www.indeed.com/viewjob?jk=<id>`, and continue via normal result pagination when more new links are needed.
- Discovery should stop at canonical JD links. Reading the right-side JD body or detail-page正文 is part of later capture, not scheduler responsibility.
- First-milestone browser discovery should only consume the primary vertical results list. Ignore horizontal carousels, related-job rails, and detail-page recommendation modules until the primary discovery loop is stable.
- Prefer APIs when available
- Use scripted browser automation where feasible
- Use `Computer Use` for brittle, high-friction manual-style flows
- When a page exposes richer company-level insights, treat company profile capture as a sibling artifact to JD capture rather than folding everything into the job document
- Treat company enrichment as multi-source by default: source-native company signals first, LinkedIn company/insights second, official site/careers third, other public sources last
- For LinkedIn enrichment, treat company URL resolution as a separate step: canonical company link first, cached slug/url second, direct insights URL third, search fallback last
- Treat LinkedIn insights blocks as optional modules. In current real-page testing, `Total employee count` and `function distribution` are stable high-value blocks, while openings/alumni/affiliated-pages may appear inconsistently across companies
- Company profile output should bias toward maximal evidence preservation rather than early summarization. Analyzer-facing handoff should retain summary metrics, tables, time series, related pages, available/missing signals, source snapshots, and raw captured blocks whenever possible.

## Notification Strategy

`Output` is the system component that owns result delivery.

It is responsible for:

- rendering analyzer output into a Notion page payload
- rendering analyzer output into a Telegram short message
- attaching the Notion page link to the Telegram reply

It is not responsible for:

- tracker discovery dedupe
- capture retries
- analyzer caching or reruns

Preferred initial channel: Telegram

Why:

- good mobile experience
- simple bot-based delivery
- easy to send concise summaries with links
- low operational overhead for a personal workflow

Fallbacks:

- email
- share sheet / shortcut handoff
- lightweight web intake page
- local summary dashboard
- thread automation follow-up inside Codex

Current first runnable output path:

- always create a Notion analysis page in `🧠 分析报告库`
- send a Telegram short message that includes:
  - 决策结论
  - 核心理由
  - 风险
  - `JD` 链接
  - `Notion` 分析页链接

## Secrets TODO

- TODO: the current local-development assumption is that secrets can live in a local file such as `.env.local`.
- TODO: if this system graduates to long-running automation, multi-machine execution, or cloud deployment, move secrets out of local flat files and into a managed secrets system such as AWS Secrets Manager.

## Current Capture Shape

- public interfaces:
  - `job link -> bundle`
  - `company name -> bundle`
- `jd.md`: human-readable normalized posting text
- `company_profile.md`: human-readable company context, trends, bridge signals, and insights
- `source_snapshots`: preserve which signals came from the source job board, LinkedIn, official site, or other enrichment sources
- `related_pages` / `available_signals` / `missing_signals` / `raw_sections`: preserve as much analyzer-relevant company evidence as practical
- `manifest.json`: machine-readable bundle index for downstream consumers
- bundle directory: standard handoff unit for analyzer, Telegram, Notion, and archival flows
- cache: company-level static fields and dynamic insights live in separate namespaces so one company can be reused across many jobs
- resolver mapping: company-to-LinkedIn slug/url resolution should be cacheable so repeated jobs do not need repeated company search
- tracker scheduler state: tracker runs and discovered job links should be persisted separately from analyzer results so discovery can stay lightweight and replaceable
