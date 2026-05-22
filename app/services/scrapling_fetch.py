from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

from scrapling.fetchers import FetcherSession


DEFAULT_SCRAPLING_HEADERS = {
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "",
}


class ScraplingFetchError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, url: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.url = url


def build_url(url: str, params: dict[str, Any] | None = None) -> str:
    if not params:
        return url
    query = urlencode({key: value for key, value in params.items() if value is not None}, doseq=True)
    if not query:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{query}"


def create_scrapling_session(
    *,
    timeout_seconds: int | float,
    headers: dict[str, str] | None = None,
    retries: int = 1,
) -> FetcherSession:
    merged_headers = {**DEFAULT_SCRAPLING_HEADERS, **(headers or {})}
    return FetcherSession(
        impersonate="chrome",
        stealthy_headers=True,
        headers=merged_headers,
        follow_redirects="safe",
        retries=retries,
        retry_delay=1,
        timeout=timeout_seconds,
    )


def response_status(response: Any) -> int:
    try:
        return int(getattr(response, "status", 0) or 0)
    except (TypeError, ValueError):
        return 0


def response_url(response: Any) -> str:
    return str(getattr(response, "url", "") or "")


def response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if text is not None:
        text_value = str(text)
        if text_value:
            return text_value

    html_content = getattr(response, "html_content", "")
    if html_content:
        return str(html_content)

    body = getattr(response, "body", b"")
    if isinstance(body, bytes):
        encoding = getattr(response, "encoding", "utf-8") or "utf-8"
        return body.decode(encoding, errors="ignore")
    return str(body or "")


def response_json(response: Any) -> Any:
    json_method = getattr(response, "json", None)
    if callable(json_method):
        return json_method()
    return json.loads(response_text(response))


def raise_for_status(response: Any) -> None:
    status = response_status(response)
    if 400 <= status:
        url = response_url(response)
        raise ScraplingFetchError(f"HTTP {status} for {url or 'request'}", status=status, url=url)
