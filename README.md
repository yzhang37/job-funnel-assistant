# 找工作自动化助手

这个项目用来搭建一个“半自动找工作工作台”：

1. 从招聘网站收集岗位
2. 根据你的分析模板判断是否匹配
3. 把合适岗位写入 Notion
4. 用消息推送提醒你
5. 由你决定是否继续投递

## 目标

这个项目不追求“全自动海投”，而是追求：

- 更快筛掉不合适岗位
- 更稳定记录适合岗位
- 更方便统一回看和管理
- 保留人工决策权

## 建议工作流

当前推荐的主流程：

1. `Tracker` 定期访问你配置好的 job trackers
2. `Manual Intake` 也可以直接把 `job link` / `JD 文本` / 附件送进系统
3. `Capture` 抓 JD 和公司画像，并输出 bundle
4. `Analyzer` 按你的模板分析匹配度
5. `Output` 把结果写入 Notion，并回复 Telegram
6. 你确认后再决定是否投递

## 为什么这样设计

这条链路适合你的场景：

- 邮件只是提醒，不是完整数据源；真正的机会池来自 tracker / search results
- 有些网站需要网页自动化，不能只靠 API
- 你已经有现成分析模板和简历模板，适合复用
- 你希望先稳定发现新岗位，再交给后面的抓取和分析，而不是让调度层直接替你做判断
- 你不一定总在电脑前，所以手动入口必须支持手机优先、任意格式、低摩擦输入

## 入口设计

当前全局上收敛成两类入口：

### 1. Scheduled Tracker Intake

这是后台入口，职责是：

- 定期访问你配置好的 trackers
- 只发现新的 canonical JD links
- 不做 JD 抓取
- 不做公司画像
- 不做分析

当前设计前提：

- 这层真正运行时需要 `Computer Use`
- 因为要自动打开浏览器、进入搜索结果页、点主结果卡片、翻页，直到拿到足够多的新 JD links

这层的输出是：

- `new job links`

然后再交给 Capture Program。

### 2. Manual Intake

这是你主动喂数据的入口，职责是：

- 接受你随手发来的岗位信息
- 统一转换成后续 capture 可消费的请求

Manual Intake 需要支持的 payload：

- `job_url`
- `jd_text`
- `attachments`
- `company_name`
- `notes`

这层不应该因为入口不同而分叉后续流程。无论来自 Telegram、邮件还是 web form，后面都应该走同一个 capture / analyzer 链路。

## 全局节点

当前全局链路应该理解成：

- `Tracker / Manual Intake -> Capture -> Analyzer -> Output`

更精确的表述是：

- `(Tracker)` / `(Manual Intake)` -> `Capture (outputs bundle)` -> `Analyzer` -> `Output`

这里的关键点是：

- `Tracker` 只发现新的 JD links
- `Manual Intake` 只接收人工输入
- `Capture` 同时负责抓取和输出 bundle，bundle 不是单独业务节点
- `Analyzer` 才负责判断 `主攻 / 备胎 / 放弃`
- `Output` 负责把 Analyzer 的结果真正交付给你：
  - 写入 Notion 分析页
  - 回复 Telegram 短消息
  - 在 Telegram 中附上 Notion 页面链接

## Manual Intake 渠道优先级

### 1. Telegram

推荐作为主入口。

适合：

- 手机直接发 URL
- 粘贴 JD 文本
- 发截图 / PDF
- 补一句你当前最关心的问题

为什么优先：

- 手机体验最好
- 交互即时
- 支持任意混合输入
- 后续还能直接回推摘要和分析结果
- 当前 bot 应视为 owner-only 入口：只有配置好的 owner chat / owner user 发来的消息才会进入 manual intake
- 当前第一版已验证：
  - `JD 文本`
  - `岗位链接 + JD 文本`
- 当前第一版仍未接入：
  - `纯岗位链接` 直接自动抓网页再分析

### 2. Email Forward

推荐作为补充入口，而不是主入口。

适合：

- 直接转发 recruiter 邮件
- 转发 job alert
- 转发别的邮箱里突然收到的 JD

为什么保留：

- 有些内容本来就在邮件里
- 直接转发比复制粘贴更省事

### 3. Share Sheet / Shortcut

推荐作为后续增强入口。

适合：

- 手机上看到一个职位网页，直接“分享到助手”
- 比复制链接再发消息更少一步

### 4. Lightweight Web Intake Page

推荐作为通用兜底入口。

适合：

- 粘贴 URL
- 粘贴 JD 文本
- 上传截图 / PDF
- 临时补 company name / notes

它的价值在于：

- 跨设备
- 不依赖特定聊天工具
- 可以承接任意来源

## 推荐集成

### 1. 网页自动化

优先级：

- API 或 RSS，如果目标网站支持
- 浏览器自动化，如果网站必须登录或强依赖前端交互
- `Computer Use` 只用于不好脚本化、但确实值得自动化的页面流程

当前这套系统在第一阶段要明确两点：

- `Tracker` 真实执行依赖 `Computer Use`
- `Capture` 真实执行也依赖 `Computer Use`

原因：

- Tracker 需要自动打开搜索结果页、点卡片、翻页、拿 canonical JD link
- Capture 需要自动打开岗位页、展开内容、进入 company / insights 页面并收集证据

## 当前已打通的最短人工链路

当前仓库已经能跑通这条手动链路：

1. 输入一段 `JD 文本`，或输入 `岗位链接 + JD 文本`
2. `Capture` 生成 bundle
3. `Analyzer` 生成结构化结果和完整 markdown 报告
4. `Output` 自动在 `🧠 分析报告库` 中创建一条 Notion 页面
5. `Output` 自动发送一条 Telegram 短消息，并带上 Notion 页面链接

手动单次运行脚本：

```bash
python3 scripts/run_manual_intake_once.py \
  --text-file /tmp/manual_input.txt \
  --source-channel telegram \
  --provider auto \
  --write-notion \
  --send-telegram
```

如果要处理真实 Telegram bot 收到的消息：

```bash
python3 scripts/process_telegram_manual_intake.py --provider auto
```

当前 Telegram manual intake 的限制：

- 支持 `JD 文本`
- 支持 `岗位链接 + JD 文本`
- 暂不支持 `纯岗位链接` 自动触发 live browser capture
- 只处理配置好的 owner 消息：优先读取 `TELEGRAM_USER_ID`；如果没配，则退回到私聊场景下用 `TELEGRAM_CHAT_ID` 限制 chat；bot 自己的回复消息不会进入 intake

TODO:

- 当前本地开发可以先使用仓库根目录下的 `.env.local` 保存本地 secrets。
- 如果后续进入长期运行、多机部署或云环境，建议把 Telegram / Notion / OpenAI 等凭证迁移到更安全的 secrets 管理方案，例如 AWS Secrets Manager。

### 2. 岗位管理

推荐先用 Notion 作为岗位中台，记录：

- 公司
- 职位
- 链接
- 地点
- 薪资
- 发布时间
- 匹配度结论
- 分析摘要
- 当前状态

### 3. 消息提醒

当前建议优先顺序：

1. Telegram
2. 邮件
3. 其他聊天工具

原因：

- Telegram Bot 最适合程序化发送摘要和链接
- 成本低，接入简单，后续也容易扩展
- 你可以在手机上快速浏览，再决定是否回到 Notion 处理
- Email 更适合做 forward intake 和 fallback，不适合做主工作台

## 当前仓库结构

```text
.
├── AGENTS.md
├── README.md
├── PLANS.md
├── automations/
├── config/
│   └── trackers.toml
├── data/
│   ├── cache/
│   ├── processed/
│   └── raw/
├── docs/
├── examples/
├── profiles/
├── prompts/
├── scripts/
│   ├── analyze_job_fit.py
│   ├── build_company_profile_bundle.py
│   ├── build_job_capture_bundle.py
│   ├── list_due_trackers.py
│   ├── normalize_job_links.py
│   ├── prepare_tracker_discovery_batch.py
│   ├── record_tracker_discovery.py
│   ├── process_telegram_manual_intake.py
│   ├── render_company_profile.py
│   ├── render_jd_markdown.py
│   ├── run_job_funnel_analysis.py
│   ├── run_manual_intake_once.py
│   ├── send_telegram_message.py
│   └── prepare_wolai_import.py
├── src/
│   └── job_search_assistant/
│       ├── integrations/
│       ├── runtime/
│       └── tracker_scheduler/
└── templates/
```

## 当前技术选择

当前分析器采用“Python 编排 + LLM 判断”的形态：

- Python 负责：输入处理、profile stack、prompt 组装、结果校验、报告渲染
- LLM 负责：按照固定 analyzer spec 做深度判断
- 本地 dry-run 可用 `mock provider`
- 本地真实运行时，当前默认优先使用已登录的 `Codex` CLI
- `OpenAI Responses API` 仍然保留，但只是可选 fallback，不是本地单机工作流的默认前提

这样做的原因：

- 这个任务的核心不是普通规则匹配，而是需要 LLM 做综合判断
- 候选人画像需要独立插拔，不能绑死在单个 prompt 文本里
- 后续接 Notion、通知、抓取脚本时，这个 analyzer 仍然可以保持单独部件
- 对当前用户场景，更重要的是“本地电脑直接跑”，而不是额外引入一套单独 API 计费路径

当前 browser capture 的第一阶段目标非常克制：

- 先不追求完整 packet
- 先不强绑定截图数量
- 先把浏览器里提取到的结构化内容整理成一个干净的 `jd.md`
- 这层默认按跨平台设计，不先绑定 LinkedIn / Indeed / MeeBoss / YC / Glassdoor 的专属字段

这样后续不管是 `Computer Use`、其他 agent，还是手工补充内容，都能先把最核心的 JD 文本层稳定落地。

公司画像这一层现在也单独建模了：

- 岗位页里的 company profile / premium insight 不再硬塞进 `jd.md`
- 改为单独输出 `company_profile.md`
- 这层既支持岗位页内嵌摘要，也支持完整的 company insights 页面
- 如果某个平台存在“高级洞察 / premium insights”，这层允许抓更完整的表格、趋势和 alumni 信息

公司画像 enrichment 的默认顺序现在定成：

1. 先抓来源站自己的 company signals
2. 如果能解析到 LinkedIn，就默认补抓 LinkedIn company page / insights
3. 再补官网和官方 careers
4. 最后才是其他公开网页

而且这些来源不应该互相覆盖。现在 `company_profile` schema 已经支持 `source_snapshots`，用来同时保存：

- source-native signals
- linkedin signals
- official signals
- other signals

并且当前的方向是不做过早裁剪。第一程序输出的 `company_profile` 应尽量多保留：

- normalized summary fields
- metric tables
- time series
- related pages
- available signals
- missing signals
- raw sections
- source snapshots

这样 analyzer 以后拿到的不是“几条摘要”，而是一份高密度证据包。

如果 enrichment 目标是 LinkedIn，公司解析的推荐顺序是：

1. 先吃当前页面已经暴露的 LinkedIn company link
2. 再查本地缓存过的 slug / company URL
3. 已知 slug 时直接跳 `/company/<slug>/insights/`
4. 只有前面都没有时，才走 LinkedIn 搜索公司名

这样做的原因：

- 比搜索更省点击
- 比猜 slug 更稳
- 更适合后续自动化
- 同一家公司可以长期复用缓存

这条路径现在已经做过一次真实验证：

- `Jack & Jill`
- canonical page: `https://www.linkedin.com/company/jackandjillai`
- direct insights page: `https://www.linkedin.com/company/jackandjillai/insights/`

这次实测确认：

- 已知 slug 时，直接跳 `/company/<slug>/insights/` 是有效路径
- 页面能直接暴露 `Total employee count`
- 页面能直接暴露 `Employee distribution and headcount growth by function`
- 还可能出现 `Affiliated pages` 这种对产品/品牌结构有帮助的块
- 但不是每家公司都会暴露完全相同的 block，所以 openings、alumni、affiliated pages 都应该视为 optional sections

现在总 pipeline 对外已经开始收口成两个主要 capture 接口：

1. `job link -> bundle`
   - 目标产物：
     - `jd.md`
     - `job_posting.json`
     - `company_profile.md`
     - `company_profile.json`
     - `manifest.json`
     - 可选 `attachments/`
2. `company name -> bundle`
   - 目标产物：
     - `company_profile.md`
     - `company_profile.json`
     - `manifest.json`
     - 可选 `attachments/`

这里的 bundle 是目录包，不强制一开始就 zip。

这样做的好处是：

- analyzer、Telegram、Notion、缓存都围绕同一个 handoff format
- 以后接 Computer Use 或别的 agent，不需要再重新定义输出协议
- 附件数量和文件名都可以保持松散，不需要写死

在这两个公开 capture 接口之前，现在多了一层调度入口：

- `tracker url -> new job links`

这层只解决一件事：

- 定期访问你配置好的 tracker / search results URL
- 把当前结果里之前没见过的 job links 发现出来

它不负责：

- 匹配度判断
- 公司价值判断
- 排序优先级

这些都属于后面的 capture / analyzer。

当前这层已经做过真实的 LinkedIn / Indeed discovery 实验，验证到的规则是：

1. discovery 这一步只需要 JD link，不需要先抓 JD 正文或公司画像
2. 最稳的链接提取方式不是读详情正文，而是：
   - LinkedIn：点击左侧岗位卡片，从搜索结果页 URL 里读 `currentJobId`，再规范化成 `https://www.linkedin.com/jobs/view/<job_id>/`
   - Indeed：点击主结果卡片，从 URL 里读 `vjk` / `jk`，再规范化成 `https://www.indeed.com/viewjob?jk=<id>`
3. 如果当前页新的链接不够，就继续翻页；翻页属于调度器内部行为，不应该暴露成用户配置
4. 第一版 discovery 默认只消费主结果列表，不抓横向 carousel、相关推荐 rail、详情页推荐模块
5. 这一步到“拿到 canonical JD link”就结束，后面再交给 Capture Program

换句话说，现在系统的用户侧使用方式是：

- 后台：`Scheduled Tracker Intake -> new job links`
- 手动：`Manual Intake -> job_url / jd_text / attachments`
- 中间统一走：`Capture (outputs bundle) -> Analyzer`

## 模板文件

- `templates/analysis_template.md`: 粘贴你的岗位分析模板
- `templates/resume_template.md`: 粘贴你的简历模板或简历版本说明
- `templates/analysis_profile.example.json`: 第一版规则化分析器示例配置
- `templates/job_posting_example.json`: 单岗位 dry-run 示例输入

## Analyzer 关键文件

- `prompts/job_funnel_resume_fit_analyst_spec.md`: 你给定的 analyzer 原始 spec
- `config/cache_policy.toml`: 缓存策略配置，支持默认值、namespace 级别覆盖、字段级覆盖
- `profiles/default_stack.json`: 默认候选人画像 stack
- `profiles/base_candidate.md`: 长期稳定候选人画像
- `profiles/preferences/`: 兴趣方向、岗位偏好等可插拔层
- `profiles/work_auth/`: visa / sponsorship / clearance 相关可插拔层
- `profiles/patches/`: 近期简历更新或特殊补丁
- `scripts/run_job_funnel_analysis.py`: 新的主入口
- `scripts/render_jd_markdown.py`: 将 capture 得到的结构化 section 渲染成 `jd.md`
- `scripts/render_company_profile.py`: 将公司画像 capture 渲染成 `company_profile.md`，并可选写入缓存
- `scripts/build_job_capture_bundle.py`: 生成标准化 job bundle
- `scripts/build_company_profile_bundle.py`: 生成标准化 company profile bundle
- `scripts/run_manual_intake_once.py`: 运行一条 manual intake，并完成 Capture -> Analyzer -> Notion -> Telegram
- `scripts/process_telegram_manual_intake.py`: 拉取 Telegram bot updates，并按 manual intake 流程处理
- `scripts/send_telegram_message.py`: 从 `.env.local` 读取 bot 凭证，发送一条 Telegram 消息
- `scripts/list_due_trackers.py`: 列出当前应该运行的 trackers
- `scripts/normalize_job_links.py`: 把浏览器里拿到的 LinkedIn / Indeed 原始 URL 规范化成稳定 JD link
- `scripts/prepare_tracker_discovery_batch.py`: 把浏览器会话里观察到的一批原始 URL 转成“哪些是新的 JD link”
- `scripts/record_tracker_discovery.py`: 记录一次 tracker 运行发现了哪些 job links
- `examples/jd_example.md`: 示例 JD
- `examples/company_profile_example.json`: 示例公司画像输入
- `src/job_search_assistant/cache/`: 配置驱动的缓存策略与 SQLite 存储
- `src/job_search_assistant/capture/`: browser capture 的最小文本整理层
- `src/job_search_assistant/tracker_scheduler/`: tracker 配置、due 逻辑、存储抽象与 SQLite 第一版实现
- `docs/company-profile-capture.md`: company profile capture spec
- `docs/capture-bundle-spec.md`: bundle / manifest / 两个公开接口说明
- `docs/tracker-scheduler.md`: tracker-first discovery 层说明

## 当前可运行命令

1. 旧版轻量规则匹配：

```bash
python3 scripts/analyze_job_fit.py \
  --job templates/job_posting_example.json \
  --profile templates/analysis_profile.example.json \
  --pretty
```

2. 新版 Job Funnel / Resume Fit Analyst：

本地 mock dry-run：

```bash
python3 scripts/run_job_funnel_analysis.py \
  --jd-file examples/jd_example.md \
  --provider mock \
  --analysis-mode quick
```

默认用本机已登录的 Codex 真跑：

```bash
python3 scripts/run_job_funnel_analysis.py \
  --jd-file examples/jd_example.md \
  --provider auto \
  --analysis-mode full
```

如果你明确想走 OpenAI API fallback：

```bash
export OPENAI_API_KEY=...

python3 scripts/run_job_funnel_analysis.py \
  --jd-file examples/jd_example.md \
  --provider openai \
  --analysis-mode full \
  --enable-web-search \
  --markdown-output examples/reports/example_report.md \
  --json-output examples/reports/example_report.json
```

provider 选择顺序：

- `auto`：优先 `codex`，其次 `openai`，最后 `mock`
- `codex`：强制使用本机已登录的 Codex CLI
- `openai`：强制使用 `OPENAI_API_KEY`
- `mock`：只做本地假数据 dry-run

输入说明：

- 最小输入就是一个 JD 文本
- 可选再补：`--company-name`、`--job-url`、`--special-questions-file`、`--notes-file`
- 可选追加截图：重复使用 `--image`
- 可选切换候选人画像层：`--profile-stack`、`--profile-fragment`

新版输出会包含两层：

- Markdown 报告：严格按你定义的 8 个 section 输出
- JSON 原始载荷：包含 `run_metadata`、`analysis_metadata`、`report`

profile stack 的意义：

- `base_candidate`: 长期稳定候选人背景
- `preferences`: 感兴趣方向
- `work_auth`: visa / sponsorship / clearance 等身份层
- `patches`: 最近简历补丁、求职策略补丁

更新这些内容时，不需要改 analyzer spec，只需要替换或追加 profile fragment。

3. 浏览器抓取第一阶段：整理成 `jd.md`

```bash
python3 scripts/render_jd_markdown.py \
  --input examples/browser_capture_sections.example.json \
  --output examples/browser_capture_sections.example.md
```

这一步的定位：

- 输入：浏览器里已经提取到的结构化 section 文本
- 输出：一个适合后续分析、存档、复用的 `jd.md`
- 暂时不要求：
  - 完整 job packet
  - 固定数量截图
  - 平台专属字段全部齐全
- 这层的输入格式是“宽松 section 文本”，不是 LinkedIn 专属 schema

4. 浏览器抓取第二阶段：整理成 `company_profile.md`

```bash
python3 scripts/render_company_profile.py \
  --input examples/company_profile_example.json \
  --output examples/company_profile_example.md
```

可选同时写缓存：

```bash
python3 scripts/render_company_profile.py \
  --input examples/company_profile_example.json \
  --url https://www.linkedin.com/company/gleanwork/insights/?insightType=HEADCOUNT \
  --cache-db data/cache/job_search.sqlite3 \
  --print-cache-summary
```

这一步的定位：

- 输入：一个宽松的 company profile capture JSON
- 核心入口可以只靠 `source_url`
- 输出：`company_profile.md`
- 可选把公司静态资料和动态洞察分别写入缓存
- 如果来源页面存在 premium / advanced insights，这层允许承接更完整的表格和时间序列
- 同时支持 `source_snapshots`，把原站、LinkedIn、官网等来源分开保留
- 同时支持 `related_pages`、`available_signals`、`missing_signals`、`raw_sections`
- 目标是让第一程序输出给 analyzer 的 company profile 尽可能完整，而不是先缩水成摘要

5. 生成 job capture bundle：

```bash
python3 scripts/build_job_capture_bundle.py \
  --job-input examples/browser_capture_sections.example.json \
  --company-profile-input examples/company_profile_example.json \
  --output-dir data/raw/example-job-bundle
```

6. 生成 company profile bundle：

```bash
python3 scripts/build_company_profile_bundle.py \
  --input examples/company_profile_example.json \
  --output-dir data/raw/example-company-bundle
```

这两条命令当前的定位：

- 先把标准 bundle 输出 contract 固定下来
- 浏览器驱动层后续只负责把抓到的数据喂给 bundle writer
- 暂时还不是“给一个 URL 就自动抓完”的最终版本

7. 列出当前到期的 trackers：

```bash
python3 scripts/list_due_trackers.py \
  --config config/trackers.toml \
  --db data/cache/tracker_scheduler.sqlite3
```

8. 记录一次 tracker 运行结果：

```bash
python3 scripts/record_tracker_discovery.py \
  --config config/trackers.toml \
  --db data/cache/tracker_scheduler.sqlite3 \
  --tracker-id mid_level_software_engineer_golang \
  --job-url https://www.linkedin.com/jobs/view/1 \
  --job-url https://www.linkedin.com/jobs/view/2
```

这两条命令当前的定位：

- `list_due_trackers.py` 只判断“哪些 tracker 现在该跑了”
- `record_tracker_discovery.py` 只记录“这次发现了哪些 job links，哪些是新的”
- 这层只做 discovery，不做 analysis
- 真正的翻页、抓够 `target_new_jobs` 条新链接，属于后续浏览器执行层

9. 把原始 LinkedIn / Indeed URL 规范化成 JD link：

```bash
python3 scripts/normalize_job_links.py \
  --url "https://www.linkedin.com/jobs/search-results/?currentJobId=4391165384&keywords=Mid+level+software+engineer" \
  --url "https://www.linkedin.com/jobs/view/4391193012/?alternateChannel=search" \
  --url "https://www.indeed.com/jobs?q=software+engineer&l=Bellevue%2C+WA&vjk=f07957d490af8c1d"
```

这条命令当前的定位：

- 接收浏览器里实际拿到的 LinkedIn / Indeed URL
- 支持 LinkedIn `search-results?...currentJobId=<id>` 和 `/jobs/view/<id>/...`
- 支持 Indeed `search` / `viewjob` URL 里的 `jk` / `vjk`
- 输出统一的 canonical JD link
- 方便后续浏览器执行层只做点击和分页，不需要自己拼很多 URL 逻辑

10. 准备一次浏览器 discovery batch：

```bash
python3 scripts/prepare_tracker_discovery_batch.py \
  --config config/trackers.toml \
  --db data/cache/tracker_scheduler.sqlite3 \
  --tracker-id mid_level_software_engineer_linkedin \
  --raw-url "https://www.linkedin.com/jobs/search-results/?currentJobId=4391165384&keywords=Mid+level+software+engineer" \
  --raw-url "https://www.linkedin.com/jobs/view/4391193012/?alternateChannel=search"
```

这条命令当前的定位：

- 接收浏览器会话里观察到的一批原始 URL
- 规范化成 canonical JD link
- 标记哪些链接是本轮新发现的
- 输出一个 discovery batch，供后续真正的浏览器执行层或调度层消费

注意：

- 当前 Python 代码还没有直接驱动 `Computer Use`
- 真正的 `URL -> 打开浏览器 -> 点开 Premium Insights -> 抓取内容` 仍属于下一阶段浏览器驱动层
- 当前代码层已经先把“统一 schema / markdown 产物 / cache 落点”准备好了
- 当前 tracker discovery 只关注主结果列表，不处理横向 carousel、相关推荐或详情页推荐模块

但从全局设计上，已经明确：

- `Tracker` 真实执行需要 `Computer Use`
- `Capture` 真实执行也需要 `Computer Use`

未来如果这层接上浏览器驱动，推荐的 enrichment 入口顺序也已经定下来了：

- `job page company link`
- `cached company url / slug`
- `direct insights url`
- `linkedin search fallback`

而且当前已知：

- `direct insights url` 已经在真实公司页上验证过可行
- 不能把 `Total job openings` 当成必有字段
- `Total employee count` 和 `function distribution` 目前看更像高价值、高命中率块

## Cache Layer

仓库现在内置了一个轻量缓存层，目标是给后续的 capture agent 和 analyzer 复用公司级/岗位级快照数据。

设计原则：

- TTL 不写死在代码里，而是放在 `config/cache_policy.toml`
- 支持三层继承：`defaults -> profiles.<namespace> -> [[rules]] 字段级覆盖`
- 同一 namespace 下，不同字段可以有不同 freshness 策略
- 数据库存储使用 SQLite，适合本地单用户工作流

当前推荐的缓存 namespace：

- `company_insights`: 公司级 Premium insights、headcount、alumni 等
- `job_posting`: 具体岗位状态、JD 文本、相关 openings
- `company_profile_static`: 公司简介、行业、官网等变化较慢的数据
- `capture_artifact`: 截图、原始抓取产物等长期可复用材料

当前默认缓存思想：

- `job_posting` 更短，例如 `6h - 1d`
- `company_insights` 中等，例如 `14d - 30d`
- `company_profile_static` 更长，例如 `90d`
- `capture_artifact` 基本按归档处理

这不是写死逻辑，只是 `config/cache_policy.toml` 里的初始配置。后续你可以按字段继续细化，比如单独给 `total_employees`、`job_openings_total`、`notable_alumni` 配不同 TTL。

另外，后续建议单独增加一个 company resolver mapping cache，至少记录：

- `company_name`
- `linkedin_company_slug`
- `linkedin_company_url`
- `linkedin_insights_url`
- `resolved_via`
- `resolved_at`
- `confidence`

## Company Profile Capture Spec

`company_profile` 这层的设计原则：

- URL 是入口，但 schema 不绑死某个平台
- narrative sections、metric tables、time series、bridge signals 分开保存
- `company_profile_static` 与 `company_insights` 分 namespace 缓存
- 遇到 `Show Premium Insights` 一类入口时，优先进入完整 insights 页抓更结构化的数据
- 对 LinkedIn `Insights` 页要按 optional blocks 设计，不要求每家公司都出现同样的表或卡片

更完整说明见：

- [docs/company-profile-capture.md](/Users/l/Projects/找工作/docs/company-profile-capture.md)
- [docs/linkedin-company-resolution.md](/Users/l/Projects/找工作/docs/linkedin-company-resolution.md)
- [docs/capture-bundle-spec.md](/Users/l/Projects/找工作/docs/capture-bundle-spec.md)
- [docs/tracker-scheduler.md](/Users/l/Projects/找工作/docs/tracker-scheduler.md)
- [docs/intake-channels.md](/Users/l/Projects/找工作/docs/intake-channels.md)

## Tracker Scheduler

当前调度层的边界是：

1. 读取 `config/trackers.toml`
2. 按 `source_frequency` 判断哪些 trackers 到期
3. 访问 tracker 对应的 search results
4. 发现新的 job links
5. 把这些链接交给后续 capture

这里的 tracker 配置当前刻意保持很瘦：

- `id`
- `label`
- `url`
- `source_frequency`
- `target_new_jobs`
- `enabled`

其中：

- `target_new_jobs = 30` 的意思不是“抓前 30 条”
- 而是“本次尽量抓到 30 条之前没见过的新链接；如果结果到底了，就提前停止”
- 当前真实页面实验还确认了：
  - LinkedIn：点左侧结果卡片 -> 读 `currentJobId` -> 规范化成 JD link -> 必要时切到 `Page 2`
  - Indeed：点主结果卡片 -> 读 `vjk` / `jk` -> 规范化成 JD link -> 需要时继续翻页
- 第一版只抓主结果列表，不抓横向 carousel、相关推荐 rail、详情页推荐模块

数据库层也没有写死 SQLite 作为唯一选择。现在的实现是：

- 先抽象调度状态存储接口
- 默认实现 `SQLiteTrackerStateStore`
- 后续可以补 MySQL / Aurora，而不改上层 scheduler 逻辑

## 下一步

当前最重要的不是先写很多代码，而是先把以下四件事落地：

1. 把 tracker browser execution 真正接到 discovery 层，稳定拿到新的 JD links
2. 把 manual intake 的产品层定义固定下来：Telegram 主入口、Email Forward 补充入口、Share Sheet / Web Intake 作为后续增强
3. 用真实 JD 跑一轮新版 analyzer
4. 决定后续要不要把输出自动写入 Notion / 通知

这些确定后，这个部件就可以作为整个找工作工作台的核心判断引擎。
