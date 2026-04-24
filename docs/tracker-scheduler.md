# Tracker Scheduler

## Goal

这层只解决一件事：

- 定期访问你配置好的 Job Trackers
- 把当前搜索结果里“新的 job links”发现出来

它**不负责**：

- 匹配度判断
- 排序好坏
- 公司价值分析
- 是否值得投递

这些都属于后面的 capture / analyzer。

当前执行前提：

- 这层在真实运行时需要 `Computer Use`
- 因为它要自动打开浏览器、进入搜索结果页、点击主结果卡片、翻页，并最终拿到足够多的新 canonical JD links

## Pipeline Boundary

推荐顺序：

1. `Tracker Scheduler`
2. `Capture Program`
3. `Analyzer`

也就是：

- 第一步只找链接
- 第二步只抓内容
- 第三步才做判断

## Config File

当前用：

- `config/trackers.toml`

每个 tracker 的最小字段：

- `id`
- `label`
- `url`
- `source_frequency`
- `target_new_jobs`
- `enabled`

字段含义：

- `id`: 稳定内部标识
- `label`: 给人看的名字
- `url`: 对应 tracker / search results URL
- `source_frequency`: 这个 tracker 的巡检节奏，支持 `daily` / `weekly` / `biweekly` / `monthly` / `bimonthly` / `quarterly`
- `target_new_jobs`: 本次运行希望抓到多少条新的 job links；如果来源结果不足，就抓到 source exhaust 为止
- `enabled`: 是否启用

注意：

- `target_new_jobs = 30` 的意思不是“抓前 30 条”
- 而是“尽量抓到 30 条之前没见过的新 job links”
- 翻页是抓取器内部行为，不需要放进配置文件

## Due Logic

当前 due 判断使用自然日历周期，而不是滚动 interval：

1. 从没跑过 -> `due`
2. 上次失败且超过 failure cooldown -> `due`
3. 上次成功但已经进入新的 calendar bucket -> `due`
4. 否则暂时不跑

例如：

- `daily`: 西雅图本地自然日变更后才 due
- `weekly`: ISO week 变更后才 due
- `biweekly`: 两周 bucket 变更后才 due
- `monthly`: 月份变更后才 due
- `bimonthly`: 双月 bucket 变更后才 due
- `quarterly`: 季度变更后才 due

默认调度时区是 `America/Los_Angeles`。数据库时间仍然以 UTC 存储。

## Runtime Admission Control

在 queue-driven runtime 里，“due” 不等于立刻入队。Tracker worker 会先经过 MySQL admission control：

- 同一个 tracker 同时最多只有一个 active discovery request
- 每轮最多 admit `max_admissions_per_cycle` 个 tracker
- 全局 active discovery request 数量受 `max_pending_discovery_requests` 限制
- stale active request 会按 `discovery_request_ttl_hours` 过期
- admission 排序优先照顾从未 admit 或最久未 admit 的 tracker，避免 tracker starvation
- 每次 tracker run 下游最多发出 `max_capture_requests_per_tracker_run` 个 capture request

这些配置在本地 `config/runtime.toml` 的 `[services.tracker]` 里；默认模板在 `config_templates/runtime.toml`。

## Worker-Scoped Graceful Shutdown

Tracker Worker 支持 worker-scoped `drain-current`：

- 如果当前 worker idle，它不会再 poll 新消息，直接退出
- 如果当前 worker 正在处理一个 discovery message，它会完成当前消息、记录状态、提交 offset，然后退出
- 不会 drain 全局 Kafka queue
- 不会阻止其他 Tracker worker 继续消费

控制命令：

```bash
./.venv/bin/python scripts/control_tracker_service.py --state drain-current --worker-id default
./.venv/bin/python scripts/control_tracker_service.py --state running --worker-id default
```

## Source Adapters

第一版 discovery 不是写死在 LinkedIn 里的，而是按平台适配器处理。

当前已验证：

- `linkedin`
- `indeed`

统一原则：

- 这层只输出 canonical JD link
- 不读取详情页正文做判断
- 不抓公司画像
- 不做分析

### LinkedIn

当前验证过的稳定路径：

1. 打开 `jobs/search-results` 页面
2. 点击左侧主结果列表里的岗位卡片
3. 从当前 URL 里读取 `currentJobId`
4. 规范化成 `https://www.linkedin.com/jobs/view/<job_id>/`

### Indeed

当前验证过的稳定路径：

1. 打开搜索结果页
2. 点击主结果列表里的岗位卡片
3. 从当前 URL 里读取 `vjk` / `jk`
4. 规范化成 `https://www.indeed.com/viewjob?jk=<id>`

## Discovery Scope

第一版 browser discovery 的范围故意很窄：

- 只消费主结果列表
- 只获取 JD link

明确忽略：

- 横向 carousel
- 相关推荐 rail
- 详情页里的推荐模块

原因：

- 这些区域更像补充推荐而不是主结果集
- 容易重复
- 成本高，但对 scheduler 的收益低
- 后续如果需要，可以作为 secondary source 单独支持

## Storage Boundary

这层状态不应该写死在 SQLite SQL 里。

当前实现方式是：

- 抽象出 `TrackerStateStore`
- queue-driven runtime 使用 `MySQLTrackerStateStore`
- `SQLiteTrackerStateStore` 只保留给旧 CLI / 本地 utility 路径

后续可以补：

- MySQL
- Aurora

但上层 scheduler/service 不需要改。

## Current Tables

Tracker state 会记录这些信息：

1. `tracker_runs`
   - 每次 tracker 运行的摘要
   - 包括状态、发现数量、新链接数量

2. `discovered_jobs`
   - 全局唯一 job URL
   - 用来判断什么叫“新的”

3. `tracker_job_hits`
   - 某个 tracker 命中过哪些 job URL
   - 用来保留 tracker 层面的发现历史

这里的重复命中**不是价值信号**，只是一种调度状态。

4. `tracker_discovery_requests`
   - runtime admission / active coalesce / stale expiry 状态

5. `runtime_worker_controls`
   - worker-scoped control plane，例如 Tracker `drain-current`

## CLI

当前第一版提供三个核心命令：

### 1. 列出当前到期的 trackers

```bash
python3 scripts/list_due_trackers.py
```

### 2. 记录一次 tracker 运行结果

```bash
python3 scripts/record_tracker_discovery.py \
  --tracker-id mid_level_software_engineer_golang \
  --job-url https://www.linkedin.com/jobs/view/1 \
  --job-url https://www.linkedin.com/jobs/view/2
```

这条命令只负责：

- 记录本次运行
- 记录哪些链接是新的
- 更新本地调度状态

不会自动进入分析。

### 3. 把原始 tracker URL 规范化成 JD link

```bash
python3 scripts/normalize_job_links.py \
  --url "https://www.linkedin.com/jobs/search-results/?currentJobId=4391165384&keywords=Mid+level+software+engineer" \
  --url "https://www.linkedin.com/jobs/view/4391193012/?alternateChannel=search" \
  --url "https://www.indeed.com/jobs?q=software+engineer&l=Bellevue%2C+WA&vjk=f07957d490af8c1d"
```

这条命令的作用是：

- 接收浏览器里真正能拿到的 LinkedIn / Indeed URL
- 支持 LinkedIn `search-results?...currentJobId=<id>` 和 `/jobs/view/<id>/...`
- 支持 Indeed URL 中的 `jk` / `vjk`
- 统一输出 canonical JD link
- 让浏览器执行层专注在点卡片、翻页和采集，而不是自己拼 URL

### 4. 把一批浏览器里观察到的原始 URL 准备成 discovery batch

```bash
python3 scripts/prepare_tracker_discovery_batch.py \
  --config config/trackers.toml \
  --db data/cache/tracker_scheduler.sqlite3 \
  --tracker-id mid_level_software_engineer_linkedin \
  --raw-url "https://www.linkedin.com/jobs/search-results/?currentJobId=4391165384&keywords=Mid+level+software+engineer" \
  --raw-url "https://www.linkedin.com/jobs/view/4391193012/?alternateChannel=search"
```

这条命令的作用是：

- 读取一个 tracker 配置
- 规范化一批 raw URLs
- 对比数据库里已经见过的链接
- 输出本轮哪些是新的、哪些是已有的
- 仍然不进入分析

## Validated Browser Experiments

### LinkedIn

已经用真实 tracker 做过一次 Chrome / Computer Use 实验，验证到的流程是：

1. 打开一个 LinkedIn tracker 对应的 `search-results` 页面
2. 点击左侧岗位卡片
3. 当前页面 URL 会带上 `currentJobId=<job_id>`
4. 用这个 `job_id` 规范化出 `https://www.linkedin.com/jobs/view/<job_id>/`
5. 如果第一页不够，就切到 `Page 2`
6. 重复以上动作，直到抓够 `target_new_jobs` 或结果耗尽

这次实验确认了几件事：

- discovery 这一步只需要 JD link，不需要读取右侧 JD 正文
- 对当前验证过的 tracker，第一页左侧岗位卡片已经能从页面结构里直接拿到，不需要先滚动左侧列表
- 切到 `Page 2` 后，LinkedIn 会短暂出现 skeleton loading，所以浏览器执行层要留一点等待/重试空间
- 这层只输出 JD links，后面的 JD / 公司画像 / analyzer 都是下一层的职责

### Indeed

也已经用真实 Indeed 搜索结果页做过一次实验，验证到的流程是：

1. 打开 Indeed 搜索结果页
2. 点击主列表里的 job card
3. 当前 URL 会带上 `vjk=<job_id>` 或 `jk=<job_id>`
4. 用这个 id 规范化出 `https://www.indeed.com/viewjob?jk=<job_id>`
5. 如果当前页新的链接不够，就继续翻页
6. 重复以上动作，直到抓够 `target_new_jobs` 或结果耗尽

这次实验也确认：

- 这一步仍然只需要 JD link
- 不需要读取详情页正文
- 分页属于 discovery runtime 内部行为
- 横向推荐区域不属于第一版抓取范围

## Current Limitation

当前这层已经有一轮真实的 live browser executor，可用来：

- 打开搜索结果页
- 点击主结果卡片
- 读取 `currentJobId` 或 `vjk` / `jk`
- 返回一批原始 URL
- 再由 `BrowserDiscoverySession` 规范化、去重并判断 new/existing

当前新增的约束是：

- `Tracker` 浏览器执行必须遵守“打开 -> 执行 -> 清理”
- 宿主机会先打开一个专用 Chrome 自动化窗口
- 任务结束后只关闭本次自动化新增窗口
- 不退出 Chrome 进程，不影响用户原有窗口

当前仍然存在的限制主要是：

- 如果同一个 tracker 因为大量历史已见链接而需要更深分页，后续还可以继续增强 prompt / host loop
