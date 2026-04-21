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

1. 岗位来源采集
2. 结构化清洗
3. 按你的模板分析匹配度
4. 写入 Notion 数据库
5. 发送消息提醒
6. 你确认后再决定是否投递

## 为什么这样设计

这条链路适合你的场景：

- 有些网站需要网页自动化，不能只靠 API
- 你已经有现成分析模板和简历模板，适合复用
- 你希望先收到“值得看”的内容，而不是让系统直接替你投递

## 推荐集成

### 1. 网页自动化

优先级：

- API 或 RSS，如果目标网站支持
- 浏览器自动化，如果网站必须登录或强依赖前端交互
- `Computer Use` 只用于不好脚本化、但确实值得自动化的页面流程

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

## 当前仓库结构

```text
.
├── AGENTS.md
├── README.md
├── PLANS.md
├── automations/
├── config/
├── data/
│   ├── processed/
│   └── raw/
├── docs/
├── examples/
├── profiles/
├── prompts/
├── scripts/
│   ├── analyze_job_fit.py
│   ├── render_jd_markdown.py
│   ├── run_job_funnel_analysis.py
│   └── prepare_wolai_import.py
├── src/
│   └── job_search_assistant/
└── templates/
```

## 当前技术选择

当前分析器采用“Python 编排 + LLM 判断”的形态：

- Python 负责：输入处理、profile stack、prompt 组装、结果校验、报告渲染
- LLM 负责：按照固定 analyzer spec 做深度判断
- 本地 dry-run 可用 `mock provider`
- 真正调用模型时，当前实现支持 OpenAI Responses API

这样做的原因：

- 这个任务的核心不是普通规则匹配，而是需要 LLM 做综合判断
- 候选人画像需要独立插拔，不能绑死在单个 prompt 文本里
- 后续接 Notion、通知、抓取脚本时，这个 analyzer 仍然可以保持单独部件

当前 browser capture 的第一阶段目标非常克制：

- 先不追求完整 packet
- 先不强绑定截图数量
- 先把浏览器里提取到的结构化内容整理成一个干净的 `jd.md`
- 这层默认按跨平台设计，不先绑定 LinkedIn / Indeed / MeeBoss / YC / Glassdoor 的专属字段

这样后续不管是 `Computer Use`、其他 agent，还是手工补充内容，都能先把最核心的 JD 文本层稳定落地。

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
- `examples/jd_example.md`: 示例 JD
- `src/job_search_assistant/cache/`: 配置驱动的缓存策略与 SQLite 存储
- `src/job_search_assistant/capture/`: browser capture 的最小文本整理层

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

使用 OpenAI Responses API 真跑：

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

## 下一步

当前最重要的不是先写很多代码，而是先把以下三件事落地：

1. 用真实 JD 跑一轮新版 analyzer
2. 把 visa / sponsorship / 最新简历变化拆成独立 profile fragment
3. 决定后续要不要把输出自动写入 Notion / 通知

这些确定后，这个部件就可以作为整个找工作工作台的核心判断引擎。
