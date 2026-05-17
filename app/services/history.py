from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app.models import DomainLead
from app.services.activities import build_activity
from app.services.scoring import normalize_domain

WAYBACK_CDX_URL = "https://web.archive.org/cdx/search/cdx"
WAYBACK_AVAILABLE_URL = "https://archive.org/wayback/available"
ARCHIVE_SAMPLE_LIMIT = 100


@dataclass(slots=True)
class ArchiveHistoryResult:
    status: str
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    snapshot_count: int = 0
    active_years: int = 0
    source_url: str = ""
    error: str = ""


def _parse_wayback_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d%H%M%S")
    except ValueError:
        return None


async def lookup_archive_history(domain: str, *, timeout_seconds: int = 15) -> ArchiveHistoryResult:
    normalized = normalize_domain(domain)
    if not normalized or "." not in normalized:
        return ArchiveHistoryResult(status="UNKNOWN", error="域名格式无效")

    params = {
        "url": normalized,
        "matchType": "domain",
        "output": "json",
        "fl": "timestamp,statuscode",
        "filter": "statuscode:200",
        "collapse": "timestamp:8",
        "limit": ARCHIVE_SAMPLE_LIMIT,
    }
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
        try:
            response = await client.get(WAYBACK_CDX_URL, params=params)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                return ArchiveHistoryResult(status="UNKNOWN", source_url=str(response.url), error="Wayback 返回格式异常")

            rows = payload[1:] if payload and isinstance(payload[0], list) else payload
            timestamps = [
                parsed
                for row in rows
                if isinstance(row, list) and row
                for parsed in [_parse_wayback_timestamp(str(row[0] or ""))]
                if parsed is not None
            ]
            latest_response = await client.get(WAYBACK_AVAILABLE_URL, params={"url": normalized})
            latest_response.raise_for_status()
            latest_payload = latest_response.json()
            closest = latest_payload.get("archived_snapshots", {}).get("closest", {}) if isinstance(latest_payload, dict) else {}
            latest_seen_at = _parse_wayback_timestamp(str(closest.get("timestamp") or "")) if closest else None

            if not timestamps and latest_seen_at is None:
                return ArchiveHistoryResult(status="NO_ARCHIVE", source_url=str(response.url))

            first_seen_at = min(timestamps) if timestamps else latest_seen_at
            last_seen_at = latest_seen_at or max(timestamps)
            active_years = max(1, int((last_seen_at - first_seen_at).days / 365.25) + 1)
            return ArchiveHistoryResult(
                status="FOUND",
                first_seen_at=first_seen_at,
                last_seen_at=last_seen_at,
                snapshot_count=max(len(timestamps), 1 if latest_seen_at else 0),
                active_years=active_years,
                source_url=str(response.url),
            )
        except Exception as exc:  # noqa: BLE001
            return ArchiveHistoryResult(status="UNKNOWN", error=str(exc) or exc.__class__.__name__)


def score_history(result: ArchiveHistoryResult, *, now: datetime | None = None) -> tuple[int, str, list[str]]:
    now = now or datetime.utcnow()
    if result.status == "NO_ARCHIVE":
        return 0, "EMPTY", ["未发现公开网页历史"]
    if result.status != "FOUND":
        return 0, "UNKNOWN", [result.error or "缺少可靠历史数据"]

    score = 0
    reasons: list[str] = []

    if result.active_years >= 10:
        score += 40
        reasons.append("公开历史跨度超过 10 年")
    elif result.active_years >= 5:
        score += 30
        reasons.append("公开历史跨度超过 5 年")
    elif result.active_years >= 2:
        score += 20
        reasons.append("公开历史跨度超过 2 年")
    else:
        score += 10
        reasons.append("已有公开历史，但跨度较短")

    if result.snapshot_count >= ARCHIVE_SAMPLE_LIMIT:
        score += 30
        reasons.append(f"至少 {ARCHIVE_SAMPLE_LIMIT} 天公开快照")
    elif result.snapshot_count >= 50:
        score += 30
        reasons.append("公开快照较丰富")
    elif result.snapshot_count >= 20:
        score += 20
        reasons.append("存在连续历史痕迹")
    elif result.snapshot_count >= 5:
        score += 10
        reasons.append("存在一定历史痕迹")
    else:
        reasons.append("公开快照数量较少")

    if result.last_seen_at:
        days_since_last_seen = (now - result.last_seen_at).days
        if days_since_last_seen <= 365:
            score += 20
            reasons.append("近一年仍有公开快照")
        elif days_since_last_seen <= 730:
            score += 10
            reasons.append("两年内仍有公开快照")
        else:
            reasons.append("最近公开快照已超过两年")

    score = max(0, min(100, score))
    if score >= 80:
        grade = "RICH"
    elif score >= 60:
        grade = "SOLID"
    elif score >= 35:
        grade = "TRACE"
    else:
        grade = "THIN"
    return score, grade, reasons


async def refresh_history_for_lead(db: Session, lead: DomainLead) -> DomainLead:
    now = datetime.utcnow()
    result = await lookup_archive_history(lead.domain)
    score, grade, reasons = score_history(result, now=now)

    lead.history_status = result.status
    lead.archive_first_seen_at = result.first_seen_at
    lead.archive_last_seen_at = result.last_seen_at
    lead.archive_snapshot_count = result.snapshot_count
    lead.archive_active_years = result.active_years
    lead.archive_source_url = result.source_url
    lead.history_error = result.error
    lead.last_history_checked_at = now
    lead.history_score = score
    lead.history_grade = grade
    lead.history_reasons = json.dumps(reasons, ensure_ascii=False)

    db.add(
        build_activity(
            lead,
            event_type="HISTORY_CHECKED",
            title="已刷新历史画像",
            detail=f"{result.status} / {grade} / {score}",
        )
    )
    db.commit()
    db.refresh(lead)
    return lead
