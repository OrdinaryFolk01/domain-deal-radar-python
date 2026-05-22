from __future__ import annotations

from app.models import DomainLead


def build_contact_message(lead: DomainLead) -> str:
    """生成只询问域名转让的话术。

    用户当前策略是只买域名，不买整站/源码/内容，所以话术避免强调整站接手，
    降低对方因“网站资产”预期而抬价的概率。
    """
    if getattr(lead, "contact_message", ""):
        return lead.contact_message

    domain = lead.domain
    return f"""你好，我看到你名下这个域名 {domain}，想问下这个域名后续有没有转让考虑？

如果你愿意出，可以直接说一个心理价位，方便的话，也可以留个微信继续沟通。"""


def build_email_subject(lead: DomainLead) -> str:
    return lead.last_email_subject or f"咨询域名 {lead.domain} 是否考虑转让"


def build_detail_message(lead: DomainLead) -> str:
    return f"""## {lead.domain}

建议：{lead.suggestion}
评分：{lead.score}
建议首次报价：{lead.first_offer} 元
建议最高价：{lead.max_offer} 元
联系方式：
- 邮箱：{lead.emails or "-"}
- 手机：{lead.phones or "-"}
- 微信：{lead.wechats or "-"}
- QQ：{lead.qqs or "-"}

话术：

{build_contact_message(lead)}
"""
