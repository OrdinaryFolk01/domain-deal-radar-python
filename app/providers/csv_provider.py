from __future__ import annotations

import csv
import io
from typing import Any

from app.providers.base import DataSourceProvider, ProviderField, ProviderMeta, SourceRecord
from app.services.scoring import normalize_domain, to_int


GENERIC_CSV_ALIASES: dict[str, list[str]] = {
    "domain": ["domain", "域名", "网站", "网址", "url", "URL", "站点"],
    "title": ["title", "标题", "网站标题", "站点标题", "名称"],
    "baidu_pc_weight": ["baiduPcWeight", "baidu_pc_weight", "PC权重", "pc权重", "百度PC权重", "百度权重", "权重"],
    "baidu_mobile_weight": ["baiduMobileWeight", "baidu_mobile_weight", "移动权重", "百度移动权重", "移动端权重", "移动百度权重"],
    "indexed_count": ["indexedCount", "indexed_count", "收录", "收录量", "百度收录", "百度收录量", "网页收录"],
    "sogou_weight": ["sogouWeight", "sogou_weight", "搜狗权重"],
    "so_weight": ["soWeight", "so_weight", "360权重", "好搜权重"],
    "sm_weight": ["smWeight", "sm_weight", "神马权重"],
    "toutiao_weight": ["toutiaoWeight", "toutiao_weight", "头条权重"],
    "bing_weight": ["bingWeight", "bing_weight", "必应权重", "Bing权重"],
    "sogou_indexed_count": ["sogouIndexedCount", "sogou_indexed_count", "搜狗收录", "搜狗收录量"],
    "so_indexed_count": ["soIndexedCount", "so_indexed_count", "360收录", "360收录量"],
    "sm_indexed_count": ["smIndexedCount", "sm_indexed_count", "神马收录", "神马收录量"],
    "toutiao_indexed_count": ["toutiaoIndexedCount", "toutiao_indexed_count", "头条收录", "头条收录量"],
    "bing_indexed_count": ["bingIndexedCount", "bing_indexed_count", "必应收录", "必应收录量", "Bing收录"],
    "icp_type": ["icpType", "icp_type", "备案类型", "备案主体", "主体类型", "备案性质"],
    "last_update": ["lastUpdate", "last_update", "最近更新", "更新时间", "最后更新", "更新日期"],
    "remark": ["remark", "备注", "说明", "标签"],
    "source_url": ["sourceUrl", "source_url", "来源链接", "采集链接"],
}


class GenericCsvProvider(DataSourceProvider):
    meta = ProviderMeta(
        provider_id="generic_csv",
        name="通用 CSV",
        kind="file",
        description="兼容英文/中文表头的通用 CSV 数据源，适合手动整理后的候选域名。",
        accepted_extensions=[".csv"],
        fields=[
            ProviderField("domain", "域名", True, "域名、URL 或站点地址"),
            ProviderField("title", "标题"),
            ProviderField("baidu_pc_weight", "百度 PC 权重"),
            ProviderField("baidu_mobile_weight", "百度移动权重"),
            ProviderField("indexed_count", "百度收录量"),
            ProviderField("sogou_weight", "搜狗权重"),
            ProviderField("so_weight", "360权重"),
            ProviderField("sm_weight", "神马权重"),
            ProviderField("toutiao_weight", "头条权重"),
            ProviderField("bing_weight", "必应权重"),
            ProviderField("sogou_indexed_count", "搜狗收录"),
            ProviderField("so_indexed_count", "360收录"),
            ProviderField("sm_indexed_count", "神马收录"),
            ProviderField("toutiao_indexed_count", "头条收录"),
            ProviderField("bing_indexed_count", "必应收录"),
            ProviderField("icp_type", "备案类型"),
            ProviderField("last_update", "最近更新"),
            ProviderField("remark", "备注"),
        ],
        notes="默认导入入口使用该 Provider。",
    )
    aliases = GENERIC_CSV_ALIASES

    def _get_value(self, row: dict[str, str], canonical: str) -> str:
        for key in self.aliases.get(canonical, []):
            if key in row:
                return row.get(key, "")
        return ""

    def _read_rows(self, content: bytes) -> list[dict[str, str]]:
        text = content.decode("utf-8-sig", errors="ignore")
        reader = csv.DictReader(io.StringIO(text))
        rows: list[dict[str, str]] = []
        for raw_row in reader:
            rows.append({k.strip(): (v or "").strip() for k, v in raw_row.items() if k is not None})
        return rows

    def parse_file(self, content: bytes, *, filename: str = "") -> list[SourceRecord]:
        self.validate_file(filename or "upload.csv")
        records: list[SourceRecord] = []
        for row in self._read_rows(content):
            domain = normalize_domain(self._get_value(row, "domain"))
            if not domain:
                continue
            records.append(
                SourceRecord(
                    domain=domain,
                    title=self._get_value(row, "title"),
                    baidu_pc_weight=to_int(self._get_value(row, "baidu_pc_weight")),
                    baidu_mobile_weight=to_int(self._get_value(row, "baidu_mobile_weight")),
                    indexed_count=to_int(self._get_value(row, "indexed_count")),
                    sogou_weight=to_int(self._get_value(row, "sogou_weight")),
                    so_weight=to_int(self._get_value(row, "so_weight")),
                    sm_weight=to_int(self._get_value(row, "sm_weight")),
                    toutiao_weight=to_int(self._get_value(row, "toutiao_weight")),
                    bing_weight=to_int(self._get_value(row, "bing_weight")),
                    sogou_indexed_count=to_int(self._get_value(row, "sogou_indexed_count")),
                    so_indexed_count=to_int(self._get_value(row, "so_indexed_count")),
                    sm_indexed_count=to_int(self._get_value(row, "sm_indexed_count")),
                    toutiao_indexed_count=to_int(self._get_value(row, "toutiao_indexed_count")),
                    bing_indexed_count=to_int(self._get_value(row, "bing_indexed_count")),
                    icp_type=self._get_value(row, "icp_type"),
                    last_update=self._get_value(row, "last_update"),
                    remark=self._get_value(row, "remark"),
                    source_provider=self.meta.provider_id,
                    source_url=self._get_value(row, "source_url"),
                    raw=dict(row),
                )
            )
        return records

    @staticmethod
    def records_to_rows(records: list[SourceRecord]) -> list[dict[str, Any]]:
        return [record.to_lead_row() for record in records]
