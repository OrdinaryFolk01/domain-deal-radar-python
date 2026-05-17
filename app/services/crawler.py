from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx

from app.services.contact_extract import discover_contact_links, extract_contacts, extract_title

COMMON_CONTACT_PATHS = [
    "/contact",
    "/contact-us",
    "/about",
    "/about-us",
    "/lianxi",
    "/lianxiwomen",
    "/about.html",
    "/contact.html",
    "/aboutus.html",
    "/contactus.html",
    "/plus/list.php?tid=1",
    "/plus/list.php?tid=2",
]


@dataclass(slots=True)
class PageCrawlResult:
    url: str
    status_code: str = ""
    final_url: str = ""
    title: str = ""
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    wechats: list[str] = field(default_factory=list)
    qqs: list[str] = field(default_factory=list)
    html: str = ""
    error: str = ""


@dataclass(slots=True)
class CrawlResult:
    domain: str
    status_code: str
    final_url: str
    title: str
    emails: list[str]
    phones: list[str]
    wechats: list[str]
    qqs: list[str]
    pages: list[PageCrawlResult] = field(default_factory=list)
    error: str = ""

    @property
    def pages_done(self) -> int:
        return len(self.pages)

    @property
    def pages_total(self) -> int:
        return len(self.pages)


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _merge_contacts(pages: list[PageCrawlResult]) -> dict[str, list[str]]:
    return {
        "emails": _unique([item for page in pages for item in page.emails]),
        "phones": _unique([item for page in pages for item in page.phones]),
        "wechats": _unique([item for page in pages for item in page.wechats]),
        "qqs": _unique([item for page in pages for item in page.qqs]),
    }


async def fetch_page(client: httpx.AsyncClient, url: str) -> PageCrawlResult:
    try:
        resp = await client.get(url)
        content_type = resp.headers.get("content-type", "")
        html = resp.text if "text/html" in content_type or "charset" in content_type else ""
        contacts = extract_contacts(html)
        return PageCrawlResult(
            url=url,
            status_code=str(resp.status_code),
            final_url=str(resp.url),
            title=extract_title(html),
            emails=contacts["emails"],
            phones=contacts["phones"],
            wechats=contacts["wechats"],
            qqs=contacts["qqs"],
            html=html,
        )
    except Exception as exc:  # noqa: BLE001
        return PageCrawlResult(url=url, error=str(exc))


async def _fetch_best_home(client: httpx.AsyncClient, domain: str) -> PageCrawlResult:
    last_result = PageCrawlResult(url=f"https://{domain}", error="未开始")
    for url in [f"https://{domain}", f"http://{domain}"]:
        result = await fetch_page(client, url)
        last_result = result
        if result.status_code and result.status_code not in {"403", "404", "500", "502", "503", "504"}:
            return result
        await asyncio.sleep(0.05)
    return last_result


def _build_contact_urls(home: PageCrawlResult, *, max_pages: int) -> list[str]:
    base_url = home.final_url or home.url
    urls = [base_url]

    for path in COMMON_CONTACT_PATHS:
        urls.append(urljoin(base_url, path))

    urls.extend(discover_contact_links(home.html, base_url, limit=max_pages))

    # 去重且限制数量。首页必须保留在第一位。
    unique_urls = _unique(urls)
    return unique_urls[:max_pages]


async def crawl_site(domain: str, *, timeout_seconds: int = 8, max_pages: int = 8) -> CrawlResult:
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout_seconds,
        headers={"User-Agent": "Mozilla/5.0 DomainDealRadar/1.0; local-research-tool"},
    ) as client:
        home = await _fetch_best_home(client, domain)
        if not home.status_code and not home.final_url:
            return CrawlResult(
                domain=domain,
                status_code="",
                final_url="",
                title="",
                emails=[],
                phones=[],
                wechats=[],
                qqs=[],
                pages=[home],
                error=home.error or "首页访问失败",
            )

        urls = _build_contact_urls(home, max_pages=max_pages)
        pages: list[PageCrawlResult] = [home]

        # 首页已经抓过，其他联系页串行抓取，避免单站点并发过猛。
        for url in urls[1:]:
            page = await fetch_page(client, url)
            pages.append(page)
            # 已拿到明确联系方式时可以提前停止，减少请求。
            merged = _merge_contacts(pages)
            if len(merged["emails"]) + len(merged["phones"]) + len(merged["wechats"]) + len(merged["qqs"]) >= 3:
                break
            await asyncio.sleep(0.12)

    contacts = _merge_contacts(pages)
    first_ok = next((page for page in pages if page.status_code), home)
    first_title = next((page.title for page in pages if page.title), "")
    errors = [page.error for page in pages if page.error]

    return CrawlResult(
        domain=domain,
        status_code=first_ok.status_code,
        final_url=first_ok.final_url,
        title=first_title,
        emails=contacts["emails"],
        phones=contacts["phones"],
        wechats=contacts["wechats"],
        qqs=contacts["qqs"],
        pages=pages,
        error=" | ".join(errors[:3]),
    )


async def fetch_home(domain: str, timeout_seconds: int = 8) -> CrawlResult:
    """兼容旧接口：只暴露聚合后的首页/联系方式结果。"""
    return await crawl_site(domain, timeout_seconds=timeout_seconds, max_pages=1)
