# Architecture Draft

## Proposed Pipeline

1. Source collector
2. Job normalizer
3. Fit analyzer
4. Notion writer
5. Notification sender

## Collector Strategy

- Prefer APIs when available
- Use scripted browser automation where feasible
- Use `Computer Use` for brittle, high-friction manual-style flows

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
