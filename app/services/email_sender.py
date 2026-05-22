from __future__ import annotations

import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from sqlalchemy.orm import Session

from app.models import DomainLead, EmailLog
from app.services.activities import build_activity
from app.services.email_settings import get_effective_email_settings


class EmailSendError(RuntimeError):
    pass


def _decode_smtp_payload(payload: object) -> str:
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="replace").strip()
    return str(payload).strip()


def _is_qq_smtp_host(host: str) -> bool:
    normalized = host.strip().lower().rstrip(".")
    return normalized == "smtp.qq.com" or normalized.endswith(".qq.com")


def _smtp_auth_methods(server: smtplib.SMTP) -> set[str]:
    auth = server.esmtp_features.get("auth", "")
    return {method.upper() for method in auth.split()}


def _smtp_login(server: smtplib.SMTP, *, host: str, user: str, password: str) -> None:
    if not user:
        return
    server.ehlo_or_helo_if_needed()

    # QQ SMTP advertises AUTH PLAIN, but in practice it can close the connection
    # during Python's default login negotiation. AUTH LOGIN returns stable errors.
    if _is_qq_smtp_host(host) and "LOGIN" in _smtp_auth_methods(server):
        server.user = user
        server.password = password
        server.auth("LOGIN", server.auth_login)
        return

    server.login(user, password)


def _validate_smtp_settings(settings: object) -> None:
    smtp_use_ssl = bool(getattr(settings, "smtp_use_ssl"))
    smtp_use_tls = bool(getattr(settings, "smtp_use_tls"))
    smtp_port = int(getattr(settings, "smtp_port"))

    if smtp_use_ssl and smtp_use_tls:
        raise EmailSendError("SMTP 加密配置错误：SSL 和 STARTTLS 只能开启一个")
    if smtp_port == 465 and not smtp_use_ssl:
        raise EmailSendError("SMTP 加密配置错误：465 端口通常必须开启 SSL，并关闭 STARTTLS")


def _smtp_error_message(exc: Exception, settings: object) -> str:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        detail = _decode_smtp_payload(exc.smtp_error)
        suffix = ""
        if _is_qq_smtp_host(str(getattr(settings, "smtp_host", ""))):
            suffix = "请确认 QQ 邮箱已开启 SMTP/POP3/IMAP 服务，并使用邮箱授权码，不要使用网页登录密码。"
        return f"SMTP 认证失败：{detail or exc.smtp_code}。{suffix}".strip()

    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return "SMTP 连接被服务器关闭：请检查端口与 SSL/STARTTLS 配置是否匹配，并确认账号授权码有效"

    return str(exc)


def _is_ascii_email_address(value: str) -> bool:
    return "@" in value and all(ord(char) < 128 for char in value)


def _sender_identity(settings: object) -> tuple[str, str]:
    smtp_user = str(getattr(settings, "smtp_user") or "").strip()
    smtp_from = str(getattr(settings, "smtp_from") or "").strip()
    display_name = "Domain Deal Radar"
    address = ""

    if smtp_from:
        parsed_display, parsed_address = parseaddr(smtp_from)
        if _is_ascii_email_address(parsed_address):
            address = parsed_address
            display_name = parsed_display.strip() or display_name
        else:
            display_name = smtp_from

    if not address:
        address = smtp_user

    if not _is_ascii_email_address(address):
        raise EmailSendError("SMTP 发件人配置错误：请填写有效发件邮箱；中文名称可以填在发件人名称中")

    return formataddr((display_name, address), charset="utf-8"), address


def _recipient_identity(to_email: str) -> tuple[str, str]:
    parsed_display, parsed_address = parseaddr(to_email.strip())
    if not _is_ascii_email_address(parsed_address):
        raise EmailSendError("收件人邮箱格式错误：请填写有效邮箱地址")
    if parsed_display.strip():
        return formataddr((parsed_display.strip(), parsed_address), charset="utf-8"), parsed_address
    return parsed_address, parsed_address


def send_lead_email(db: Session, lead: DomainLead, *, to_email: str, subject: str, body: str) -> EmailLog:
    settings = get_effective_email_settings(db)
    if not settings.smtp_host:
        raise EmailSendError("SMTP 未配置：请先在邮件设置中填写 SMTP 主机和发件人，或配置 .env")
    _validate_smtp_settings(settings)
    from_header, envelope_from = _sender_identity(settings)
    to_header, envelope_to = _recipient_identity(to_email)

    log = EmailLog(
        lead_id=lead.id,
        domain=lead.domain,
        to_email=to_email.strip(),
        subject=subject.strip() or f"咨询域名 {lead.domain} 是否考虑转让",
        body=body,
        status="PENDING",
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    try:
        msg = EmailMessage()
        msg["From"] = from_header
        msg["To"] = to_header
        msg["Subject"] = log.subject
        msg.set_content(body)

        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20) as server:
                server.ehlo()
                _smtp_login(
                    server,
                    host=settings.smtp_host,
                    user=settings.smtp_user,
                    password=settings.smtp_password,
                )
                server.send_message(msg, from_addr=envelope_from, to_addrs=[envelope_to])
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
                server.ehlo()
                if settings.smtp_use_tls:
                    server.starttls()
                    server.ehlo()
                _smtp_login(
                    server,
                    host=settings.smtp_host,
                    user=settings.smtp_user,
                    password=settings.smtp_password,
                )
                server.send_message(msg, from_addr=envelope_from, to_addrs=[envelope_to])

        now = datetime.utcnow()
        log.status = "SENT"
        log.sent_at = now
        lead.last_email_to = to_email.strip()
        lead.last_email_subject = log.subject
        lead.last_emailed_at = now
        lead.last_contacted_at = now
        lead.contact_message = body
        if not lead.next_action:
            lead.next_action = "等待回复，三天后跟进"
        scheduled_follow_up = False
        if not lead.next_follow_up_at:
            lead.next_follow_up_at = now + timedelta(days=3)
            scheduled_follow_up = True
        if lead.lead_status == "NEW":
            lead.lead_status = "CONTACTED"
        db.add(
            build_activity(
                lead,
                event_type="EMAIL_SENT",
                title="邮件已发送",
                detail=f"发送至 {to_email.strip()}",
            )
        )
        if scheduled_follow_up:
            db.add(
                build_activity(
                    lead,
                    event_type="FOLLOW_UP_SCHEDULED",
                    title="已自动安排下次跟进",
                    detail=lead.next_follow_up_at.isoformat(sep=" ", timespec="minutes"),
                )
            )
        db.commit()
        db.refresh(log)
        return log
    except Exception as exc:  # noqa: BLE001
        error_message = _smtp_error_message(exc, settings)
        log.status = "FAILED"
        log.error_message = error_message
        db.commit()
        raise EmailSendError(f"邮件发送失败：{error_message}") from exc
