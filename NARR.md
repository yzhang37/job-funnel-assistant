# Job Search Assistant Narrative Document

版本：2026-04-22  
状态：基线叙事文档  
修改规则：**未经用户明确许可，不得改动本文件**

## 1. 背景与目标

### 1.1 背景

本项目要构建一个个人找工作自动化助手，核心不是“全自动海投”，而是：

1. 自动发现岗位
2. 自动抓取岗位与公司信息
3. 自动根据候选人画像进行分析
4. 自动把结果写入 Notion
5. 自动把摘要回到 Telegram，方便用户在手机上做决策

当前项目已经形成了统一的 5 个系统部件：

1. `Tracker`
2. `Manual Intake`
3. `Capture`
4. `Analyzer`
5. `Output`

系统的 canonical chain 已经在文档中明确为：

- `Tracker / Manual Intake -> Capture -> Analyzer -> Output`

更精确地说：

- `(Tracker)` / `(Manual Intake)` -> `Capture (outputs bundle)` -> `Analyzer` -> `Output`

### 1.2 目标

本阶段目标不是支持所有网站、所有输入，而是先把最小可用闭环跑通，并确保部件边界清晰、后续可扩展。

本阶段优先级：

1. 让 `Manual Intake -> Capture -> Analyzer -> Output` 可生产使用
2. 让 `Tracker -> JD links` 的 discovery 稳定
3. 保持 `Capture` 和 `Analyzer` 的职责严格分离
4. 为未来 `纯 job_url` 自动抓取补全执行口

### 1.3 非目标

本阶段明确不是目标的内容：

- 自动投递
- 自动提交 job form
- 自动替用户做最终申请决策
- 多云部署 / 微服务化
- 浏览器脚本反爬优化的大规模投入
- 完整状态机 / 工作流系统

## 2. 当前项目真实规模

### 2.1 仓库规模

当前仓库主要包含：

- 核心文档：
  - `AGENTS.md`
  - `README.md`
  - `PLANS.md`
  - `docs/architecture.md`
- 运行脚本：
  - `scripts/process_telegram_manual_intake.py`
  - `scripts/run_manual_intake_once.py`
  - `scripts/run_job_funnel_analysis.py`
  - `scripts/send_telegram_message.py`
  - `scripts/list_due_trackers.py`
  - `scripts/record_tracker_discovery.py`
  - `scripts/prepare_tracker_discovery_batch.py`
- 核心代码：
  - `src/job_search_assistant/manual_flow.py`
  - `src/job_search_assistant/analyzer/*`
  - `src/job_search_assistant/capture/*`
  - `src/job_search_assistant/tracker_scheduler/*`
  - `src/job_search_assistant/integrations/*`

### 2.2 当前是中等复杂度单机工作流项目

它不是一个简单脚本，也不是大型分布式系统。

更准确地说，它是一个：

- 单机优先
- 组件清晰
- 强依赖外部 SaaS（Telegram / Notion）
- 浏览器自动化参与较多
- 分析环节由 Codex 驱动

的个人自动化工作流系统。

### 2.3 当前部署假设

当前最合理部署假设是：

- 一台本地 MacBook Pro 作为执行机
- Telegram 作为手动入口与消息出口
- Notion 作为长期分析库
- 本地 Codex CLI 作为 Analyzer 默认执行器

## 3. 用户需求收口

### 3.1 用户的核心诉求

用户当前最明确的诉求有 4 个：

1. 手机优先
   - 最好直接在 Telegram 发内容
   - 收到结果也在 Telegram 看
2. 完整链路自动化
   - 输入内容后，不需要人工再搬运数据
   - 要自动到 Notion 和 Telegram
3. 组件严格分工
   - `Manual Intake` 不能越权做 `Capture` 的事
   - `Capture` 不能越权做 `Analyzer` 的事
   - 每个组件职责必须稳定
4. 成本敏感
   - 不希望 Analyzer 默认走 `OPENAI_API_KEY`
   - 希望优先使用本地已登录的 Codex

### 3.2 当前明确支持的人工输入

根据当前代码，Manual Intake 支持的输入形态定义为：

- `job_url`
- `jd_text`
- `attachments`
- `company_name`
- `notes`

但是，当前代码真正跑通的手动链路只包括：

- `JD 文本`
- `JD Link + JD 文本`

当前还未跑通：

- `纯 JD Link -> live browser capture`

这点非常重要，后续实现必须以此为准。

## 4. 五个部件的工程边界

### 4.1 Tracker

职责：

- 定期访问配置好的 tracker URL
- 只发现新的 canonical JD links
- 不抓 JD
- 不抓公司画像
- 不做分析

当前代码状态：

已实现：

- tracker config
- due 逻辑
- SQLite 存储
- LinkedIn / Indeed 链接规范化
- browser discovery batch 逻辑

未实现：

- 真正自动打开浏览器、点卡片、翻页、抓满 `target_new_jobs`

当前收口：

**Tracker 当前只到“发现 JD links”这一步。**

### 4.2 Manual Intake

职责：

- 接收人工输入
- 规范化成内部请求对象
- 把请求交给 Capture
- 不做抓取判断
- 不做分析判断

当前代码状态：

入口脚本：

- `scripts/process_telegram_manual_intake.py`
- `scripts/run_manual_intake_once.py`

当前实现问题：

- 代码里曾被加入“只有 URL 就拒绝”的临时限制
- 这不符合正确架构边界
- 这不是用户需求，而是错误的产品化判断

正确收口：

**Manual Intake 只收输入，不应决定是否抓网页。**

### 4.3 Capture

职责：

- 吃 `job_url` / `jd_text` / 两者组合
- 决定是否需要打开网页抓最小 JD
- 生成 bundle

bundle 包含：

- `jd.md`
- `job_posting.json`
- `company_profile.json`
- `company_profile.md`
- `manifest.json`

当前代码状态：

已实现：

- bundle writer
- JD markdown renderer
- company profile schema
- manual text-based capture path

未实现：

- `job_url only -> live browser capture -> bundle`

当前收口：

**Capture 的 bundle 输出协议已经明确，但 `纯 URL` 的 live capture 入口还没接上。**

### 4.4 Analyzer

职责：

- 吃 Capture 输出
- 根据固定分析模板生成结构化分析
- 给出：
  - `主攻`
  - `备胎`
  - `放弃`

当前代码状态：

已实现：

- `run_job_funnel_analysis.py`
- bundle 输入支持
- `company_profile` 自动带入 packet
- 本地默认 provider 优先 `Codex`

Provider 选择顺序：

1. `codex`
2. `openai` fallback
3. `mock`

当前收口：

**Analyzer 已经是可运行组件，而且现在默认按用户要求优先使用本机 Codex。**

### 4.5 Output

职责：

- 接收 Analyzer 结果
- 写 Notion 分析页
- 发 Telegram 短消息
- 在 Telegram 中附上 Notion 页链接

当前代码状态：

已实现：

- Notion page create
- Telegram short reply
- manual chain 的 output 已真实验证过

当前收口：

**Output 是已可用组件。**

## 5. 当前代码与文档到底收口在哪一步

### 5.1 文档收口

当前 `AGENTS.md`、`README.md`、`PLANS.md`、`docs/architecture.md` 的共同收口是：

全局系统模型：

- `Tracker`
- `Manual Intake`
- `Capture`
- `Analyzer`
- `Output`

全局链路：

- `Tracker / Manual Intake -> Capture -> Analyzer -> Output`

当前执行假设：

- `Tracker` 需要 `Computer Use`
- `Capture` 需要 `Computer Use`

当前人工链路限制：

- 支持：
  - `JD 文本`
  - `岗位链接 + JD 文本`
- 不支持：
  - `纯 job_url` 自动触发 live browser capture

也就是说：

**文档已经明确承认：纯链接链路还没接。**

### 5.2 代码收口

当前代码的真实收口，比文档更窄一点：

已真实跑通的代码链路：

- `Telegram / CLI 输入 JD 文本`
- `build_manual_capture_bundle(...)`
- `run_analysis_for_capture_bundle(...)`
- `NotionAnalysisReportClient.create_analysis_page(...)`
- `TelegramBotClient.send_message(...)`

代码级未打通点：

- `build_manual_capture_bundle(...)` 仍要求 `jd_text`
- `process_telegram_manual_intake.py` 当前仍有 URL-only 的拦截逻辑
- 没有 `job_url only -> live browser capture` 的实现入口

也就是说：

**代码目前真正收口在：**

- `JD 文本（或 URL + JD 文本） -> Capture -> Analyzer -> Output`

而不是：

- `纯 URL -> Capture -> Analyzer -> Output`

## 6. 当前已实现需求 vs 未实现需求

### 6.1 已实现需求

A. Telegram 手动分析最短链路

已实现：

- Telegram 收消息
- 只处理 owner 消息
- 用手动输入构建 bundle
- 调 Analyzer
- 写 Notion
- 回 Telegram

B. Notion 分析报告库

已实现：

- `🧠 分析报告库`
- 中文字段
- 完整分析页写入

C. Telegram 输出

已实现：

- 短结果
- Notion 分析页链接

D. Tracker discovery

已实现：

- due 逻辑
- JD link 规范化
- discovery session 数据结构

### 6.2 未实现需求

A. 纯 JD Link capture

未实现：

- `job_url only -> 打开网页 -> 抓最小 JD 文本 -> 继续后续`

B. Tracker 到后续全自动

未实现：

- `Tracker -> 一批 JD Links -> Capture -> Analyzer -> Output`

C. 真正常驻部署

未实现：

- 本地 poller / 定时任务的生产部署脚本与守护

## 7. 当前最小生产范围

如果现在只做一个真正可生产部署的 MVP，它应该是：

### 7.1 支持范围

输入：

- Telegram 手动输入：
  - `JD 正文`
  - 或 `JD Link + JD 正文`

输出：

- 自动写 Notion 分析页
- 自动回 Telegram 短消息

### 7.2 不包含

- 纯链接自动抓取
- Tracker 自动进入后续分析
- Email forward
- Web intake

### 7.3 原因

因为这条范围是当前代码真正已经接近完成、且可稳定部署的部分。

## 8. 工程结论

### 8.1 这个项目现在的真实规模

这是一个：

- 五组件架构已经明确
- 文档边界已经稳定
- 部分链路真实可用
- 但还存在关键缺口的
- 单机本地工作流系统

### 8.2 当前项目最核心的收口

文档层收口在：

- 五组件模型
- `Tracker / Manual Intake -> Capture -> Analyzer -> Output`
- 当前 manual chain 支持 `JD 文本` 与 `URL + JD 文本`
- 纯链接链路未接

代码层收口在：

- `JD 文本（或 URL + JD 文本） -> Capture -> Analyzer -> Output`

没有收口到：

- `纯 URL 自动抓取`

### 8.3 现在最重要的事实

如果只按当前代码和文档说：

- 项目不是没做出来
- 但也没有完整做到“所有输入都通”
- 当前真正完成的是 JD 正文链路，不是纯链接链路
