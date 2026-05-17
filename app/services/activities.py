from __future__ import annotations

from app.models import DomainLead, LeadActivity


def build_activity(
    lead: DomainLead,
    *,
    event_type: str,
    title: str,
    detail: str = "",
) -> LeadActivity:
    return LeadActivity(
        lead_id=lead.id,
        domain=lead.domain,
        event_type=event_type,
        title=title,
        detail=detail,
    )
