# Intake Channels

## Goal

把“用户怎么把岗位机会送进系统”这件事单独说清楚。

当前全局只定义两类入口：

1. `Scheduled Tracker Intake`
2. `Manual Intake`

这份文档只讨论入口，不讨论 capture / analyzer 的内部实现。

全局节点关系固定为：

- `(Tracker)` / `(Manual Intake)` -> `Capture (outputs bundle)` -> `Analyzer`

## 1. Scheduled Tracker Intake

这是后台入口。

输入来源：

- LinkedIn / Indeed 等搜索结果 tracker
- 未来可扩展到其他 job board search results

职责：

- 定期访问 tracker
- 只发现新的 canonical JD links
- 不抓 JD 正文
- 不抓公司画像
- 不做分析

当前执行前提：

- 这层需要 `Computer Use`
- 因为它要真正打开浏览器、进入搜索结果页、点击主结果卡片、翻页并拿回 canonical JD links

输出：

- `new job links`

然后交给 Capture Program。

## 2. Manual Intake

这是用户主动喂数据的入口。

设计原则：

- 手机优先
- 任意格式输入
- 低摩擦
- 不因为渠道不同而分叉后续链路

### 支持的 payload

- `job_url`
- `jd_text`
- `attachments`
- `company_name`
- `notes`

### 统一内部请求形态

无论来自哪个渠道，最终都应该落成同一种 request shape。

例如：

```json
{
  "source_channel": "telegram",
  "job_url": "https://example.com/job/123",
  "jd_text": null,
  "company_name": null,
  "attachments": [],
  "notes": "帮我重点看 visa 风险"
}
```

或者：

```json
{
  "source_channel": "email_forward",
  "job_url": null,
  "jd_text": "Senior Backend Engineer ...",
  "company_name": "ExampleCo",
  "attachments": [],
  "notes": null
}
```

## Channel Priority

### 1. Telegram

推荐作为主 manual intake 入口。

适合：

- 手机直接发链接
- 粘贴 JD 文本
- 发送截图 / PDF
- 顺手补一句本次特别关心的问题

为什么优先：

- 最适合手机
- 交互即时
- 支持混合输入
- 适合作为后续 notification / digest 的同一出口
- 当前实现应收紧为 owner-only：只有配置好的 owner chat / owner user 发来的消息才进入 manual intake

### 2. Email Forward

推荐作为补充入口。

适合：

- 转发 recruiter 邮件
- 转发 job alert
- 转发别的邮箱里突然收到的 JD

为什么保留：

- 有些岗位本来就先出现在邮件里
- 直接转发比复制粘贴更省事

### 3. Share Sheet / Shortcut

推荐作为后续增强入口。

适合：

- 手机上看到网页后直接“分享到助手”
- 比复制链接再切应用更少一步

### 4. Lightweight Web Intake Page

推荐作为通用兜底入口。

适合：

- 粘贴 URL
- 粘贴 JD 文本
- 上传截图 / PDF
- 临时补 company name / notes

为什么有价值：

- 跨设备
- 不依赖特定聊天工具
- 可以承接任何来源

## Non-Goals For Intake

入口层不应该：

- 做匹配度分析
- 判断主攻/备胎/放弃
- 自动提交申请
- 因渠道不同走不同的 capture / analyzer 分支

## Handoff

入口层之后的统一链路是：

1. `Capture (outputs bundle)`
2. `Analyzer`

也就是：

- 入口负责收材料
- Capture 负责抓取、整理证据并输出 bundle
- Analyzer 负责判断
