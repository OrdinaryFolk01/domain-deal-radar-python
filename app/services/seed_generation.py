from __future__ import annotations

import re

from pypinyin import lazy_pinyin

from app.services.scoring import normalize_domain

DOMAIN_TOKEN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$|^[a-z0-9]$")
CHINESE_CHAR_PATTERN = re.compile(r"[\u3400-\u9fff]")
DEFAULT_SUFFIXES = ["com", "cn", "com.cn", "net", "ai", "app", "io"]
DEFAULT_PREFIXES = ["", "ai", "my", "go", "get", "best", "52"]


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = value.strip().lower()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _safe_token(value: str) -> str:
    token = value.strip().lower().replace("_", "-").replace(" ", "-")
    token = re.sub(r"[^a-z0-9-]", "", token)
    token = re.sub(r"-+", "-", token).strip("-")
    if not token or not DOMAIN_TOKEN_PATTERN.match(token):
        return ""
    return token


def normalize_seed_keywords(keywords: list[str]) -> tuple[list[dict[str, str]], list[str]]:
    normalized: list[dict[str, str]] = []
    invalid: list[str] = []
    seen_tokens: set[str] = set()

    for raw_keyword in keywords:
        raw = raw_keyword.strip()
        if not raw:
            continue
        candidate = "".join(lazy_pinyin(raw)) if CHINESE_CHAR_PATTERN.search(raw) else raw
        token = _safe_token(candidate)
        if not token:
            invalid.append(raw)
            continue
        if token in seen_tokens:
            continue
        seen_tokens.add(token)
        normalized.append({"raw": raw, "token": token})
    return normalized, invalid


def generate_seed_domains(
    keywords: list[str],
    *,
    suffixes: list[str] | None = None,
    prefixes: list[str] | None = None,
    limit: int = 500,
) -> list[dict[str, str]]:
    suffixes = _unique(suffixes or DEFAULT_SUFFIXES)
    prefixes = _unique(prefixes or DEFAULT_PREFIXES)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    normalized_keywords, _ = normalize_seed_keywords(keywords)
    for item in normalized_keywords:
        raw_keyword = item["raw"]
        token = item["token"]
        names = [token]
        for prefix in prefixes:
            safe_prefix = _safe_token(prefix)
            if not safe_prefix:
                continue
            names.append(f"{safe_prefix}{token}")
            names.append(f"{safe_prefix}-{token}")
        for name in _unique(names):
            for suffix in suffixes:
                suffix = suffix.strip().lower().lstrip(".")
                domain = normalize_domain(f"{name}.{suffix}")
                if not domain or domain in seen:
                    continue
                seen.add(domain)
                rows.append(
                    {
                        "domain": domain,
                        "title": "",
                        "remark": (
                            f"关键词种子生成：{raw_keyword}"
                            if raw_keyword.lower() == token
                            else f"关键词种子生成：{raw_keyword} → {token}"
                        ),
                        "source_provider": "keyword_seed_generator",
                        "source_url": "",
                    }
                )
                if len(rows) >= limit:
                    return rows
    return rows
