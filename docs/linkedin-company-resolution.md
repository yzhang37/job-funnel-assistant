# LinkedIn Company Resolution Strategy

## Goal

当岗位最初来自：

- LinkedIn job page
- Indeed
- MeeBoss
- YC / Wellfound
- 其他 job board

后续如果需要补公司画像，优先判断是否值得跳到 LinkedIn company page / insights page 做 enrichment。

注意：

- LinkedIn enrichment 是默认高优先级补充源
- 但它不应该覆盖掉来源站自己已经暴露的公司洞察
- 正确做法是保留 `source-native signals + linkedin signals + official signals`
- 并且在能抓到时，尽量保留完整 blocks、related pages、available/missing signals，而不是只摘几条摘要

## Core Principle

不要把“搜索公司名”当默认第一步。

更稳的顺序是：

1. 当前页面已经暴露的 canonical company link
2. 本地缓存过的 company slug / company URL
3. 已知 slug 后直接拼 LinkedIn insights URL
4. 只有前面都没有时，才走 LinkedIn 搜索公司名

## Recommended Resolution Order

### 1. Canonical company link from current page

最优先来源：

- job page 里的公司链接
- 招聘页页头、公司卡片、logo 链接
- 页面上已经暴露的 `/company/<slug>/...` 路径

原因：

- 这是页面自己给出的 canonical path
- 比“猜 slug”更稳
- 比“搜索公司名”更省点击
- 更适合自动化

## 2. Cached mapping

如果之前已经解析过同一家公司，优先复用缓存：

- `company_name -> linkedin_company_slug`
- `company_name -> linkedin_company_url`
- `company_name -> linkedin_insights_url`

推荐额外缓存：

- `resolved_from`
- `resolved_at`
- `confidence`

这样同一家公司后续不需要重复搜索。

## 3. Direct insights URL

如果已经知道 LinkedIn company slug，例如：

- `gleanwork`

那么优先直接尝试：

- `https://www.linkedin.com/company/gleanwork/insights/`

必要时再补查询参数，例如：

- `?insightType=HEADCOUNT`

这是最适合 capture agent 的路径，因为：

- 点击最少
- 路径稳定
- 容易缓存
- 能直接进入 richer company profile source

2026-04-21 的真实页面验证：

- `https://www.linkedin.com/company/jackandjillai/insights/` 可以直接访问
- 页面直接暴露了：
  - `Total employee count`
  - `Employee distribution and headcount growth by function`
  - `Affiliated pages`

这说明 direct insights URL 不只是设计假设，而是已经在真实公司页面上跑通。

## 4. LinkedIn search fallback

只有在以下情况才走搜索：

- 当前页面没有 company canonical URL
- 本地没有缓存
- 无法可靠推断 slug

搜索的价值在于：

- 能处理重名公司
- 能处理品牌名和 slug 不一致
- 能处理 holding entity / stealth / subsidiary 这种情况

但缺点也明显：

- 鼠标点击更多
- 页面歧义更多
- 自动化不稳定性更高

所以搜索应该是 fallback，不应该是默认主路径。

另外要注意：

- 即便 direct insights URL 可达，不同公司暴露的 block 也不完全一样
- 不应该要求每家公司都有 `Total job openings`
- 更合理的做法是先抓高价值基础块，再按页面可见情况追加 optional blocks

## Why This Matters

这条顺序本质上是：

- 减少浏览器操作
- 提高解析准确率
- 降低 slug 猜错风险
- 为后续缓存铺路

如果后面 company profile capture 主要依赖 LinkedIn enrichment，那么“company slug 解析”本身就应该是一个可缓存步骤，而不是每次都人工重新找。

## Suggested Cache Fields

建议未来单独留一个 resolver mapping：

- `company_name`
- `linkedin_company_slug`
- `linkedin_company_url`
- `linkedin_insights_url`
- `resolved_from_url`
- `resolved_via`
- `resolved_at`
- `confidence`

`resolved_via` 可选值示例：

- `job_page_company_link`
- `cached_mapping`
- `direct_slug`
- `linkedin_search`

## Relationship To Company Profile Capture

这份策略不等于 company profile schema。

它是 company profile capture 之前的一步：

1. capture source-native company signals if the current job board exposes them
2. resolve company
3. jump to richer LinkedIn source if available
4. capture `company_profile`
5. preserve source attribution in `source_snapshots`
6. cache profile and mapping

## Current Boundary

当前仓库还没有把这条 resolver 直接写成浏览器自动化代码。

现在已经明确的是：

- 文档策略
- 优先级顺序
- 后续缓存方向

等我们测试完更多真实页面，再决定是否把它实装成：

- `resolve_linkedin_company_url(url_or_company_name)`
- 或更通用的 enrichment resolver。
