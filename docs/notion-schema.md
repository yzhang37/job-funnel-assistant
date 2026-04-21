# Notion Schema

## Parent Page

- `找工作项目`

## Databases

### 1. Stage Policy

Fields:

- `Stage Name`
- `SLA (days)`
- `Is Terminal`
- `Ghost Candidate After (days)`

Seeded stages:

- `Pending Referral`
- `Applied`
- `Recruiter Contacted`
- `Screening`
- `Interviewing`
- `Offer`
- `Ghost`
- `Rejected`

### 2. Jobs

Primary fields:

- `Title`
- `Company`
- `External ID`
- `Source`
- `Canonical URL`
- `POC / Recruiter`
- `Stage`
- `Applied At`
- `Last Activity`
- `Notes`
- `Snooze Until`
- `Created Time`
- `Country`
- `Mock / Test`
- `Original Create Time`

Derived fields:

- `company_slug`
- `title_slug`
- `unique_id`
- `SLA (days)`
- `Is Terminal`
- `Ghost Candidate After (days)`
- `Reference Date`
- `Days Since Update`
- `Next Follow-up`
- `Follow-up Summary`
- `Follow-up Soon`
- `Follow-up Due`
- `Follow-up Overdue`
- `Needs Follow-up`
- `Stage Name`

## Formula Notes

The current Notion connector accepted the following adaptations:

- `company_slug` and `title_slug` are regex-based but do not force lowercase in the formula layer
- `unique_id` is computed inline instead of referencing other formula properties
- `Needs Follow-up` uses `Stage Name` string checks instead of a direct boolean test on the `Is Terminal` rollup, because the connector rejected that comparison during schema creation

## Imported Data

- Historical Wolai data has been imported into `Jobs`.
- Existing test rows were kept, but moved behind a `Mock / Test` checkbox so they stay hidden from normal working views.

Mock rows currently include:

- `Senior Backend Engineer`
- `Machine Learning Engineer`
- `Product Engineer`
- `Frontend Engineer`

Useful views:

- `快速录入`
- `待跟进`
- `待跟进卡片`
- `最近活动`
- `全部岗位`
- `进度看板`
- `处理池`

Gallery follow-up presentation:

- `待跟进` now uses a compact gallery layout with `Follow-up Summary`
- `Follow-up Summary` is intended for human-readable cards such as `122 天未更新 · 2026-04-20 跟进`
- `Follow-up Soon`, `Follow-up Due`, and `Follow-up Overdue` are automatic boolean formulas derived from application activity dates
