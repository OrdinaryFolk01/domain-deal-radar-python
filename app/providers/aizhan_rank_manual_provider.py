from __future__ import annotations

from app.providers.aizhan_manual_provider import AizhanManualCsvProvider
from app.providers.base import ProviderField, ProviderMeta


class AizhanRankManualCsvProvider(AizhanManualCsvProvider):
    """爱站权重综合页面数据手动整理 Provider。

    当前只处理用户从 rank.aizhan.com 查询后合法整理/导出的 CSV，不包含登录、验证码、付费数据抓取。
    """

    meta = ProviderMeta(
        provider_id="aizhan_rank_manual_csv",
        name="爱站权重综合 CSV",
        kind="file",
        description="用于导入 rank.aizhan.com 权重综合查询中的百度、搜狗、360、神马、头条、必应权重和收录数据。",
        accepted_extensions=[".csv"],
        fields=[
            ProviderField("domain", "域名", True, "域名/网址/站点"),
            ProviderField("title", "网站标题"),
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
            ProviderField("icp_type", "备案主体/备案类型"),
            ProviderField("remark", "备注"),
        ],
        notes="适合从爱站权重综合结果页手动整理 CSV 后导入。后续可在该 Provider 下接官方 API 或授权采集。",
    )
