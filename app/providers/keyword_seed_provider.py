from __future__ import annotations

from app.providers.base import DataSourceProvider, ProviderField, ProviderMeta, SourceRecord
from app.services.seed_generation import generate_seed_domains


class KeywordSeedTxtProvider(DataSourceProvider):
    meta = ProviderMeta(
        provider_id="keyword_seed_txt",
        name="关键词种子 TXT",
        kind="file",
        description="每行一个中文、英文或拼音关键词，自动生成 .com/.cn/.net/.ai/.app 等候选域名。",
        accepted_extensions=[".txt"],
        fields=[ProviderField("keyword", "中文 / 英文 / 拼音关键词", True)],
        notes="中文关键词会自动转成拼音，例如 小说 → xiaoshuo。",
    )

    def parse_file(self, content: bytes, *, filename: str = "") -> list[SourceRecord]:
        self.validate_file(filename or "keywords.txt")
        text = content.decode("utf-8-sig", errors="ignore")
        keywords = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
        rows = generate_seed_domains(keywords, limit=500)
        return [
            SourceRecord(
                domain=row["domain"],
                remark=row.get("remark", ""),
                source_provider=self.meta.provider_id,
                raw={"keyword": row.get("remark", "")},
            )
            for row in rows
        ]
