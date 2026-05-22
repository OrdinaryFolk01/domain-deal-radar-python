from __future__ import annotations

import asyncio
import base64
import re
import socket
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, quote, quote_plus, urlparse

import tldextract
from bs4 import BeautifulSoup

from app.services.registration import lookup_registration
from app.services.scoring import normalize_domain, to_int
from app.services.scrapling_fetch import (
    build_url,
    create_scrapling_session,
    raise_for_status,
    response_json,
    response_text,
    response_url,
)


DEFAULT_HEADERS = {
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "",
}


@dataclass(slots=True)
class SearchResult:
    domain: str
    title: str
    url: str
    summary: str = ""
    engine: str = ""


@dataclass(slots=True)
class SiteIndexResult:
    engine: str
    domain: str
    count: int | None
    query_url: str
    status: str
    error: str = ""


@dataclass(slots=True)
class WeightLookupResult:
    status: str
    weights: dict[str, int] = field(default_factory=dict)
    indexed_counts: dict[str, int] = field(default_factory=dict)
    site_nature: str = ""
    source: str = "manual"
    source_url: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    @property
    def max_weight(self) -> int:
        return max(self.weights.values()) if self.weights else 0


@dataclass(slots=True)
class WhoisIntelResult:
    status: str
    source: str
    source_url: str = ""
    registrar: str = ""
    registrar_email: str = ""
    registrar_phone: str = ""
    dns_servers: list[str] = field(default_factory=list)
    registered_at: str = ""
    expires_at: str = ""
    raw_excerpt: str = ""
    error: str = ""


@dataclass(slots=True)
class IpIntelResult:
    status: str
    ips: list[str] = field(default_factory=list)
    country: str = ""
    region: str = ""
    city: str = ""
    isp: str = ""
    org: str = ""
    asn: str = ""
    is_domestic: bool = False
    is_cdn: bool = False
    error: str = ""


class SearchEngineProvider(ABC):
    provider_id: str
    name: str

    @abstractmethod
    async def search(self, query: str, *, limit: int, timeout_seconds: int) -> list[SearchResult]:
        raise NotImplementedError


class SiteIndexProvider(ABC):
    provider_id: str
    name: str

    @abstractmethod
    async def lookup(self, domain: str, *, timeout_seconds: int) -> SiteIndexResult:
        raise NotImplementedError


class WeightProvider(ABC):
    provider_id: str
    name: str

    @abstractmethod
    async def lookup(
        self,
        domain: str,
        *,
        seed: dict[str, Any] | None = None,
        timeout_seconds: int,
    ) -> WeightLookupResult:
        raise NotImplementedError


class WhoisIntelProvider(ABC):
    provider_id: str
    name: str

    @abstractmethod
    async def lookup(self, domain: str, *, timeout_seconds: int) -> WhoisIntelResult:
        raise NotImplementedError


class IpIntelProvider(ABC):
    provider_id: str
    name: str

    @abstractmethod
    async def lookup(self, domain: str, *, timeout_seconds: int) -> IpIntelResult:
        raise NotImplementedError


def _registered_domain(value: str) -> str:
    parsed = urlparse(value if "://" in value else f"https://{value}")
    host = parsed.hostname or value
    domain = normalize_domain(host)
    extracted = tldextract.extract(domain)
    return extracted.registered_domain or domain


def _clean_result_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"}:
        return url
    return ""


def _matches_domain(domain: str, roots: tuple[str, ...]) -> bool:
    return any(domain == root or domain.endswith(f".{root}") for root in roots)


def _absolute_url(href: str, base_url: str) -> str:
    if not href:
        return ""
    parsed = urlparse(href)
    if parsed.scheme in {"http", "https"}:
        return href
    if href.startswith("/"):
        base = urlparse(base_url)
        return f"{base.scheme}://{base.netloc}{href}"
    return ""


async def _resolve_redirect_url(client: Any, url: str, *, redirect_domains: tuple[str, ...]) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not _matches_domain(host, redirect_domains):
        return url
    try:
        response = await client.get(url)
        return response_url(response)
    except Exception:  # noqa: BLE001
        return url


def _result_summary(anchor: Any) -> str:
    parent = anchor.find_parent(["li", "div", "section", "article"])
    return parent.get_text(" ", strip=True) if parent else anchor.get_text(" ", strip=True)


def _parse_count_value(value: str, unit: str = "") -> int:
    try:
        number = float(value.replace(",", "").strip())
    except ValueError:
        return 0
    normalized_unit = unit.strip().lower()
    multiplier = 1
    if normalized_unit == "万":
        multiplier = 10000
    elif normalized_unit in {"k", "thousand"}:
        multiplier = 1000
    elif normalized_unit in {"m", "million"}:
        multiplier = 1000000
    elif normalized_unit in {"b", "billion"}:
        multiplier = 1000000000
    return int(number * multiplier)


def _decode_google_result_url(href: str) -> str:
    parsed = urlparse(href)
    target = (parse_qs(parsed.query).get("q") or [""])[0]
    return _clean_result_url(target or href)


def _decode_bing_result_url(href: str) -> str:
    parsed = urlparse(href)
    if parsed.scheme in {"http", "https"} and "bing.com" not in parsed.netloc:
        return href

    encoded = (parse_qs(parsed.query).get("u") or [""])[0]
    if encoded.startswith("a1"):
        encoded = encoded[2:]
    if not encoded:
        return ""
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        return base64.urlsafe_b64decode(padded.encode()).decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return ""


def _parse_result_count(text: str) -> tuple[int | None, str]:
    normalized = text.replace(",", "").replace("，", "").replace("\xa0", " ")
    zero_patterns = ["没有找到", "未找到", "No results", "There are no results"]
    if any(pattern.lower() in normalized.lower() for pattern in zero_patterns):
        return 0, ""

    patterns = [
        r"该网站约\s*([\d.]+)\s*(万)?个网页被360搜索收录",
        r"找到相关结果(?:数)?约?\s*([\d.]+)\s*(万)?个",
        r"找到约?\s*([\d.]+)\s*(万)?条相关结果",
        r"约\s*([\d.]+)\s*(万)?条相关结果",
        r"约\s*([\d.]+)\s*(万)?个",
        r"约有\s*([\d.]+)\s*(万)?项结果",
        r"([\d.]+)\s*(万)?条结果",
        r"About\s*([\d.]+)\s*(K|M|B|thousand|million|billion)?\s*results",
        r"([\d.]+)\s*(K|M|B|thousand|million|billion)?\s*results",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            return _parse_count_value(match.group(1), match.group(2) or ""), ""
    return None, "无法解析 site: 结果数量"


def _parse_integer_text(value: str) -> int:
    text = value.replace(",", "").replace("，", "").strip()
    if not text or text == "-":
        return 0
    sign = -1 if text.startswith("-") else 1
    text = text.lstrip("+-").strip()
    unit = ""
    if text.endswith("万"):
        unit = "万"
        text = text[:-1]
    return sign * _parse_count_value(text, unit)


def _node_text(soup: BeautifulSoup, node_id: str) -> str:
    node = soup.find(id=node_id)
    return node.get_text(" ", strip=True) if node else ""


def _node_int(soup: BeautifulSoup, node_id: str) -> int:
    return _parse_integer_text(_node_text(soup, node_id))


def _image_alt_int(soup: BeautifulSoup, node_id: str) -> int:
    node = soup.find(id=node_id)
    image = node.find("img") if node else None
    return to_int(image.get("alt") if image else "")


def _has_challenge(text: str) -> bool:
    lowered = text.lower()
    return any(
        token in lowered
        for token in [
            "验证码",
            "安全验证",
            "最后一步",
            "解决以下难题",
            "captcha",
            "verify you are human",
            "enablejs",
            "httpservice/retry/enablejs",
            "trouble accessing google search",
        ]
    )


class HtmlSearchEngineProvider(SearchEngineProvider):
    search_url = ""
    query_param = "q"
    extra_params: dict[str, str] = {}
    result_selectors: tuple[str, ...] = ("h3 a",)
    excluded_domains: tuple[str, ...] = ()
    redirect_domains: tuple[str, ...] = ()

    def decode_href(self, href: str) -> str:
        return _clean_result_url(_absolute_url(href, self.search_url))

    async def search(self, query: str, *, limit: int, timeout_seconds: int) -> list[SearchResult]:
        params = {self.query_param: query, **self.extra_params}
        async with create_scrapling_session(timeout_seconds=timeout_seconds, headers=DEFAULT_HEADERS) as client:
            response = await client.get(build_url(self.search_url, params))
            raise_for_status(response)
            html = response_text(response)
            if _has_challenge(html):
                raise RuntimeError(f"{self.name} 返回验证码或安全验证页面")

            soup = BeautifulSoup(html, "html.parser")
            anchors = []
            for selector in self.result_selectors:
                anchors.extend(soup.select(selector))
            if not anchors:
                anchors = soup.select("a")

            rows: list[SearchResult] = []
            seen: set[str] = set()
            for anchor in anchors:
                title = anchor.get_text(" ", strip=True)
                href = str(anchor.get("href") or "")
                if not title or not href:
                    continue
                url = self.decode_href(href)
                if self.redirect_domains:
                    url = await _resolve_redirect_url(client, url, redirect_domains=self.redirect_domains)
                domain = _registered_domain(url) if url else ""
                if not domain or domain in seen or _matches_domain(domain, self.excluded_domains):
                    continue
                seen.add(domain)
                rows.append(
                    SearchResult(
                        domain=domain,
                        title=title,
                        url=url,
                        summary=_result_summary(anchor),
                        engine=self.provider_id,
                    )
                )
                if len(rows) >= limit:
                    break
        return rows


class BingSearchEngineProvider(SearchEngineProvider):
    provider_id = "bing"
    name = "Bing"

    async def search(self, query: str, *, limit: int, timeout_seconds: int) -> list[SearchResult]:
        params = {"q": query, "count": min(max(limit * 3, 10), 50), "setlang": "zh-hans"}
        async with create_scrapling_session(timeout_seconds=timeout_seconds, headers=DEFAULT_HEADERS) as client:
            response = await client.get(build_url("https://www.bing.com/search", params))
            raise_for_status(response)
            html = response_text(response)

        soup = BeautifulSoup(html, "html.parser")
        rows: list[SearchResult] = []
        seen: set[str] = set()
        for anchor in soup.select("li.b_algo h2 a"):
            url = _decode_bing_result_url(str(anchor.get("href") or ""))
            domain = _registered_domain(url) if url else ""
            if not domain or domain in seen:
                continue
            seen.add(domain)
            summary = anchor.find_parent("li").get_text(" ", strip=True) if anchor.find_parent("li") else ""
            rows.append(SearchResult(domain=domain, title=anchor.get_text(" ", strip=True), url=url, summary=summary, engine=self.provider_id))
            if len(rows) >= limit:
                break
        return rows


class BaiduSearchEngineProvider(SearchEngineProvider):
    provider_id = "baidu"
    name = "百度"

    async def _resolve_href(self, client: Any, href: str) -> str:
        parsed = urlparse(href)
        if parsed.scheme not in {"http", "https"}:
            return ""
        if "baidu.com" not in parsed.netloc:
            return href
        try:
            response = await client.get(href)
            return response_url(response)
        except Exception:  # noqa: BLE001
            return href

    async def search(self, query: str, *, limit: int, timeout_seconds: int) -> list[SearchResult]:
        params = {"wd": query, "rn": min(max(limit * 3, 10), 50)}
        async with create_scrapling_session(timeout_seconds=timeout_seconds, headers=DEFAULT_HEADERS) as client:
            response = await client.get(build_url("https://www.baidu.com/s", params))
            raise_for_status(response)
            html = response_text(response)
            if _has_challenge(html):
                raise RuntimeError("百度返回验证码或安全验证页面")
            soup = BeautifulSoup(html, "html.parser")
            anchors = soup.select("h3 a") or soup.select("a")
            rows: list[SearchResult] = []
            seen: set[str] = set()
            for anchor in anchors:
                title = anchor.get_text(" ", strip=True)
                href = str(anchor.get("href") or "")
                if not title or not href:
                    continue
                url = await self._resolve_href(client, href)
                domain = _registered_domain(url) if url else ""
                if not domain or domain in seen or domain.endswith("baidu.com"):
                    continue
                seen.add(domain)
                parent = anchor.find_parent(["div", "section", "article"])
                summary = parent.get_text(" ", strip=True) if parent else title
                rows.append(SearchResult(domain=domain, title=title, url=url, summary=summary, engine=self.provider_id))
                if len(rows) >= limit:
                    break
        return rows


class SogouSearchEngineProvider(HtmlSearchEngineProvider):
    provider_id = "sogou"
    name = "搜狗"
    search_url = "https://www.sogou.com/web"
    query_param = "query"
    result_selectors = ("h3 a", ".vrwrap h3 a")
    excluded_domains = ("sogou.com", "sogoucdn.com")
    redirect_domains = ("sogou.com",)


class So360SearchEngineProvider(HtmlSearchEngineProvider):
    provider_id = "360"
    name = "360搜索"
    search_url = "https://www.so.com/s"
    query_param = "q"
    result_selectors = ("h3 a", ".result h3 a", ".res-list h3 a")
    excluded_domains = ("so.com", "360.cn", "360.com", "haosou.com")
    redirect_domains = ("so.com",)


class ToutiaoSearchEngineProvider(HtmlSearchEngineProvider):
    provider_id = "toutiao"
    name = "头条"
    search_url = "https://so.toutiao.com/search"
    query_param = "keyword"
    result_selectors = ("h3 a", ".result-title a", "a")
    excluded_domains = ("toutiao.com", "toutiaoapi.com", "snssdk.com", "pstatp.com", "bytedance.net")


class GoogleSearchEngineProvider(HtmlSearchEngineProvider):
    provider_id = "google"
    name = "谷歌"
    search_url = "https://www.google.com/search"
    query_param = "q"
    extra_params = {"hl": "zh-CN", "num": "10"}
    result_selectors = ('a[href^="/url?"]', "h3 a", "a")
    excluded_domains = ("google.com", "googleusercontent.com", "gstatic.com")

    def decode_href(self, href: str) -> str:
        decoded = _decode_google_result_url(href)
        if decoded:
            return decoded
        return _clean_result_url(_absolute_url(href, self.search_url))


class BingSiteIndexProvider(SiteIndexProvider):
    provider_id = "bing"
    name = "Bing site 查询"

    async def lookup(self, domain: str, *, timeout_seconds: int) -> SiteIndexResult:
        query_url = f"https://www.bing.com/search?q={quote_plus(f'site:{domain}')}"
        try:
            async with create_scrapling_session(timeout_seconds=timeout_seconds, headers=DEFAULT_HEADERS) as client:
                response = await client.get(query_url)
                raise_for_status(response)
            html = response_text(response)
            text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
            if _has_challenge(html) or _has_challenge(text):
                return SiteIndexResult(self.provider_id, domain, None, query_url, "ERROR", "Bing 返回验证码或安全验证页面")
            count, error = _parse_result_count(text)
            return SiteIndexResult(self.provider_id, domain, count, query_url, "SUCCESS" if error == "" else "ERROR", error)
        except Exception as exc:  # noqa: BLE001
            return SiteIndexResult(self.provider_id, domain, None, query_url, "ERROR", str(exc))


class BaiduSiteIndexProvider(SiteIndexProvider):
    provider_id = "baidu"
    name = "百度 site 查询"

    async def lookup(self, domain: str, *, timeout_seconds: int) -> SiteIndexResult:
        query_url = f"https://www.baidu.com/s?wd={quote_plus(f'site:{domain}')}"
        try:
            async with create_scrapling_session(timeout_seconds=timeout_seconds, headers=DEFAULT_HEADERS) as client:
                response = await client.get(query_url)
                raise_for_status(response)
            html = response_text(response)
            text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
            if _has_challenge(html) or _has_challenge(text):
                return SiteIndexResult(self.provider_id, domain, None, query_url, "ERROR", "百度返回验证码或安全验证页面")
            count, error = _parse_result_count(text)
            return SiteIndexResult(self.provider_id, domain, count, query_url, "SUCCESS" if error == "" else "ERROR", error)
        except Exception as exc:  # noqa: BLE001
            return SiteIndexResult(self.provider_id, domain, None, query_url, "ERROR", str(exc))


class SearchPageSiteIndexProvider(SiteIndexProvider):
    search_url = ""
    query_param = "q"
    extra_params: dict[str, str] = {}

    def build_query_url(self, domain: str) -> str:
        params = {self.query_param: f"site:{domain}", **self.extra_params}
        query = "&".join(f"{key}={quote_plus(value)}" for key, value in params.items())
        return f"{self.search_url}?{query}"

    async def lookup(self, domain: str, *, timeout_seconds: int) -> SiteIndexResult:
        query_url = self.build_query_url(domain)
        try:
            async with create_scrapling_session(timeout_seconds=timeout_seconds, headers=DEFAULT_HEADERS) as client:
                response = await client.get(query_url)
                raise_for_status(response)
            html = response_text(response)
            text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
            if _has_challenge(html) or _has_challenge(text):
                return SiteIndexResult(self.provider_id, domain, None, query_url, "ERROR", f"{self.name} 返回验证码或安全验证页面")
            count, error = _parse_result_count(text)
            return SiteIndexResult(self.provider_id, domain, count, query_url, "SUCCESS" if error == "" else "ERROR", error)
        except Exception as exc:  # noqa: BLE001
            return SiteIndexResult(self.provider_id, domain, None, query_url, "ERROR", str(exc))


class SogouSiteIndexProvider(SearchPageSiteIndexProvider):
    provider_id = "sogou"
    name = "搜狗 site 查询"
    search_url = "https://www.sogou.com/web"
    query_param = "query"


class So360SiteIndexProvider(SearchPageSiteIndexProvider):
    provider_id = "360"
    name = "360 site 查询"
    search_url = "https://www.so.com/s"
    query_param = "q"


class ToutiaoSiteIndexProvider(SearchPageSiteIndexProvider):
    provider_id = "toutiao"
    name = "头条 site 查询"
    search_url = "https://so.toutiao.com/search"
    query_param = "keyword"


class GoogleSiteIndexProvider(SearchPageSiteIndexProvider):
    provider_id = "google"
    name = "谷歌 site 查询"
    search_url = "https://www.google.com/search"
    query_param = "q"
    extra_params = {"hl": "zh-CN", "num": "10"}


class ManualAizhanWeightProvider(WeightProvider):
    provider_id = "aizhan_manual"
    name = "爱站人工/授权权重"

    async def lookup(
        self,
        domain: str,
        *,
        seed: dict[str, Any] | None = None,
        timeout_seconds: int,
    ) -> WeightLookupResult:
        _ = timeout_seconds
        seed = seed or {}
        weight_keys = [
            "baidu_pc_weight",
            "baidu_mobile_weight",
            "sogou_weight",
            "so_weight",
            "sm_weight",
            "toutiao_weight",
            "bing_weight",
        ]
        indexed_keys = [
            "indexed_count",
            "sogou_indexed_count",
            "so_indexed_count",
            "sm_indexed_count",
            "toutiao_indexed_count",
            "bing_indexed_count",
        ]
        weights = {key: to_int(seed.get(key)) for key in weight_keys}
        indexed_counts = {key: to_int(seed.get(key)) for key in indexed_keys}
        site_nature = str(seed.get("site_nature") or seed.get("icp_type") or "").strip()
        if not any(value > 0 for value in weights.values()) and not site_nature:
            return WeightLookupResult(status="MISSING", weights=weights, site_nature=site_nature, error="缺少爱站权重和网站性质数据")
        return WeightLookupResult(status="SUCCESS", weights=weights, indexed_counts=indexed_counts, site_nature=site_nature)


class PublicAizhanWeightProvider(WeightProvider):
    provider_id = "aizhan_public"
    name = "爱站公开综合查询"

    async def lookup(
        self,
        domain: str,
        *,
        seed: dict[str, Any] | None = None,
        timeout_seconds: int,
    ) -> WeightLookupResult:
        _ = seed
        normalized_domain = normalize_domain(domain)
        source_url = f"https://www.aizhan.com/cha/{quote(normalized_domain, safe='')}/"
        try:
            async with create_scrapling_session(
                timeout_seconds=timeout_seconds,
                headers={"Referer": "https://www.aizhan.com/"},
            ) as client:
                response = await client.get(source_url)
                raise_for_status(response)
            html = response_text(response)
            soup = BeautifulSoup(html, "html.parser")
            visible_text = soup.get_text(" ", strip=True)
            if _has_challenge(visible_text):
                return WeightLookupResult(
                    status="ERROR",
                    source=self.provider_id,
                    source_url=source_url,
                    error="爱站返回验证码或安全验证页面",
                )
            weights = {
                "baidu_pc_weight": _image_alt_int(soup, "baidurank_br"),
                "baidu_mobile_weight": _image_alt_int(soup, "baidurank_mbr"),
                "sogou_weight": _image_alt_int(soup, "sogou_pr"),
                "so_weight": _image_alt_int(soup, "360_pr"),
                "sm_weight": _image_alt_int(soup, "sm_pr") or _image_alt_int(soup, "shenma_pr"),
                "toutiao_weight": _image_alt_int(soup, "toutiao_pr"),
                "bing_weight": _image_alt_int(soup, "bing_pr"),
            }
            indexed_counts = {
                "indexed_count": _node_int(soup, "shoulu1_baidu"),
                "sogou_indexed_count": _node_int(soup, "shoulu1_sogou"),
                "so_indexed_count": _node_int(soup, "shoulu1_360"),
                "sm_indexed_count": _node_int(soup, "shoulu1_sm"),
                "toutiao_indexed_count": _node_int(soup, "shoulu1_toutiao"),
                "bing_indexed_count": _node_int(soup, "shoulu1_bing"),
            }
            metadata = {
                "title": (soup.title.get_text(" ", strip=True) if soup.title else ""),
                "icp_number": _node_text(soup, "icp_icp"),
                "icp_company": _node_text(soup, "icp_company"),
                "icp_passed_at": _node_text(soup, "icp_passtime"),
                "domain_age": _node_text(soup, "whois_created"),
                "baidu_route_ip": _node_text(soup, "baidurank_ip"),
                "baidu_mobile_route_ip": _node_text(soup, "baidurank_m_ip"),
                "baidu_pc_keywords": _node_int(soup, "cc1"),
                "baidu_mobile_keywords": _node_int(soup, "cc2"),
                "homepage_position": _node_text(soup, "shoulu1_baiduposition"),
                "backlinks": _node_int(soup, "backlink"),
                "baidu_24h_indexed": _node_int(soup, "shoulu3_1days"),
                "baidu_7d_indexed": _node_int(soup, "shoulu3_7days"),
                "baidu_30d_indexed": _node_int(soup, "shoulu3_30days"),
                "google_weight": _image_alt_int(soup, "google_pr"),
                "google_indexed_count": _node_int(soup, "shoulu1_google"),
            }
            site_nature = _node_text(soup, "icp_type")
            if not any(value > 0 for value in weights.values()) and not site_nature:
                return WeightLookupResult(
                    status="MISSING",
                    weights=weights,
                    indexed_counts=indexed_counts,
                    site_nature=site_nature,
                    source=self.provider_id,
                    source_url=source_url,
                    metadata=metadata,
                    error="爱站页面未解析到权重或网站性质数据",
                )
            return WeightLookupResult(
                status="SUCCESS",
                weights=weights,
                indexed_counts=indexed_counts,
                site_nature=site_nature,
                source=self.provider_id,
                source_url=source_url,
                metadata=metadata,
            )
        except Exception as exc:  # noqa: BLE001
            return WeightLookupResult(
                status="ERROR",
                source=self.provider_id,
                source_url=source_url,
                error=str(exc),
            )


def _first_label_value(text: str, labels: list[str]) -> str:
    for label in labels:
        pattern = rf"{re.escape(label)}\s*[:：]?\s*([^\n\r]+)"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            return re.split(r"\s{2,}|复制|查看", value)[0].strip()
    return ""


class ChinazWhoisIntelProvider(WhoisIntelProvider):
    provider_id = "chinaz"
    name = "站长工具 Whois"

    async def lookup(self, domain: str, *, timeout_seconds: int) -> WhoisIntelResult:
        source_url = f"https://whois.chinaz.com/{domain}"
        try:
            async with create_scrapling_session(timeout_seconds=timeout_seconds, headers=DEFAULT_HEADERS) as client:
                response = await client.get(source_url)
                raise_for_status(response)
            text = BeautifulSoup(response_text(response), "html.parser").get_text("\n", strip=True)
            if _has_challenge(text):
                return WhoisIntelResult(status="ERROR", source=self.provider_id, source_url=source_url, error="站长工具返回验证码或安全验证页面")
            dns_raw = _first_label_value(text, ["DNS服务器", "Name Server", "DNS"])
            dns_servers = [item.strip() for item in re.split(r"[,，\s]+", dns_raw) if item.strip()]
            return WhoisIntelResult(
                status="SUCCESS",
                source=self.provider_id,
                source_url=source_url,
                registrar=_first_label_value(text, ["注册商", "Registrar"]),
                registrar_email=_first_label_value(text, ["注册商邮箱", "Registrar Abuse Contact Email", "邮箱"]),
                registrar_phone=_first_label_value(text, ["注册商电话", "Registrar Abuse Contact Phone", "电话"]),
                dns_servers=dns_servers[:8],
                registered_at=_first_label_value(text, ["注册时间", "Creation Date", "创建时间"]),
                expires_at=_first_label_value(text, ["过期时间", "Registry Expiry Date", "到期时间"]),
                raw_excerpt=text[:1200],
            )
        except Exception as exc:  # noqa: BLE001
            return WhoisIntelResult(status="ERROR", source=self.provider_id, source_url=source_url, error=str(exc))


class RdapWhoisIntelProvider(WhoisIntelProvider):
    provider_id = "rdap"
    name = "RDAP"

    async def lookup(self, domain: str, *, timeout_seconds: int) -> WhoisIntelResult:
        result = await lookup_registration(domain, timeout_seconds=timeout_seconds)
        return WhoisIntelResult(
            status="SUCCESS" if result.status in {"REGISTERED", "AVAILABLE"} else "ERROR",
            source=self.provider_id,
            source_url=result.source_url,
            registrar=result.registrar_name,
            registered_at=result.registered_at.isoformat(sep=" ", timespec="seconds") if result.registered_at else "",
            expires_at=result.expires_at.isoformat(sep=" ", timespec="seconds") if result.expires_at else "",
            raw_excerpt=" | ".join(result.rdap_status or []),
            error=result.error,
        )


class IpWhoisIntelProvider(IpIntelProvider):
    provider_id = "ipwhois"
    name = "IP/ASN 情报"

    async def lookup(self, domain: str, *, timeout_seconds: int) -> IpIntelResult:
        try:
            infos = await asyncio.to_thread(socket.getaddrinfo, domain, None, proto=socket.IPPROTO_TCP)
            ips = []
            for item in infos:
                ip = item[4][0]
                if ip not in ips:
                    ips.append(ip)
        except Exception as exc:  # noqa: BLE001
            return IpIntelResult(status="ERROR", error=f"DNS 解析失败：{exc}")

        if not ips:
            return IpIntelResult(status="ERROR", error="DNS 未返回 IP")

        first_ip = ips[0]
        try:
            async with create_scrapling_session(timeout_seconds=timeout_seconds, headers=DEFAULT_HEADERS) as client:
                response = await client.get(build_url(f"https://ipwho.is/{first_ip}", {"lang": "zh-CN"}))
                raise_for_status(response)
            payload = response_json(response)
            connection = payload.get("connection") if isinstance(payload.get("connection"), dict) else {}
            isp = str(connection.get("isp") or payload.get("isp") or "")
            org = str(connection.get("org") or payload.get("org") or "")
            asn = str(connection.get("asn") or "")
            country_code = str(payload.get("country_code") or "")
            provider_text = f"{isp} {org}".lower()
            cdn_tokens = ["cloudflare", "akamai", "fastly", "cdn", "edgecast", "网宿", "加速"]
            return IpIntelResult(
                status="SUCCESS",
                ips=ips,
                country=str(payload.get("country") or ""),
                region=str(payload.get("region") or ""),
                city=str(payload.get("city") or ""),
                isp=isp,
                org=org,
                asn=asn,
                is_domestic=country_code.upper() == "CN" or "中国" in str(payload.get("country") or ""),
                is_cdn=any(token in provider_text for token in cdn_tokens),
            )
        except Exception as exc:  # noqa: BLE001
            return IpIntelResult(status="PARTIAL", ips=ips, error=str(exc))


class ProviderRegistry:
    def __init__(self) -> None:
        self.search_engines: dict[str, SearchEngineProvider] = {
            "baidu": BaiduSearchEngineProvider(),
            "sogou": SogouSearchEngineProvider(),
            "360": So360SearchEngineProvider(),
            "bing": BingSearchEngineProvider(),
            "toutiao": ToutiaoSearchEngineProvider(),
            "google": GoogleSearchEngineProvider(),
        }
        self.site_index_providers: dict[str, SiteIndexProvider] = {
            "baidu": BaiduSiteIndexProvider(),
            "sogou": SogouSiteIndexProvider(),
            "360": So360SiteIndexProvider(),
            "bing": BingSiteIndexProvider(),
            "toutiao": ToutiaoSiteIndexProvider(),
            "google": GoogleSiteIndexProvider(),
        }
        self.weight_providers: dict[str, WeightProvider] = {
            "aizhan_public": PublicAizhanWeightProvider(),
            "aizhan_manual": ManualAizhanWeightProvider(),
        }
        self.whois_providers: dict[str, WhoisIntelProvider] = {
            "chinaz": ChinazWhoisIntelProvider(),
            "rdap": RdapWhoisIntelProvider(),
        }
        self.ip_providers: dict[str, IpIntelProvider] = {"ipwhois": IpWhoisIntelProvider()}

    def list_search_engines(self, *, enabled_ids: set[str] | None = None) -> list[dict[str, object]]:
        if enabled_ids is None:
            enabled_ids = set(self.search_engines)
        return [
            {"provider_id": provider.provider_id, "name": provider.name, "enabled": provider.provider_id in enabled_ids}
            for provider in self.search_engines.values()
        ]

    def get_search_engine(self, provider_id: str) -> SearchEngineProvider:
        return self._get(self.search_engines, provider_id, "搜索引擎")

    def get_site_index_provider(self, provider_id: str) -> SiteIndexProvider:
        return self._get(self.site_index_providers, provider_id, "site 索引 Provider")

    def get_weight_provider(self, provider_id: str = "aizhan_manual") -> WeightProvider:
        return self._get(self.weight_providers, provider_id, "权重 Provider")

    def get_whois_provider(self, provider_id: str) -> WhoisIntelProvider:
        return self._get(self.whois_providers, provider_id, "Whois Provider")

    def get_ip_provider(self, provider_id: str = "ipwhois") -> IpIntelProvider:
        return self._get(self.ip_providers, provider_id, "IP Provider")

    @staticmethod
    def _get(providers: dict[str, Any], provider_id: str, label: str) -> Any:
        provider = providers.get(provider_id)
        if provider is None:
            raise ValueError(f"未知{label}：{provider_id}")
        return provider
