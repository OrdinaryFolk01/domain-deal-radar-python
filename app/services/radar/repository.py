from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.orm import Session

from app.models import DomainCandidate
from app.services.radar.constants import CANDIDATE_DISCOVERED
from app.services.radar.providers import SearchResult
from app.services.scoring import get_domain_parts, normalize_domain


def safe_json_loads(value: str, fallback: Any) -> Any:
    try:
        data = json.loads(value or "")
    except json.JSONDecodeError:
        return fallback
    return data if data is not None else fallback


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _append_unique(existing_json: str, value: str) -> str:
    values = safe_json_loads(existing_json, [])
    if not isinstance(values, list):
        values = []
    if value and value not in values:
        values.append(value)
    return json_dumps(values)


class CandidateRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, candidate_id: int) -> DomainCandidate | None:
        return self.db.get(DomainCandidate, candidate_id)

    def list(
        self,
        *,
        status: str = "",
        keyword: str = "",
        sources: list[str] | None = None,
        ids: list[int] | None = None,
        limit: int = 200,
    ) -> list[DomainCandidate]:
        stmt = select(DomainCandidate)
        clauses = []
        if ids is not None:
            if not ids:
                return []
            clauses.append(DomainCandidate.id.in_(ids))
        if status:
            clauses.append(DomainCandidate.status == status)
        if keyword:
            like = f"%{keyword}%"
            clauses.append(
                or_(
                    DomainCandidate.domain.like(like),
                    DomainCandidate.title.like(like),
                    DomainCandidate.keyword.like(like),
                    DomainCandidate.keywords.like(like),
                    DomainCandidate.reject_reason.like(like),
                )
            )
        selected_sources = [source.strip() for source in sources or [] if source.strip()]
        if selected_sources:
            source_clauses = []
            for source in selected_sources:
                source_clauses.append(DomainCandidate.search_engine == source)
                source_clauses.append(DomainCandidate.search_engines.like(f'%"{source}"%'))
            clauses.append(or_(*source_clauses))
        if clauses:
            stmt = stmt.where(and_(*clauses))
        stmt = stmt.order_by(desc(DomainCandidate.updated_at), desc(DomainCandidate.created_at)).limit(limit)
        return list(self.db.scalars(stmt))

    def upsert_search_result(
        self,
        result: SearchResult,
        *,
        keyword: str,
        status: str = CANDIDATE_DISCOVERED,
        reject_reason: str = "",
    ) -> tuple[DomainCandidate, bool]:
        domain = normalize_domain(result.domain)
        root_domain, suffix = get_domain_parts(domain)
        existing = self.db.scalar(select(DomainCandidate).where(DomainCandidate.domain == domain))
        created = False
        now = datetime.utcnow()

        if existing is None:
            candidate = DomainCandidate(
                domain=domain,
                root_domain=root_domain,
                suffix=suffix,
                title=result.title,
                summary=result.summary,
                search_engine=result.engine,
                search_engines=json_dumps([result.engine] if result.engine else []),
                keyword=keyword,
                keywords=json_dumps([keyword] if keyword else []),
                source_url=result.url,
                source_urls=json_dumps([result.url] if result.url else []),
                status=status,
                reject_reason=reject_reason,
                created_at=now,
                updated_at=now,
            )
            self.db.add(candidate)
            created = True
        else:
            candidate = existing
            candidate.title = candidate.title or result.title
            candidate.summary = candidate.summary or result.summary
            candidate.search_engine = candidate.search_engine or result.engine
            candidate.keyword = candidate.keyword or keyword
            candidate.source_url = candidate.source_url or result.url
            candidate.search_engines = _append_unique(candidate.search_engines, result.engine)
            candidate.keywords = _append_unique(candidate.keywords, keyword)
            candidate.source_urls = _append_unique(candidate.source_urls, result.url)
            if candidate.status == CANDIDATE_DISCOVERED and status != CANDIDATE_DISCOVERED:
                candidate.status = status
                candidate.reject_reason = reject_reason
            candidate.updated_at = now

        self.db.flush()
        return candidate, created

    def update_snapshots(
        self,
        candidate: DomainCandidate,
        *,
        status: str | None = None,
        reject_reason: str | None = None,
        weight_snapshot: dict[str, Any] | None = None,
        site_index_snapshot: dict[str, Any] | None = None,
        whois_snapshot: dict[str, Any] | None = None,
        ip_snapshot: dict[str, Any] | None = None,
        contact_snapshot: dict[str, Any] | None = None,
        priority_score: int | None = None,
    ) -> DomainCandidate:
        if status is not None:
            candidate.status = status
        if reject_reason is not None:
            candidate.reject_reason = reject_reason
        if weight_snapshot is not None:
            candidate.weight_snapshot = json_dumps(weight_snapshot)
        if site_index_snapshot is not None:
            candidate.site_index_snapshot = json_dumps(site_index_snapshot)
        if whois_snapshot is not None:
            candidate.whois_snapshot = json_dumps(whois_snapshot)
        if ip_snapshot is not None:
            candidate.ip_snapshot = json_dumps(ip_snapshot)
        if contact_snapshot is not None:
            candidate.contact_snapshot = json_dumps(contact_snapshot)
        if priority_score is not None:
            candidate.priority_score = priority_score
        candidate.updated_at = datetime.utcnow()
        self.db.add(candidate)
        self.db.flush()
        return candidate

    def mark_promoted(self, candidate: DomainCandidate, lead_id: int) -> DomainCandidate:
        candidate.status = "PROMOTED"
        candidate.promoted_lead_id = lead_id
        candidate.reject_reason = ""
        candidate.updated_at = datetime.utcnow()
        self.db.add(candidate)
        self.db.flush()
        return candidate
