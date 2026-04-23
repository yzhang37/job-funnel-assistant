# Job Search Assistant Narrative Document

版本：2026-04-23  
状态：基线叙事文档  
修改规则：**未经用户明确许可，不得改动本文件**

## 1. 背景与目标

### 1.1 背景

本项目要构建一个个人找工作自动化助手。核心不是“全自动海投”，而是：

1. 自动发现岗位
2. 自动抓取岗位与公司信息
3. 自动根据候选人画像进行分析
4. 自动把结果写入 Notion
5. 自动把摘要回到 Telegram，方便用户在手机上做决策

当前项目统一收口为 5 个业务组件：

1. `Tracker`
2. `Manual Intake`
3. `Capture`
4. `Analyzer`
5. `Output`

标准链路为：

- `Tracker / Manual Intake -> Capture -> Analyzer -> Output`

更精确地说：

- `(Tracker)` / `(Manual Intake)` -> `Capture (outputs bundle)` -> `Analyzer` -> `Output`

### 1.2 目标

本阶段目标不是支持所有网站、所有输入，而是先把最小可用闭环跑通，并确保：

1. 组件边界清晰
2. `job_url only` 与 `jd_text` 都能稳定进入 `Capture`
3. `Company Profile / Insights / Cache` 严格收口在 `Capture`
4. `Analyzer` 默认优先使用本机 `Codex`
5. 系统从“同步串行调用”演进到“消息驱动 + worker”
6. 所有依赖 `Computer Use` 的浏览器任务都能安全调度、窗口可回收、不互相打架

### 1.3 非目标

本阶段明确不是目标的内容：

- 自动投递
- 自动提交 job form
- 自动替用户做最终申请决策
- 多云部署 / 微服务化
- 浏览器脚本反爬优化的大规模投入
- 完整状态机 / 大而全的工作流平台

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
  - `scripts/run_tracker_live_discovery.py`
  - `scripts/list_due_trackers.py`
  - `scripts/record_tracker_discovery.py`
  - `scripts/prepare_tracker_discovery_batch.py`
- 核心代码：
  - `src/job_search_assistant/manual_flow.py`
  - `src/job_search_assistant/analyzer/*`
  - `src/job_search_assistant/capture/*`
  - `src/job_search_assistant/tracker_scheduler/*`
  - `src/job_search_assistant/runtime/*`
  - `src/job_search_assistant/integrations/*`

### 2.2 当前是中等复杂度单机工作流项目

它不是一个简单脚本，也不是大型分布式系统。

更准确地说，它是一个：

- 单机优先
- 组件清晰
- 强依赖外部 SaaS（Telegram / Notion）
- 浏览器自动化参与较多
- 分析环节由 Codex 驱动
- 正在从“同步串行执行”演进到“消息驱动 + worker”的

个人自动化工作流系统。

### 2.3 当前部署假设

当前最合理部署假设是：

- 一台本地 MacBook Pro 作为执行机
- Telegram 作为手动入口与消息出口
- Notion 作为长期分析库
- 本地 Codex CLI 作为 `Capture` / `Analyzer` 的默认执行器

## 3. 用户需求收口

### 3.1 用户的核心诉求

用户当前最明确的诉求有 5 个：

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
5. 运行时必须稳
   - `Tracker` 和 `Capture` 都会用到 `Computer Use`
   - 在同一台 Mac 上不能并行抢同一个桌面 / 同一个 Chrome
   - 浏览器执行必须是可调度、可回收、可串行保护的

### 3.2 当前明确支持的人工输入

根据当前代码，`Manual Intake` 支持的输入形态定义为：

- `job_url`
- `jd_text`
- `attachments`
- `company_name`
- `notes`

当前已经真实跑通的输入包括：

- `JD 文本`
- `JD Link + JD 文本`
- `纯 JD Link`

`Manual Intake` 的职责是：

- 只接收人工输入
- 规范化成内部请求对象
- 把请求交给 `Capture`

它不负责：

- 决定是否抓网页
- 决定是否分析
- 决定是否拒绝 URL-only

## 4. 五个业务组件

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
- live browser discovery executor
- `Tracker` 级别的浏览器窗口生命周期管理

当前收口：

**Tracker 当前已经能真实打开浏览器、收集 JD links，并在任务结束后自动清理本次新增 Chrome 窗口；但它仍然只负责 discovery，不直接进入 `Capture` / `Analyzer`。**

### 4.2 Manual Intake

职责：

- 接收人工输入
- 规范化成内部请求对象
- 把请求交给 `Capture`
- 不做抓取判断
- 不做分析判断

当前代码状态：

入口脚本：

- `scripts/process_telegram_manual_intake.py`
- `scripts/run_manual_intake_once.py`

当前收口：

**Manual Intake 只收输入，不应决定是否抓网页。**

### 4.3 Capture

职责：

- 吃 `job_url` / `jd_text` / 两者组合
- 决定是否需要打开网页抓取
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
- `jd_text -> bundle`
- `job_url only -> live browser capture -> bundle`
- `jd_text -> company profile enrichment -> bundle`
- `Company Profile / Insights / Cache` 已全部收口在 `Capture`
- `Capture` 级别的浏览器窗口生命周期管理

当前收口：

**Capture 已经是完整抓取节点：输入 `job_url only`、`jd_text`、或两者组合，都可以产出标准 bundle 并移交给 `Analyzer`。**

### 4.4 Analyzer

职责：

- 吃 `Capture` 输出
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

## 5. 运行时基础设施层（非业务组件）

五个业务组件保持不变，但运行时需要明确一层基础设施。

### 5.1 Message Queue

目标：

- 让 5 个业务组件之间不再直接同步串行调用
- 每个组件通过消息边界对接下一步

目标链路：

- `Tracker / Manual Intake -> Queue -> Capture`
- `Capture -> Queue -> Analyzer`
- `Analyzer -> Queue -> Output`

好处：

- 解耦
- 可恢复
- 可重试
- 可观测
- 不会因为 Telegram poller 同步跑完整链路而把体验拖成十几分钟

### 5.2 Browser Execution Broker

这是单机桌面资源的执行仲裁层，不是第六个业务组件。

职责：

- 把 `Computer Use` 视为单机独占资源
- 接收来自 `Tracker` 和 `Capture` 的浏览器任务
- 统一排队
- 一次只执行一个浏览器任务
- 为每个任务管理浏览器窗口生命周期：打开 -> 执行 -> 清理
- cleanup 只关闭本次任务新增窗口
- 不退出 Chrome 进程
- 不影响用户原有窗口

存在原因：

- `Tracker` 与 `Capture` 都依赖 `Computer Use`
- 在同一台 Mac 上，它们不能真正并行操作同一个桌面 / 同一个 Chrome
- 因此它们在运行时必须通过单消费者执行层串行化

结论：

**在单机单桌面模型下，`Tracker` 和 `Capture` 不应并行直接使用 `Computer Use`。**

## 6. 当前代码与文档到底收口在哪一步

### 6.1 文档收口

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

当前运行时原则：

- 5 个业务组件允许通过消息驱动解耦
- 但所有依赖 `Computer Use` 的浏览器任务必须通过单消费者执行层串行化
- 在单机单桌面模型下，`Tracker` 和 `Capture` 不应并行直接操作 Chrome

当前人工链路支持：

- `JD 文本`
- `岗位链接 + JD 文本`
- `纯 job_url`

也就是说：

**文档层现在应收口到：Manual Intake 可以把 `JD 文本`、`URL + JD 文本`、`纯 job_url` 统一交给 `Capture`。**

### 6.2 代码收口

当前代码的真实收口已经比最初完整很多。

已真实跑通的代码链路：

- `Telegram / CLI 输入 JD 文本`
- `Telegram / CLI 输入纯 job_url`
- `build_manual_capture_bundle(...)`
- `run_analysis_for_capture_bundle(...)`
- `NotionAnalysisReportClient.create_analysis_page(...)`
- `TelegramBotClient.send_message(...)`
- `run_tracker_live_discovery(...)`

代码级已打通点：

- `build_manual_capture_bundle(...)` 已支持 `jd_text` 与 `job_url`
- `process_telegram_manual_intake.py` 已支持把 `纯 job_url` 交给 `Capture`
- `job_url only -> live browser capture -> bundle` 已接入 `Capture`
- `Tracker` 已有 live browser discovery executor
- `Tracker` 与 `Capture` 都已有浏览器窗口生命周期管理

当前代码尚未完成的运行时点：

- 5 个业务组件之间的消息队列化
- `Browser Execution Broker` 作为正式单消费者 worker 的落地
- `Tracker -> Capture -> Analyzer -> Output` 的自动异步衔接

## 7. 当前已实现需求 vs 未实现需求

### 7.1 已实现需求

#### A. Telegram 手动分析最短链路

已实现：

- Telegram 收消息
- 只处理 owner 消息
- 用手动输入构建 bundle
- 调 Analyzer
- 写 Notion
- 回 Telegram

#### B. Notion 分析报告库

已实现：

- `🧠 分析报告库`
- 中文字段
- 完整分析页写入

#### C. Telegram 输出

已实现：

- 短结果
- Notion 分析页链接

#### D. Tracker discovery

已实现：

- due 逻辑
- JD link 规范化
- discovery session 数据结构
- live browser discovery

#### E. 浏览器生命周期管理

已实现：

- `Capture` 在任务前打开专用自动化窗口
- `Capture` 在任务后关闭本次新增窗口
- `Tracker` 在任务前打开专用自动化窗口
- `Tracker` 在任务后关闭本次新增窗口
- 不退出 Chrome 进程
- 不影响用户原有窗口

### 7.2 未实现需求

#### A. Tracker 到后续全自动

未实现：

- `Tracker -> 一批 JD Links -> Capture -> Analyzer -> Output`

#### B. 消息队列化执行模型

未实现：

- `Tracker / Manual Intake -> Queue -> Capture`
- `Capture -> Queue -> Analyzer`
- `Analyzer -> Queue -> Output`
- 单消费者 `Browser Execution Broker`

#### C. 优先级调度

未实现：

- `Capture > Tracker` 的浏览器资源优先级
- 带优先级的浏览器任务队列

#### D. 真正常驻部署

未实现：

- 多 worker 常驻脚本 / 守护
- 后台 job queue 的生产部署

## 8. 当前最小生产范围

如果现在只做一个真正可生产部署的 MVP，它应该是：

### 8.1 支持范围

输入：

- Telegram 手动输入：
  - `JD 正文`
  - `JD Link + JD 正文`
  - `JD Link only`

输出：

- 自动写 Notion 分析页
- 自动回 Telegram 短消息

后台能力：

- `Tracker` 可以独立做 live discovery
- `Capture` 可以独立做 live browser capture
- 两者在各自任务内都能自动回收本次新增 Chrome 窗口

### 8.2 当前不包含

- `Tracker` 自动进入后续分析
- Email forward
- Web intake
- 基于消息队列的异步 worker 调度

### 8.3 原因

因为这条范围是当前代码已经能稳定部署的部分。

下一阶段重点不是再补基础输入能力，而是把运行时从“同步串行调用”演进成：

- 组件之间消息驱动
- 浏览器任务统一入队
- 单消费者执行 `Computer Use`
- 手动任务高于后台 tracker

推荐的优先级模型：

- `P1`: `Manual Intake -> Capture(job_url only)`
- `P2`: `Tracker discovery`
- `P3`: `company name -> company profile` 等补充抓取

## 9. 工程结论

### 9.1 这个项目现在的真实规模

这是一个：

- 五组件架构已经明确
- 文档边界已经稳定
- 多条关键链路已经真实可用
- 正在进入运行时解耦阶段的
- 单机本地工作流系统

### 9.2 当前项目最核心的收口

文档层收口在：

- 五组件模型
- `Tracker / Manual Intake -> Capture -> Analyzer -> Output`
- 当前 Manual Intake 支持 `JD 文本`、`URL + JD 文本`、`纯 job_url`
- `Tracker` 与 `Capture` 都依赖 `Computer Use`
- 但依赖 `Computer Use` 的任务在未来必须统一进入单消费者执行层

代码层收口在：

- `JD 文本 / URL + JD 文本 / 纯 job_url -> Capture -> Analyzer -> Output`
- `Tracker -> live browser discovery -> canonical JD links`

没有收口到：

- 5 组件的消息队列化运行模型
- `Browser Execution Broker`
- `Tracker -> Capture -> Analyzer -> Output` 的全自动异步串联

### 9.3 现在最重要的事实

如果只按当前代码和文档说：

- 项目不是没做出来
- 当前 Manual Intake 的三种核心输入都已能进入 `Capture`
- `Tracker` 与 `Capture` 的浏览器任务都已具备窗口自动回收能力
- 当前最主要的缺口已经从“输入是否支持”转移到了“运行时如何用消息队列和单消费者模型避免 `Computer Use` 冲突”
