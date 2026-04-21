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
- `url`: 对应 LinkedIn tracker / search results URL
- `source_frequency`: 这个 tracker 的原始巡检节奏，目前支持 `daily` / `weekly`
- `target_new_jobs`: 本次运行希望抓到多少条新的 job links；如果 LinkedIn 结果不足，就抓到 source exhaust 为止
- `enabled`: 是否启用

注意：

- `target_new_jobs = 30` 的意思不是“抓前 30 条”
- 而是“尽量抓到 30 条之前没见过的新 job links”
- 翻页是抓取器内部行为，不需要放进配置文件

## Due Logic

当前第一版 due 判断很简单：

1. 从没跑过 -> `due`
2. 上次失败 -> `due`
3. 上次成功且超过频率窗口 -> `due`
4. 否则暂时不跑

例如：

- `daily`: 距离上次成功 >= 1 day
- `weekly`: 距离上次成功 >= 7 days

## Storage Boundary

这层状态不应该写死在 SQLite SQL 里。

当前实现方式是：

- 抽象出 `TrackerStateStore`
- 默认只实现 `SQLiteTrackerStateStore`

后续可以补：

- MySQL
- Aurora

但上层 scheduler/service 不需要改。

## Current Tables

SQLite 第一版会记录三类信息：

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

## CLI

当前第一版提供两个命令：

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

### 3. 把原始 LinkedIn URL 规范化成 JD link

```bash
python3 scripts/normalize_linkedin_job_links.py \
  --url "https://www.linkedin.com/jobs/search-results/?currentJobId=4391165384&keywords=Mid+level+software+engineer" \
  --url "https://www.linkedin.com/jobs/view/4391193012/?alternateChannel=search"
```

这条命令的作用是：

- 接收浏览器里真正能拿到的 LinkedIn URL
- 支持 `search-results?...currentJobId=<id>` 和 `/jobs/view/<id>/...`
- 统一输出 canonical JD link
- 让浏览器执行层专注在点卡片、翻页和采集，而不是自己拼 URL

## Validated LinkedIn Browser Experiment

这次已经用真实 tracker 做过一次 Chrome / Computer Use 实验，验证到的流程是：

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

## Current Limitation

当前这层还没有把上面的浏览器实验路径真正接进自动执行。

也就是说：

- 已经有 `trackers.toml`
- 已经有 due 判断
- 已经有状态存储
- 已经有“记录发现到新链接”的接口
- 已经有把原始 LinkedIn URL 规范化成 canonical JD link 的工具层

但真正的：

- 打开 LinkedIn search results
- 点击结果卡片
- 读取 `currentJobId`
- 一路翻页直到抓够 `target_new_jobs`

仍然需要后续的浏览器执行层来接。
