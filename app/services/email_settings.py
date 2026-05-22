from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AppSetting

EMAIL_SETTINGS_KEY = "email.smtp"


@dataclass(slots=True)
class EffectiveEmailSettings:
    receive_protocol: str
    receive_host: str
    receive_port: int
    receive_use_ssl: bool
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    smtp_use_tls: bool
    smtp_use_ssl: bool
    source: str

    @property
    def has_password(self) -> bool:
        return bool(self.smtp_password)


def _dynamic_settings(db: Session) -> dict[str, Any]:
    row = db.get(AppSetting, EMAIL_SETTINGS_KEY)
    if row is None or not row.value:
        return {}
    try:
        data = json.loads(row.value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def get_effective_email_settings(db: Session) -> EffectiveEmailSettings:
    env = get_settings()
    dynamic = _dynamic_settings(db)
    source = "dynamic" if dynamic else "env"
    receive_protocol = str(dynamic.get("receive_protocol") or env.mail_receive_protocol or "imap").strip().lower()
    if receive_protocol not in {"imap", "pop3"}:
        receive_protocol = "imap"

    return EffectiveEmailSettings(
        receive_protocol=receive_protocol,
        receive_host=str(dynamic.get("receive_host") or env.mail_receive_host or "").strip(),
        receive_port=int(dynamic.get("receive_port") or env.mail_receive_port or 993),
        receive_use_ssl=bool(dynamic.get("receive_use_ssl", env.mail_receive_use_ssl)),
        smtp_host=str(dynamic.get("smtp_host") or env.smtp_host or "").strip(),
        smtp_port=int(dynamic.get("smtp_port") or env.smtp_port or 587),
        smtp_user=str(dynamic.get("smtp_user") or env.smtp_user or "").strip(),
        smtp_password=str(dynamic.get("smtp_password") or env.smtp_password or ""),
        smtp_from=str(dynamic.get("smtp_from") or env.smtp_from or "").strip(),
        smtp_use_tls=bool(dynamic.get("smtp_use_tls", env.smtp_use_tls)),
        smtp_use_ssl=bool(dynamic.get("smtp_use_ssl", env.smtp_use_ssl)),
        source=source,
    )


def serialize_email_settings(db: Session) -> dict[str, object]:
    config = get_effective_email_settings(db)
    return {
        "receive_protocol": config.receive_protocol,
        "receive_host": config.receive_host,
        "receive_port": config.receive_port,
        "receive_use_ssl": config.receive_use_ssl,
        "smtp_host": config.smtp_host,
        "smtp_port": config.smtp_port,
        "smtp_user": config.smtp_user,
        "smtp_from": config.smtp_from,
        "smtp_use_tls": config.smtp_use_tls,
        "smtp_use_ssl": config.smtp_use_ssl,
        "has_password": config.has_password,
        "source": config.source,
    }


def save_email_settings(db: Session, payload: dict[str, Any]) -> dict[str, object]:
    current = _dynamic_settings(db)
    password = payload.get("smtp_password")
    if password is None or password == "":
        password = current.get("smtp_password", "")
    receive_protocol = str(payload.get("receive_protocol") or "imap").strip().lower()
    if receive_protocol not in {"imap", "pop3"}:
        receive_protocol = "imap"

    data = {
        "receive_protocol": receive_protocol,
        "receive_host": str(payload.get("receive_host") or "").strip(),
        "receive_port": int(payload.get("receive_port") or 993),
        "receive_use_ssl": bool(payload.get("receive_use_ssl", True)),
        "smtp_host": str(payload.get("smtp_host") or "").strip(),
        "smtp_port": int(payload.get("smtp_port") or 587),
        "smtp_user": str(payload.get("smtp_user") or "").strip(),
        "smtp_password": str(password or ""),
        "smtp_from": str(payload.get("smtp_from") or "").strip(),
        "smtp_use_tls": bool(payload.get("smtp_use_tls", True)),
        "smtp_use_ssl": bool(payload.get("smtp_use_ssl", False)),
    }

    row = db.get(AppSetting, EMAIL_SETTINGS_KEY)
    if row is None:
        row = AppSetting(key=EMAIL_SETTINGS_KEY)
        db.add(row)
    row.value = json.dumps(data, ensure_ascii=False)
    row.updated_at = datetime.utcnow()
    db.commit()
    return serialize_email_settings(db)
