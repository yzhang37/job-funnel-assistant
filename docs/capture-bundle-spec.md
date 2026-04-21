# Capture Bundle Spec

## Goal

把浏览器抓取、公司画像 enrichment、后续 analyzer / Telegram / Notion 之间的交接格式固定成统一 bundle。

这层解决的问题不是“怎么抓页面”，而是：

- 抓完后如何稳定交给下游
- 如何同时承载 `JD`、`company_profile`、附件和元信息
- 如何让 `job link` 接口和 `company name` 接口共享同一套产物约定

## Public Interfaces

当前总 pipeline 对外收敛成两个公开接口：

1. `job link -> bundle`
   - 输入：一个 JD URL
   - 目标输出：
     - `jd.md`
     - `job_posting.json`
     - `company_profile.md`
     - `company_profile.json`
     - `manifest.json`
     - `attachments/`

2. `company name -> bundle`
   - 输入：公司名
   - 目标输出：
     - `company_profile.md`
     - `company_profile.json`
     - `manifest.json`
     - 可选 `attachments/`

注意：

- 这两个接口共享 resolver、company profile capture、cache 等底层能力
- 第一个接口是主入口，第二个接口适合预热缓存、单独研究公司、补公司画像

## Bundle Layout

### Job Capture Bundle

```text
<bundle_dir>/
  manifest.json
  job_posting.json
  jd.md
  company_profile.json         # optional
  company_profile.md           # optional
  attachments/                 # optional
```

### Company Profile Bundle

```text
<bundle_dir>/
  manifest.json
  company_profile.json
  company_profile.md
  attachments/                 # optional
```

## Manifest Shape

`manifest.json` 负责让程序理解“这一包里有什么”。

最小字段：

- `bundle_version`
- `bundle_kind`
- `generated_at`
- `subject`
- `source_inputs`
- `artifacts`
- `attachments`
- `available_outputs`
- `notes`

另外建议 `company_profile.json` 内部保留：

- `source_snapshots`

这样 bundle 里的公司画像可以同时承载：

- 来源站自己的公司信号
- LinkedIn enrichment
- 官网 / careers 补充信号

并且应该尽量保留：

- `related_pages`
- `available_signals`
- `missing_signals`
- `raw_sections`
- `source_snapshots`

设计原则：

- 不把平台差异写死在 manifest 顶层
- 附件必须是数组
- `artifacts` 只描述产物，不重复存长文本内容
- 有些产物可缺省，例如 `job capture bundle` 里暂时没有 `company_profile`
- `company_profile.json` 应尽量保留高密度证据，而不是过早裁剪成几条摘要

## Attachment Policy

- 附件数量不固定
- 文件名不应有语义硬编码要求
- 通过 `attachments[]` 元数据描述用途
- 本地默认先生成目录 bundle
- 需要跨 agent / Telegram / 归档时，再由上层决定是否压成 zip

## Current First Version

当前仓库已经有第一版 bundle builder：

- `scripts/build_job_capture_bundle.py`
- `scripts/build_company_profile_bundle.py`
- `src/job_search_assistant/capture/bundle.py`

这版已经完成：

- 标准 bundle 目录输出
- `manifest.json`
- `jd.md` / `company_profile.md`
- 归一化 JSON 副本
- 本地附件复制到 `attachments/`

这版还没有完成：

- 真正的 `URL -> 浏览器抓取 -> 自动填 bundle`
- 真正的 `company name -> resolver -> insights capture`

也就是说：

- 当前这层已经把输出 contract 固定好了
- 浏览器驱动层后续只需要把抓到的数据喂给这套 bundle writer

## Why This Boundary

这个边界的好处是：

- `Computer Use`、脚本化浏览器、别的 agent 都可以复用同一输出格式
- analyzer 只需要消费 bundle，不需要关心抓取细节
- Telegram / Notion / 缓存 / 人工回看都能围绕同一个目录包工作
- 后面如果换平台，不需要重写 bundle contract
