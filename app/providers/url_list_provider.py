from __future__ import annotations

import re

from app.providers.base import DataSourceProvider, ProviderField, ProviderMeta, SourceRecord
from app.services.scoring import normalize_domain


class UrlListProvider(DataSourceProvider):
    meta = ProviderMeta(
        provider_id="url_list_txt",
        name="URL / 域名 TXT 列表",
        kind="file",
        description="每行一个域名或 URL，适合把网页、表格、聊天记录里整理出的候选列表直接导入。",
        accepted_extensions=[".txt", ".csv"],
        fields=[ProviderField("domain", "每行一个域名或 URL", True)],
        notes="会自动忽略空行和注释行。",
    )

    def parse_file(self, content: bytes, *, filename: str = "") -> list[SourceRecord]:
        self.validate_file(filename or "domains.txt")
        text = content.decode("utf-8-sig", errors="ignore")
        records: list[SourceRecord] = []
        seen: set[str] = set()
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # 兼容 CSV/复制文本：从一行中取第一个像域名/URL 的片段。
            matched = re.search(r"(?:https?://)?(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?:/[^,\s]*)?", line)
            if not matched:
                continue
            domain = normalize_domain(matched.group(0))
            if not domain or domain in seen:
                continue
            seen.add(domain)
            records.append(SourceRecord(domain=domain, source_provider=self.meta.provider_id, raw={"line": line}))
        return records
