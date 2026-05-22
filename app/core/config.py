from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = Field(default="Domain Deal Radar", alias="APP_NAME")
    database_url: str = Field(default="sqlite:///./data/radar.db", alias="DATABASE_URL")
    crawler_concurrency: int = Field(default=5, alias="CRAWLER_CONCURRENCY")
    crawler_timeout_seconds: int = Field(default=8, alias="CRAWLER_TIMEOUT_SECONDS")
    search_engines: str = Field(default="baidu", alias="SEARCH_ENGINES")
    default_site_index_engines: str = Field(
        default="baidu,sogou,360,bing,toutiao,google",
        alias="DEFAULT_SITE_INDEX_ENGINES",
    )
    site_index_min_count: int = Field(default=10000, alias="SITE_INDEX_MIN_COUNT")
    search_concurrency: int = Field(default=2, alias="SEARCH_CONCURRENCY")
    search_timeout_seconds: int = Field(default=12, alias="SEARCH_TIMEOUT_SECONDS")
    aizhan_provider_mode: str = Field(default="manual", alias="AIZHAN_PROVIDER_MODE")
    whois_intel_provider_mode: str = Field(
        default="chinaz,rdap", alias="WHOIS_INTEL_PROVIDER_MODE"
    )
    ip_intel_provider_mode: str = Field(
        default="ipwhois", alias="IP_INTEL_PROVIDER_MODE"
    )

    # 邮件收件配置。当前用于全局账号配置展示，后续接入收信/回信同步时复用。
    mail_receive_protocol: str = Field(default="imap", alias="MAIL_RECEIVE_PROTOCOL")
    mail_receive_host: str = Field(default="", alias="MAIL_RECEIVE_HOST")
    mail_receive_port: int = Field(default=993, alias="MAIL_RECEIVE_PORT")
    mail_receive_use_ssl: bool = Field(default=True, alias="MAIL_RECEIVE_USE_SSL")

    # SMTP 邮件发送配置。留空时后端会拒绝发送，并提示先配置邮件设置或 .env。
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="", alias="SMTP_FROM")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    smtp_use_ssl: bool = Field(default=False, alias="SMTP_USE_SSL")

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
