# PLANS.md

## Phase 0: Foundation

- [x] Create repository guidance files
- [x] Import user's analysis template
- [ ] Import user's resume template
- [ ] Confirm first target job sources
- [ ] Confirm preferred notification channel
- [x] Create first standalone job-fit analyzer component
- [x] Build LLM-driven Job Funnel / Resume Fit Analyst runner

## Phase 1: Data Model

- [ ] Define normalized job schema
- [x] Define Notion database schema
- [x] Import historical Wolai job data into Notion
- [x] Define suitability scoring output shape
- [ ] Decide how to deduplicate repeated job posts

## Phase 2: First End-To-End Flow

- [ ] Collect jobs from one source
- [ ] Normalize captured data
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
