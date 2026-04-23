# Company Profile Capture Spec

## Goal

把“岗位页附带的公司画像”与“公司 Insights 页面”整理成可复用、可缓存、跨平台的 `company_profile` 产物。

当前实现边界已经明确：

- `Company Profile / Insights / Cache` 全部属于 `Capture`
- `Manual Intake` 只负责把 `job_url` / `jd_text` / `company_name` 交给 `Capture`
- `Analyzer` 只消费 `Capture` 产出的 bundle 和 company profile 证据

这层的目标不是直接做岗位判断，而是给后续：

1. JD 分析器提供公司级上下文
2. 缓存公司级趋势、竞争、bridge signals
3. 给 Telegram / Notion / 人工回看提供可读材料

## Design Principles

- 不写死 LinkedIn-only schema
- 不穷举公司、平台、固定 section 名称
- 支持部分成功，能抓多少先落多少
- 优先保留原始叙事块，再补结构化表格和时间序列
- 有原站洞察时先抓原站，再补 LinkedIn，再补官网/官方 careers，且要保留来源分层
- 第一程序输出的 `company_profile` 应尽量保留证据，不要在 capture 阶段过早浓缩成几条摘要
- URL 是入口，但真正的浏览器驱动可以来自 `Computer Use`、脚本化浏览器、或其他 agent
- 在当前项目设计里，真实的 company profile capture 以 `Computer Use` 为前提执行层
- 当前生产链路里，`company_profile_static` / `company_insights` cache 也在 `Capture` 同一步写入，而不是交给其他组件补写

## Capture Modes

### Mode 1: Embedded Profile

来源是 job page 上附带的公司画像卡片，例如：

- company focus areas
- hiring & headcount
- latest hiring trend
- bridge signals
- competitors

适合快速发现和轻量缓存。

### Mode 2: Full Insights Page

来源是 job page 中的 `Show Premium Insights` 或公司页 `Insights`。

优先级更高，因为通常会暴露：

- total job openings table
- total employee count
- employee distribution and growth by function
- notable company alumni
- 更完整的趋势图和表格

注意：

- 这些 block 不是每家公司都齐全
- 目前实测里，`Total employee count` 和 `Employee distribution and headcount growth by function` 命中率更高
- `Total job openings`、`Notable company alumni`、`Affiliated pages` 应视为可选增强块

## Required Minimum Fields

一个 `company_profile` 至少应包含：

- `company_name`
- `source_url`

推荐补充：

- `source_platform`
- `company_tagline`
- `company_description`
- `industry`
- `headquarters`
- `followers_text`
- `employee_size_text`
- `employees_on_platform_text`

## High-Value Capture Blocks

优先抓这些块：

1. `headline_metrics`
   - total employees
   - total job openings
   - company growth
   - engineering growth
   - median tenure

2. `narrative_sections`
   - company focus areas
   - hiring & headcount summary
   - competitors summary
   - about company

3. `metric_tables`
   - openings by function
   - headcount distribution by function

4. `time_series`
   - employee count by month
   - other trend lines if available

5. `bridge_signals`
   - hires from companies
   - hires from schools
   - “people in your network”

6. `notable_alumni`
   - name
   - current role
   - previous role at company

7. `affiliated_pages`
   - 子品牌
   - showcase page
   - 产品线相关页面
   - 其他有助于理解公司结构的关联页面

8. `source_snapshots`
   - source-native job board signals
   - LinkedIn company page / insights signals
   - official website / careers signals
   - other enrichment signals

9. `related_pages`
   - parent page
   - affiliated pages
   - pages people also viewed
   - related platform / product pages

10. `available_signals` / `missing_signals`
   - 当前确实拿到了哪些高价值块
   - 当前明确缺失哪些高价值块

11. `raw_sections`
   - 原始长文本 block
   - 截断前的竞争格局 / hiring summary / about company 文本
   - 其他暂时不想丢掉、但还没完全标准化的页面材料

## Workflow

推荐 capture workflow：

1. 打开 job URL
2. 做一次 full-page discovery pass
3. 先抓岗位页里可见的 company profile blocks
4. 把这些 source-native 信号先存入 `source_snapshots`
5. 如果当前页面已经暴露 canonical company link，优先复用它
6. 如果存在 `Show Premium Insights` / `Insights`，继续进入完整 insights page
7. 如果 job page 没有 insights，但已经有 LinkedIn company slug 或 cached company URL，直接尝试 `/company/<slug>/insights/`
8. 只有在缺少 canonical company URL / cached mapping / slug 时，才回退到 company-name search
9. 再补官方 company site / careers
10. 优先抓结构化表格和时间序列
11. 再抓 narrative sections
12. 输出：
   - `company_profile.json`
   - `company_profile.md`
   - `manifest.json` if the result is packaged as a reusable bundle
13. 将 static / dynamic 字段分别写入缓存

2026-04-21 的真实页面验证结果：

- `https://www.linkedin.com/company/jackandjillai/insights/` 可直接访问
- 页面稳定暴露了：
  - `Total employee count`
  - `Employee distribution and headcount growth by function`
  - `Affiliated pages`
- 但没有像部分其他公司那样稳定暴露 `Total job openings`

这进一步证明：

- `/company/<slug>/insights/` 是值得优先尝试的 enrichment path
- `Insights` 页需要按“可选块集合”而不是“固定 schema”来抓

## LinkedIn Resolution Strategy

如果 enrichment 目标是 LinkedIn company insights，推荐顺序：

1. job page 现成的 company link
2. 本地缓存过的 slug / company URL
3. 已知 slug 后直接拼 `/company/<slug>/insights/`
4. LinkedIn 搜索公司名作为兜底

原因：

- 减少点击
- 更适合自动化
- 降低 slug 猜错风险
- 同一家公司后续可直接复用

更完整说明见：

- [docs/linkedin-company-resolution.md](/Users/l/Projects/找工作/docs/linkedin-company-resolution.md)

## Cache Mapping

建议拆成两个 namespace：

- `company_profile_static`
  - 公司名称
  - tagline
  - description
  - industry
  - headquarters
  - followers
  - employee size
  - featured customers

- `company_insights`
  - headline metrics
  - bridge signals
  - competitor names
  - narrative sections
  - metric tables
  - time series
  - notable alumni
  - affiliated pages

此外，建议后续增加独立的 resolver mapping cache，用来保存：

- `company_name -> linkedin_company_slug`
- `company_name -> linkedin_company_url`
- `company_name -> linkedin_insights_url`
- `resolved_via`
- `resolved_at`
- `confidence`

## Current Code Shape

当前仓库里的实现：

- `src/job_search_assistant/capture/company_profile.py`
  - 通用 schema
  - markdown renderer
  - cache payload split
  - `source_snapshots` support for source-native + LinkedIn + official evidence
  - `related_pages` / `available_signals` / `missing_signals` / `raw_sections`
- `src/job_search_assistant/capture/bundle.py`
  - bundle / manifest writer
- `scripts/render_company_profile.py`
  - `json -> company_profile.md`
  - 可选写入 SQLite cache
- `scripts/build_company_profile_bundle.py`
  - `json -> company_profile bundle`

相关 bundle 约定见：

- [docs/capture-bundle-spec.md](/Users/l/Projects/找工作/docs/capture-bundle-spec.md)

## Important Limitation

当前 Python 代码层还没有直接驱动 `Computer Use`。

也就是说：

- 现在已经有了统一的数据模型、markdown 产物和缓存入口
- 但真正的 `URL -> 打开浏览器 -> 点击 Insights -> 抽取内容` 仍然需要后续接入浏览器驱动层

这是刻意保留的边界，不把浏览器自动化硬编码进当前的纯 Python capture 层。
