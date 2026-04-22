# Architecture Draft

## Proposed Pipeline

1. Tracker monitor / scheduler
2. Browser capture / page traversal
3. Job normalizer
4. Company profile normalizer
5. Bundle writer / manifest builder
6. Fit analyzer
7. Notion writer
8. Notification sender

## Collector Strategy

- Treat configured job trackers as the first discovery layer. The scheduler should periodically revisit tracker URLs and discover previously unseen job links.
- Scheduler scope is intentionally narrow: discover new job links, persist run state, and hand links off to capture. Do not do fit analysis or ranking in this stage.
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

Preferred initial channel: Telegram

Why:

- good mobile experience
- simple bot-based delivery
- easy to send concise summaries with links
- low operational overhead for a personal workflow

Fallbacks:

- email
- local summary dashboard
- thread automation follow-up inside Codex

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
