from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = Field(default="Domain Deal Radar", alias="APP_NAME")
    database_url: str = Field(default="sqlite:///./data/radar.db", alias="DATABASE_URL")
    crawler_concurrency: int = Field(default=5, alias="CRAWLER_CONCURRENCY")
    crawler_timeout_seconds: int = Field(default=8, alias="CRAWLER_TIMEOUT_SECONDS")

    # SMTP 邮件发送配置。留空时后端会拒绝发送，并提示先配置 .env。
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
