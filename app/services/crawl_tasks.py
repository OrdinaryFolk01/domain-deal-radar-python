from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import CrawlLog, CrawlTask, DomainLead
from app.services.crawler import CrawlResult, crawl_site
from app.services.scoring import score_lead
import json


@dataclass(slots=True)
class BatchCrawlSummary:
    batch_id: str
    total: int
    success: int
    failed: int
    skipped: int = 0


def _join(values: list[str]) -> str:
    return " | ".join(values)


def _rescore_after_crawl(lead: DomainLead) -> None:
    result = score_lead(
        {
            "domain": lead.domain,
            "title": lead.title,
            "baidu_pc_weight": lead.baidu_pc_weight,
            "baidu_mobile_weight": lead.baidu_mobile_weight,
            "indexed_count": lead.indexed_count,
            "sogou_weight": lead.sogou_weight,
            "so_weight": lead.so_weight,
            "sm_weight": lead.sm_weight,
            "toutiao_weight": lead.toutiao_weight,
            "bing_weight": lead.bing_weight,
            "sogou_indexed_count": lead.sogou_indexed_count,
            "so_indexed_count": lead.so_indexed_count,
            "sm_indexed_count": lead.sm_indexed_count,
            "toutiao_indexed_count": lead.toutiao_indexed_count,
            "bing_indexed_count": lead.bing_indexed_count,
            "icp_type": lead.icp_type,
            "last_update": lead.last_update,
            "remark": lead.remark,
        }
    )
    lead.root_domain = result.root_domain
    lead.suffix = result.suffix
    lead.score = result.score
    lead.score_breakdown = json.dumps(result.breakdown, ensure_ascii=False)
    lead.risk_flags = " | ".join(result.risk_flags)
    lead.suggestion = result.suggestion
    lead.first_offer = result.first_offer
    lead.max_offer = result.max_offer


def create_crawl_tasks(db: Session, leads: list[DomainLead], *, batch_id: str | None = None) -> tuple[str, list[CrawlTask]]:
    current_batch_id = batch_id or uuid4().hex[:12]
    tasks: list[CrawlTask] = []
    now = datetime.utcnow()

    for lead in leads:
        lead.crawl_status = "PENDING"
        lead.crawl_error = ""
        task = CrawlTask(
            batch_id=current_batch_id,
            lead_id=lead.id,
            domain=lead.domain,
            status="PENDING",
            created_at=now,
        )
        db.add(task)
        tasks.append(task)

    db.commit()
    for task in tasks:
        db.refresh(task)
    return current_batch_id, tasks


def apply_crawl_result(db: Session, *, lead: DomainLead, task: CrawlTask, result: CrawlResult) -> bool:
    now = datetime.utcnow()
    success = bool(result.status_code or result.final_url) and not (result.error and not result.status_code)

    lead.status_code = result.status_code
    lead.final_url = result.final_url
    if result.title:
        lead.title = result.title
    lead.emails = _join(result.emails)
    lead.phones = _join(result.phones)
    lead.wechats = _join(result.wechats)
    lead.qqs = _join(result.qqs)
    lead.crawl_status = "SUCCESS" if success else "FAILED"
    lead.crawl_error = "" if success else (result.error or "抓取失败")
    lead.crawl_pages_done = result.pages_done
    lead.crawl_pages_total = result.pages_total
    lead.last_crawled_at = now

    task.status = lead.crawl_status
    task.error_message = lead.crawl_error
    task.pages_done = result.pages_done
    task.pages_total = result.pages_total
    task.finished_at = now

    for page in result.pages:
        db.add(
            CrawlLog(
                task_id=task.id,
                batch_id=task.batch_id,
                lead_id=lead.id,
                domain=lead.domain,
                url=page.url,
                status_code=page.status_code,
                final_url=page.final_url,
                title=page.title,
                emails=_join(page.emails),
                phones=_join(page.phones),
                wechats=_join(page.wechats),
                qqs=_join(page.qqs),
                error_message=page.error,
            )
        )

    _rescore_after_crawl(lead)
    return success


async def run_crawl_batch(
    db: Session,
    leads: list[DomainLead],
    *,
    concurrency: int = 5,
    timeout_seconds: int = 8,
    max_pages: int = 8,
) -> BatchCrawlSummary:
    if not leads:
        return BatchCrawlSummary(batch_id="", total=0, success=0, failed=0)

    batch_id, tasks = create_crawl_tasks(db, leads)
    task_map = {task.lead_id: task for task in tasks}
    targets = [(lead.id, lead.domain) for lead in leads]

    now = datetime.utcnow()
    for task in tasks:
        task.status = "RUNNING"
        task.started_at = now
    for lead in leads:
        lead.crawl_status = "RUNNING"
        lead.crawl_error = ""
    db.commit()

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def crawl_one(lead_id: int, domain: str) -> tuple[int, CrawlResult]:
        async with semaphore:
            result = await crawl_site(domain, timeout_seconds=timeout_seconds, max_pages=max_pages)
            return lead_id, result

    results = await asyncio.gather(*(crawl_one(lead_id, domain) for lead_id, domain in targets))

    success_count = 0
    failed_count = 0
    for lead_id, result in results:
        lead = db.get(DomainLead, lead_id)
        task = task_map.get(lead_id)
        if lead is None or task is None:
            failed_count += 1
            continue
        ok = apply_crawl_result(db, lead=lead, task=task, result=result)
        if ok:
            success_count += 1
        else:
            failed_count += 1

    db.commit()
    return BatchCrawlSummary(batch_id=batch_id, total=len(leads), success=success_count, failed=failed_count)
