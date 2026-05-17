from __future__ import annotations

from app.providers.base import ProviderField, ProviderMeta, SourceRecord
from app.providers.csv_provider import GenericCsvProvider
from app.services.scoring import normalize_domain, to_int


class ExpiredDomainCsvProvider(GenericCsvProvider):
    meta = ProviderMeta(
        provider_id="expired_domain_csv",
        name="过期/删除域名 CSV",
        kind="file",
        description="导入过期域名、删除域名、抢注平台导出的 CSV，自动映射域名、反链、收录、长度等字段。",
        accepted_extensions=[".csv"],
        fields=[
            ProviderField("domain", "域名", True),
            ProviderField("indexed_count", "收录/页面数"),
            ProviderField("remark", "备注/来源字段"),
        ],
        notes="适合后续接过期域名平台导出的列表。当前版本只做文件导入，不自动抢注。",
    )
    aliases = {
        **GenericCsvProvider.aliases,
        "domain": ["domain", "Domain", "域名", "网址", "Name", "name"],
        "indexed_count": ["indexedCount", "indexed_count", "收录", "百度收录", "BL", "Backlinks", "DP", "Pages"],
        "remark": ["remark", "备注", "Status", "状态", "Archive", "DropDate", "删除时间"],
    }

    def parse_file(self, content: bytes, *, filename: str = "") -> list[SourceRecord]:
        self.validate_file(filename or "expired.csv")
        records: list[SourceRecord] = []
        for row in self._read_rows(content):
            domain = normalize_domain(self._get_value(row, "domain"))
            if not domain:
                continue
            remark_parts = []
            for key in ["DropDate", "删除时间", "Status", "状态", "Archive", "年龄", "Age"]:
                if key in row and row[key]:
                    remark_parts.append(f"{key}:{row[key]}")
            if self._get_value(row, "remark"):
                remark_parts.append(self._get_value(row, "remark"))
            records.append(
                SourceRecord(
                    domain=domain,
                    title=self._get_value(row, "title"),
                    indexed_count=to_int(self._get_value(row, "indexed_count")),
                    remark=" | ".join(remark_parts),
                    source_provider=self.meta.provider_id,
                    source_url=self._get_value(row, "source_url"),
                    raw=dict(row),
                )
            )
        return records
