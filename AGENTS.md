# 项目协作说明

## 项目定位

`Domain Deal Radar Python` 是一个本地运行的域名 / 老站收购线索管理后台。核心目标是把爱站、站长工具、过期域名、URL 列表、关键词种子等来源整理成线索，然后完成评分筛选、抓取联系方式、增强尽调、注册情报、历史画像、邮件触达和跟进记录。

## 技术栈

- Python 3.11+
- FastAPI + Uvicorn
- SQLite + SQLAlchemy
- Jinja2 模板 + 原生 JavaScript
- Scrapling `FetcherSession` + `BeautifulSoup` / `lxml` 做站点页面抓取与联系方式解析
- `httpx` 用于 RDAP、Bing 搜索、Wayback 等非站点爬虫类外部请求
- `tldextract` 做域名归一化与根域名提取
- Provider 插件层接入不同线索来源

## 常用命令

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
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
- `app/static/app.js`、`app/templates/index.html`、`app/static/style.css`：单页后台的前端交互、模板和样式。

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

## 爬虫扩展策略

当前已经把站点抓取底层从 `httpx.AsyncClient` 升级为 Scrapling 静态 `FetcherSession`，但没有把业务改成 Scrapling Spider。

原因：

- 当前业务抓的是候选域名首页和少量联系页，核心价值在业务入库、任务日志、评分、尽调和跟进闭环。
- 现有 `crawl_site()` 返回结构已经被多个业务服务复用，必须保持稳定。
- Scrapling 静态 Fetcher 先提供浏览器 impersonation、重试、会话和更好的后续扩展点。
- Scrapling 的 `DynamicFetcher` / `StealthyFetcher` / Spider 能力更强，但会引入浏览器运行成本，默认不应该用于所有线索。

后续扩展建议：

- 保留 `crawl_site()` 和 `PageCrawlResult` / `CrawlResult` 作为业务边界。
- 在 `app/services/crawler.py` 内部继续抽象 fetch adapter，必要时增加 `DynamicFetcher` / `StealthyFetcher`，只给明确需要 JS 或强保护的少量站点使用。
- 不要把整个项目迁移成 Scrapling Spider，除非目标变成长期、多层级、大规模站群爬取。

## 开发注意

- 修改爬虫时优先保持 `crawl_site()` 的入参、返回字段和语义稳定。
- 调整并发、超时等行为时优先通过 `app/core/config.py` 的 `CRAWLER_CONCURRENCY`、`CRAWLER_TIMEOUT_SECONDS` 配置。
- 不要默认强爬需要登录、验证码或付费接口的页面；抓取第三方站点前注意 robots、服务条款和访问频率。
- Provider 层用于导入和生成线索，抓取层用于补充线索详情；不要把两层职责混在一起。
- 提交 GitHub 时生成详细的中文 commit message。
