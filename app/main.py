from __future__ import annotations

from pathlib import Path
import json
from typing import Annotated
from datetime import datetime

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi import Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, delete, desc, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db, init_db
from app.models import CrawlLog, CrawlTask, DiscoveryTask, DomainLead, EmailLog, LeadActivity
from app.providers import ProviderError, list_providers
from app.schemas import CrawlLogOut, CrawlTaskOut, DiscoveryTaskOut, EmailLogOut, EmailSendRequest, EmailSendResponse, LeadActivityOut, LeadOut, LeadUpdate, ManualLeadCreate, SearchDiscoveryRequest, SeedDiscoveryRequest
from app.services.activities import build_activity
from app.services.analysis import analyze_lead, run_analysis_batch
from app.services.crawl_tasks import run_crawl_batch
from app.services.discovery import discover_from_external_links, discover_from_search_results, import_seed_keywords, list_discovery_tasks
from app.services.email_sender import EmailSendError, send_lead_email
from app.services.import_export import (
    export_csv,
    export_json,
    parse_csv_content,
    parse_provider_file,
    preview_provider_file,
    restore_from_json,
    upsert_leads_from_rows,
)
from app.services.message import build_contact_message, build_detail_message, build_email_subject
from app.services.lead_profile import build_lead_profile
from app.services.history import refresh_history_for_lead
from app.services.registration import refresh_registration_for_lead
from app.services.scoring import score_lead

BASE_DIR = Path(__file__).resolve().parent
settings = get_settings()

app = FastAPI(title=settings.app_name)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request, "app_name": settings.app_name})


def build_lead_query(
    *,
    keyword: str = "",
    status: str = "",
    min_score: int | None = None,
    risk: str = "",
    crawl_status: str = "",
):
    stmt = select(DomainLead)
    clauses = []

    if keyword:
        like = f"%{keyword}%"
        clauses.append(
            or_(
                DomainLead.domain.like(like),
                DomainLead.title.like(like),
                DomainLead.remark.like(like),
                DomainLead.icp_type.like(like),
            )
        )

    if status:
        clauses.append(DomainLead.lead_status == status)

    if crawl_status:
        clauses.append(DomainLead.crawl_status == crawl_status)

    if min_score is not None:
        clauses.append(DomainLead.score >= min_score)

    if risk == "has_risk":
        clauses.append(DomainLead.risk_flags != "")
    elif risk == "no_risk":
        clauses.append(DomainLead.risk_flags == "")

    if clauses:
        stmt = stmt.where(and_(*clauses))

    return stmt.order_by(desc(DomainLead.created_at), desc(DomainLead.updated_at), desc(DomainLead.score))


@app.get("/api/leads", response_model=list[LeadOut])
def list_leads(
    db: Annotated[Session, Depends(get_db)],
    keyword: str = Query(default=""),
    status: str = Query(default=""),
    crawl_status: str = Query(default=""),
    min_score: int | None = Query(default=None),
    risk: str = Query(default=""),
    limit: int = Query(default=500, ge=1, le=5000),
) -> list[DomainLead]:
    stmt = build_lead_query(keyword=keyword, status=status, min_score=min_score, risk=risk, crawl_status=crawl_status).limit(limit)
    return list(db.scalars(stmt))


@app.get("/api/leads/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: int, db: Annotated[Session, Depends(get_db)]) -> DomainLead:
    lead = db.get(DomainLead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="线索不存在")
    return lead


@app.patch("/api/leads/{lead_id}", response_model=LeadOut)
def update_lead(lead_id: int, payload: LeadUpdate, db: Annotated[Session, Depends(get_db)]) -> DomainLead:
    lead = db.get(DomainLead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="线索不存在")

    updates = payload.model_dump(exclude_unset=True)
    previous_status = lead.lead_status
    previous_note = lead.contact_note
    previous_follow_up = lead.next_follow_up_at
    previous_action = lead.next_action

    for field, value in updates.items():
        current_value = getattr(lead, field)
        if isinstance(current_value, str):
            setattr(lead, field, value or "")
        elif isinstance(current_value, bool):
            setattr(lead, field, bool(value))
        elif isinstance(current_value, datetime) or field.endswith("_at"):
            setattr(lead, field, value)
        else:
            setattr(lead, field, value if value is not None else 0)

    if "lead_status" in updates and lead.lead_status != previous_status:
        db.add(
            build_activity(
                lead,
                event_type="STATUS_CHANGED",
                title="跟进状态已更新",
                detail=f"{previous_status} → {lead.lead_status}",
            )
        )
    if "contact_note" in updates and lead.contact_note != previous_note:
        db.add(
            build_activity(
                lead,
                event_type="NOTE_UPDATED",
                title="跟进记录已更新",
                detail=lead.contact_note[:500],
            )
        )
    if "next_follow_up_at" in updates and lead.next_follow_up_at != previous_follow_up:
        detail = lead.next_follow_up_at.isoformat(sep=" ", timespec="minutes") if lead.next_follow_up_at else "已清空"
        db.add(
            build_activity(
                lead,
                event_type="FOLLOW_UP_SCHEDULED",
                title="下次跟进时间已更新",
                detail=detail,
            )
        )
    if "next_action" in updates and lead.next_action != previous_action:
        db.add(
            build_activity(
                lead,
                event_type="NEXT_ACTION_UPDATED",
                title="下一步动作已更新",
                detail=lead.next_action,
            )
        )

    db.commit()
    db.refresh(lead)
    return lead


@app.delete("/api/leads/{lead_id}")
def delete_lead(lead_id: int, db: Annotated[Session, Depends(get_db)]) -> dict[str, bool]:
    lead = db.get(DomainLead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="线索不存在")
    db.execute(delete(CrawlLog).where(CrawlLog.lead_id == lead_id))
    db.execute(delete(CrawlTask).where(CrawlTask.lead_id == lead_id))
    db.execute(delete(EmailLog).where(EmailLog.lead_id == lead_id))
    db.execute(delete(LeadActivity).where(LeadActivity.lead_id == lead_id))
    db.delete(lead)
    db.commit()
    return {"ok": True}


@app.get("/api/providers")
def get_data_source_providers() -> list[dict[str, object]]:
    return list_providers()


@app.post("/api/providers/{provider_id}/preview")
async def preview_provider_import(provider_id: str, file: UploadFile) -> dict[str, object]:
    content = await file.read()
    try:
        return preview_provider_file(provider_id, content, filename=file.filename or "upload.csv")
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/providers/{provider_id}/import")
async def import_from_provider(provider_id: str, file: UploadFile, db: Annotated[Session, Depends(get_db)]) -> dict[str, int]:
    content = await file.read()
    try:
        rows = parse_provider_file(provider_id, content, filename=file.filename or "upload.csv")
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return upsert_leads_from_rows(db, rows)


@app.post("/api/import/csv")
async def import_csv(file: UploadFile, db: Annotated[Session, Depends(get_db)]) -> dict[str, int]:
    content = await file.read()
    rows = parse_csv_content(content)
    return upsert_leads_from_rows(db, rows)


@app.post("/api/leads/manual")
async def create_manual_leads(payload: ManualLeadCreate, db: Annotated[Session, Depends(get_db)]) -> dict[str, object]:
    raw_items = (
        payload.domains.replace("，", "\n")
        .replace(",", "\n")
        .replace(";", "\n")
        .replace("；", "\n")
        .splitlines()
    )

    domains: list[str] = []
    for item in raw_items:
        for part in item.split():
            score_result = score_lead({"domain": part})
            normalized = score_result.root_domain
            if normalized and "." in normalized and normalized not in domains:
                domains.append(normalized)

    if not domains:
        raise HTTPException(status_code=400, detail="请至少输入一个有效域名")

    rows = [
        {
            "domain": domain,
            "title": payload.title.strip(),
            "remark": payload.remark.strip(),
            "source_provider": "manual_input",
            "source_url": "manual_input",
            "discovered_from": "manual_input",
        }
        for domain in domains
    ]

    result = upsert_leads_from_rows(db, rows)
    leads = list(db.scalars(select(DomainLead).where(DomainLead.domain.in_(domains))))

    crawl_summary: dict[str, int | str] | None = None
    analysis_summary: dict[str, int] | None = None

    if payload.auto_crawl and leads:
        summary = await run_crawl_batch(
            db,
            leads,
            concurrency=settings.crawler_concurrency,
            timeout_seconds=settings.crawler_timeout_seconds,
            max_pages=8,
        )
        crawl_summary = {
            "batch_id": summary.batch_id,
            "total": summary.total,
            "success": summary.success,
            "failed": summary.failed,
            "skipped": summary.skipped,
        }

    if payload.auto_analyze and leads:
        analysis_summary = await run_analysis_batch(
            db,
            leads,
            concurrency=settings.crawler_concurrency,
            timeout_seconds=settings.crawler_timeout_seconds,
            max_pages=4,
        )

    return {
        **result,
        "domains": domains,
        "crawl": crawl_summary,
        "analysis": analysis_summary,
    }


@app.post("/api/restore/json")
async def restore_json(file: UploadFile, db: Annotated[Session, Depends(get_db)]) -> dict[str, int]:
    content = await file.read()
    return restore_from_json(db, content)


@app.get("/api/export/csv")
def download_csv(
    db: Annotated[Session, Depends(get_db)],
    keyword: str = Query(default=""),
    status: str = Query(default=""),
    crawl_status: str = Query(default=""),
    min_score: int | None = Query(default=None),
    risk: str = Query(default=""),
) -> Response:
    leads = list(db.scalars(build_lead_query(keyword=keyword, status=status, min_score=min_score, risk=risk, crawl_status=crawl_status)))
    content = export_csv(leads)
    return Response(
        content=content.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=domain-leads.csv"},
    )


@app.get("/api/export/json")
def download_json(db: Annotated[Session, Depends(get_db)]) -> Response:
    leads = list(db.scalars(select(DomainLead).order_by(desc(DomainLead.updated_at))))
    return Response(
        content=export_json(leads).encode("utf-8"),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=domain-leads-backup.json"},
    )


@app.post("/api/leads/{lead_id}/rescore", response_model=LeadOut)
def rescore_lead(lead_id: int, db: Annotated[Session, Depends(get_db)]) -> DomainLead:
    lead = db.get(DomainLead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="线索不存在")

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
    db.commit()
    db.refresh(lead)
    return lead


@app.post("/api/leads/{lead_id}/crawl", response_model=LeadOut)
async def crawl_lead(lead_id: int, db: Annotated[Session, Depends(get_db)]) -> DomainLead:
    lead = db.get(DomainLead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="线索不存在")

    await run_crawl_batch(
        db,
        [lead],
        concurrency=1,
        timeout_seconds=settings.crawler_timeout_seconds,
        max_pages=8,
    )
    db.refresh(lead)
    return lead


@app.post("/api/crawl/batch")
async def crawl_batch(
    db: Annotated[Session, Depends(get_db)],
    keyword: str = Query(default=""),
    status: str = Query(default=""),
    crawl_status: str = Query(default=""),
    min_score: int | None = Query(default=None),
    risk: str = Query(default=""),
    limit: int = Query(default=30, ge=1, le=300),
    max_pages: int = Query(default=8, ge=1, le=20),
) -> dict[str, int | str]:
    leads = list(
        db.scalars(
            build_lead_query(keyword=keyword, status=status, min_score=min_score, risk=risk, crawl_status=crawl_status).limit(limit)
        )
    )
    summary = await run_crawl_batch(
        db,
        leads,
        concurrency=settings.crawler_concurrency,
        timeout_seconds=settings.crawler_timeout_seconds,
        max_pages=max_pages,
    )
    return {
        "batch_id": summary.batch_id,
        "total": summary.total,
        "success": summary.success,
        "failed": summary.failed,
        "skipped": summary.skipped,
    }


@app.post("/api/crawl/retry-failed")
async def retry_failed_crawls(
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=30, ge=1, le=300),
    max_pages: int = Query(default=8, ge=1, le=20),
) -> dict[str, int | str]:
    leads = list(db.scalars(select(DomainLead).where(DomainLead.crawl_status == "FAILED").order_by(desc(DomainLead.updated_at)).limit(limit)))
    summary = await run_crawl_batch(
        db,
        leads,
        concurrency=settings.crawler_concurrency,
        timeout_seconds=settings.crawler_timeout_seconds,
        max_pages=max_pages,
    )
    return {
        "batch_id": summary.batch_id,
        "total": summary.total,
        "success": summary.success,
        "failed": summary.failed,
        "skipped": summary.skipped,
    }


@app.get("/api/crawl/tasks", response_model=list[CrawlTaskOut])
def list_crawl_tasks(db: Annotated[Session, Depends(get_db)], limit: int = Query(default=50, ge=1, le=500)) -> list[CrawlTask]:
    return list(db.scalars(select(CrawlTask).order_by(desc(CrawlTask.created_at)).limit(limit)))


@app.get("/api/leads/{lead_id}/crawl/logs", response_model=list[CrawlLogOut])
def list_lead_crawl_logs(lead_id: int, db: Annotated[Session, Depends(get_db)], limit: int = Query(default=50, ge=1, le=500)) -> list[CrawlLog]:
    return list(db.scalars(select(CrawlLog).where(CrawlLog.lead_id == lead_id).order_by(desc(CrawlLog.created_at)).limit(limit)))




@app.post("/api/leads/{lead_id}/analyze", response_model=LeadOut)
async def analyze_single_lead(lead_id: int, db: Annotated[Session, Depends(get_db)]) -> DomainLead:
    lead = db.get(DomainLead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="线索不存在")
    await analyze_lead(
        db,
        lead,
        timeout_seconds=settings.crawler_timeout_seconds,
        max_pages=4,
    )
    db.refresh(lead)
    return lead


@app.post("/api/analysis/batch")
async def analyze_batch(
    db: Annotated[Session, Depends(get_db)],
    keyword: str = Query(default=""),
    status: str = Query(default=""),
    crawl_status: str = Query(default=""),
    min_score: int | None = Query(default=None),
    risk: str = Query(default=""),
    limit: int = Query(default=30, ge=1, le=300),
) -> dict[str, int]:
    leads = list(
        db.scalars(
            build_lead_query(keyword=keyword, status=status, min_score=min_score, risk=risk, crawl_status=crawl_status).limit(limit)
        )
    )
    return await run_analysis_batch(
        db,
        leads,
        concurrency=settings.crawler_concurrency,
        timeout_seconds=settings.crawler_timeout_seconds,
        max_pages=4,
    )


@app.post("/api/leads/{lead_id}/registration", response_model=LeadOut)
async def refresh_single_registration(lead_id: int, db: Annotated[Session, Depends(get_db)]) -> DomainLead:
    lead = db.get(DomainLead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="线索不存在")
    return await refresh_registration_for_lead(db, lead)


@app.post("/api/registration/batch")
async def refresh_registration_batch(
    db: Annotated[Session, Depends(get_db)],
    keyword: str = Query(default=""),
    status: str = Query(default=""),
    crawl_status: str = Query(default=""),
    min_score: int | None = Query(default=None),
    risk: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, int]:
    leads = list(
        db.scalars(
            build_lead_query(keyword=keyword, status=status, min_score=min_score, risk=risk, crawl_status=crawl_status).limit(limit)
        )
    )
    summary = {"total": len(leads), "success": 0, "failed": 0}
    for lead in leads:
        await refresh_registration_for_lead(db, lead)
        if lead.registration_status == "UNKNOWN":
            summary["failed"] += 1
        else:
            summary["success"] += 1
    return summary


@app.post("/api/leads/{lead_id}/history", response_model=LeadOut)
async def refresh_single_history(lead_id: int, db: Annotated[Session, Depends(get_db)]) -> DomainLead:
    lead = db.get(DomainLead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="线索不存在")
    return await refresh_history_for_lead(db, lead)


@app.post("/api/history/batch")
async def refresh_history_batch(
    db: Annotated[Session, Depends(get_db)],
    keyword: str = Query(default=""),
    status: str = Query(default=""),
    crawl_status: str = Query(default=""),
    min_score: int | None = Query(default=None),
    risk: str = Query(default=""),
    limit: int = Query(default=10, ge=1, le=50),
) -> dict[str, int]:
    leads = list(
        db.scalars(
            build_lead_query(keyword=keyword, status=status, min_score=min_score, risk=risk, crawl_status=crawl_status).limit(limit)
        )
    )
    summary = {"total": len(leads), "success": 0, "failed": 0}
    for lead in leads:
        await refresh_history_for_lead(db, lead)
        if lead.history_status == "UNKNOWN":
            summary["failed"] += 1
        else:
            summary["success"] += 1
    return summary


@app.post("/api/discovery/keywords")
def discover_from_keywords(payload: SeedDiscoveryRequest, db: Annotated[Session, Depends(get_db)]) -> dict[str, int | str]:
    keywords = [line.strip() for line in payload.keywords.replace(",", "\n").splitlines() if line.strip()]
    if not keywords:
        raise HTTPException(status_code=400, detail="请至少输入一个英文/拼音关键词")
    return import_seed_keywords(
        db,
        keywords=keywords,
        suffixes=payload.suffixes,
        prefixes=payload.prefixes,
        limit=payload.limit,
    )


@app.post("/api/discovery/search")
async def discover_from_search(payload: SearchDiscoveryRequest, db: Annotated[Session, Depends(get_db)]) -> dict[str, object]:
    return await discover_from_search_results(
        db,
        query=payload.query.strip(),
        limit=payload.limit,
        auto_crawl=payload.auto_crawl,
        crawl_concurrency=settings.crawler_concurrency,
        crawl_timeout_seconds=settings.crawler_timeout_seconds,
    )


@app.post("/api/discovery/external-links")
async def discover_external_links(
    db: Annotated[Session, Depends(get_db)],
    keyword: str = Query(default=""),
    status: str = Query(default=""),
    crawl_status: str = Query(default=""),
    min_score: int | None = Query(default=None),
    risk: str = Query(default=""),
    source_limit: int = Query(default=10, ge=1, le=100),
    new_limit: int = Query(default=100, ge=1, le=1000),
) -> dict[str, int | str]:
    leads = list(
        db.scalars(
            build_lead_query(keyword=keyword, status=status, min_score=min_score, risk=risk, crawl_status=crawl_status).limit(source_limit)
        )
    )
    return await discover_from_external_links(
        db,
        leads,
        limit=new_limit,
        timeout_seconds=settings.crawler_timeout_seconds,
        max_pages=4,
    )


@app.get("/api/discovery/tasks", response_model=list[DiscoveryTaskOut])
def get_discovery_tasks(db: Annotated[Session, Depends(get_db)], limit: int = Query(default=50, ge=1, le=500)) -> list[DiscoveryTask]:
    return list_discovery_tasks(db, limit=limit)

@app.get("/api/leads/{lead_id}/message", response_class=PlainTextResponse)
def get_message(lead_id: int, db: Annotated[Session, Depends(get_db)], detail: bool = Query(default=False)) -> str:
    lead = db.get(DomainLead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="线索不存在")
    return build_detail_message(lead) if detail else build_contact_message(lead)


@app.get("/api/leads/{lead_id}/email-template")
def get_email_template(lead_id: int, db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    lead = db.get(DomainLead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="线索不存在")
    first_email = next((item.strip() for item in (lead.emails or "").replace("；", "|").replace(";", "|").replace(",", "|").split("|") if item.strip()), "")
    return {
        "to": lead.last_email_to or first_email,
        "subject": build_email_subject(lead),
        "body": build_contact_message(lead),
    }


@app.post("/api/leads/{lead_id}/send-email", response_model=EmailSendResponse)
def send_email_for_lead(lead_id: int, payload: EmailSendRequest, db: Annotated[Session, Depends(get_db)]) -> EmailSendResponse:
    lead = db.get(DomainLead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="线索不存在")
    try:
        log = send_lead_email(db, lead, to_email=payload.to, subject=payload.subject, body=payload.body)
    except EmailSendError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return EmailSendResponse(ok=True, message="邮件已发送", log_id=log.id)


@app.get("/api/leads/{lead_id}/email-logs", response_model=list[EmailLogOut])
def list_email_logs(lead_id: int, db: Annotated[Session, Depends(get_db)], limit: int = Query(default=20, ge=1, le=100)) -> list[EmailLog]:
    return list(db.scalars(select(EmailLog).where(EmailLog.lead_id == lead_id).order_by(desc(EmailLog.created_at)).limit(limit)))


@app.get("/api/leads/{lead_id}/profile")
def get_lead_profile(lead_id: int, db: Annotated[Session, Depends(get_db)]) -> dict[str, object]:
    lead = db.get(DomainLead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="线索不存在")
    return build_lead_profile(lead)


@app.get("/api/leads/{lead_id}/activities", response_model=list[LeadActivityOut])
def list_lead_activities(lead_id: int, db: Annotated[Session, Depends(get_db)], limit: int = Query(default=30, ge=1, le=100)) -> list[LeadActivity]:
    return list(db.scalars(select(LeadActivity).where(LeadActivity.lead_id == lead_id).order_by(desc(LeadActivity.created_at)).limit(limit)))


@app.post("/api/clear")
def clear_all(db: Annotated[Session, Depends(get_db)]) -> dict[str, bool]:
    db.execute(delete(CrawlLog))
    db.execute(delete(CrawlTask))
    db.execute(delete(DiscoveryTask))
    db.execute(delete(EmailLog))
    db.execute(delete(LeadActivity))
    db.execute(delete(DomainLead))
    db.commit()
    return {"ok": True}
