from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

from sqlalchemy.orm import Session

from app.models import DomainLead
from app.services.activities import build_activity
from app.services.scoring import normalize_domain
from app.services.scrapling_fetch import create_scrapling_session, raise_for_status, response_json, response_status

IANA_RDAP_BOOTSTRAP_URL = "https://data.iana.org/rdap/dns.json"
_BOOTSTRAP_CACHE: dict[str, object] | None = None
_BOOTSTRAP_FETCHED_AT: datetime | None = None


@dataclass(slots=True)
class RegistrationLookupResult:
    status: str
    registrar_name: str = ""
    registrar_handle: str = ""
    registered_at: datetime | None = None
    expires_at: datetime | None = None
    rdap_status: list[str] | None = None
    source_url: str = ""
    error: str = ""


def _parse_rdap_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _extract_event(events: list[dict[str, object]], action: str) -> datetime | None:
    for item in events:
        if item.get("eventAction") == action:
            return _parse_rdap_datetime(str(item.get("eventDate") or ""))
    return None


def _extract_vcard_name(entity: dict[str, object]) -> str:
    vcard_array = entity.get("vcardArray")
    if not isinstance(vcard_array, list) or len(vcard_array) < 2 or not isinstance(vcard_array[1], list):
        return ""
    for entry in vcard_array[1]:
        if isinstance(entry, list) and len(entry) >= 4 and entry[0] in {"fn", "org"}:
            return str(entry[3] or "")
    return ""


def _extract_registrar(payload: dict[str, object]) -> tuple[str, str]:
    entities = payload.get("entities")
    if not isinstance(entities, list):
        return "", ""
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        roles = entity.get("roles")
        if isinstance(roles, list) and "registrar" in roles:
            return _extract_vcard_name(entity), str(entity.get("handle") or "")
    return "", ""


def _find_service_base_url(domain: str, bootstrap: dict[str, object]) -> str:
    labels = domain.lower().strip(".").split(".")
    services = bootstrap.get("services")
    if not isinstance(services, list):
        return ""

    best_match = ""
    best_urls: list[str] = []
    for service in services:
        if not isinstance(service, list) or len(service) != 2:
            continue
        suffixes, urls = service
        if not isinstance(suffixes, list) or not isinstance(urls, list):
            continue
        for suffix in suffixes:
            suffix_text = str(suffix).lower()
            suffix_labels = suffix_text.split(".")
            if labels[-len(suffix_labels) :] == suffix_labels and len(suffix_text) > len(best_match):
                best_match = suffix_text
                best_urls = [str(item) for item in urls if item]
    return best_urls[0] if best_urls else ""


async def _load_bootstrap(client: object) -> dict[str, object]:
    global _BOOTSTRAP_CACHE, _BOOTSTRAP_FETCHED_AT
    now = datetime.utcnow()
    if _BOOTSTRAP_CACHE is not None and _BOOTSTRAP_FETCHED_AT and now - _BOOTSTRAP_FETCHED_AT < timedelta(hours=24):
        return _BOOTSTRAP_CACHE
    response = await client.get(IANA_RDAP_BOOTSTRAP_URL)
    raise_for_status(response)
    payload = response_json(response)
    if not isinstance(payload, dict):
        raise RuntimeError("IANA RDAP bootstrap 返回格式异常")
    _BOOTSTRAP_CACHE = payload
    _BOOTSTRAP_FETCHED_AT = now
    return payload


async def lookup_registration(domain: str, *, timeout_seconds: int = 12) -> RegistrationLookupResult:
    normalized = normalize_domain(domain)
    if not normalized or "." not in normalized:
        return RegistrationLookupResult(status="UNKNOWN", error="域名格式无效")

    headers = {"Accept": "application/rdap+json, application/json"}
    async with create_scrapling_session(timeout_seconds=timeout_seconds, headers=headers) as client:
        try:
            bootstrap = await _load_bootstrap(client)
            base_url = _find_service_base_url(normalized, bootstrap)
            if not base_url:
                return RegistrationLookupResult(status="UNKNOWN", error="未找到该后缀的 RDAP 服务")

            query_url = urljoin(base_url if base_url.endswith("/") else f"{base_url}/", f"domain/{normalized}")
            response = await client.get(query_url)
            if response_status(response) == 404:
                return RegistrationLookupResult(status="AVAILABLE", source_url=query_url)
            raise_for_status(response)
            payload = response_json(response)
            if not isinstance(payload, dict):
                return RegistrationLookupResult(status="UNKNOWN", source_url=query_url, error="RDAP 返回格式异常")

            events = payload.get("events") if isinstance(payload.get("events"), list) else []
            registered_at = _extract_event(events, "registration")
            expires_at = _extract_event(events, "expiration")
            registrar_name, registrar_handle = _extract_registrar(payload)
            statuses = [str(item) for item in payload.get("status", [])] if isinstance(payload.get("status"), list) else []
            return RegistrationLookupResult(
                status="REGISTERED",
                registrar_name=registrar_name,
                registrar_handle=registrar_handle,
                registered_at=registered_at,
                expires_at=expires_at,
                rdap_status=statuses,
                source_url=query_url,
            )
        except Exception as exc:  # noqa: BLE001
            return RegistrationLookupResult(status="UNKNOWN", error=str(exc))


def score_buyability(result: RegistrationLookupResult, *, now: datetime | None = None) -> tuple[int, str, list[str]]:
    now = now or datetime.utcnow()
    reasons: list[str] = []

    if result.status == "AVAILABLE":
        return 95, "OPEN", ["RDAP 未返回已注册对象，可作为直接注册候选"]
    if result.status != "REGISTERED":
        return 0, "UNKNOWN", [result.error or "缺少可靠注册数据"]

    score = 35
    reasons.append("已注册，需联系持有人或等待窗口")

    if result.registered_at:
        age_days = (now - result.registered_at).days
        if age_days >= 365 * 5:
            score += 10
            reasons.append("域名历史较长，资产质量更像可收购对象")

    if result.expires_at:
        days = (result.expires_at - now).days
        if days < 0:
            score += 40
            reasons.append("已过期，可能进入生命周期后段")
        elif days <= 30:
            score += 30
            reasons.append("30 天内到期")
        elif days <= 90:
            score += 20
            reasons.append("90 天内到期")
        elif days <= 180:
            score += 10
            reasons.append("180 天内到期")
        elif days > 365:
            score -= 10
            reasons.append("距离到期超过 1 年")
    else:
        reasons.append("未获得到期时间")

    statuses = {item.lower() for item in (result.rdap_status or [])}
    if {"pending delete", "redemption period"} & statuses:
        score += 40
        reasons.append("处于删除 / 赎回相关状态")
    if any("transfer prohibited" in item for item in statuses):
        reasons.append("存在转移锁，成交需额外确认")

    score = max(0, min(100, score))
    if score >= 80:
        grade = "HOT"
    elif score >= 60:
        grade = "WARM"
    elif score >= 40:
        grade = "WATCH"
    else:
        grade = "COLD"
    return score, grade, reasons


async def refresh_registration_for_lead(db: Session, lead: DomainLead) -> DomainLead:
    now = datetime.utcnow()
    result = await lookup_registration(lead.domain)
    score, grade, reasons = score_buyability(result, now=now)

    lead.registration_status = result.status
    lead.registrar_name = result.registrar_name
    lead.registrar_handle = result.registrar_handle
    lead.domain_registered_at = result.registered_at
    lead.domain_expires_at = result.expires_at
    lead.domain_age_days = (now - result.registered_at).days if result.registered_at else 0
    lead.days_until_expiry = (result.expires_at - now).days if result.expires_at else 0
    lead.rdap_status = " | ".join(result.rdap_status or [])
    lead.rdap_source_url = result.source_url
    lead.rdap_error = result.error
    lead.last_registration_checked_at = now
    lead.buyability_score = score
    lead.buyability_grade = grade
    lead.buyability_reasons = json.dumps(reasons, ensure_ascii=False)

    db.add(
        build_activity(
            lead,
            event_type="REGISTRATION_CHECKED",
            title="已刷新注册情报",
            detail=f"{result.status} / {grade} / {score}",
        )
    )
    db.commit()
    db.refresh(lead)
    return lead
