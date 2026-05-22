from __future__ import annotations

import base64
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import tldextract
from bs4 import BeautifulSoup
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import DiscoveryTask, DomainLead
from app.services.contact_extract import extract_external_domains
from app.services.crawler import crawl_site
from app.services.crawl_tasks import run_crawl_batch
from app.services.import_export import upsert_leads_from_rows
from app.services.scoring import normalize_domain
from app.services.seed_generation import generate_seed_domains, normalize_seed_keywords
from app.services.scrapling_fetch import build_url, create_scrapling_session, raise_for_status, response_text

SEARCH_EXCLUDED_DOMAINS = {
    "bing.com",
    "microsoft.com",
    "baidu.com",
    "qq.com",
    "zhihu.com",
    "weibo.com",
    "wikipedia.org",
}

def create_discovery_task(db: Session, *, provider_id: str, source_type: str, keyword: str) -> DiscoveryTask:
    task = DiscoveryTask(
        provider_id=provider_id,
        source_type=source_type,
        status="RUNNING",
        keyword=keyword,
        started_at=datetime.utcnow(),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def finish_discovery_task(
    db: Session,
    task: DiscoveryTask,
    *,
    total: int,
    created: int,
    updated: int,
    skipped: int = 0,
    error: str = "",
) -> DiscoveryTask:
    task.status = "FAILED" if error else "SUCCESS"
    task.total = total
    task.created_count = created
    task.updated_count = updated
    task.skipped_count = skipped
    task.error_message = error
    task.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(task)
    return task


def import_seed_keywords(
    db: Session,
    *,
    keywords: list[str],
    suffixes: list[str] | None = None,
    prefixes: list[str] | None = None,
    limit: int = 500,
) -> dict[str, int | str]:
    task = create_discovery_task(
        db,
        provider_id="keyword_seed_generator",
        source_type="keyword_seed",
        keyword="\n".join(keywords[:50]),
    )
    try:
        normalized_keywords, invalid_keywords = normalize_seed_keywords(keywords)
        rows = generate_seed_domains(keywords, suffixes=suffixes, prefixes=prefixes, limit=limit)
        result = upsert_leads_from_rows(db, rows)
        finish_discovery_task(
            db,
            task,
            total=len(rows),
            created=result["created"],
            updated=result["updated"],
            skipped=len(invalid_keywords),
        )
        return {
            "task_id": task.id,
            **result,
            "normalized_keywords": normalized_keywords,
            "invalid_keywords": invalid_keywords,
        }
    except Exception as exc:  # noqa: BLE001
        finish_discovery_task(db, task, total=0, created=0, updated=0, skipped=0, error=str(exc))
        raise


def _decode_bing_result_url(href: str) -> str:
    parsed = urlparse(href)
    if parsed.scheme in {"http", "https"} and "bing.com" not in parsed.netloc:
        return href

    query = parse_qs(parsed.query)
    encoded = (query.get("u") or [""])[0]
    if encoded.startswith("a1"):
        encoded = encoded[2:]
    if not encoded:
        return ""
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        return base64.urlsafe_b64decode(padded.encode()).decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return ""


async def search_web_domains(query: str, *, limit: int = 10, timeout_seconds: int = 15) -> list[dict[str, str]]:
    params = {
        "q": query,
        "count": min(max(limit * 3, 10), 50),
        "setlang": "zh-hans",
    }
    async with create_scrapling_session(timeout_seconds=timeout_seconds) as client:
        response = await client.get(build_url("https://www.bing.com/search", params))
        raise_for_status(response)
        html = response_text(response)

    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.select("li.b_algo h2 a"):
        href = str(anchor.get("href") or "")
        target_url = _decode_bing_result_url(href)
        parsed = urlparse(target_url)
        host = parsed.hostname or ""
        domain = normalize_domain(host)
        registered = tldextract.extract(domain).registered_domain or domain
        if not registered or registered in seen or registered in SEARCH_EXCLUDED_DOMAINS:
            continue
        seen.add(registered)
        rows.append(
            {
                "domain": registered,
                "title": anchor.get_text(" ", strip=True),
                "remark": f"中文搜索发现：{query}",
                "source_provider": "bing_search_discovery",
                "source_url": target_url,
                "discovered_from": f"search:{query}",
            }
        )
        if len(rows) >= limit:
            break
    return rows


async def discover_from_search_results(
    db: Session,
    *,
    query: str,
    limit: int = 10,
    auto_crawl: bool = True,
    crawl_concurrency: int = 5,
    crawl_timeout_seconds: int = 8,
) -> dict[str, object]:
    task = create_discovery_task(
        db,
        provider_id="bing_search_discovery",
        source_type="search_results",
        keyword=query,
    )
    try:
        rows = await search_web_domains(query, limit=limit)
        result = upsert_leads_from_rows(db, rows)
        domains = [row["domain"] for row in rows]
        leads = list(db.scalars(select(DomainLead).where(DomainLead.domain.in_(domains)))) if domains else []
        for row in rows:
            item = next((lead for lead in leads if lead.domain == row["domain"]), None)
            if item:
                item.discovered_from = row.get("discovered_from", "")
        db.commit()

        crawl_summary: dict[str, int | str] | None = None
        if auto_crawl and leads:
            summary = await run_crawl_batch(
                db,
                leads,
                concurrency=crawl_concurrency,
                timeout_seconds=crawl_timeout_seconds,
                max_pages=4,
            )
            crawl_summary = {
                "batch_id": summary.batch_id,
                "total": summary.total,
                "success": summary.success,
                "failed": summary.failed,
                "skipped": summary.skipped,
            }

        finish_discovery_task(db, task, total=len(rows), created=result["created"], updated=result["updated"])
        return {"task_id": task.id, **result, "domains": domains, "crawl": crawl_summary}
    except Exception as exc:  # noqa: BLE001
        finish_discovery_task(db, task, total=0, created=0, updated=0, skipped=0, error=str(exc))
        raise


async def discover_from_external_links(
    db: Session,
    leads: list[DomainLead],
    *,
    limit: int = 200,
    timeout_seconds: int = 8,
    max_pages: int = 4,
) -> dict[str, int | str]:
    task = create_discovery_task(
        db,
        provider_id="external_link_discovery",
        source_type="external_links",
        keyword=", ".join([lead.domain for lead in leads[:20]]),
    )
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    skipped = 0
    try:
        for lead in leads:
            crawl = await crawl_site(lead.domain, timeout_seconds=timeout_seconds, max_pages=max_pages)
            html_pages = [page.html for page in crawl.pages if page.html]
            base_url = crawl.final_url or f"https://{lead.domain}"
            found = extract_external_domains(html_pages, base_url)
            for domain in found:
                domain = normalize_domain(domain)
                if not domain or domain == lead.domain:
                    skipped += 1
                    continue
                registered = tldextract.extract(domain).registered_domain or domain
                if registered in seen:
                    continue
                seen.add(registered)
                rows.append(
                    {
                        "domain": registered,
                        "title": "",
                        "remark": f"从 {lead.domain} 外链发现",
                        "source_provider": "external_link_discovery",
                        "source_url": base_url,
                        "discovered_from": lead.domain,
                    }
                )
                if len(rows) >= limit:
                    break
            if len(rows) >= limit:
                break
        result = upsert_leads_from_rows(db, rows)
        # upsert_leads_from_rows 暂时不识别 discovered_from，这里二次补齐。
        for row in rows:
            item = db.scalar(select(DomainLead).where(DomainLead.domain == row["domain"]))
            if item:
                item.discovered_from = row.get("discovered_from", "")
        db.commit()
        finish_discovery_task(db, task, total=len(rows), created=result["created"], updated=result["updated"], skipped=skipped)
        return {"task_id": task.id, **result}
    except Exception as exc:  # noqa: BLE001
        finish_discovery_task(db, task, total=len(rows), created=0, updated=0, skipped=skipped, error=str(exc))
        raise


def list_discovery_tasks(db: Session, *, limit: int = 50) -> list[DiscoveryTask]:
    return list(db.scalars(select(DiscoveryTask).order_by(desc(DiscoveryTask.created_at)).limit(limit)))
