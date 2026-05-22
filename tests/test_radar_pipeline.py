from __future__ import annotations

import unittest
from dataclasses import asdict
from datetime import datetime
from typing import Any
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import Base
from app.models import DomainCandidate, DomainLead
from app.services.radar.constants import (
    CANDIDATE_NEED_SITE_INDEX,
    CANDIDATE_PROMOTED,
    CANDIDATE_QUALIFIED,
    CANDIDATE_REJECTED,
)
from app.services.radar.pipelines import CandidateQualificationPipeline, RadarDiscoveryPipeline
from app.services.radar.providers import (
    BaiduSearchEngineProvider,
    BingSearchEngineProvider,
    IpIntelResult,
    ProviderRegistry,
    SearchResult,
    SiteIndexResult,
    WeightLookupResult,
    WhoisIntelResult,
)
from app.services.radar.repository import CandidateRepository, json_dumps, safe_json_loads
from app.services.scoring import get_domain_parts, normalize_domain


class FakeResponse:
    def __init__(self, *, text: str, url: str = "https://search.example/") -> None:
        self.status = 200
        self.text = text
        self.url = url


class FakeScraplingClient:
    def __init__(self, html: str) -> None:
        self.html = html

    async def get(self, url: str) -> FakeResponse:
        return FakeResponse(text=self.html, url=url)


class FakeScraplingSession:
    def __init__(self, html: str) -> None:
        self.client = FakeScraplingClient(html)

    async def __aenter__(self) -> FakeScraplingClient:
        return self.client

    async def __aexit__(self, *_args: object) -> None:
        return None


class StaticSiteIndexProvider:
    def __init__(self, result: SiteIndexResult) -> None:
        self.result = result

    async def lookup(self, domain: str, *, timeout_seconds: int) -> SiteIndexResult:
        _ = timeout_seconds
        return SiteIndexResult(
            engine=self.result.engine,
            domain=domain,
            count=self.result.count,
            query_url=self.result.query_url,
            status=self.result.status,
            error=self.result.error,
        )


class StaticWeightProvider:
    def __init__(self, result: WeightLookupResult) -> None:
        self.result = result

    async def lookup(self, domain: str, *, seed: dict[str, Any] | None = None, timeout_seconds: int) -> WeightLookupResult:
        _ = domain, seed, timeout_seconds
        return self.result


class StaticWhoisProvider:
    async def lookup(self, domain: str, *, timeout_seconds: int) -> WhoisIntelResult:
        _ = timeout_seconds
        return WhoisIntelResult(
            status="SUCCESS",
            source="fake",
            registrar="Example Registrar",
            registrar_email="abuse@example-registrar.test",
            dns_servers=["ns1.example-dns.test"],
            raw_excerpt=f"{domain} whois",
        )


class StaticIpProvider:
    async def lookup(self, domain: str, *, timeout_seconds: int) -> IpIntelResult:
        _ = domain, timeout_seconds
        return IpIntelResult(status="SUCCESS", ips=["203.0.113.10"], country="中国", isp="Example ISP", is_domestic=True)


class BlockingSearchProvider:
    provider_id = "baidu"
    name = "百度"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, query: str, *, limit: int, timeout_seconds: int) -> list[SearchResult]:
        _ = limit, timeout_seconds
        self.calls.append(query)
        raise RuntimeError("百度返回验证码或安全验证页面")


class BlockingSearchRegistry:
    def __init__(self, provider: BlockingSearchProvider) -> None:
        self.provider = provider

    def get_search_engine(self, provider_id: str) -> BlockingSearchProvider:
        _ = provider_id
        return self.provider


class StaticRegistry:
    def __init__(
        self,
        *,
        site_index: SiteIndexResult | None = None,
        weight: WeightLookupResult | None = None,
    ) -> None:
        self.site_index = site_index or SiteIndexResult("bing", "example.com", 20000, "https://bing.example", "SUCCESS")
        self.weight = weight or WeightLookupResult(
            status="SUCCESS",
            weights={"baidu_pc_weight": 1},
            indexed_counts={"indexed_count": 20000},
            site_nature="个人",
        )

    def get_site_index_provider(self, provider_id: str) -> StaticSiteIndexProvider:
        _ = provider_id
        return StaticSiteIndexProvider(self.site_index)

    def get_weight_provider(self, provider_id: str = "aizhan_manual") -> StaticWeightProvider:
        _ = provider_id
        return StaticWeightProvider(self.weight)

    def get_whois_provider(self, provider_id: str) -> StaticWhoisProvider:
        _ = provider_id
        return StaticWhoisProvider()

    def get_ip_provider(self, provider_id: str = "ipwhois") -> StaticIpProvider:
        _ = provider_id
        return StaticIpProvider()


def site_index_snapshot(count: int | None, *, status: str = "SUCCESS", error: str = "") -> str:
    return json_dumps(
        {
            "checked_at": "2026-05-22 10:00:00",
            "min_count": 10000,
            "results": [
                asdict(SiteIndexResult("bing", "example.com", count, "https://bing.example", status, error)),
            ],
        }
    )


def weight_snapshot(*, weight: int, site_nature: str = "个人", status: str = "SUCCESS") -> str:
    return json_dumps(
        {
            "checked_at": "2026-05-22 10:00:00",
            "source": "manual",
            "source_url": "https://aizhan.example/example.com",
            "status": status,
            "weights": {"baidu_pc_weight": weight, "baidu_mobile_weight": 0},
            "indexed_counts": {"indexed_count": 20000, "bing_indexed_count": 18000},
            "site_nature": site_nature,
            "metadata": {"icp_passed_at": "2026-01-01"},
            "error": "",
        }
    )


class RadarPipelineTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(bind=engine)
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
        self.db: Session = self.SessionLocal()

    def tearDown(self) -> None:
        self.db.close()

    def add_candidate(
        self,
        *,
        domain: str = "example.com",
        status: str = "DISCOVERED",
        site_index: str = "{}",
        weight: str = "{}",
    ) -> DomainCandidate:
        normalized = normalize_domain(domain)
        root_domain, suffix = get_domain_parts(normalized)
        candidate = DomainCandidate(
            domain=normalized,
            root_domain=root_domain,
            suffix=suffix,
            title="Example",
            summary="Example summary",
            search_engine="bing",
            search_engines=json_dumps(["bing", "baidu"]),
            keyword="学习资料",
            keywords=json_dumps(["学习资料"]),
            source_url="https://example.com/source",
            source_urls=json_dumps(["https://example.com/source"]),
            status=status,
            site_index_snapshot=site_index,
            weight_snapshot=weight,
            whois_snapshot=json_dumps({"checked_at": "2026-05-22", "results": [{"registrar": "Cached Registrar"}]}),
            ip_snapshot=json_dumps({"checked_at": "2026-05-22", "isp": "Cached ISP"}),
        )
        self.db.add(candidate)
        self.db.commit()
        self.db.refresh(candidate)
        return candidate

    async def test_baidu_and_bing_providers_return_search_result_objects(self) -> None:
        cases = [
            (
                BingSearchEngineProvider(),
                '<html><body><li class="b_algo"><h2><a href="https://bing-result.test/page">Bing Result</a></h2><p>summary</p></li></body></html>',
                "bing-result.test",
            ),
            (
                BaiduSearchEngineProvider(),
                '<html><body><h3><a href="https://baidu-result.test/page">百度结果</a></h3></body></html>',
                "baidu-result.test",
            ),
        ]

        for provider, html, expected_domain in cases:
            with self.subTest(provider=provider.provider_id):
                with patch("app.services.radar.providers.create_scrapling_session", return_value=FakeScraplingSession(html)):
                    rows = await provider.search("学习资料", limit=5, timeout_seconds=1)

                self.assertGreaterEqual(len(rows), 1)
                self.assertIsInstance(rows[0], SearchResult)
                self.assertEqual(rows[0].domain, expected_domain)
                self.assertEqual(rows[0].engine, provider.provider_id)
                self.assertTrue(rows[0].title)
                self.assertTrue(rows[0].url.startswith("https://"))

    async def test_search_engine_challenge_skips_remaining_keywords(self) -> None:
        provider = BlockingSearchProvider()
        pipeline = RadarDiscoveryPipeline(self.db, registry=BlockingSearchRegistry(provider))

        result = await pipeline.run(
            keywords="学习资料, 简历模板, 在线工具",
            keyword_mode="manual",
            search_engines=["baidu"],
            limit=5,
        )

        self.assertEqual(provider.calls, ["学习资料"])
        self.assertEqual(result["errors"], ["baidu: 百度返回验证码或安全验证页面，已跳过本轮剩余关键词"])

    async def test_all_zero_weights_reject_candidate(self) -> None:
        candidate = self.add_candidate(site_index=site_index_snapshot(20000), weight=weight_snapshot(weight=0))
        pipeline = CandidateQualificationPipeline(self.db, registry=StaticRegistry())

        await pipeline.qualify(candidate)

        self.assertEqual(candidate.status, CANDIDATE_REJECTED)
        self.assertIn("所有平台权重为 0", candidate.reject_reason)

    async def test_low_site_index_rejects_candidate(self) -> None:
        candidate = self.add_candidate(site_index=site_index_snapshot(9999), weight=weight_snapshot(weight=1))
        pipeline = CandidateQualificationPipeline(self.db, registry=StaticRegistry())

        await pipeline.qualify(candidate)

        self.assertEqual(candidate.status, CANDIDATE_REJECTED)
        self.assertIn("低于门槛", candidate.reject_reason)

    async def test_missing_aizhan_data_marks_need_weight(self) -> None:
        candidate = self.add_candidate(site_index=site_index_snapshot(20000), weight=weight_snapshot(weight=0, site_nature="", status="MISSING"))
        pipeline = CandidateQualificationPipeline(self.db, registry=StaticRegistry())

        await pipeline.qualify(candidate)

        self.assertEqual(candidate.status, "NEED_WEIGHT")
        self.assertIn("缺少爱站权重", candidate.reject_reason)

    async def test_weighted_personal_site_with_enough_index_qualifies(self) -> None:
        candidate = self.add_candidate(site_index=site_index_snapshot(30000), weight=weight_snapshot(weight=2))
        pipeline = CandidateQualificationPipeline(self.db, registry=StaticRegistry())

        await pipeline.qualify(candidate)

        self.assertEqual(candidate.status, CANDIDATE_QUALIFIED)
        self.assertEqual(candidate.reject_reason, "")
        self.assertGreater(candidate.priority_score, 0)
        whois = safe_json_loads(candidate.whois_snapshot, {})
        self.assertEqual(whois["results"][0]["registrar_email"], "abuse@example-registrar.test")

    async def test_site_index_lookup_error_marks_need_site_index(self) -> None:
        candidate = self.add_candidate(weight=weight_snapshot(weight=1))
        registry = StaticRegistry(site_index=SiteIndexResult("bing", "example.com", None, "https://bing.example", "ERROR", "captcha"))
        pipeline = CandidateQualificationPipeline(self.db, registry=registry)

        await pipeline.qualify(candidate, site_index_engines=["bing"])

        self.assertEqual(candidate.status, CANDIDATE_NEED_SITE_INDEX)
        self.assertIn("site: 查询异常", candidate.reject_reason)

    async def test_promote_keeps_radar_sources_and_candidate_snapshots(self) -> None:
        candidate = self.add_candidate(
            status=CANDIDATE_QUALIFIED,
            site_index=site_index_snapshot(30000),
            weight=weight_snapshot(weight=3),
        )
        original_whois_snapshot = candidate.whois_snapshot
        original_ip_snapshot = candidate.ip_snapshot
        pipeline = CandidateQualificationPipeline(self.db, registry=StaticRegistry())

        lead = await pipeline.promote(candidate, auto_crawl=False)

        self.assertIsInstance(lead, DomainLead)
        self.assertEqual(lead.source_provider, "radar_candidate")
        self.assertEqual(lead.source_url, "https://example.com/source")
        self.assertEqual(lead.discovered_from, "学习资料")
        self.assertEqual(lead.baidu_pc_weight, 3)
        self.assertEqual(lead.indexed_count, 30000)
        self.assertEqual(candidate.status, CANDIDATE_PROMOTED)
        self.assertEqual(candidate.promoted_lead_id, lead.id)
        self.assertEqual(candidate.whois_snapshot, original_whois_snapshot)
        self.assertEqual(candidate.ip_snapshot, original_ip_snapshot)
        self.assertTrue(safe_json_loads(candidate.site_index_snapshot, {}).get("results"))
        self.assertTrue(safe_json_loads(candidate.weight_snapshot, {}).get("weights"))

    async def test_non_qualified_candidate_cannot_promote(self) -> None:
        candidate = self.add_candidate(site_index=site_index_snapshot(30000), weight=weight_snapshot(weight=1))
        pipeline = CandidateQualificationPipeline(self.db, registry=StaticRegistry())

        with self.assertRaisesRegex(ValueError, "只有 QUALIFIED 候选"):
            await pipeline.promote(candidate, auto_crawl=False)

    def test_unknown_provider_id_raises_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "未知搜索引擎：missing"):
            ProviderRegistry().get_search_engine("missing")

    def test_search_engine_registry_marks_default_enabled_engines(self) -> None:
        engines = ProviderRegistry().list_search_engines(enabled_ids={"360", "toutiao"})
        enabled_by_id = {str(item["provider_id"]): bool(item["enabled"]) for item in engines}

        self.assertTrue(enabled_by_id["360"])
        self.assertTrue(enabled_by_id["toutiao"])
        self.assertFalse(enabled_by_id["baidu"])
        self.assertFalse(enabled_by_id["google"])

    def test_candidate_repository_filters_ids_and_keeps_time_sort(self) -> None:
        older = self.add_candidate(domain="older.example")
        newer = self.add_candidate(domain="newer.example")
        other = self.add_candidate(domain="other.example")
        older.updated_at = datetime(2026, 5, 22, 9, 0, 0)
        newer.updated_at = datetime(2026, 5, 22, 10, 0, 0)
        other.updated_at = datetime(2026, 5, 22, 11, 0, 0)
        self.db.commit()

        rows = CandidateRepository(self.db).list(ids=[older.id, newer.id], limit=10)

        self.assertEqual([row.id for row in rows], [newer.id, older.id])
        self.assertEqual(CandidateRepository(self.db).list(ids=[]), [])


if __name__ == "__main__":
    unittest.main()
