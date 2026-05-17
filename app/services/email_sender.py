from __future__ import annotations

import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import DomainLead, EmailLog
from app.services.activities import build_activity


class EmailSendError(RuntimeError):
    pass


def _first_configured_sender() -> tuple[str, str]:
    settings = get_settings()
    sender = settings.smtp_from or settings.smtp_user
    if not settings.smtp_host or not sender:
        raise EmailSendError("SMTP 未配置：请先在 .env 中填写 SMTP_HOST、SMTP_USER、SMTP_PASSWORD、SMTP_FROM")
    return sender, settings.smtp_user


def send_lead_email(db: Session, lead: DomainLead, *, to_email: str, subject: str, body: str) -> EmailLog:
    settings = get_settings()
    sender, smtp_user = _first_configured_sender()

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
        msg["From"] = formataddr(("Domain Deal Radar", sender))
        msg["To"] = to_email.strip()
        msg["Subject"] = log.subject
        msg.set_content(body)

        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20) as server:
                if smtp_user:
                    server.login(smtp_user, settings.smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
                server.ehlo()
                if settings.smtp_use_tls:
                    server.starttls()
                    server.ehlo()
                if smtp_user:
                    server.login(smtp_user, settings.smtp_password)
                server.send_message(msg)

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
        log.status = "FAILED"
        log.error_message = str(exc)
        db.commit()
        raise EmailSendError(f"邮件发送失败：{exc}") from exc
