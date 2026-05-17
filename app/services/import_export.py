from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DomainLead
from app.providers import get_provider
from app.providers.csv_provider import GenericCsvProvider
from app.services.scoring import normalize_domain, score_lead, to_int

CSV_FIELD_ALIASES = {
    "domain": ["domain", "域名", "网站", "网址"],
    "title": ["title", "标题", "网站标题"],
    "baidu_pc_weight": ["baiduPcWeight", "baidu_pc_weight", "PC权重", "百度PC权重", "百度权重"],
    "baidu_mobile_weight": ["baiduMobileWeight", "baidu_mobile_weight", "移动权重", "百度移动权重", "移动端权重"],
    "indexed_count": ["indexedCount", "indexed_count", "收录", "收录量", "百度收录", "百度收录量"],
    "sogou_weight": ["sogouWeight", "sogou_weight", "搜狗权重"],
    "so_weight": ["soWeight", "so_weight", "360权重", "好搜权重"],
    "sm_weight": ["smWeight", "sm_weight", "神马权重"],
    "toutiao_weight": ["toutiaoWeight", "toutiao_weight", "头条权重"],
    "bing_weight": ["bingWeight", "bing_weight", "必应权重", "Bing权重"],
    "sogou_indexed_count": ["sogouIndexedCount", "sogou_indexed_count", "搜狗收录", "搜狗收录量"],
    "so_indexed_count": ["soIndexedCount", "so_indexed_count", "360收录", "360收录量"],
    "sm_indexed_count": ["smIndexedCount", "sm_indexed_count", "神马收录", "神马收录量"],
    "toutiao_indexed_count": ["toutiaoIndexedCount", "toutiao_indexed_count", "头条收录", "头条收录量"],
    "bing_indexed_count": ["bingIndexedCount", "bing_indexed_count", "必应收录", "必应收录量", "Bing收录"],
    "icp_type": ["icpType", "icp_type", "备案类型", "备案主体", "主体类型"],
    "last_update": ["lastUpdate", "last_update", "最近更新", "更新时间", "最后更新"],
    "remark": ["remark", "备注"],
}

EXPORT_FIELDS = [
    "id",
    "domain",
    "root_domain",
    "suffix",
    "title",
    "baidu_pc_weight",
    "baidu_mobile_weight",
    "indexed_count",
    "sogou_weight",
    "so_weight",
    "sm_weight",
    "toutiao_weight",
    "bing_weight",
    "sogou_indexed_count",
    "so_indexed_count",
    "sm_indexed_count",
    "toutiao_indexed_count",
    "bing_indexed_count",
    "icp_type",
    "last_update",
    "remark",
    "source_provider",
    "source_url",
    "status_code",
    "final_url",
    "emails",
    "phones",
    "wechats",
    "qqs",
    "crawl_status",
    "crawl_error",
    "crawl_pages_done",
    "crawl_pages_total",
    "last_crawled_at",
    "analysis_status",
    "analysis_error",
    "dns_resolved",
    "resolved_ips",
    "ssl_status",
    "ssl_expires_at",
    "ssl_days_left",
    "icp_number",
    "public_security_record",
    "site_health",
    "enhanced_risk_flags",
    "last_analyzed_at",
    "discovered_from",
    "registration_status",
    "registrar_name",
    "registrar_handle",
    "domain_registered_at",
    "domain_expires_at",
    "domain_age_days",
    "days_until_expiry",
    "rdap_status",
    "rdap_source_url",
    "rdap_error",
    "last_registration_checked_at",
    "buyability_score",
    "buyability_grade",
    "buyability_reasons",
    "history_status",
    "archive_first_seen_at",
    "archive_last_seen_at",
    "archive_snapshot_count",
    "archive_active_years",
    "archive_source_url",
    "history_error",
    "last_history_checked_at",
    "history_score",
    "history_grade",
    "history_reasons",
    "score",
    "score_breakdown",
    "risk_flags",
    "suggestion",
    "first_offer",
    "max_offer",
    "lead_status",
    "contact_note",
    "contact_message",
    "next_action",
    "next_follow_up_at",
    "last_contacted_at",
    "last_email_to",
    "last_email_subject",
    "last_emailed_at",
    "deal_price",
    "resell_price",
    "give_up_reason",
    "created_at",
    "updated_at",
]


def _get_value(row: dict[str, str], canonical: str) -> str:
    for key in CSV_FIELD_ALIASES[canonical]:
        if key in row:
            return row.get(key, "")
    return ""


def parse_csv_content(content: bytes) -> list[dict[str, Any]]:
    provider = GenericCsvProvider()
    return provider.records_to_rows(provider.parse_file(content, filename="upload.csv"))


def parse_provider_file(provider_id: str, content: bytes, *, filename: str = "") -> list[dict[str, Any]]:
    provider = get_provider(provider_id)
    return [record.to_lead_row() for record in provider.parse_file(content, filename=filename)]


def preview_provider_file(provider_id: str, content: bytes, *, filename: str = "", limit: int = 20) -> dict[str, Any]:
    rows = parse_provider_file(provider_id, content, filename=filename)
    return {
        "provider_id": provider_id,
        "total": len(rows),
        "rows": rows[:limit],
    }

def upsert_leads_from_rows(db: Session, rows: list[dict[str, Any]]) -> dict[str, int]:
    created = 0
    updated = 0

    for row in rows:
        domain = normalize_domain(row["domain"])
        if not domain:
            continue

        score = score_lead(row)
        existing = db.scalar(select(DomainLead).where(DomainLead.domain == domain))

        if existing is None:
            lead = DomainLead(domain=domain)
            db.add(lead)
            created += 1
        else:
            lead = existing
            updated += 1

        lead.root_domain = score.root_domain
        lead.suffix = score.suffix
        lead.title = row.get("title") or lead.title or ""
        lead.baidu_pc_weight = to_int(row.get("baidu_pc_weight"))
        lead.baidu_mobile_weight = to_int(row.get("baidu_mobile_weight"))
        lead.indexed_count = to_int(row.get("indexed_count"))
        lead.sogou_weight = to_int(row.get("sogou_weight")) or lead.sogou_weight or 0
        lead.so_weight = to_int(row.get("so_weight")) or lead.so_weight or 0
        lead.sm_weight = to_int(row.get("sm_weight")) or lead.sm_weight or 0
        lead.toutiao_weight = to_int(row.get("toutiao_weight")) or lead.toutiao_weight or 0
        lead.bing_weight = to_int(row.get("bing_weight")) or lead.bing_weight or 0
        lead.sogou_indexed_count = to_int(row.get("sogou_indexed_count")) or lead.sogou_indexed_count or 0
        lead.so_indexed_count = to_int(row.get("so_indexed_count")) or lead.so_indexed_count or 0
        lead.sm_indexed_count = to_int(row.get("sm_indexed_count")) or lead.sm_indexed_count or 0
        lead.toutiao_indexed_count = to_int(row.get("toutiao_indexed_count")) or lead.toutiao_indexed_count or 0
        lead.bing_indexed_count = to_int(row.get("bing_indexed_count")) or lead.bing_indexed_count or 0
        lead.icp_type = row.get("icp_type") or lead.icp_type or ""
        lead.last_update = row.get("last_update") or lead.last_update or ""
        lead.remark = row.get("remark") or lead.remark or ""
        lead.source_provider = row.get("source_provider") or lead.source_provider or ""
        lead.source_url = row.get("source_url") or lead.source_url or ""
        lead.discovered_from = row.get("discovered_from") or lead.discovered_from or ""
        lead.score = score.score
        lead.score_breakdown = json.dumps(score.breakdown, ensure_ascii=False)
        lead.risk_flags = " | ".join(score.risk_flags)
        lead.suggestion = score.suggestion
        lead.first_offer = score.first_offer
        lead.max_offer = score.max_offer

    db.commit()
    return {"created": created, "updated": updated, "total": created + updated}


def serialize_lead(lead: DomainLead) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for field in EXPORT_FIELDS:
        value = getattr(lead, field)
        if isinstance(value, datetime):
            value = value.isoformat(sep=" ", timespec="seconds")
        data[field] = value
    return data


def export_csv(leads: list[DomainLead]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=EXPORT_FIELDS)
    writer.writeheader()
    for lead in leads:
        writer.writerow(serialize_lead(lead))
    return output.getvalue()


def export_json(leads: list[DomainLead]) -> str:
    return json.dumps([serialize_lead(lead) for lead in leads], ensure_ascii=False, indent=2)


def restore_from_json(db: Session, content: bytes) -> dict[str, int]:
    rows = json.loads(content.decode("utf-8"))
    if not isinstance(rows, list):
        raise ValueError("JSON 顶层必须是数组")

    created = 0
    updated = 0
    editable_fields = [field for field in EXPORT_FIELDS if field not in {"id", "created_at", "updated_at"}]

    for row in rows:
        if not isinstance(row, dict):
            continue
        domain = normalize_domain(str(row.get("domain") or ""))
        if not domain:
            continue

        existing = db.scalar(select(DomainLead).where(DomainLead.domain == domain))
        if existing is None:
            lead = DomainLead(domain=domain)
            db.add(lead)
            created += 1
        else:
            lead = existing
            updated += 1

        for field in editable_fields:
            if field in row:
                current_value = getattr(lead, field)
                raw_value = row[field]
                if isinstance(current_value, str):
                    setattr(lead, field, raw_value or "")
                elif isinstance(current_value, bool):
                    setattr(lead, field, bool(raw_value))
                elif isinstance(current_value, datetime) or field.endswith("_at"):
                    if raw_value:
                        try:
                            setattr(lead, field, datetime.fromisoformat(str(raw_value)))
                        except ValueError:
                            setattr(lead, field, None)
                    else:
                        setattr(lead, field, None)
                else:
                    setattr(lead, field, raw_value or 0)

    db.commit()
    return {"created": created, "updated": updated, "total": created + updated}
