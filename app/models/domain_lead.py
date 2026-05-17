from __future__ import annotations

from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class DomainLead(Base):
    __tablename__ = "domain_leads"
    __table_args__ = (UniqueConstraint("domain", name="uq_domain_leads_domain"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    domain: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    root_domain: Mapped[str] = mapped_column(String(255), default="")
    suffix: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(500), default="")

    baidu_pc_weight: Mapped[int] = mapped_column(Integer, default=0)
    baidu_mobile_weight: Mapped[int] = mapped_column(Integer, default=0)
    indexed_count: Mapped[int] = mapped_column(Integer, default=0)

    # 爱站权重综合字段：rank.aizhan.com 可看到多搜索平台权重与收录数据。
    # indexed_count 继续作为百度收录/默认收录字段，兼容旧数据。
    sogou_weight: Mapped[int] = mapped_column(Integer, default=0)
    so_weight: Mapped[int] = mapped_column(Integer, default=0)
    sm_weight: Mapped[int] = mapped_column(Integer, default=0)
    toutiao_weight: Mapped[int] = mapped_column(Integer, default=0)
    bing_weight: Mapped[int] = mapped_column(Integer, default=0)
    sogou_indexed_count: Mapped[int] = mapped_column(Integer, default=0)
    so_indexed_count: Mapped[int] = mapped_column(Integer, default=0)
    sm_indexed_count: Mapped[int] = mapped_column(Integer, default=0)
    toutiao_indexed_count: Mapped[int] = mapped_column(Integer, default=0)
    bing_indexed_count: Mapped[int] = mapped_column(Integer, default=0)

    icp_type: Mapped[str] = mapped_column(String(100), default="")
    last_update: Mapped[str] = mapped_column(String(50), default="")
    remark: Mapped[str] = mapped_column(Text, default="")
    source_provider: Mapped[str] = mapped_column(String(100), default="", index=True)
    source_url: Mapped[str] = mapped_column(String(1000), default="")

    status_code: Mapped[str] = mapped_column(String(20), default="")
    final_url: Mapped[str] = mapped_column(String(1000), default="")
    emails: Mapped[str] = mapped_column(Text, default="")
    phones: Mapped[str] = mapped_column(Text, default="")
    wechats: Mapped[str] = mapped_column(Text, default="")
    qqs: Mapped[str] = mapped_column(Text, default="")

    # 批量抓取任务中心字段
    crawl_status: Mapped[str] = mapped_column(String(50), default="PENDING", index=True)
    crawl_error: Mapped[str] = mapped_column(Text, default="")
    crawl_pages_done: Mapped[int] = mapped_column(Integer, default=0)
    crawl_pages_total: Mapped[int] = mapped_column(Integer, default=0)
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


    # 增强分析字段：用于 DNS / SSL / 备案号 / 页面健康度 / 停放页风险等
    analysis_status: Mapped[str] = mapped_column(String(50), default="PENDING", index=True)
    analysis_error: Mapped[str] = mapped_column(Text, default="")
    dns_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_ips: Mapped[str] = mapped_column(Text, default="")
    ssl_status: Mapped[str] = mapped_column(String(50), default="")
    ssl_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ssl_days_left: Mapped[int] = mapped_column(Integer, default=0)
    icp_number: Mapped[str] = mapped_column(String(255), default="")
    public_security_record: Mapped[str] = mapped_column(String(255), default="")
    site_health: Mapped[str] = mapped_column(String(80), default="")
    enhanced_risk_flags: Mapped[str] = mapped_column(Text, default="")
    last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    discovered_from: Mapped[str] = mapped_column(String(255), default="")

    # 注册情报 / 可买性字段
    registration_status: Mapped[str] = mapped_column(String(50), default="UNCHECKED", index=True)
    registrar_name: Mapped[str] = mapped_column(String(255), default="")
    registrar_handle: Mapped[str] = mapped_column(String(255), default="")
    domain_registered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    domain_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    domain_age_days: Mapped[int] = mapped_column(Integer, default=0)
    days_until_expiry: Mapped[int] = mapped_column(Integer, default=0)
    rdap_status: Mapped[str] = mapped_column(Text, default="")
    rdap_source_url: Mapped[str] = mapped_column(String(1200), default="")
    rdap_error: Mapped[str] = mapped_column(Text, default="")
    last_registration_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    buyability_score: Mapped[int] = mapped_column(Integer, default=0)
    buyability_grade: Mapped[str] = mapped_column(String(50), default="UNKNOWN", index=True)
    buyability_reasons: Mapped[str] = mapped_column(Text, default="[]")

    # 历史画像字段：当前先接公开 Web Archive 线索，后续可继续并入历史 DNS / 风险情报。
    history_status: Mapped[str] = mapped_column(String(50), default="UNCHECKED", index=True)
    archive_first_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    archive_last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    archive_snapshot_count: Mapped[int] = mapped_column(Integer, default=0)
    archive_active_years: Mapped[int] = mapped_column(Integer, default=0)
    archive_source_url: Mapped[str] = mapped_column(String(1200), default="")
    history_error: Mapped[str] = mapped_column(Text, default="")
    last_history_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    history_score: Mapped[int] = mapped_column(Integer, default=0)
    history_grade: Mapped[str] = mapped_column(String(50), default="UNKNOWN", index=True)
    history_reasons: Mapped[str] = mapped_column(Text, default="[]")

    score: Mapped[int] = mapped_column(Integer, default=0)
    score_breakdown: Mapped[str] = mapped_column(Text, default="[]")
    risk_flags: Mapped[str] = mapped_column(Text, default="")
    suggestion: Mapped[str] = mapped_column(String(255), default="")
    first_offer: Mapped[int] = mapped_column(Integer, default=0)
    max_offer: Mapped[int] = mapped_column(Integer, default=0)

    lead_status: Mapped[str] = mapped_column(String(50), default="NEW", index=True)
    contact_note: Mapped[str] = mapped_column(Text, default="")
    contact_message: Mapped[str] = mapped_column(Text, default="")
    next_action: Mapped[str] = mapped_column(String(255), default="")
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_email_to: Mapped[str] = mapped_column(String(500), default="")
    last_email_subject: Mapped[str] = mapped_column(String(500), default="")
    last_emailed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deal_price: Mapped[int] = mapped_column(Integer, default=0)
    resell_price: Mapped[int] = mapped_column(Integer, default=0)
    give_up_reason: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CrawlTask(Base):
    __tablename__ = "crawl_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("domain_leads.id", ondelete="CASCADE"), index=True, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), index=True, default="")
    task_type: Mapped[str] = mapped_column(String(50), default="SITE_CRAWL")
    status: Mapped[str] = mapped_column(String(50), index=True, default="PENDING")
    pages_total: Mapped[int] = mapped_column(Integer, default=0)
    pages_done: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CrawlLog(Base):
    __tablename__ = "crawl_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("crawl_tasks.id", ondelete="SET NULL"), index=True, nullable=True)
    batch_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("domain_leads.id", ondelete="CASCADE"), index=True, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), index=True, default="")
    url: Mapped[str] = mapped_column(String(1200), default="")
    status_code: Mapped[str] = mapped_column(String(20), default="")
    final_url: Mapped[str] = mapped_column(String(1200), default="")
    title: Mapped[str] = mapped_column(String(500), default="")
    emails: Mapped[str] = mapped_column(Text, default="")
    phones: Mapped[str] = mapped_column(Text, default="")
    wechats: Mapped[str] = mapped_column(Text, default="")
    qqs: Mapped[str] = mapped_column(Text, default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class EmailLog(Base):
    __tablename__ = "email_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("domain_leads.id", ondelete="CASCADE"), index=True, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), index=True, default="")
    to_email: Mapped[str] = mapped_column(String(500), default="")
    subject: Mapped[str] = mapped_column(String(500), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(50), index=True, default="PENDING")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LeadActivity(Base):
    __tablename__ = "lead_activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("domain_leads.id", ondelete="CASCADE"), index=True, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), index=True, default="")
    event_type: Mapped[str] = mapped_column(String(80), index=True, default="")
    title: Mapped[str] = mapped_column(String(255), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class DiscoveryTask(Base):
    __tablename__ = "discovery_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_id: Mapped[str] = mapped_column(String(100), index=True, default="")
    source_type: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(50), index=True, default="PENDING")
    keyword: Mapped[str] = mapped_column(Text, default="")
    total: Mapped[int] = mapped_column(Integer, default=0)
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
