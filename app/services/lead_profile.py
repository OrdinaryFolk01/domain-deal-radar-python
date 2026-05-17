from __future__ import annotations

import json
from datetime import datetime

from app.models import DomainLead


def _split_pipe(value: str) -> list[str]:
    return [item.strip() for item in (value or "").split("|") if item.strip()]


def _safe_breakdown(value: str) -> list[dict[str, object]]:
    try:
        data = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _safe_reasons(value: str) -> list[str]:
    try:
        data = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return [str(item) for item in data] if isinstance(data, list) else []


def _recommended_action(lead: DomainLead, *, now: datetime) -> str:
    has_contact = any([lead.emails, lead.phones, lead.wechats, lead.qqs])
    if lead.lead_status in {"BOUGHT", "RESOLD"}:
        return "已成交，沉淀复盘数据"
    if lead.lead_status == "GIVE_UP":
        return "已放弃，保留原因供后续校准"
    if lead.risk_flags and lead.score < 45:
        return "先人工复核风险，再决定是否继续"
    if lead.buyability_grade == "OPEN":
        return "可直接考虑注册，不必先找持有人"
    if lead.buyability_grade == "HOT":
        return "先做持有人触达，同时盯到期窗口"
    if not has_contact:
        return "先补联系方式"
    if lead.lead_status == "NEW":
        return "可发起首次联系"
    if lead.next_follow_up_at and lead.next_follow_up_at <= now:
        return "今天需要跟进"
    if lead.lead_status == "CONTACTED":
        return "等待回复，按计划二次跟进"
    if lead.lead_status in {"REPLIED", "NEGOTIATING"}:
        return "继续推进谈价"
    return "继续补充尽调信息"


def build_lead_profile(lead: DomainLead) -> dict[str, object]:
    now = datetime.utcnow()
    contacts = {
        "emails": len(_split_pipe(lead.emails)),
        "phones": len(_split_pipe(lead.phones)),
        "wechats": len(_split_pipe(lead.wechats)),
        "qqs": len(_split_pipe(lead.qqs)),
    }
    active_platforms = sum(
        1
        for value in [
            lead.baidu_pc_weight,
            lead.baidu_mobile_weight,
            lead.sogou_weight,
            lead.so_weight,
            lead.sm_weight,
            lead.toutiao_weight,
            lead.bing_weight,
        ]
        if value > 0
    )
    risk_level = "HIGH" if lead.risk_flags else "LOW"
    if lead.enhanced_risk_flags and risk_level == "LOW":
        risk_level = "MEDIUM"

    radar_grade = "A" if lead.score >= 85 else "B" if lead.score >= 65 else "C" if lead.score >= 45 else "D"
    contactability = "READY" if sum(contacts.values()) > 0 else "MISSING"
    follow_up_state = "DUE" if lead.next_follow_up_at and lead.next_follow_up_at <= now else "SCHEDULED" if lead.next_follow_up_at else "UNSET"

    signals: list[str] = []
    if active_platforms >= 3:
        signals.append(f"{active_platforms} 个平台有权重")
    elif active_platforms:
        signals.append(f"{active_platforms} 个平台有权重")
    if lead.site_health:
        signals.append(f"站点状态 {lead.site_health}")
    if sum(contacts.values()) > 0:
        signals.append(f"已找到 {sum(contacts.values())} 类联系方式")
    if lead.icp_number:
        signals.append("已提取备案号")
    if lead.last_emailed_at:
        signals.append("已有邮件触达")
    if lead.registrar_name:
        signals.append(f"注册商 {lead.registrar_name}")
    if lead.domain_expires_at:
        signals.append(f"距到期 {lead.days_until_expiry} 天")
    if lead.archive_active_years:
        signals.append(f"公开历史 {lead.archive_active_years} 年")
    if lead.archive_snapshot_count:
        snapshot_label = "100+" if lead.archive_snapshot_count >= 100 else str(lead.archive_snapshot_count)
        signals.append(f"历史快照 {snapshot_label} 天")

    return {
        "radar_grade": radar_grade,
        "risk_level": risk_level,
        "contactability": contactability,
        "follow_up_state": follow_up_state,
        "recommended_action": _recommended_action(lead, now=now),
        "contacts": contacts,
        "signals": signals,
        "score_breakdown": _safe_breakdown(lead.score_breakdown),
        "buyability": {
            "score": lead.buyability_score,
            "grade": lead.buyability_grade,
            "status": lead.registration_status,
            "reasons": _safe_reasons(lead.buyability_reasons),
        },
        "history": {
            "score": lead.history_score,
            "grade": lead.history_grade,
            "status": lead.history_status,
            "reasons": _safe_reasons(lead.history_reasons),
        },
    }
