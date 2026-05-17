from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

CONTACT_LINK_KEYWORDS = [
    "联系",
    "联系我们",
    "关于",
    "关于我们",
    "合作",
    "商务合作",
    "广告合作",
    "投稿",
    "友情链接",
    "contact",
    "about",
    "cooperation",
    "business",
]


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


def extract_title(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    title = soup.find("title")
    return " ".join(title.get_text(strip=True).split()) if title else ""


def extract_contacts(html: str) -> dict[str, list[str]]:
    if not html:
        return {"emails": [], "phones": [], "wechats": [], "qqs": []}

    soup = BeautifulSoup(html, "lxml")
    text = " ".join(soup.get_text(" ").split())

    emails = _unique(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text))
    phones = _unique(re.findall(r"(?:\+?86[-\s]?)?1[3-9]\d{9}", text))

    qq_raw = re.findall(r"(?:QQ|qq|Qq|联系QQ|客服QQ)[:：\s]*([1-9]\d{4,11})", text)
    qqs = _unique(qq_raw)

    wechat_raw = re.findall(r"(?:微信|微信号|wechat|WeChat)[:：\s]*([a-zA-Z][-_a-zA-Z0-9]{5,19})", text)
    wechats = _unique(wechat_raw)

    return {"emails": emails, "phones": phones, "wechats": wechats, "qqs": qqs}


def discover_contact_links(html: str, base_url: str, *, limit: int = 8) -> list[str]:
    """从首页中发现疑似联系页/关于页链接。只保留同域名链接，避免无意抓取外站。"""
    if not html or not base_url:
        return []

    soup = BeautifulSoup(html, "lxml")
    base_host = urlparse(base_url).netloc.lower()
    urls: list[str] = []

    for tag in soup.find_all("a"):
        href = (tag.get("href") or "").strip()
        text = tag.get_text(" ", strip=True)
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue

        haystack = f"{href} {text}".lower()
        if not any(keyword.lower() in haystack for keyword in CONTACT_LINK_KEYWORDS):
            continue

        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.netloc.lower() != base_host:
            continue

        normalized = absolute.split("#", 1)[0]
        urls.append(normalized)
        if len(_unique(urls)) >= limit:
            break

    return _unique(urls)


def extract_external_domains(html_pages: list[str], base_url: str, *, limit: int = 100) -> list[str]:
    """从一组 HTML 页面中提取外链根域名，用于反查潜在线索。

    只提取 http/https 链接；过滤常见社交、统计、CDN、邮箱等非收购目标域名。
    """
    if not html_pages or not base_url:
        return []

    import tldextract

    ignored_roots = {
        "qq.com",
        "weixin.qq.com",
        "weibo.com",
        "baidu.com",
        "google.com",
        "google-analytics.com",
        "cnzz.com",
        "umeng.com",
        "alicdn.com",
        "bdimg.com",
        "jsdelivr.net",
        "bootstrapcdn.com",
        "cloudflare.com",
        "cloudflareinsights.com",
        "github.com",
        "gitee.com",
    }
    base_root = tldextract.extract(base_url).registered_domain
    domains: list[str] = []
    seen: set[str] = set()

    for html in html_pages:
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        for tag in soup.find_all("a"):
            href = (tag.get("href") or "").strip()
            if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue
            absolute = urljoin(base_url, href)
            parsed = urlparse(absolute)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                continue
            root = tldextract.extract(parsed.hostname).registered_domain
            if not root or root == base_root or root in ignored_roots or root in seen:
                continue
            seen.add(root)
            domains.append(root)
            if len(domains) >= limit:
                return domains
    return domains
