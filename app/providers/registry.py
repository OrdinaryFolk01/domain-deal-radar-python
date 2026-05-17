from __future__ import annotations

from dataclasses import asdict

from app.providers.aizhan_manual_provider import AizhanManualCsvProvider
from app.providers.aizhan_rank_manual_provider import AizhanRankManualCsvProvider
from app.providers.base import DataSourceProvider, ProviderError
from app.providers.chinaz_manual_provider import ChinazManualCsvProvider
from app.providers.csv_provider import GenericCsvProvider
from app.providers.expired_domain_csv_provider import ExpiredDomainCsvProvider
from app.providers.keyword_seed_provider import KeywordSeedTxtProvider
from app.providers.url_list_provider import UrlListProvider


_PROVIDERS: dict[str, DataSourceProvider] = {
    provider.meta.provider_id: provider
    for provider in [
        GenericCsvProvider(),
        AizhanManualCsvProvider(),
        AizhanRankManualCsvProvider(),
        ChinazManualCsvProvider(),
        ExpiredDomainCsvProvider(),
        UrlListProvider(),
        KeywordSeedTxtProvider(),
    ]
}


def list_providers() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for provider in _PROVIDERS.values():
        meta = provider.get_meta()
        result.append(
            {
                "provider_id": meta.provider_id,
                "name": meta.name,
                "kind": meta.kind,
                "description": meta.description,
                "accepted_extensions": meta.accepted_extensions,
                "enabled": meta.enabled,
                "notes": meta.notes,
                "fields": [asdict(field) for field in meta.fields],
            }
        )
    return result


def get_provider(provider_id: str) -> DataSourceProvider:
    provider = _PROVIDERS.get(provider_id)
    if provider is None:
        raise ProviderError(f"未知数据源 Provider：{provider_id}")
    if not provider.get_meta().enabled:
        raise ProviderError(f"数据源 Provider 已禁用：{provider_id}")
    return provider
