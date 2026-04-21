# Company Profile Capture Spec

## Goal

把“岗位页附带的公司画像”与“公司 Insights 页面”整理成可复用、可缓存、跨平台的 `company_profile` 产物。

这层的目标不是直接做岗位判断，而是给后续：

1. JD 分析器提供公司级上下文
2. 缓存公司级趋势、竞争、bridge signals
3. 给 Telegram / Notion / 人工回看提供可读材料

## Design Principles

- 不写死 LinkedIn-only schema
- 不穷举公司、平台、固定 section 名称
- 支持部分成功，能抓多少先落多少
- 优先保留原始叙事块，再补结构化表格和时间序列
- URL 是入口，但真正的浏览器驱动可以来自 `Computer Use`、脚本化浏览器、或其他 agent

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

## Workflow

推荐 capture workflow：

1. 打开 job URL
2. 做一次 full-page discovery pass
3. 先抓岗位页里可见的 company profile blocks
4. 如果存在 `Show Premium Insights` / `Insights`，继续进入完整 insights page
5. 优先抓结构化表格和时间序列
6. 再抓 narrative sections
7. 输出：
   - `company_profile.json`
   - `company_profile.md`
8. 将 static / dynamic 字段分别写入缓存

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

## Current Code Shape

当前仓库里的实现：

- `src/job_search_assistant/capture/company_profile.py`
  - 通用 schema
  - markdown renderer
  - cache payload split
- `scripts/render_company_profile.py`
  - `json -> company_profile.md`
  - 可选写入 SQLite cache

## Important Limitation

当前 Python 代码层还没有直接驱动 `Computer Use`。

也就是说：

- 现在已经有了统一的数据模型、markdown 产物和缓存入口
- 但真正的 `URL -> 打开浏览器 -> 点击 Insights -> 抽取内容` 仍然需要后续接入浏览器驱动层

这是刻意保留的边界，不把浏览器自动化硬编码进当前的纯 Python capture 层。
