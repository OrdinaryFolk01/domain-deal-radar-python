from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import tldextract

COMMERCIAL_KEYWORDS = [
    "考研",
    "复试",
    "调剂",
    "择校",
    "专业课",
    "题库",
    "网课",
    "教育",
    "学习",
    "AI",
    "人工智能",
    "工具",
    "SaaS",
    "CRM",
    "小程序",
    "私域",
    "销售",
    "获客",
    "简历",
    "合同",
    "PDF",
    "图片压缩",
    "在线生成",
    "在线查询",
]

RISK_KEYWORDS = [
    "博彩",
    "赌博",
    "彩票",
    "娱乐城",
    "真人",
    "百家乐",
    "体育投注",
    "成人",
    "色情",
    "约炮",
    "私服",
    "外挂",
    "破解",
    "贷款",
    "网贷",
    "黑户",
    "代办信用卡",
    "高仿",
    "仿牌",
]

HIGH_RISK_ENTITY_KEYWORDS = ["政府", "法院", "公安", "医院", "大学", "学院", "学校", "银行", "证券"]


@dataclass(slots=True)
class ScoreResult:
    score: int
    breakdown: list[dict[str, object]]
    risk_flags: list[str]
    suggestion: str
    first_offer: int
    max_offer: int
    root_domain: str
    suffix: str


def normalize_domain(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace("https://", "")
        .replace("http://", "")
        .replace("www.", "", 1)
        .split("/")[0]
        .split("?")[0]
        .split("#")[0]
    )


def to_int(value: Any) -> int:
    if value is None:
        return 0
    text = str(value).replace(",", "").strip()
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def get_domain_parts(domain: str) -> tuple[str, str]:
    extracted = tldextract.extract(domain)
    suffix = extracted.suffix or domain.split(".")[-1]
    root_domain = f"{extracted.domain}.{extracted.suffix}" if extracted.suffix else domain
    return root_domain, suffix


def days_from(date_text: str) -> int | None:
    if not date_text:
        return None

    formats = ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y-%m-%d %H:%M:%S"]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_text.strip(), fmt)
            return (datetime.now() - dt).days
        except ValueError:
            continue
    return None


def detect_risk_flags(domain: str, title: str, remark: str, icp_type: str) -> list[str]:
    text = f"{domain} {title} {remark} {icp_type}"
    flags: list[str] = []

    for keyword in RISK_KEYWORDS:
        if keyword in text:
            flags.append(f"高风险词:{keyword}")

    for keyword in HIGH_RISK_ENTITY_KEYWORDS:
        if keyword in text:
            flags.append(f"敏感主体词:{keyword}")

    if re.search(r"gov\.cn$", domain):
        flags.append("gov.cn 不建议交易")
    if re.search(r"edu\.cn$", domain):
        flags.append("edu.cn 不建议交易")

    return list(dict.fromkeys(flags))


def get_suggestion(score: int, risk_flags: list[str]) -> str:
    if risk_flags and score < 30:
        return "放弃，高风险"
    if score >= 85:
        return "高优先级，建议联系询价"
    if score >= 65:
        return "可跟进，适合低价试探"
    if score >= 45:
        return "观察，价格低才考虑"
    return "放弃或暂不联系"


def estimate_offer(
    *,
    score: int,
    baidu_pc_weight: int,
    baidu_mobile_weight: int,
    indexed_count: int,
    suffix: str,
    icp_type: str,
    risk_flags: list[str],
    extra_max_weight: int = 0,
    extra_indexed_count: int = 0,
) -> tuple[int, int]:
    if risk_flags and score < 40:
        return 0, 0

    max_weight = max(baidu_pc_weight, baidu_mobile_weight, extra_max_weight)
    total_indexed = max(indexed_count, extra_indexed_count)
    base = 300 + max_weight * 800 + min(math.log10(total_indexed + 1) * 500, 2500)

    if suffix == "com":
        base *= 1.3
    elif suffix == "ai":
        base *= 1.15
    elif suffix == "cn":
        base *= 1.05

    if "个人" in icp_type:
        base *= 1.1

    if score >= 85:
        base *= 1.2
    elif score < 55:
        base *= 0.65

    first_offer = round((base * 0.35) / 100) * 100
    max_offer = round((base * 0.7) / 100) * 100
    return int(first_offer), int(max_offer)


def score_lead(payload: dict[str, Any]) -> ScoreResult:
    domain = normalize_domain(str(payload.get("domain") or ""))
    title = str(payload.get("title") or "")
    remark = str(payload.get("remark") or "")
    icp_type = str(payload.get("icp_type") or payload.get("icpType") or "")
    last_update = str(payload.get("last_update") or payload.get("lastUpdate") or "")
    baidu_pc_weight = to_int(payload.get("baidu_pc_weight") or payload.get("baiduPcWeight"))
    baidu_mobile_weight = to_int(payload.get("baidu_mobile_weight") or payload.get("baiduMobileWeight"))
    indexed_count = to_int(payload.get("indexed_count") or payload.get("indexedCount"))
    extra_weights = [
        to_int(payload.get("sogou_weight")),
        to_int(payload.get("so_weight")),
        to_int(payload.get("sm_weight")),
        to_int(payload.get("toutiao_weight")),
        to_int(payload.get("bing_weight")),
    ]
    extra_indexed_values = [
        to_int(payload.get("sogou_indexed_count")),
        to_int(payload.get("so_indexed_count")),
        to_int(payload.get("sm_indexed_count")),
        to_int(payload.get("toutiao_indexed_count")),
        to_int(payload.get("bing_indexed_count")),
    ]

    root_domain, suffix = get_domain_parts(domain)
    score = 0
    breakdown: list[dict[str, object]] = []

    def add_component(category: str, label: str, points: float, reason: str) -> None:
        nonlocal score
        score += points
        if points:
            breakdown.append(
                {
                    "category": category,
                    "label": label,
                    "points": round(points, 2),
                    "reason": reason,
                }
            )

    max_weight = max(baidu_pc_weight, baidu_mobile_weight, *extra_weights)
    add_component("seo", "最高权重", min(max_weight * 12, 50), f"最高平台权重为 {max_weight}")

    active_platforms = sum(1 for value in [baidu_pc_weight, baidu_mobile_weight, *extra_weights] if value > 0)
    if active_platforms >= 3:
        add_component("seo", "多平台覆盖", 6, f"{active_platforms} 个平台有权重")
    elif active_platforms == 2:
        add_component("seo", "多平台覆盖", 3, "2 个平台有权重")

    total_indexed = max(indexed_count, *extra_indexed_values)
    if total_indexed > 0:
        add_component("seo", "收录规模", min(math.log10(total_indexed + 1) * 8, 32), f"最高收录量 {total_indexed}")

    if suffix == "com":
        add_component("domain", "后缀", 15, ".com 后缀")
    elif suffix == "cn":
        add_component("domain", "后缀", 8, ".cn 后缀")
    elif suffix == "com.cn":
        add_component("domain", "后缀", 6, ".com.cn 后缀")
    elif suffix == "ai":
        add_component("domain", "后缀", 8, ".ai 后缀")
    elif suffix in {"io", "app", "net"}:
        add_component("domain", "后缀", 5, f".{suffix} 后缀")
    else:
        add_component("domain", "后缀", -5, f".{suffix or '-'} 后缀")

    name_part = domain.split(".")[0] if domain else ""
    if len(name_part) <= 6:
        add_component("domain", "域名长度", 12, f"主名称长度 {len(name_part)}")
    elif len(name_part) <= 10:
        add_component("domain", "域名长度", 8, f"主名称长度 {len(name_part)}")
    elif len(name_part) <= 15:
        add_component("domain", "域名长度", 3, f"主名称长度 {len(name_part)}")
    else:
        add_component("domain", "域名长度", -5, f"主名称长度 {len(name_part)}")

    commercial_text = f"{domain} {title} {remark}".lower()
    matched = [kw for kw in COMMERCIAL_KEYWORDS if kw.lower() in commercial_text]
    if matched:
        add_component("market", "商业关键词", min(len(matched) * 6, 24), "、".join(matched[:4]))

    if "个人" in icp_type:
        add_component("ownership", "备案主体", 12, "个人主体")
    elif "企业" in icp_type:
        add_component("ownership", "备案主体", 2, "企业主体")
    elif "无" in icp_type:
        add_component("ownership", "备案主体", -4, "无备案")
    elif any(x in icp_type for x in ["政府", "学校", "事业"]):
        add_component("ownership", "备案主体", -40, f"敏感主体：{icp_type}")

    stale_days = days_from(last_update)
    if stale_days is not None:
        if stale_days > 720:
            add_component("timing", "长期未更新", 10, f"距今约 {stale_days} 天")
        elif stale_days > 365:
            add_component("timing", "较久未更新", 6, f"距今约 {stale_days} 天")
        elif stale_days < 90:
            add_component("timing", "近期更新", -4, f"距今约 {stale_days} 天")

    risk_flags = detect_risk_flags(domain, title, remark, icp_type)
    if any(flag.startswith("高风险词") for flag in risk_flags):
        add_component("risk", "高风险词", -100, " | ".join(flag for flag in risk_flags if flag.startswith("高风险词")))
    if any(flag.startswith("敏感主体词") for flag in risk_flags):
        add_component("risk", "敏感主体词", -30, " | ".join(flag for flag in risk_flags if flag.startswith("敏感主体词")))
    if "gov.cn 不建议交易" in risk_flags or "edu.cn 不建议交易" in risk_flags:
        add_component("risk", "限制后缀", -100, "gov.cn / edu.cn 不建议交易")

    score = round(score)
    first_offer, max_offer = estimate_offer(
        score=score,
        baidu_pc_weight=baidu_pc_weight,
        baidu_mobile_weight=baidu_mobile_weight,
        indexed_count=indexed_count,
        extra_max_weight=max(extra_weights) if extra_weights else 0,
        extra_indexed_count=max(extra_indexed_values) if extra_indexed_values else 0,
        suffix=suffix,
        icp_type=icp_type,
        risk_flags=risk_flags,
    )

    return ScoreResult(
        score=score,
        breakdown=breakdown,
        risk_flags=risk_flags,
        suggestion=get_suggestion(score, risk_flags),
        first_offer=first_offer,
        max_offer=max_offer,
        root_domain=root_domain,
        suffix=suffix,
    )
