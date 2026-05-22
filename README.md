# Domain Deal Radar Python

本项目是一个本地运行的域名 / 老站收购管理后台，适合从爱站、站长工具等渠道整理候选域名后，做线索导入、评分筛选、批量抓取联系方式、跟进状态、成交 / 放弃记录。

技术栈：

- Python 3.11+
- FastAPI
- SQLite
- SQLAlchemy
- Jinja2 + 原生 JavaScript
- Scrapling FetcherSession + BeautifulSoup / lxml（站点抓取、搜索发现、RDAP / Wayback 外部请求与解析）
- Provider 数据源插件层
- 批量抓取任务中心

## 功能

- 导入爱站 CSV / 站长工具 CSV / 通用 CSV
- 手动输入单个或多个域名 / URL，直接新增线索
- Provider 插件化数据源接入
- 自动评分、风险标记、建议报价
- 表格筛选：关键词、跟进状态、抓取状态、风险、最低评分
- 一键生成 / 复制联系话术
- 跟进状态管理
- 成交价、转售价、放弃原因记录
- JSON 备份 / 恢复
- CSV 导出
- 单条线索抓取
- 批量抓取当前筛选线索
- 抓取失败重试
- 抓取任务记录
- 抓取日志查看
- 自动抓取首页 + 常见联系页 / 关于页
- 自动提取邮箱、手机号、微信、QQ
- 抓取后自动重新评分

## 快速开始

```bash
cd domain-deal-radar-python
python -m venv .venv
```

macOS / Linux：

```bash
source .venv/bin/activate
```

Windows PowerShell：

```powershell
.venv\Scripts\Activate.ps1
```

安装依赖：

```bash
pip install -r requirements.txt
```

启动：

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

浏览器打开：

```text
http://127.0.0.1:8000
```

## 手动新增域名

除了导入 CSV，也可以在页面点击「手动新增域名」，直接输入单个或多个域名 / URL。支持：

```text
example.com
https://www.demo.cn/contact
aixuexi.com, kaoyan123.cn
```

系统会自动规范化为根域名、去重、评分，并记录来源为 `manual_input`。可选择新增后立即执行联系方式抓取或增强分析。

接口：

```text
POST /api/leads/manual
```

请求示例：

```json
{
  "domains": "example.com\nhttps://www.demo.cn/contact",
  "title": "",
  "remark": "手动录入",
  "auto_crawl": true,
  "auto_analyze": false
}
```

## CSV 格式

可以使用英文表头：

```csv
domain,title,baiduPcWeight,baiduMobileWeight,indexedCount,icpType,lastUpdate,remark
example.com,考研资料网,2,2,3500,个人,2023-01-01,长期未更新
```

也兼容部分中文表头：

```csv
域名,标题,PC权重,移动权重,收录量,备案类型,最近更新,备注
example.com,考研资料网,2,2,3500,个人,2023-01-01,长期未更新
```

## 数据源 Provider 插件层

`app/providers/` 用于统一接入各种数据源。当前内置：

| Provider ID | 名称 | 类型 | 用途 |
|---|---|---|---|
| `generic_csv` | 通用 CSV | 文件导入 | 导入你自己整理的 CSV |
| `aizhan_manual_csv` | 爱站手动 CSV | 文件导入 | 导入爱站查询后整理/导出的数据 |
| `chinaz_manual_csv` | 站长工具手动 CSV | 文件导入 | 导入站长工具整理/导出的数据 |

后端接口：

```text
GET  /api/providers
POST /api/providers/{provider_id}/preview
POST /api/providers/{provider_id}/import
POST /api/leads/manual
```

新增 Provider 的最小写法：

```python
from app.providers.base import DataSourceProvider, ProviderMeta, SourceRecord

class MyProvider(DataSourceProvider):
    meta = ProviderMeta(
        provider_id="my_provider",
        name="我的数据源",
        kind="file",
        description="说明",
        accepted_extensions=[".csv"],
    )

    def parse_file(self, content: bytes, *, filename: str = "") -> list[SourceRecord]:
        return [
            SourceRecord(
                domain="example.com",
                title="示例站点",
                source_provider=self.meta.provider_id,
            )
        ]
```

然后在 `app/providers/registry.py` 注册即可。

## 批量抓取任务中心

本版本新增了批量抓取任务中心。页面上可以：

- 批量抓取当前筛选结果
- 设置本次最多抓取数量
- 重试抓取失败线索
- 查看最近抓取任务
- 在线索详情里查看抓取日志

后端接口：

```text
POST /api/leads/{lead_id}/crawl
POST /api/crawl/batch
POST /api/crawl/retry-failed
GET  /api/crawl/tasks
GET  /api/leads/{lead_id}/crawl/logs
```

抓取会访问：

```text
首页
/contact
/contact-us
/about
/about-us
/lianxi
/lianxiwomen
/about.html
/contact.html
/aboutus.html
/contactus.html
```

同时也会从首页自动发现包含“联系我们 / 关于我们 / 商务合作 / 广告合作 / contact / about”等关键词的同域链接。

抓取结果会保存到：

```text
crawl_tasks  # 抓取任务
crawl_logs   # 页面抓取日志
domain_leads # 汇总联系方式、状态码、最终 URL、抓取状态
```

## 状态说明

跟进状态：

| 状态 | 含义 |
|---|---|
| NEW | 新线索 |
| CHECKED | 已检查 |
| CONTACTED | 已联系 |
| REPLIED | 已回复 |
| NEGOTIATING | 谈价中 |
| BOUGHT | 已买入 |
| RESOLD | 已转卖 |
| GIVE_UP | 已放弃 |

抓取状态：

| 状态 | 含义 |
|---|---|
| PENDING | 待抓取 |
| RUNNING | 抓取中 |
| SUCCESS | 抓取成功 |
| FAILED | 抓取失败 |

## 配置

`.env` 可配置：

```text
APP_NAME=Domain Deal Radar
DATABASE_URL=sqlite:///./data/radar.db
CRAWLER_CONCURRENCY=5
CRAWLER_TIMEOUT_SECONDS=8
```

建议刚开始把 `CRAWLER_CONCURRENCY` 设为 3～5，不要一上来高并发。

## 后续扩展建议

下一步可以继续加：

- ICP 备案 Provider
- Whois Provider
- 百度 site 收录检测 Provider
- 历史快照 Provider
- 反链 Provider
- 代理池
- 定时任务
- 后台异步队列：Celery / RQ / Dramatiq
- 联系人 CRM 表
- 报价历史表
- 线索评分变化历史表

## 注意

- 不建议强爬需要登录、验证码或付费接口的页面。
- 抓取第三方站点前，应遵守对方 robots、服务条款和访问频率限制。
- 交易前仍需人工检查历史内容、备案、反链、商标和收录真实性。

> 说明：当前爱站 Provider 是“手动导入插件”，不包含绕过登录、验证码或付费接口的逻辑。后续如果你有授权接口，可以在同一个 Provider 下新增远程拉取方法。

## V0.4：增强分析 + 自动发现新线索

本版本同时补齐两个自动化方向：

### 1. 已导入域名增强分析

新增接口：

```text
POST /api/leads/{lead_id}/analyze
POST /api/analysis/batch
```

增强分析会对已导入线索执行：

- DNS 解析检查
- 解析 IP 记录
- SSL 证书状态、过期时间、剩余天数
- 首页/联系页轻量抓取
- ICP 备案号提取
- 公安备案号提取
- 页面健康度判断：ACTIVE、PARKED、FORBIDDEN、NOT_FOUND、SERVER_ERROR、CROSS_DOMAIN_REDIRECT 等
- 停放页/出售页/乱码/跨域跳转等增强风险标记

新增字段：

```text
analysis_status
analysis_error
dns_resolved
resolved_ips
ssl_status
ssl_expires_at
ssl_days_left
icp_number
public_security_record
site_health
enhanced_risk_flags
last_analyzed_at
discovered_from
```

### 2. 自动发现新线索

新增接口：

```text
POST /api/discovery/keywords
POST /api/discovery/search
POST /api/discovery/external-links
GET  /api/discovery/tasks
```

已支持三种发现方式：

#### 关键词种子生成

输入中文、英文或拼音关键词，例如：

```text
小说
kaoyan
tiku
xuexi
aiagent
```

中文关键词会自动转成拼音后再生成候选，例如：

```text
小说 → xiaoshuo
```

系统会自动组合：

```text
kaoyan.com
kaoyan.cn
kaoyan.net
kaoyan.ai
aikaoyan.com
mykaoyan.com
getkaoyan.com
...
```

注意：当前不自动判断域名是否可注册，只负责生成候选线索，后续可接 Whois / 注册商 API。

#### 中文搜索发现

输入中文或英文检索词，例如：

```text
小说
考研
图片压缩
```

系统会从搜索结果里提取真实站点域名，写入线索库，并自动执行一次基础抓取。这个入口适合找“已经在线上活着”的同行站、内容站和工具站。

#### 已抓页面外链反查

系统会从当前筛选出的线索里抓取首页/联系页，提取外链根域名，并生成新的候选线索。

适合发现：

- 友情链接站点
- 同行业老站
- 内容站互链资源
- 站群痕迹
- 潜在可收购站长资源

### 3. 新增 Provider

```text
expired_domain_csv   过期/删除域名 CSV
url_list_txt         URL / 域名 TXT 列表
keyword_seed_txt     关键词种子 TXT
```

现在数据源层包含：

```text
generic_csv
+aizhan_manual_csv
+chinaz_manual_csv
+expired_domain_csv
+url_list_txt
+keyword_seed_txt
```

### 4. 后续预留

后面可以继续接：

```text
whois_provider          Whois / 到期时间 / 注册商
icp_official_provider   备案官方查询，需人工验证码或合规接口
baidu_site_provider     百度 site 收录检查，建议谨慎频控
wechat_block_provider   微信拦截检测
registrar_api_provider  注册商可注册检查 / 抢注接口
proxy_pool              代理池
celery_tasks            队列化任务中心
```

## 本版新增：话术编辑、邮件发送、多平台权重字段

### 1. 只买域名的话术

默认联系话术已改为“只需要域名本身，不需要源码、内容、服务器或整站数据”。在线索详情中可以直接编辑“联系话术 / 邮件正文”，点击“保存”后会写入该线索的 `contact_message`，以后复制话术和邮件正文都会优先使用你编辑后的版本。

### 2. 一键发送邮件

线索详情里新增“收件人邮箱、邮件主题、发送邮件”。系统会默认取抓取到的第一条邮箱，你也可以手动修改。

发送前需要在 `.env` 配置 SMTP：

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your@example.com
SMTP_PASSWORD=your_smtp_auth_code
SMTP_FROM=your@example.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false
```

建议使用邮箱服务商生成的 SMTP 授权码，不要填写网页登录密码。发送成功后，线索状态会从“新线索”自动改为“已联系”，并记录邮件日志。

### 3. 爱站权重综合字段

`rank.aizhan.com` 可以查看多个搜索平台的权重和收录数据。当前版本已在数据结构和 CSV Provider 中支持：

- 百度 PC 权重：`baidu_pc_weight` / `百度PC权重`
- 百度移动权重：`baidu_mobile_weight` / `百度移动权重`
- 百度收录：`indexed_count` / `百度收录`
- 搜狗权重 / 收录：`sogou_weight`、`sogou_indexed_count`
- 360 权重 / 收录：`so_weight`、`so_indexed_count`
- 神马权重 / 收录：`sm_weight`、`sm_indexed_count`
- 头条权重 / 收录：`toutiao_weight`、`toutiao_indexed_count`
- 必应权重 / 收录：`bing_weight`、`bing_indexed_count`

后续如果接爱站官方 API 或你自己的采集 Provider，可以直接写入这些字段，不需要再改表结构。

## 下一层骨架：线索画像、评分拆解、跟进时间线

这版开始把“雷达”和“销售台”接到同一根脊梁上：

- 每条线索会保存 `score_breakdown`，详情页能看到评分为什么加分 / 扣分
- 详情页新增线索画像，汇总雷达等级、风险等级、触达状态、建议动作
- 线索新增 `next_action`、`next_follow_up_at`、`last_contacted_at`
- 邮件发送成功后，会自动记录时间线，并默认安排 3 天后的下一次跟进
- 首页新增“待跟进”统计，开始把 outreach 从一次性动作变成连续流程

接下来最自然的扩展是两条：

1. 向左补尽调：Whois、注册商、到期时间、历史解析、历史快照  
2. 向右补成交：批量待跟进视图、二次跟进模板、报价历史、成交复盘

## 注册情报 / 可买性层

这版开始把“值不值得要”与“买不买得到”拆开：

- 新增注册情报字段：注册状态、注册商、注册时间、到期时间、剩余天数、RDAP 状态
- 新增可买性字段：`buyability_score`、`buyability_grade`、`buyability_reasons`
- 详情页可单条刷新注册信息，工具栏可批量刷新当前筛选结果
- 线索画像会同时显示资产评分与可买性评分，不再把“好域名”和“好机会”混为一谈

当前实现优先使用 RDAP，而不是继续堆旧式 WHOIS 解析。这样更适合作为后续注册状态、到期窗口、赎回 / 删除期判断的底座。

## 历史画像层

这版继续把“过去像不像真资产”拆成独立维度，而不是塞进总分里：

- 新增历史画像字段：公开历史状态、首次快照、最近快照、历史快照样本、活跃年数
- 新增历史评分字段：`history_score`、`history_grade`、`history_reasons`
- 详情页可单条刷新历史画像，工具栏可批量刷新当前筛选结果
- 线索画像现在会同时展示：资产评分、可买性评分、历史画像评分

当前实现先接入 Internet Archive / Wayback 的公开历史快照索引，用它判断“是否存在历史、历史跨度多长、最近是否仍有公开痕迹”。为避免把一次查询拖得太重，当前快照数采用轻量样本（最多展示为 `100+`）；这层是后续继续并入历史 DNS、黑名单、商标风险等证据的底座。
