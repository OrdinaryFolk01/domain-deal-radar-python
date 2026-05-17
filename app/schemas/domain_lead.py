from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class LeadUpdate(BaseModel):
    lead_status: str | None = None
    contact_note: str | None = None
    contact_message: str | None = None
    next_action: str | None = None
    next_follow_up_at: datetime | None = None
    deal_price: int | None = Field(default=None, ge=0)
    resell_price: int | None = Field(default=None, ge=0)
    give_up_reason: str | None = None
    remark: str | None = None


class EmailSendRequest(BaseModel):
    to: str = Field(..., min_length=3, description="收件人邮箱")
    subject: str = Field(default="", description="邮件主题")
    body: str = Field(..., min_length=1, description="邮件正文")


class EmailSendResponse(BaseModel):
    ok: bool
    message: str
    log_id: int | None = None


class EmailLogOut(BaseModel):
    id: int
    lead_id: int
    domain: str
    to_email: str
    subject: str
    body: str
    status: str
    error_message: str
    created_at: datetime
    sent_at: datetime | None

    model_config = {"from_attributes": True}


class LeadActivityOut(BaseModel):
    id: int
    lead_id: int
    domain: str
    event_type: str
    title: str
    detail: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ManualLeadCreate(BaseModel):
    domains: str = Field(..., min_length=1, description="单个或多个域名，支持换行、逗号、空格分隔")
    title: str = ""
    remark: str = ""
    auto_crawl: bool = False
    auto_analyze: bool = False


class LeadOut(BaseModel):
    id: int
    domain: str
    root_domain: str
    suffix: str
    title: str
    baidu_pc_weight: int
    baidu_mobile_weight: int
    indexed_count: int
    sogou_weight: int
    so_weight: int
    sm_weight: int
    toutiao_weight: int
    bing_weight: int
    sogou_indexed_count: int
    so_indexed_count: int
    sm_indexed_count: int
    toutiao_indexed_count: int
    bing_indexed_count: int
    icp_type: str
    last_update: str
    remark: str
    source_provider: str
    source_url: str
    status_code: str
    final_url: str
    emails: str
    phones: str
    wechats: str
    qqs: str
    crawl_status: str
    crawl_error: str
    crawl_pages_done: int
    crawl_pages_total: int
    last_crawled_at: datetime | None
    analysis_status: str
    analysis_error: str
    dns_resolved: bool
    resolved_ips: str
    ssl_status: str
    ssl_expires_at: datetime | None
    ssl_days_left: int
    icp_number: str
    public_security_record: str
    site_health: str
    enhanced_risk_flags: str
    last_analyzed_at: datetime | None
    discovered_from: str
    registration_status: str
    registrar_name: str
    registrar_handle: str
    domain_registered_at: datetime | None
    domain_expires_at: datetime | None
    domain_age_days: int
    days_until_expiry: int
    rdap_status: str
    rdap_source_url: str
    rdap_error: str
    last_registration_checked_at: datetime | None
    buyability_score: int
    buyability_grade: str
    buyability_reasons: str
    history_status: str
    archive_first_seen_at: datetime | None
    archive_last_seen_at: datetime | None
    archive_snapshot_count: int
    archive_active_years: int
    archive_source_url: str
    history_error: str
    last_history_checked_at: datetime | None
    history_score: int
    history_grade: str
    history_reasons: str
    score: int
    score_breakdown: str
    risk_flags: str
    suggestion: str
    first_offer: int
    max_offer: int
    lead_status: str
    contact_note: str
    contact_message: str
    next_action: str
    next_follow_up_at: datetime | None
    last_contacted_at: datetime | None
    last_email_to: str
    last_email_subject: str
    last_emailed_at: datetime | None
    deal_price: int
    resell_price: int
    give_up_reason: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CrawlTaskOut(BaseModel):
    id: int
    batch_id: str
    lead_id: int
    domain: str
    task_type: str
    status: str
    pages_total: int
    pages_done: int
    error_message: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class CrawlLogOut(BaseModel):
    id: int
    task_id: int | None
    batch_id: str
    lead_id: int
    domain: str
    url: str
    status_code: str
    final_url: str
    title: str
    emails: str
    phones: str
    wechats: str
    qqs: str
    error_message: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SeedDiscoveryRequest(BaseModel):
    keywords: str
    suffixes: list[str] = Field(default_factory=lambda: ["com", "cn", "com.cn", "net", "ai", "app", "io"])
    prefixes: list[str] = Field(default_factory=lambda: ["", "ai", "my", "go", "get", "best", "52"])
    limit: int = Field(default=500, ge=1, le=5000)


class SearchDiscoveryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="中文或英文检索词")
    limit: int = Field(default=10, ge=1, le=30)
    auto_crawl: bool = True


class DiscoveryTaskOut(BaseModel):
    id: int
    provider_id: str
    source_type: str
    status: str
    keyword: str
    total: int
    created_count: int
    updated_count: int
    skipped_count: int
    error_message: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}
