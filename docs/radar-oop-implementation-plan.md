# 域名雷达 OOP 实施追踪计划

> 用途：记录“可选搜索引擎 + Site 索引预筛 + Whois/运营商情报”的实施范围、完成状态和后续缺口，方便检索哪些已经做了、哪些还没做。

## 状态说明

- `[ ]` 未开始
- `[~]` 进行中
- `[√]` 已完成

## 总体目标

把当前项目从“导入 CSV 后分析线索”为主，升级为：

```text
选择搜索引擎 -> 关键词搜索 -> 候选池 -> site: 索引核验 -> 爱站权重/网站性质核验 -> Whois/IP 情报 -> 联系方式抓取 -> 合格后入正式线索库
```

导入功能保留为辅助工具，不作为主入口。

## 实施清单

### 1. 候选池数据层

- [x] 新增 `domain_candidates` 表，用于保存搜索发现但还未正式入库的域名。
- [x] 候选字段包含域名、标题、摘要、搜索引擎、关键词、来源 URL。
- [x] 候选字段包含预筛状态、淘汰原因、权重快照、`site:` 索引快照、Whois/IP 情报快照。
- [x] 候选状态固定为：`DISCOVERED`、`REJECTED`、`NEED_WEIGHT`、`NEED_SITE_INDEX`、`QUALIFIED`、`PROMOTED`。
- [x] SQLite 老库启动时能自动创建新表，不要求清库。

### 2. OOP 架构

- [x] 定义 `SearchEngineProvider`，用策略模式实现百度、Bing 搜索。
- [x] 定义 `SiteIndexProvider`，用策略模式实现百度、Bing 的 `site:{domain}` 查询。
- [x] 定义 `WeightProvider`，用于爱站授权适配器或人工补录适配器。
- [x] 定义 `WhoisIntelProvider`，用于 Chinaz Whois、RDAP 等公开 Whois 来源。
- [x] 定义 `IpIntelProvider`，用于 IP -> ASN/ISP/地区/CDN 情报。
- [x] 定义 `ProviderRegistry` / `ProviderFactory`，前端搜索引擎列表从注册表输出，不硬编码。
- [x] 定义 `CandidateRepository`，候选池读写不散落 SQLAlchemy 查询。
- [x] 定义 `RadarDiscoveryPipeline`，负责搜索、过滤、去重、写候选池。
- [x] 定义 `CandidateQualificationPipeline`，负责索引、权重、网站性质、Whois/IP 情报和合格判断。
- [x] 定义 `CandidateRule` 责任链，拆分大站过滤、索引门槛、权重门槛、网站性质门槛。

### 3. 搜索发现

- [x] 第一版支持百度和 Bing Provider。
- [x] 发现中心提供搜索引擎选择，支持单选或多选。
- [x] 搜索结果过滤广告、搜索引擎自家页面、百科/问答/电商/政府/学校/医院/银行/大公司/机构站/平台内容页。
- [x] 支持手动关键词。
- [x] 支持内置词库随机关键词。
- [x] 同域名多搜索引擎来源合并，不重复创建候选。

### 4. `site:` 索引核验

- [x] 默认可用发现来源搜索引擎查询 `site:{domain}`。
- [x] 支持配置百度/Bing 都查。
- [x] 任一引擎解析到索引量 `>= 10000` 才继续。
- [x] 验证码、异常页、无法解析数量时进入 `NEED_SITE_INDEX`。
- [x] 爱站索引字段只作为参考展示，不参与硬门槛。

### 5. 爱站权重与网站性质

- [x] 所有平台权重为 0 时淘汰。
- [x] 任一平台权重大于 0 时继续。
- [x] 网站性质非个人时淘汰。
- [x] 网站性质缺失或适配器不可用时进入 `NEED_WEIGHT`。
- [x] 不实现绕过登录、验证码、付费接口的采集。

### 6. Whois/IP/联系方式

- [x] Chinaz Whois 适配器提取注册商、DNS、注册/过期时间等公开信息。
- [x] IP 情报独立查询服务器 ASN/ISP/地区/CDN。
- [x] 国内运营商/国内云厂商加分，海外/CDN 降优先级。
- [x] Whois 注册商邮箱、abuse 邮箱、DNS 服务商联系方式标记为辅助线索，不覆盖站内站长联系方式。
- [x] 只有 `QUALIFIED` 候选允许转入正式线索库。
- [x] 转入后复用现有抓取、评分、增强分析、注册情报、历史画像和邮件跟进。

### 7. API

- [x] `GET /api/search-engines`
- [x] `POST /api/radar/discovery/start`
- [x] `GET /api/candidates`
- [x] `POST /api/candidates/{id}/site-index`
- [x] `POST /api/candidates/{id}/weight-check`
- [x] `POST /api/candidates/{id}/intel`
- [x] `POST /api/candidates/{id}/promote`
- [x] `POST /api/candidates/batch-qualify`

### 8. 前端

- [x] 发现中心加入搜索引擎选择。
- [x] 发现中心加入雷达搜索 / 随机发现入口。
- [x] 发现中心加入候选池表格。
- [x] 候选池展示状态、索引、权重、网站性质、Whois/IP 摘要、淘汰原因。
- [x] 候选池支持单条核验、批量预筛、合格候选转正式线索。
- [x] 导入/导出保留，但弱化为辅助工具。

### 9. 测试与验证

- [x] ProviderFactory 未知 id 返回明确错误。
- [x] 百度/Bing Provider 返回统一结果对象。
- [x] 全权重 0 -> `REJECTED`。
- [x] 有权重但 `site:` 索引低于 10000 -> `REJECTED`。
- [x] 有权重、个人站、`site:` 索引达标 -> `QUALIFIED`。
- [x] `site:` 查询异常 -> `NEED_SITE_INDEX`。
- [x] 爱站数据缺失 -> `NEED_WEIGHT`。
- [x] `QUALIFIED` 之外的候选不能 promote。
- [x] promote 后保留搜索来源、索引、权重、Whois/IP 快照。
- [x] 现有线索列表、批量抓取、增强分析、注册情报、历史画像、邮件触达不受影响。

### 10. Vue 3 WebUI 迁移

- [x] 新增 `frontend/` 独立前端工程。
- [x] 使用 Vue 3 + Vite + TypeScript。
- [x] 使用 Tailwind CSS 4 + daisyUI 5。
- [x] 前端 API 调用集中到 `frontend/src/api/`。
- [x] 页面拆分为雷达发现、候选池、正式线索库、任务表、线索详情、数据工具等组件。
- [x] Vite 构建产物输出到 `app/static/frontend/`。
- [x] FastAPI `/` 优先加载 Vue 构建产物，构建缺失时回退旧模板。
- [x] 保留旧 `app/templates/index.html` 和 `app/static/app.js` 作为回退，不再作为主 UI。
- [x] `npm run build` 通过。
- [x] HTTP 探活确认 `/` 返回 Vue 构建入口。

## 默认配置

```env
SEARCH_ENGINES=baidu,sogou,360,bing,toutiao,google
DEFAULT_SITE_INDEX_ENGINES=baidu,sogou,360,bing,toutiao,google
SITE_INDEX_MIN_COUNT=10000
WHOIS_INTEL_PROVIDER_MODE=chinaz,rdap
```

## 实施记录

- 2026-05-21：创建实施追踪计划。
- 2026-05-21：完成候选表、OOP Provider/Registry、候选仓储、发现流水线、预筛规则链、API 和发现中心候选池 UI 的第一版实现。
- 2026-05-21：完成 `python -m compileall app`、`node --check app/static/app.js`、FastAPI 临时库 smoke test。
- 2026-05-21：完成 Vue 3 + Vite + TypeScript + daisyUI 前端迁移，构建产物已接入 FastAPI `/`。
- 2026-05-22：补齐雷达 Provider、候选预筛、site 异常、promote 保留快照的本地单元测试；导入/导出收进数据工具入口；候选池 Whois 注册商联系方式明确标为辅助线索。
