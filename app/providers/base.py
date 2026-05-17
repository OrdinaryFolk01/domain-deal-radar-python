from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal


ProviderKind = Literal["file", "remote", "manual", "hybrid"]


class ProviderError(Exception):
    """数据源插件异常。"""


@dataclass(slots=True)
class ProviderField:
    name: str
    label: str
    required: bool = False
    description: str = ""


@dataclass(slots=True)
class ProviderMeta:
    provider_id: str
    name: str
    kind: ProviderKind
    description: str
    accepted_extensions: list[str] = field(default_factory=list)
    fields: list[ProviderField] = field(default_factory=list)
    enabled: bool = True
    notes: str = ""


@dataclass(slots=True)
class SourceRecord:
    """插件输出的标准线索记录。"""

    domain: str
    title: str = ""
    baidu_pc_weight: int = 0
    baidu_mobile_weight: int = 0
    indexed_count: int = 0
    sogou_weight: int = 0
    so_weight: int = 0
    sm_weight: int = 0
    toutiao_weight: int = 0
    bing_weight: int = 0
    sogou_indexed_count: int = 0
    so_indexed_count: int = 0
    sm_indexed_count: int = 0
    toutiao_indexed_count: int = 0
    bing_indexed_count: int = 0
    icp_type: str = ""
    last_update: str = ""
    remark: str = ""
    source_provider: str = ""
    source_url: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_lead_row(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "title": self.title,
            "baidu_pc_weight": self.baidu_pc_weight,
            "baidu_mobile_weight": self.baidu_mobile_weight,
            "indexed_count": self.indexed_count,
            "sogou_weight": self.sogou_weight,
            "so_weight": self.so_weight,
            "sm_weight": self.sm_weight,
            "toutiao_weight": self.toutiao_weight,
            "bing_weight": self.bing_weight,
            "sogou_indexed_count": self.sogou_indexed_count,
            "so_indexed_count": self.so_indexed_count,
            "sm_indexed_count": self.sm_indexed_count,
            "toutiao_indexed_count": self.toutiao_indexed_count,
            "bing_indexed_count": self.bing_indexed_count,
            "icp_type": self.icp_type,
            "last_update": self.last_update,
            "remark": self.remark,
            "source_provider": self.source_provider,
            "source_url": self.source_url,
            "raw": self.raw,
        }


class DataSourceProvider(ABC):
    """所有数据源插件需要实现的基类。"""

    meta: ProviderMeta

    def get_meta(self) -> ProviderMeta:
        return self.meta

    def validate_file(self, filename: str) -> None:
        if not self.meta.accepted_extensions:
            return
        lower_name = filename.lower()
        if not any(lower_name.endswith(ext) for ext in self.meta.accepted_extensions):
            raise ProviderError(f"{self.meta.name} 不支持该文件类型：{filename}")

    @abstractmethod
    def parse_file(self, content: bytes, *, filename: str = "") -> list[SourceRecord]:
        """从上传文件中解析标准线索。"""

    async def fetch_remote(self, **_: Any) -> list[SourceRecord]:
        """远程数据源预留接口。"""
        raise ProviderError(f"{self.meta.name} 暂未实现远程抓取")
