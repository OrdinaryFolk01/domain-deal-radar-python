from __future__ import annotations

from app.providers.csv_provider import GENERIC_CSV_ALIASES, GenericCsvProvider
from app.providers.base import ProviderField, ProviderMeta


class ChinazManualCsvProvider(GenericCsvProvider):
    """站长工具手动 CSV Provider 预留实现。"""

    meta = ProviderMeta(
        provider_id="chinaz_manual_csv",
        name="站长工具手动 CSV",
        kind="file",
        description="用于导入从站长工具手动整理/导出的权重、收录、备案数据。",
        accepted_extensions=[".csv"],
        fields=[
            ProviderField("domain", "域名", True),
            ProviderField("title", "网站标题"),
            ProviderField("baidu_pc_weight", "百度 PC 权重"),
            ProviderField("baidu_mobile_weight", "百度移动权重"),
            ProviderField("indexed_count", "百度收录量"),
            ProviderField("icp_type", "备案主体/备案类型"),
            ProviderField("last_update", "最近更新"),
            ProviderField("remark", "备注"),
        ],
        notes="当前为手动导入插件；自动抓取需后续根据授权和页面结构单独实现。",
    )

    aliases = {
        **GENERIC_CSV_ALIASES,
        "domain": ["domain", "域名", "网站", "网址", "站点", "主域名"],
        "title": ["title", "标题", "网站标题", "网站名称"],
        "baidu_pc_weight": ["百度权重", "PC权重", "百度PC权重", "权重"],
        "baidu_mobile_weight": ["移动权重", "百度移动权重", "移动端权重"],
        "indexed_count": ["百度收录", "收录", "收录量", "网页收录"],
        "icp_type": ["备案类型", "备案主体", "主办单位性质", "备案信息"],
    }
