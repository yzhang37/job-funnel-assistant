# Architecture Draft

## Proposed Pipeline

1. Source collector
2. Browser capture / page traversal
3. Job normalizer
4. Company profile normalizer
5. Fit analyzer
6. Notion writer
7. Notification sender

## Collector Strategy

- Prefer APIs when available
- Use scripted browser automation where feasible
- Use `Computer Use` for brittle, high-friction manual-style flows
- When a page exposes richer company-level insights, treat company profile capture as a sibling artifact to JD capture rather than folding everything into the job document

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

- `jd.md`: human-readable normalized posting text
- `company_profile.md`: human-readable company context, trends, bridge signals, and insights
- cache: company-level static fields and dynamic insights live in separate namespaces so one company can be reused across many jobs
