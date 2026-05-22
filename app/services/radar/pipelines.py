from __future__ import annotations

import random
from dataclasses import asdict
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import DomainCandidate, DomainLead
from app.services.crawl_tasks import run_crawl_batch
from app.services.import_export import upsert_leads_from_rows
from app.services.radar.constants import (
    CANDIDATE_DISCOVERED,
    CANDIDATE_NEED_SITE_INDEX,
    CANDIDATE_NEED_WEIGHT,
    CANDIDATE_PROMOTED,
    CANDIDATE_QUALIFIED,
    CANDIDATE_REJECTED,
)
from app.services.radar.providers import ProviderRegistry, SearchResult
from app.services.radar.repository import CandidateRepository, safe_json_loads
from app.services.radar.rules import (
    CandidateRuleContext,
    IpIntelPriorityRule,
    LargeSiteFilterRule,
    SiteIndexThresholdRule,
    SiteNatureRule,
    WeightRule,
)
from app.services.scoring import normalize_domain


RANDOM_KEYWORD_POOL = [
    "考研资料",
    "题库",
    "学习资料",
    "作文素材",
    "图片压缩",
    "在线工具",
    "合同模板",
    "简历模板",
    "装修知识",
    "养花教程",
    "地方美食",
    "旅游攻略",
    "站长资源",
    "源码下载",
    "行业资讯",
    "培训资料",
    "宠物知识",
    "母婴知识",
    "维修教程",
    "Excel模板",
]


def _split_config(value: str) -> list[str]:
    return [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]


def _split_keywords(value: str) -> list[str]:
    raw_items = value.replace("，", "\n").replace(",", "\n").replace(";", "\n").replace("；", "\n").splitlines()
    result: list[str] = []
    for item in raw_items:
        text = item.strip()
        if text and text not in result:
            result.append(text)
    return result


def _now_text() -> str:
    return datetime.utcnow().isoformat(sep=" ", timespec="seconds")


def _is_search_challenge_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in [
            "验证码",
            "安全验证",
            "captcha",
            "verify you are human",
            "enablejs",
            "trouble accessing",
        ]
    )


class SearchResultFilter:
    def __init__(self) -> None:
        self.rule = LargeSiteFilterRule()

    def evaluate(self, result: SearchResult) -> tuple[str, str]:
        decision = self.rule.apply(CandidateRuleContext(domain=result.domain, title=result.title, summary=result.summary))
        if decision.status == CANDIDATE_REJECTED:
            return CANDIDATE_REJECTED, decision.reason
        return CANDIDATE_DISCOVERED, ""


class RadarDiscoveryPipeline:
    def __init__(self, db: Session, *, registry: ProviderRegistry | None = None) -> None:
        self.db = db
        self.settings = get_settings()
        self.registry = registry or ProviderRegistry()
        self.repository = CandidateRepository(db)
        self.filter = SearchResultFilter()

    def _select_keywords(self, *, keywords: str, keyword_mode: str, limit: int) -> list[str]:
        if keyword_mode == "random":
            count = min(max(limit, 1), 10)
            return random.sample(RANDOM_KEYWORD_POOL, k=min(count, len(RANDOM_KEYWORD_POOL)))
        selected = _split_keywords(keywords)
        return selected or random.sample(RANDOM_KEYWORD_POOL, k=1)

    async def run(
        self,
        *,
        keywords: str,
        keyword_mode: str,
        search_engines: list[str],
        limit: int,
        auto_qualify: bool = False,
    ) -> dict[str, Any]:
        selected_engines = search_engines or _split_config(self.settings.search_engines)
        selected_keywords = self._select_keywords(keywords=keywords, keyword_mode=keyword_mode, limit=limit)
        created = 0
        updated = 0
        rejected = 0
        errors: list[str] = []
        candidate_ids: list[int] = []

        per_query_limit = max(1, min(limit, 50))
        for engine_id in selected_engines:
            try:
                provider = self.registry.get_search_engine(engine_id)
            except ValueError as exc:
                errors.append(str(exc))
                continue

            for keyword in selected_keywords:
                try:
                    rows = await provider.search(keyword, limit=per_query_limit, timeout_seconds=self.settings.search_timeout_seconds)
                except Exception as exc:  # noqa: BLE001
                    if _is_search_challenge_error(exc):
                        errors.append(f"{engine_id}: {exc}，已跳过本轮剩余关键词")
                        break
                    errors.append(f"{engine_id}/{keyword}: {exc}")
                    continue
                for row in rows:
                    status, reason = self.filter.evaluate(row)
                    candidate, is_created = self.repository.upsert_search_result(row, keyword=keyword, status=status, reject_reason=reason)
                    candidate_ids.append(candidate.id)
                    created += 1 if is_created else 0
                    updated += 0 if is_created else 1
                    rejected += 1 if status == CANDIDATE_REJECTED else 0

        self.db.commit()

        qualify_summary: dict[str, Any] | None = None
        if auto_qualify and candidate_ids:
            qualification = CandidateQualificationPipeline(self.db, registry=self.registry)
            qualify_summary = await qualification.batch_qualify(candidate_ids=candidate_ids)

        return {
            "created": created,
            "updated": updated,
            "rejected": rejected,
            "errors": errors,
            "candidate_ids": candidate_ids,
            "keywords": selected_keywords,
            "search_engines": selected_engines,
            "qualification": qualify_summary,
        }


class CandidateQualificationPipeline:
    def __init__(self, db: Session, *, registry: ProviderRegistry | None = None) -> None:
        self.db = db
        self.settings = get_settings()
        self.registry = registry or ProviderRegistry()
        self.repository = CandidateRepository(db)
        self.rules = [SiteIndexThresholdRule(), WeightRule(), SiteNatureRule(), IpIntelPriorityRule()]

    async def refresh_site_index(self, candidate: DomainCandidate, *, engines: list[str] | None = None) -> DomainCandidate:
        engine_ids = engines or _split_config(self.settings.default_site_index_engines)
        results = []
        for engine_id in engine_ids:
            provider = self.registry.get_site_index_provider(engine_id)
            result = await provider.lookup(candidate.domain, timeout_seconds=self.settings.search_timeout_seconds)
            results.append(asdict(result))
        snapshot = {
            "checked_at": _now_text(),
            "min_count": self.settings.site_index_min_count,
            "results": results,
        }
        self.repository.update_snapshots(candidate, site_index_snapshot=snapshot)
        self.db.commit()
        self.db.refresh(candidate)
        return candidate

    async def refresh_weight(self, candidate: DomainCandidate, *, seed: dict[str, Any] | None = None) -> DomainCandidate:
        existing = safe_json_loads(candidate.weight_snapshot, {})
        merged_seed: dict[str, Any] = {}
        if isinstance(existing, dict):
            merged_seed.update(existing.get("weights") if isinstance(existing.get("weights"), dict) else {})
            merged_seed.update(existing.get("indexed_counts") if isinstance(existing.get("indexed_counts"), dict) else {})
            if existing.get("site_nature"):
                merged_seed["site_nature"] = existing.get("site_nature")
        if seed:
            merged_seed.update({key: value for key, value in seed.items() if value not in {None, ""}})
        public_provider = self.registry.get_weight_provider("aizhan_public")
        public_result = await public_provider.lookup(
            candidate.domain,
            seed=None,
            timeout_seconds=self.settings.search_timeout_seconds,
        )
        result = public_result
        if public_result.status != "SUCCESS" and seed:
            manual_provider = self.registry.get_weight_provider("aizhan_manual")
            result = await manual_provider.lookup(
                candidate.domain,
                seed=merged_seed,
                timeout_seconds=self.settings.search_timeout_seconds,
            )
            result.source = "manual_after_aizhan_failure"
            result.source_url = public_result.source_url
            if public_result.error:
                result.metadata["aizhan_error"] = public_result.error
        snapshot = {
            "checked_at": _now_text(),
            "source": result.source,
            "source_url": result.source_url,
            "status": result.status,
            "weights": result.weights,
            "indexed_counts": result.indexed_counts,
            "site_nature": result.site_nature,
            "metadata": result.metadata,
            "error": result.error,
        }
        self.repository.update_snapshots(candidate, weight_snapshot=snapshot)
        self.db.commit()
        self.db.refresh(candidate)
        return candidate

    async def refresh_intel(self, candidate: DomainCandidate) -> DomainCandidate:
        whois_results = []
        for provider_id in _split_config(self.settings.whois_intel_provider_mode):
            try:
                provider = self.registry.get_whois_provider(provider_id)
            except ValueError:
                continue
            whois_results.append(asdict(await provider.lookup(candidate.domain, timeout_seconds=self.settings.search_timeout_seconds)))

        ip_provider_id = _split_config(self.settings.ip_intel_provider_mode)[0] if self.settings.ip_intel_provider_mode else "ipwhois"
        ip_result = asdict(await self.registry.get_ip_provider(ip_provider_id).lookup(candidate.domain, timeout_seconds=self.settings.search_timeout_seconds))
        self.repository.update_snapshots(
            candidate,
            whois_snapshot={"checked_at": _now_text(), "results": whois_results},
            ip_snapshot={"checked_at": _now_text(), **ip_result},
        )
        self.db.commit()
        self.db.refresh(candidate)
        return candidate

    async def qualify(
        self,
        candidate: DomainCandidate,
        *,
        site_index_engines: list[str] | None = None,
        weight_seed: dict[str, Any] | None = None,
        force_weight_refresh: bool = False,
    ) -> DomainCandidate:
        if candidate.status == CANDIDATE_PROMOTED:
            return candidate

        if not safe_json_loads(candidate.site_index_snapshot, {}).get("results"):
            await self.refresh_site_index(candidate, engines=site_index_engines)
        if force_weight_refresh or weight_seed is not None or not safe_json_loads(candidate.weight_snapshot, {}).get("weights"):
            await self.refresh_weight(candidate, seed=weight_seed)

        site_index = safe_json_loads(candidate.site_index_snapshot, {})
        weight = safe_json_loads(candidate.weight_snapshot, {})
        ip_snapshot = safe_json_loads(candidate.ip_snapshot, {})
        priority_score = 0
        context = CandidateRuleContext(
            domain=candidate.domain,
            title=candidate.title,
            summary=candidate.summary,
            site_index=site_index if isinstance(site_index, dict) else {},
            weight=weight if isinstance(weight, dict) else {},
            ip=ip_snapshot if isinstance(ip_snapshot, dict) else {},
            site_index_min_count=self.settings.site_index_min_count,
        )

        final_status = CANDIDATE_QUALIFIED
        reason = ""
        for rule in self.rules:
            decision = rule.apply(context)
            priority_score += decision.priority_delta
            if decision.status in {CANDIDATE_REJECTED, CANDIDATE_NEED_SITE_INDEX, CANDIDATE_NEED_WEIGHT}:
                final_status = decision.status
                reason = decision.reason
                break

        if final_status == CANDIDATE_QUALIFIED:
            await self.refresh_intel(candidate)
            ip_snapshot = safe_json_loads(candidate.ip_snapshot, {})
            intel_decision = IpIntelPriorityRule().apply(
                CandidateRuleContext(domain=candidate.domain, title=candidate.title, summary=candidate.summary, ip=ip_snapshot)
            )
            priority_score += intel_decision.priority_delta

        self.repository.update_snapshots(candidate, status=final_status, reject_reason=reason, priority_score=priority_score)
        self.db.commit()
        self.db.refresh(candidate)
        return candidate

    async def batch_qualify(
        self,
        *,
        candidate_ids: list[int] | None = None,
        status: str = "",
        keyword: str = "",
        limit: int = 20,
        site_index_engines: list[str] | None = None,
    ) -> dict[str, int]:
        if candidate_ids:
            candidates = list(self.db.scalars(select(DomainCandidate).where(DomainCandidate.id.in_(candidate_ids)).limit(limit)))
        else:
            candidates = self.repository.list(status=status, keyword=keyword, limit=limit)

        summary = {"total": len(candidates), "qualified": 0, "rejected": 0, "need_weight": 0, "need_site_index": 0}
        for candidate in candidates:
            await self.qualify(candidate, site_index_engines=site_index_engines)
            if candidate.status == CANDIDATE_QUALIFIED:
                summary["qualified"] += 1
            elif candidate.status == CANDIDATE_REJECTED:
                summary["rejected"] += 1
            elif candidate.status == CANDIDATE_NEED_WEIGHT:
                summary["need_weight"] += 1
            elif candidate.status == CANDIDATE_NEED_SITE_INDEX:
                summary["need_site_index"] += 1
        return summary

    async def promote(self, candidate: DomainCandidate, *, auto_crawl: bool = True) -> DomainLead:
        if candidate.status != CANDIDATE_QUALIFIED:
            raise ValueError("只有 QUALIFIED 候选可以转入正式线索库")

        weight = safe_json_loads(candidate.weight_snapshot, {})
        weights = weight.get("weights") if isinstance(weight, dict) and isinstance(weight.get("weights"), dict) else {}
        weight_counts = weight.get("indexed_counts") if isinstance(weight, dict) and isinstance(weight.get("indexed_counts"), dict) else {}
        site_index = safe_json_loads(candidate.site_index_snapshot, {})
        counts = [
            item.get("count")
            for item in (site_index.get("results") if isinstance(site_index, dict) else []) or []
            if isinstance(item, dict) and isinstance(item.get("count"), int)
        ]
        indexed_count = max(counts) if counts else 0
        row = {
            "domain": candidate.domain,
            "title": candidate.title,
            "baidu_pc_weight": weights.get("baidu_pc_weight", 0),
            "baidu_mobile_weight": weights.get("baidu_mobile_weight", 0),
            "sogou_weight": weights.get("sogou_weight", 0),
            "so_weight": weights.get("so_weight", 0),
            "sm_weight": weights.get("sm_weight", 0),
            "toutiao_weight": weights.get("toutiao_weight", 0),
            "bing_weight": weights.get("bing_weight", 0),
            "indexed_count": max(indexed_count, int(weight_counts.get("indexed_count") or 0)),
            "sogou_indexed_count": weight_counts.get("sogou_indexed_count", 0),
            "so_indexed_count": weight_counts.get("so_indexed_count", 0),
            "sm_indexed_count": weight_counts.get("sm_indexed_count", 0),
            "toutiao_indexed_count": weight_counts.get("toutiao_indexed_count", 0),
            "bing_indexed_count": weight_counts.get("bing_indexed_count", 0),
            "icp_type": weight.get("site_nature", ""),
            "last_update": (weight.get("metadata") or {}).get("icp_passed_at", "") if isinstance(weight.get("metadata"), dict) else "",
            "remark": f"雷达候选转入；搜索词：{candidate.keyword}",
            "source_provider": "radar_candidate",
            "source_url": candidate.source_url,
            "discovered_from": candidate.keyword,
        }
        upsert_leads_from_rows(self.db, [row])
        lead = self.db.scalar(select(DomainLead).where(DomainLead.domain == normalize_domain(candidate.domain)))
        if lead is None:
            raise RuntimeError("候选转入后未找到正式线索")
        self.repository.mark_promoted(candidate, lead.id)
        self.db.commit()

        if auto_crawl:
            await run_crawl_batch(self.db, [lead], concurrency=1, timeout_seconds=self.settings.crawler_timeout_seconds, max_pages=4)
            self.db.refresh(lead)
        return lead
