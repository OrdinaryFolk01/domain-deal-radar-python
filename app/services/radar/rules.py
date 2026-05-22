from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.radar.constants import CANDIDATE_NEED_SITE_INDEX, CANDIDATE_NEED_WEIGHT, CANDIDATE_QUALIFIED, CANDIDATE_REJECTED


IGNORED_ROOT_DOMAINS = {
    "baidu.com",
    "bing.com",
    "microsoft.com",
    "google.com",
    "sogou.com",
    "so.com",
    "360.cn",
    "360.com",
    "haosou.com",
    "qq.com",
    "weixin.qq.com",
    "zhihu.com",
    "weibo.com",
    "wikipedia.org",
    "baike.com",
    "baike.baidu.com",
    "csdn.net",
    "taobao.com",
    "tmall.com",
    "jd.com",
    "douyin.com",
    "toutiao.com",
    "bilibili.com",
    "sohu.com",
    "sina.com.cn",
    "163.com",
    "ifeng.com",
    "thepaper.cn",
}

SENSITIVE_SUFFIXES = ("gov.cn", "edu.cn")
SENSITIVE_ENTITY_KEYWORDS = ["政府", "法院", "公安", "医院", "大学", "学院", "学校", "银行", "证券", "集团", "有限公司"]


@dataclass(slots=True)
class RuleDecision:
    status: str
    reason: str = ""
    stop: bool = False
    priority_delta: int = 0


@dataclass(slots=True)
class CandidateRuleContext:
    domain: str
    title: str = ""
    summary: str = ""
    site_index: dict[str, Any] = field(default_factory=dict)
    weight: dict[str, Any] = field(default_factory=dict)
    whois: dict[str, Any] = field(default_factory=dict)
    ip: dict[str, Any] = field(default_factory=dict)
    site_index_min_count: int = 10000


class CandidateRule:
    def apply(self, context: CandidateRuleContext) -> RuleDecision:
        raise NotImplementedError


class LargeSiteFilterRule(CandidateRule):
    def apply(self, context: CandidateRuleContext) -> RuleDecision:
        if context.domain in IGNORED_ROOT_DOMAINS:
            return RuleDecision(CANDIDATE_REJECTED, "搜索结果属于平台/大站，不适合作为个人站收购线索", True)
        if context.domain.endswith(SENSITIVE_SUFFIXES):
            return RuleDecision(CANDIDATE_REJECTED, "gov.cn / edu.cn 不建议交易", True)
        text = f"{context.domain} {context.title} {context.summary}"
        for keyword in SENSITIVE_ENTITY_KEYWORDS:
            if keyword in text:
                return RuleDecision(CANDIDATE_REJECTED, f"疑似机构或敏感主体：{keyword}", True)
        return RuleDecision("PASS")


class SiteIndexThresholdRule(CandidateRule):
    def apply(self, context: CandidateRuleContext) -> RuleDecision:
        results = context.site_index.get("results") if isinstance(context.site_index, dict) else None
        if not isinstance(results, list) or not results:
            return RuleDecision(CANDIDATE_NEED_SITE_INDEX, "缺少 site: 索引核验数据", True)

        counts = [item.get("count") for item in results if isinstance(item, dict) and isinstance(item.get("count"), int)]
        if not counts:
            return RuleDecision(CANDIDATE_NEED_SITE_INDEX, "site: 查询异常或无法解析数量", True)

        max_count = max(counts)
        if max_count < context.site_index_min_count:
            return RuleDecision(CANDIDATE_REJECTED, f"site: 索引 {max_count} 低于门槛 {context.site_index_min_count}", True)
        return RuleDecision("PASS", priority_delta=min(max_count // 10000, 30))


class WeightRule(CandidateRule):
    def apply(self, context: CandidateRuleContext) -> RuleDecision:
        status = context.weight.get("status")
        if status in {"MISSING", "ERROR"}:
            error = str(context.weight.get("error") or "").strip()
            reason = error or "缺少爱站权重和网站性质数据"
            return RuleDecision(CANDIDATE_NEED_WEIGHT, reason, True)
        weights = context.weight.get("weights") if isinstance(context.weight, dict) else None
        if not isinstance(weights, dict):
            return RuleDecision(CANDIDATE_NEED_WEIGHT, "缺少爱站权重数据", True)
        values = [int(value or 0) for value in weights.values()]
        if not values or max(values) <= 0:
            return RuleDecision(CANDIDATE_REJECTED, "所有平台权重为 0", True)
        return RuleDecision("PASS", priority_delta=min(max(values) * 10, 40))


class SiteNatureRule(CandidateRule):
    def apply(self, context: CandidateRuleContext) -> RuleDecision:
        site_nature = str(context.weight.get("site_nature") or "").strip() if isinstance(context.weight, dict) else ""
        if not site_nature:
            return RuleDecision(CANDIDATE_NEED_WEIGHT, "缺少网站性质/备案主体数据", True)
        if "个人" not in site_nature:
            return RuleDecision(CANDIDATE_REJECTED, f"网站性质不是个人：{site_nature}", True)
        return RuleDecision("PASS", priority_delta=10)


class IpIntelPriorityRule(CandidateRule):
    def apply(self, context: CandidateRuleContext) -> RuleDecision:
        if not isinstance(context.ip, dict) or not context.ip:
            return RuleDecision(CANDIDATE_QUALIFIED)
        score = 0
        if context.ip.get("is_domestic"):
            score += 8
        if context.ip.get("is_cdn"):
            score -= 5
        return RuleDecision(CANDIDATE_QUALIFIED, priority_delta=score)
