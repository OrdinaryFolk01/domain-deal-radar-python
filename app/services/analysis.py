from __future__ import annotations

import asyncio
import json
import re
import socket
import ssl
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models import DomainLead
from app.services.crawler import crawl_site
from app.services.scoring import score_lead

ICP_PATTERN = re.compile(
    r"([京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z]?ICP备\s*\d{6,}号(?:-\d+)?)"
)
PUBLIC_SECURITY_PATTERN = re.compile(
    r"([京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼]\S{0,8}公网安备\s*\d{10,}号)"
)
PARKING_KEYWORDS = [
    "domain for sale",
    "buy this domain",
    "this domain is for sale",
    "sedo domain parking",
    "afternic",
    "parkingcrew",
    "dan.com",
    "hugedomains",
    "域名出售",
    "出售该域名",
    "购买此域名",
    "停放页",
]
GARBLED_PATTERN = re.compile(r"[��]{2,}|(?:\\x[0-9a-fA-F]{2}){3,}")


@dataclass(slots=True)
class DomainAnalysisResult:
    status: str
    dns_resolved: bool
    resolved_ips: list[str]
    ssl_status: str
    ssl_expires_at: datetime | None
    ssl_days_left: int
    icp_number: str
    public_security_record: str
    site_health: str
    enhanced_risk_flags: list[str]
    error: str = ""


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def resolve_domain(domain: str) -> tuple[bool, list[str], str]:
    try:
        infos = socket.getaddrinfo(domain, None, proto=socket.IPPROTO_TCP)
        ips = _unique([item[4][0] for item in infos if item and item[4]])
        return bool(ips), ips, ""
    except Exception as exc:  # noqa: BLE001
        return False, [], str(exc)


def check_ssl(domain: str, *, timeout_seconds: int = 5) -> tuple[str, datetime | None, int, str]:
    context = ssl.create_default_context()
    try:
        with socket.create_connection((domain, 443), timeout=timeout_seconds) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
        not_after = cert.get("notAfter")
        if not not_after:
            return "NO_EXPIRE_INFO", None, 0, "证书没有 notAfter 字段"
        expires_at = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
        days_left = (expires_at - datetime.utcnow()).days
        if days_left < 0:
            return "EXPIRED", expires_at, days_left, ""
        if days_left <= 15:
            return "EXPIRING_SOON", expires_at, days_left, ""
        return "VALID", expires_at, days_left, ""
    except ssl.SSLError as exc:
        return "INVALID", None, 0, str(exc)
    except Exception as exc:  # noqa: BLE001
        return "UNAVAILABLE", None, 0, str(exc)


def extract_record_numbers(html_list: list[str]) -> tuple[str, str]:
    text = "\n".join(html_list)
    icp = _unique(ICP_PATTERN.findall(text))
    public_security = _unique(PUBLIC_SECURITY_PATTERN.findall(text))
    return " | ".join(icp[:5]), " | ".join(public_security[:5])


def detect_site_health(domain: str, status_code: str, final_url: str, title: str, html_list: list[str]) -> tuple[str, list[str]]:
    flags: list[str] = []
    if not status_code:
        return "UNREACHABLE", ["首页不可访问"]

    try:
        code = int(status_code)
    except ValueError:
        code = 0

    if code >= 500:
        flags.append(f"服务器错误:{code}")
        health = "SERVER_ERROR"
    elif code in {401, 403}:
        flags.append(f"访问受限:{code}")
        health = "FORBIDDEN"
    elif code == 404:
        flags.append("首页 404")
        health = "NOT_FOUND"
    elif 300 <= code < 400:
        health = "REDIRECT"
    else:
        health = "ACTIVE"

    if final_url:
        final_host = urlparse(final_url).hostname or ""
        if final_host and domain not in final_host and final_host not in domain:
            flags.append(f"跨域跳转:{final_host}")
            health = "CROSS_DOMAIN_REDIRECT"

    html_text = "\n".join(html_list).lower()
    title_text = (title or "").lower()
    if any(keyword in html_text or keyword in title_text for keyword in PARKING_KEYWORDS):
        flags.append("疑似域名停放/出售页")
        health = "PARKED"

    if GARBLED_PATTERN.search(title or "") or GARBLED_PATTERN.search("\n".join(html_list)[:2000]):
        flags.append("疑似乱码页面")

    if not title and health == "ACTIVE":
        flags.append("缺少页面标题")

    return health, _unique(flags)


def _merge_risk_flags(old_flags: str, new_flags: list[str]) -> str:
    merged = _unique([*old_flags.split(" | "), *new_flags])
    return " | ".join(merged)


async def analyze_lead(db: Session, lead: DomainLead, *, timeout_seconds: int = 8, max_pages: int = 4) -> DomainLead:
    lead.analysis_status = "RUNNING"
    lead.analysis_error = ""
    db.commit()

    errors: list[str] = []
    try:
        dns_ok, ips, dns_error = await asyncio.to_thread(resolve_domain, lead.domain)
        if dns_error:
            errors.append(f"DNS:{dns_error}")

        ssl_status, ssl_expires_at, ssl_days_left, ssl_error = await asyncio.to_thread(
            check_ssl,
            lead.domain,
            timeout_seconds=min(timeout_seconds, 6),
        )
        if ssl_error:
            errors.append(f"SSL:{ssl_error}")

        crawl = await crawl_site(lead.domain, timeout_seconds=timeout_seconds, max_pages=max_pages)
        html_list = [page.html for page in crawl.pages if page.html]
        icp_number, public_security_record = extract_record_numbers(html_list)
        site_health, enhanced_flags = detect_site_health(
            lead.domain,
            crawl.status_code,
            crawl.final_url,
            crawl.title,
            html_list,
        )

        if not dns_ok:
            enhanced_flags.append("DNS 解析失败")
        if ssl_status in {"EXPIRED", "INVALID"}:
            enhanced_flags.append(f"SSL异常:{ssl_status}")
        elif ssl_status == "EXPIRING_SOON":
            enhanced_flags.append("SSL 即将过期")
        if crawl.error:
            errors.append(f"CRAWL:{crawl.error}")

        lead.dns_resolved = dns_ok
        lead.resolved_ips = " | ".join(ips)
        lead.ssl_status = ssl_status
        lead.ssl_expires_at = ssl_expires_at
        lead.ssl_days_left = ssl_days_left
        lead.icp_number = icp_number
        lead.public_security_record = public_security_record
        lead.site_health = site_health
        lead.enhanced_risk_flags = " | ".join(_unique(enhanced_flags))
        lead.analysis_error = " | ".join(errors[:5])
        lead.analysis_status = "SUCCESS" if not errors else "SUCCESS_WITH_WARNINGS"
        lead.last_analyzed_at = datetime.utcnow()

        # 同步一部分抓取结果，避免增强分析后列表仍然空白。
        if crawl.status_code:
            lead.status_code = crawl.status_code
        if crawl.final_url:
            lead.final_url = crawl.final_url
        if crawl.title and not lead.title:
            lead.title = crawl.title
        if crawl.emails and not lead.emails:
            lead.emails = " | ".join(crawl.emails)
        if crawl.phones and not lead.phones:
            lead.phones = " | ".join(crawl.phones)
        if crawl.wechats and not lead.wechats:
            lead.wechats = " | ".join(crawl.wechats)
        if crawl.qqs and not lead.qqs:
            lead.qqs = " | ".join(crawl.qqs)

        lead.risk_flags = _merge_risk_flags(lead.risk_flags, enhanced_flags)

        scored = score_lead(
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
        lead.root_domain = scored.root_domain
        lead.suffix = scored.suffix
        lead.score = scored.score
        lead.score_breakdown = json.dumps(scored.breakdown, ensure_ascii=False)
        # 保留增强风险，不让重新评分覆盖掉抓取发现的风险。
        lead.risk_flags = _merge_risk_flags(" | ".join(scored.risk_flags), enhanced_flags)
        lead.suggestion = scored.suggestion
        lead.first_offer = scored.first_offer
        lead.max_offer = scored.max_offer
    except Exception as exc:  # noqa: BLE001
        lead.analysis_status = "FAILED"
        lead.analysis_error = str(exc)
        lead.last_analyzed_at = datetime.utcnow()
    finally:
        db.commit()
        db.refresh(lead)
    return lead


async def run_analysis_batch(
    db: Session,
    leads: list[DomainLead],
    *,
    concurrency: int = 3,
    timeout_seconds: int = 8,
    max_pages: int = 4,
) -> dict[str, int]:
    semaphore = asyncio.Semaphore(concurrency)
    summary = {"total": len(leads), "success": 0, "failed": 0}

    async def worker(item: DomainLead) -> None:
        async with semaphore:
            await analyze_lead(db, item, timeout_seconds=timeout_seconds, max_pages=max_pages)
            if item.analysis_status == "FAILED":
                summary["failed"] += 1
            else:
                summary["success"] += 1

    await asyncio.gather(*(worker(lead) for lead in leads))
    return summary
