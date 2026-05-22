# 项目协作说明

## 项目定位

`Domain Deal Radar Python` 是一个本地运行的域名 / 老站收购线索管理后台。核心目标是把爱站、站长工具、过期域名、URL 列表、关键词种子等来源整理成线索，然后完成评分筛选、抓取联系方式、增强尽调、注册情报、历史画像、邮件触达和跟进记录。

## 技术栈

- Python 3.11+
- FastAPI + Uvicorn
- SQLite + SQLAlchemy
- Vue 3 + Vite + TypeScript + Tailwind CSS + daisyUI 作为当前主 WebUI
- Jinja2 模板 + 原生 JavaScript 保留为旧版回退界面
- Scrapling `FetcherSession` + `BeautifulSoup` / `lxml` 做站点页面抓取、搜索发现、RDAP、Wayback 和联系方式解析
- `tldextract` 做域名归一化与根域名提取
- Provider 插件层接入不同线索来源

## 常用命令

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

发布静态产物时的前端构建命令：

```powershell
cd frontend
npm install
npm run build
```

默认访问地址：

```text
http://127.0.0.1:8000
```

## 关键目录

- `app/main.py`：FastAPI 入口，集中定义线索、Provider、抓取、分析、注册情报、历史画像、邮件等接口。
- `app/models/domain_lead.py`：核心数据表模型，包含 `domain_leads`、`crawl_tasks`、`crawl_logs`、`discovery_tasks`、`email_logs`、`lead_activities`。
- `app/services/crawler.py`：当前轻量抓取核心。负责访问首页、常见联系页 / 关于页、首页发现的同域联系链接，并聚合标题和联系方式。
- `app/services/crawl_tasks.py`：批量抓取任务中心。负责创建任务、并发控制、写入抓取日志、更新线索抓取状态，并在抓取后重新评分。
- `app/services/contact_extract.py`：从 HTML 中提取邮箱、手机号、微信、QQ，并发现联系页链接和外链域名。
- `app/services/analysis.py`：增强分析。组合 DNS、SSL、轻量抓取、备案号提取、页面健康度和停放页风险判断。
- `app/services/discovery.py`：新线索发现。包含关键词种子生成、Bing 搜索结果发现、已抓页面外链反查。
- `app/services/registration.py`：注册情报 / 可买性分析，当前优先使用 RDAP。
- `app/services/history.py`：历史画像，当前接入 Internet Archive / Wayback 公开索引。
- `app/providers/`：线索来源 Provider 插件层，现有 CSV、爱站手动 CSV、站长工具 CSV、过期域名 CSV、URL 列表、关键词种子等导入。
- `frontend/`：当前主 WebUI 源码，使用 Vue 3、Vite、TypeScript、Tailwind CSS 和 daisyUI。
- `frontend/src/api/`：前端 API 封装和类型定义，避免组件里散落 `fetch` 调用。
- `frontend/src/components/`：前端页面组件，当前拆分了发现雷达、候选池、线索表格、任务表格、数据工具和详情抽屉。
- `app/static/frontend/`：`npm run build` 的产物目录，FastAPI 根路径优先返回这里的 `index.html`。
- `app/static/app.js`、`app/templates/index.html`、`app/static/style.css`：旧版单页后台文件，当前作为构建产物缺失时的回退界面。

## 当前 WebUI 事实

- 主界面已经从单个 HTML / JS 文件迁移到 `frontend/` 下的 Vue 3 工程。
- Vite 的 `base` 配置为 `/static/frontend/`，构建产物直接输出到 `app/static/frontend/`。
- `app/main.py` 的 `/` 会优先读取 `app/static/frontend/index.html`，如果该文件不存在才回退到 Jinja2 模板。
- 前端开发时可以使用 Vite dev server，并通过 `/api` 代理到 `http://127.0.0.1:8000`。
- `/api/search-engines` 会返回全部雷达搜索 Provider 和 `enabled` 默认状态；当前默认启用 `360,toutiao`，百度、搜狗、Bing、谷歌仍可手动勾选，但经常触发验证码或安全验证。
- 本地开发默认使用热重载服务；修改 UI 后不要默认运行 `npm run build`，只有发布静态产物或专门验证生产构建时才执行。

## 当前爬虫业务事实

- 当前抓取不是通用 spider 框架，而是服务于域名线索业务的轻量定向抓取。
- `crawl_site(domain)` 是重要稳定接口，批量抓取、增强分析、搜索发现自动抓取、外链发现都依赖它。
- 底层页面获取已升级为 Scrapling `FetcherSession`，默认使用静态 Fetcher、`chrome` impersonation、`safe` redirect、1 次重试。
- 抓取策略先尝试 `https://domain`，再尝试 `http://domain`。
- 首页成功后，会访问固定联系 / 关于路径，例如 `/contact`、`/about`、`/lianxi`、`/contact.html` 等。
- 首页还会用中文和英文关键词发现同域联系页链接。
- 单站内联系页抓取是串行的，批量站点层面通过 `asyncio.Semaphore` 控制并发，避免单个站点请求过猛。
- 当前抓取目标是标题、状态码、最终 URL、邮箱、手机号、微信、QQ、页面级日志；结果会写回 `domain_leads`、`crawl_tasks`、`crawl_logs` 并触发重新评分。
- 当前逻辑不处理登录、验证码、付费接口、强反爬页面，也不应该默认绕过这些限制。
- 雷达发现遇到搜索引擎验证码 / 安全验证时，会把该 Provider 本轮剩余关键词跳过，只返回一条聚合提示，并继续尝试其他搜索引擎。

## Scrapling 抓取扩展策略

当前已经把爬虫类外部请求统一到 Scrapling 静态 `FetcherSession`，但没有把业务改成 Scrapling Spider。

原因：

- 当前业务抓的是候选域名首页和少量联系页，核心价值在业务入库、任务日志、评分、尽调和跟进闭环。
- 现有 `crawl_site()` 返回结构已经被多个业务服务复用，必须保持稳定。
- Scrapling 静态 `Fetcher` / `FetcherSession` 适合快速 HTTP 请求、无需 JS 的页面、保持 cookie / session、统一 impersonation、超时、重试、代理等配置。
- `DynamicFetcher` 适合需要浏览器自动化、JS 渲染、等待 selector、滚动 / 点击等 Playwright 操作的页面；它有三种主要形态：默认 Playwright Chromium、`real_chrome=True` 使用本机 Google Chrome、`cdp_url` 连接远程 Chrome DevTools Protocol 浏览器。
- `DynamicFetcher` / `DynamicSession` 支持 `network_idle`、`wait_selector`、`page_setup`、`page_action`、`disable_resources`、`blocked_domains` 和 `capture_xhr`；对于百度这类可能通过前端或异步接口返回结果的页面，优先考虑用 `capture_xhr` 找真实接口，再决定是否保留浏览器渲染。
- `StealthyFetcher` / `StealthySession` 是更重的反检测浏览器层，适合明确遇到反爬、浏览器指纹检测、Cloudflare 类挑战或普通 `DynamicFetcher` 不稳定时使用；可用 `real_chrome`、`cdp_url`、`user_data_dir`、`locale`、`timezone_id`、`block_webrtc`、`hide_canvas`、`solve_cloudflare` 等能力，但不应作为默认抓取层。
- Scrapling Spider 适合长期、多层级、大规模抓取；它提供并发、调度、请求去重、checkpoint 续跑、response cache、多 session 路由、blocked request 检测和 retry。当前线索系统不是站群 spider，暂不默认迁移。
- 官方文档参考：`https://scrapling.readthedocs.io/en/latest/fetching/static.html`、`https://scrapling.readthedocs.io/en/latest/fetching/dynamic.html`、`https://scrapling.readthedocs.io/en/latest/fetching/stealthy.html`、`https://scrapling.readthedocs.io/en/latest/spiders/architecture.html`。

后续扩展建议：

- 保留 `crawl_site()` 和 `PageCrawlResult` / `CrawlResult` 作为业务边界。
- 在 `app/services/crawler.py` 或独立 fetch adapter 内部做分层：默认 `FetcherSession`；遇到百度、强 JS、搜索页异步接口或静态请求失败时升级到 `DynamicFetcher`；明确反检测时再升级到 `StealthyFetcher`；需要复用已登录 / 已人工验证浏览器时使用 `cdp_url` 连接外部 Chrome。
- 对百度搜索 / site 查询，后续优先做一个小型实验入口：先用 `DynamicFetcher(real_chrome=True, network_idle=True, wait_selector=...)` 验证 DOM 是否可得，再用 `capture_xhr` 记录异步请求；如果百度仍触发验证，不要默认绕过，标记为 `ERROR` 并保留错误原因。
- 不要把整个项目迁移成 Scrapling Spider，除非目标变成长期、多层级、大规模站群爬取。

## 开发注意

- 修改爬虫时优先保持 `crawl_site()` 的入参、返回字段和语义稳定。
- 调整并发、超时等行为时优先通过 `app/core/config.py` 的 `CRAWLER_CONCURRENCY`、`CRAWLER_TIMEOUT_SECONDS` 配置。
- 不要默认强爬需要登录、验证码或付费接口的页面；抓取第三方站点前注意 robots、服务条款和访问频率。
- Provider 层用于导入和生成线索，抓取层用于补充线索详情；不要把两层职责混在一起。
- 修改代码后不要保留旧逻辑或旧 UI 分支，避免新旧路径并存导致行为错乱。
- 当前项目本地服务默认热重载；修改代码后不要默认重启服务。
- 前端改动后不要默认构建静态产物；只有用户要求、发布静态产物或排查构建问题时才运行 `npm run build`。
- 提交 GitHub 时生成详细的中文 commit message。
