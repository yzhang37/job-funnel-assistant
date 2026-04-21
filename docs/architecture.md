# Architecture Draft

## Proposed Pipeline

1. Source collector
2. Browser capture / page traversal
3. Job normalizer
4. Company profile normalizer
5. Bundle writer / manifest builder
6. Fit analyzer
7. Notion writer
8. Notification sender

## Collector Strategy

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
