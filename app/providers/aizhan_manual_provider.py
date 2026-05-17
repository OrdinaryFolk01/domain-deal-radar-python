from __future__ import annotations

from app.providers.csv_provider import GENERIC_CSV_ALIASES, GenericCsvProvider
from app.providers.base import ProviderField, ProviderMeta


class AizhanManualCsvProvider(GenericCsvProvider):
    """爱站手动导出的 CSV/手动整理表格 Provider。

    注意：这里不包含登录、验证码、付费接口抓取逻辑，只处理用户合法导出的数据。
    后续如果你有官方授权接口，可以在该 Provider 下新增 fetch_remote。
    """

    meta = ProviderMeta(
        provider_id="aizhan_manual_csv",
        name="爱站手动 CSV",
        kind="file",
        description="用于导入从爱站查询后手动整理/导出的 SEO、权重、收录、备案数据。",
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
            ProviderField("last_update", "最近更新"),
            ProviderField("remark", "备注"),
        ],
        notes="推荐当前阶段使用：爱站负责初筛，本系统负责二次分析、评分和跟进。",
    )

    aliases = {
        **GENERIC_CSV_ALIASES,
        "domain": [
            "domain", "域名", "主域名", "网站", "网址", "URL", "站点", "网站地址", "根域名"
        ],
        "title": [
            "title", "标题", "网站标题", "站点标题", "网站名称", "页面标题", "Title"
        ],
        "baidu_pc_weight": [
            "baiduPcWeight", "baidu_pc_weight", "PC权重", "pc权重", "百度PC权重", "百度pc权重", "PC百度权重", "权重", "百度权重"
        ],
        "baidu_mobile_weight": [
            "baiduMobileWeight", "baidu_mobile_weight", "移动权重", "移动百度权重", "百度移动权重", "移动端权重", "移动端百度权重"
        ],
        "indexed_count": [
            "indexedCount", "indexed_count", "收录", "收录量", "百度收录", "网页收录", "百度收录量", "索引量"
        ],
        "sogou_weight": ["sogouWeight", "sogou_weight", "搜狗权重", "搜狗PC权重"],
        "so_weight": ["soWeight", "so_weight", "360权重", "360PC权重", "好搜权重"],
        "sm_weight": ["smWeight", "sm_weight", "神马权重"],
        "toutiao_weight": ["toutiaoWeight", "toutiao_weight", "头条权重"],
        "bing_weight": ["bingWeight", "bing_weight", "必应权重", "Bing权重"],
        "sogou_indexed_count": ["sogouIndexedCount", "sogou_indexed_count", "搜狗收录", "搜狗收录量"],
        "so_indexed_count": ["soIndexedCount", "so_indexed_count", "360收录", "360收录量"],
        "sm_indexed_count": ["smIndexedCount", "sm_indexed_count", "神马收录", "神马收录量"],
        "toutiao_indexed_count": ["toutiaoIndexedCount", "toutiao_indexed_count", "头条收录", "头条收录量"],
        "bing_indexed_count": ["bingIndexedCount", "bing_indexed_count", "必应收录", "必应收录量", "Bing收录"],
        "icp_type": [
            "icpType", "icp_type", "备案类型", "备案主体", "主体类型", "备案性质", "备案信息", "主办单位性质"
        ],
        "last_update": [
            "lastUpdate", "last_update", "最近更新", "更新时间", "最后更新", "更新日期", "收录更新时间"
        ],
        "remark": [
            "remark", "备注", "说明", "标签", "行业", "分类"
        ],
        "source_url": [
            "sourceUrl", "source_url", "来源链接", "爱站链接", "查询链接"
        ],
    }
