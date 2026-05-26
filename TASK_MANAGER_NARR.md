# Task Manager NARR

## 1. 目标

Task Manager 是 Job Funnel Runtime 的本地管理台。

它不是新的业务 pipeline 节点，而是运行时 control plane：

- 查看 7 部件运行状态
- 查看 Tracker / Capture / Analyzer / Output 队列和历史
- 管理 Tracker 配置与优先级
- 管理 worker pause / resume / drain-current
- 查看基础指标、错误、日志
- 查看和 invalidate Capture cache
- 后续支持在线编辑 config，并保存到本地配置或 Parameter Store

第一阶段推荐实现成网页端：

- 本机 `localhost` 访问
- 无额外桌面客户端打包成本
- 后续可以用 Tailscale / 内网访问
- 比原生客户端更适合管理多机运行时

## 2. 系统边界

Task Manager 的稳定链路是：

```text
Browser UI -> Task Manager API -> MySQL Control Plane -> Workers / Kafka / Local Config
```

关键原则：

- `MySQL` 是可查询、可编辑、可审计的运行时状态真相
- `Kafka` 只负责异步事件传递，不作为 UI 可重排队列的唯一真相
- Worker 应周期性写 heartbeat、当前任务、错误和指标
- UI 的重排、暂停、恢复、invalidate 等操作写入 MySQL control plane
- Worker 根据 control plane 决定是否接新任务、是否 drain-current、是否重试

## 3. 核心页面

### 3.1 Overview

展示：

- 5 个业务 worker 是否存活
- MySQL / Kafka 是否可达
- 当前 backlog 总量
- 最近错误
- 当前 browser lane 是否被占用
- 每个 worker 的最后 heartbeat / PID / node_id / worker_id

### 3.2 Tracker Manager

必须支持：

- 查看所有 tracker list
- 查看 enabled / disabled
- 查看 frequency：`daily` / `weekly` / `biweekly` / `monthly` / `bimonthly` / `quarterly`
- 查看上次运行时间、下次 due 估算、成功次数、失败次数、新链接数量
- 查看正在运行的 tracker
- 查看当前 progress：已发现多少 / target_new_jobs
- 查看最近抓到的 links
- 查看 logs / errors
- 手动调整 priority
- 手动 run now
- enable / disable tracker
- 修改 URL / frequency / target_new_jobs

第一阶段代码范围：

- 读取 tracker config
- 显示 due / history / active discovery request
- 显示 tracker_runs 聚合
- 提供 worker-scoped `drain-current` / `running` 控制

第二阶段再做：

- UI 编辑 tracker config
- run now
- priority 持久化
- tracker config diff / rollback

### 3.3 Capture Queue

必须支持：

- 查看 capture queue / history
- 查看 queued / running / succeeded / failed
- 查看 job_url、company_name、bundle_dir、error
- 手动调整 queued 任务 priority
- move to front
- retry failed
- pause capture worker：不接新任务，in-flight 继续跑完
- resume capture worker

第一阶段代码范围：

- 显示 `capture_jobs`
- 显示 status 聚合
- 显示最近 failed jobs

### 3.4 Analyzer Queue

必须支持：

- 查看 analysis queue / history
- 查看 bundle_dir、decision、fit_score、error
- retry failed
- pause / resume analyzer worker
- 调整 queued priority

第一阶段代码范围：

- 显示 `analysis_jobs`
- 显示 status 聚合
- 显示最近 failed jobs

### 3.5 Output Queue

必须支持：

- 查看 Notion / Telegram output job
- 查看 notion_page_url
- 查看发送失败原因
- retry failed

第一阶段代码范围：

- 显示 `output_jobs`
- 显示 status 聚合

### 3.6 Metrics

需要指标：

- 每个服务内存 / CPU / PID
- 每个服务处理速率
- 每个服务失败率
- Kafka backlog 或 MySQL task backlog
- tracker 成功/失败/新链接数量
- tracker fairness：哪些跑得更多，哪些更少
- Capture cache hit rate
- Computer Use 节省估算

第一阶段代码范围：

- MySQL 里的 job 状态聚合
- tracker_runs 聚合
- cache namespace 聚合
- browser lease 当前占用情况

第二阶段再加：

- worker heartbeat table
- per-worker memory / CPU sampler
- cache hit / miss event table
- processing rate time-series

### 3.7 Cache Manager

必须支持：

- 查看 `job_posting`
- 查看 `company_profile_static`
- 查看 `company_insights`
- 查看 source_platform / observed_at / fresh_until / stale_until
- 查看 TTL 状态：fresh / stale / expired
- invalidate 单条 cache
- 按 company / namespace 批量 invalidate
- invalidate 后可选 enqueue refresh

第一阶段代码范围：

- 查询 `capture_cache_entries`
- 按 namespace 聚合
- 提供 invalidate endpoint：删除单条 cache entry

### 3.8 Config Manager

长期目标：

- 在线编辑 runtime config
- 在线编辑 tracker config
- 在线编辑 cache policy
- 保存到本地 `config/*.toml`
- 后续支持保存到 AWS Parameter Store
- 每次保存生成 version、diff、updated_by、updated_at
- 支持 rollback
- 保存后显示需要重启哪些组件
- 支持一键 restart 某个 launchd worker

第一阶段代码范围：

- 只读展示 config 路径与 tracker config 解析结果
- 不在线写配置，避免一开始引入配置损坏风险

## 4. Control Plane 数据模型

已经具备：

- `tracker_discovery_requests`
- `runtime_worker_controls`
- `tracker_runs`
- `capture_jobs`
- `analysis_jobs`
- `output_jobs`
- `capture_cache_entries`
- `browser_broker_leases`

需要新增但不急于第一阶段全部实现：

- `runtime_worker_heartbeats`
- `runtime_task_priorities`
- `runtime_task_audit_log`
- `runtime_config_versions`
- `runtime_cache_events`
- `runtime_metrics_samples`

## 5. Worker 控制语义

所有 worker 控制必须 worker-scoped。

支持状态：

- `running`
- `paused`
- `drain-current`
- `stopped`

语义：

- `paused`: worker 不接新任务，但进程仍活着
- `drain-current`: 当前 in-flight 完成后退出，不接新任务
- `stopped`: 空闲时退出，后续由 launchd 是否拉起另行决定
- 禁止 `drain-queue`
- 禁止全局 drain Kafka queue

第一阶段已经有 Tracker 的 `drain-current` 控制。

后续 Capture / Analyzer / Output 应统一接入同一张 `runtime_worker_controls`。

## 6. 第一阶段实现范围

第一版 Task Manager 应该做到：

- `scripts/run_task_manager.py`
- 本地 HTTP server，不引入额外 web 框架依赖
- `GET /`
- `GET /api/overview`
- `GET /api/trackers`
- `GET /api/jobs/capture`
- `GET /api/jobs/analyzer`
- `GET /api/jobs/output`
- `GET /api/cache`
- `POST /api/workers/tracker/control`
- `POST /api/cache/invalidate`

第一版 UI 可以朴素，但必须可用。

## 7. 后续实现顺序

建议阶段：

1. 只读 Dashboard + 基础控制 API
2. Worker heartbeat + memory / CPU / rate
3. Capture / Analyzer / Output pause / resume / retry
4. Tracker config CRUD + local TOML save
5. Config version / diff / rollback
6. Cache hit/miss metrics + Computer Use saving estimate
7. Parameter Store provider
8. 多机节点视图

## 8. 非目标

第一阶段不做：

- 公开公网访问
- 多用户权限系统
- 复杂前端框架
- 强杀正在跑的 Computer Use 任务
- 任意删除 Kafka topic 中的消息
- 自动提交岗位申请

## 9. Definition Of Done

一个 Task Manager 版本完成必须满足：

- API 能启动
- 首页能打开
- 至少能显示 tracker / capture / analyzer / output / cache 状态
- 控制 API 有单元测试
- predeploy checks 通过
- README / AGENTS.md 有启动命令
- 不破坏现有 runtime workers
