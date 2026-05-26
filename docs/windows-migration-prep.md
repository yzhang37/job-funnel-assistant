# Windows Migration Prep

更新时间：2026-05-26

本文记录迁移 Windows 前的前两步整理结果：

1. 冻结和盘点当前 Mac 本地状态
2. 梳理当前 git 未提交内容，给出处理建议

本文件只记录路径、类别、规模和待决策项，不记录 secret 值。

## 1. 当前仓库状态

当前仓库根目录：

```text
/Users/l/Projects/找工作
```

当前 git 状态：

- 已跟踪文件：136 个
- Task Manager 已作为独立 commit 保留：
  - `69327c5 Add local runtime task manager prototype`
- 本文档和 `PLANS.md` 的 Windows 迁移方向更新准备作为单独迁移整理提交
- 当前没有 `EXPERIMENTS.md`

项目总量约 `462M`：

| 路径 | 规模 | 分类 | Windows 迁移建议 |
| --- | ---: | --- | --- |
| `.git/` | `2.7M` | Git 历史 | 通过 git clone / branch 带走 |
| `.venv/` | `85M` | 本机 Python 虚拟环境 | 不迁，Windows 重新创建 |
| `config/` | `20K` | 本机配置，未跟踪 | 单独安全备份，再在 Windows 放回 |
| `config_templates/` | `16K` | tracked 配置模板 | 跟随 git |
| `scripts/` | `380K` | tracked 脚本 | 跟随 git |
| `src/` | `1.1M` | tracked 源码 | 跟随 git |
| `tests/` | `112K` | tracked 测试 | 跟随 git |
| `docs/` | `56K` | tracked 文档 | 跟随 git |
| `profiles/` | `32K` | tracked 用户画像模板 | 跟随 git |
| `prompts/` | `16K` | tracked 分析 prompt | 跟随 git |
| `templates/` | `16K` | tracked 模板 | 跟随 git |
| `infra/` | `20K` | tracked infra 配置 | 跟随 git，但需去 Mac 绝对路径 |
| `data/` | `373M` | runtime/cache/artifacts/logs | 分类型处理，不整体直接搬 |

## 2. 本机配置和 secrets

本机配置文件：

```text
config/trackers.toml
config/cache_policy.toml
config/runtime.toml
config/integrations.toml
```

`.env.local` 当前包含这些变量名：

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
TELEGRAM_USER_ID
OPENAI_API_KEY
NOTION_API_TOKEN
WOLAI_API_TOKEN
```

迁移建议：

- `.env.local` 不进 git
- `config/*.toml` 不进 git
- Windows 上用 `config_templates/` 初始化后，再把本机配置安全复制过去
- 后续如果从单机迁到长期多机运行，应把 secrets 迁到更安全的 secret manager

## 3. Runtime 数据盘点

`data/` 当前约 `373M`：

| 路径 | 规模/数量 | 内容 | Windows 迁移建议 |
| --- | ---: | --- | --- |
| `data/runtime/mysql/` | `270M` | 本机 MySQL 数据目录 | 不直接拷贝 data dir；用 dump/restore |
| `data/runtime/kafka/` | 很小 | Kafka 本机日志目录 | 通常不迁；Windows 初始化 topic |
| `data/runtime/browser_broker/` | 很小 | browser broker lock/preflight | 不迁；Windows 重新 preflight |
| `data/runtime_artifacts/` | `18M`, 690 个文件 | runtime capture/analyzer bundles | 如需历史结果可压缩迁移 |
| `data/runtime_artifacts/capture/` | 97 个 bundle 目录 | runtime capture 输出 | 建议保留，后续可转共享 artifact store |
| `data/raw/manual_intake/` | `1.8M`, 21 个 bundle, 135 个文件 | 早期 manual intake 输出 | 建议保留或归档 |
| `data/cache/job_search.sqlite3` | `832K`, 420 条 `cache_entries` | legacy SQLite cache | 可保留作历史 cache；主路径已是 MySQL |
| `data/cache/tracker_scheduler.sqlite3` | `28K`, 0 条 tracker run/link | legacy tracker SQLite | 可不迁或仅归档 |
| `data/logs/` | `82M` | worker/Telegram 日志 | 通常不迁；必要时归档 |
| `data/processed/wolai_import_batches.json` | `184K` | historical Wolai import batch | 已 tracked，跟随 git |
| `data/processed/telegram_manual_state.json` | `4K` | Telegram offset/state | 迁移时需谨慎，通常重新处理 owner-only offset |

## 4. Mac-only 依赖和路径

当前项目中仍有 Mac-only 或 Mac-biased 内容：

- `launchd` / `launchctl`
- `~/Library/LaunchAgents/com.yzhang.jobfunnel*.plist`
- `/Users/l/Projects/找工作/...`
- `/opt/anaconda3/...`
- `.venv/bin/python`
- 本机 Codex CLI 登录态
- 本机 Chrome / Computer Use 权限

当前发现 6 个 Mac LaunchAgent plist：

```text
/Users/l/Library/LaunchAgents/com.yzhang.jobfunnel.telegram-manual-intake.plist
/Users/l/Library/LaunchAgents/com.yzhang.jobfunnel.runtime.output.plist
/Users/l/Library/LaunchAgents/com.yzhang.jobfunnel.runtime.capture.plist
/Users/l/Library/LaunchAgents/com.yzhang.jobfunnel.runtime.manual-intake.plist
/Users/l/Library/LaunchAgents/com.yzhang.jobfunnel.runtime.analyzer.plist
/Users/l/Library/LaunchAgents/com.yzhang.jobfunnel.runtime.tracker.plist
```

`launchctl list | rg ...` 当前未显示正在加载的 job-funnel agent。

Windows 迁移建议：

- 先用 MSYS2 的 `zsh` / `oh-my-zsh` 手动 worker 命令跑通，不急着做常驻服务
- 不把 PowerShell 作为项目默认运行入口；项目脚本应尽量保持一套 POSIX/zsh 写法，让 macOS 和 Windows/MSYS2 共用同一套入口
- 后续如需常驻运行，再选择 Docker Compose、Windows Task Scheduler、Windows Service 或 WSL systemd；优先评估 Docker Compose
- browser-capable 节点需要重新做 Chrome / Computer Use preflight

## 5. Windows 运行目标

Windows 上计划支持两种运行方式。

第一种：Windows 本机 + MSYS2 zsh。

- 用户日常 shell 是 MSYS2 的 `oh-my-zsh`
- 项目命令不需要 PowerShell 版本作为第一优先级
- Python venv、git、脚本运行、手动 worker 启动都应优先按 POSIX/zsh shell 写法整理，并尽量和 macOS 使用同一套脚本
- 脚本里应优先使用相对路径、环境变量和 Python 标准库处理路径，避免硬编码 `/Users/...`、`/opt/anaconda3/...` 或 Windows 绝对路径
- 仍需注意少数 OS-owned 能力不能完全共用：`launchctl`、macOS LaunchAgents、Chrome 路径、Codex CLI 登录态、Computer Use 权限、后台服务安装方式
- 换行和可执行位需要在 git 层面保持稳定，避免同一脚本在 macOS/MSYS2 之间反复变动

第二种：未来用 Docker 按组件运行。

- `MySQL` 和 `Kafka` 优先使用容器化 runtime
- 五个业务组件可以逐步拆成独立容器：
  - `Tracker`
  - `Manual Intake`
  - `Capture`
  - `Analyzer`
  - `Output`
- `Tracker` / `Capture` 仍有浏览器和 Computer Use 约束，不应假设它们能像纯后台 worker 一样无头运行
- 多组件/多机器运行前必须先解决 shared artifact store，否则 `Capture` 生成的 bundle 可能只有本机可见
- 可选方向：共享目录、S3/MinIO，或将 bundle 内容/索引写入 MySQL

## 6. 乱码目录

发现外部目录：

```text
/Users/l/Projects/æ¾å·¥ä½
```

观察结果：

- 不是 git repository
- 目录约 `60K`
- 内容是 Kafka runtime 残留：
  - `data/runtime/kafka/kraft-combined-logs/.lock`
  - `bootstrap.checkpoint`
  - `meta.properties`
  - offset checkpoint 文件
- 目录名像是 `找工作` 的 UTF-8 字节被错误编码后生成

迁移建议：

- 标记为可疑 Kafka 残留
- 清理前先确认没有 Kafka 进程使用它
- 不应迁移到 Windows

## 7. 当前 git 未提交内容判断

Task Manager 相关内容已提交为独立 commit：

```text
69327c5 Add local runtime task manager prototype
```

该 commit 保留了两组内容。

第一组：项目纪律和 Task Manager 文档说明。

```text
AGENTS.md
README.md
TASK_MANAGER_NARR.md
```

判断：

- `AGENTS.md` 增加了操作纪律、文档纪律和 Task Manager 命令
- `README.md` 增加了本地 Task Manager 启动说明
- `TASK_MANAGER_NARR.md` 定义 Task Manager 作为 runtime control plane 的设计
- 这些内容和当前迁移整理高度相关，建议保留

第二组：Task Manager 第一版代码。

```text
scripts/run_task_manager.py
src/job_search_assistant/task_manager/
tests/test_task_manager_service.py
```

判断：

- 这是本地 runtime 管理台雏形，不是新的业务 pipeline 节点
- 当前代码能查询 MySQL runtime store、tracker due 状态、job 状态、cache、log tail、worker control
- 当前 UI/API 仍带有 Mac-first 假设，尤其是 `launchctl`
- Windows 迁移前可以保留，但需要标记为 local/Mac runtime control plane v0，而不是跨平台完成版

验证结果：

```text
.venv/bin/python -m unittest tests/test_task_manager_service.py
Ran 5 tests in 0.010s
OK

.venv/bin/python -m py_compile scripts/run_task_manager.py src/job_search_assistant/task_manager/*.py
OK
```

## 8. 第 2 步建议

Task Manager 当前内容已经作为一个独立提交保留：

```text
Add local runtime task manager prototype
```

后续处理建议：

- Task Manager 是本地 runtime control plane，不是第六个业务节点
- 第一版 Mac-first，Windows 迁移时需要替换 `launchctl` 观测层
- 不在线写配置，避免迁移前引入配置损坏风险
- Windows 本机运行命令优先面向 MSYS2 zsh，而不是 PowerShell
- Docker 化应按组件推进，但 `Tracker` / `Capture` 的浏览器约束需要单独设计

暂不建议：

- 暂不删除 Task Manager
- 暂不清理乱码 Kafka 目录
- 暂不移动 `data/`
- 暂不直接迁移 MySQL data dir

下一步建议：

1. 单独提交本文档
2. push 当前分支到 GitHub
3. 在 Windows 上通过 git clone 获取代码
4. 处理 Mac-only 路径和 service launcher
5. 做 MySQL dump / artifact archive 清单
