from __future__ import annotations

import json
import smtplib
import unittest
from email.message import EmailMessage
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import Base
from app.models import AppSetting, DomainLead, EmailLog
from app.services.email_sender import EmailSendError, send_lead_email
from app.services.email_settings import EMAIL_SETTINGS_KEY


class FakeQqSmtp:
    instances: list["FakeQqSmtp"] = []

    def __init__(self, host: str, port: int, timeout: int) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.esmtp_features: dict[str, str] = {}
        self.auth_calls: list[str] = []
        self.login_calls = 0
        self.sent_messages: list[EmailMessage] = []
        self.sent_from_addr: str | None = None
        self.sent_to_addrs: list[str] | None = None
        FakeQqSmtp.instances.append(self)

    def __enter__(self) -> "FakeQqSmtp":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def ehlo(self) -> tuple[int, bytes]:
        self.esmtp_features = {"auth": "LOGIN PLAIN"}
        return 250, b"OK"

    def ehlo_or_helo_if_needed(self) -> tuple[int, bytes]:
        return self.ehlo()

    def auth_login(self, _challenge: bytes | None = None) -> bytes:
        return b""

    def auth(self, mechanism: str, _authobject: object) -> tuple[int, bytes]:
        self.auth_calls.append(mechanism)
        return 235, b"Authentication successful"

    def login(self, _user: str, _password: str) -> tuple[int, bytes]:
        self.login_calls += 1
        raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed")

    def send_message(
        self,
        msg: EmailMessage,
        from_addr: str | None = None,
        to_addrs: list[str] | None = None,
    ) -> None:
        self.sent_from_addr = from_addr
        self.sent_to_addrs = to_addrs
        self.sent_messages.append(msg)


class FakeQqSmtpAuthFailure(FakeQqSmtp):
    def auth(self, mechanism: str, _authobject: object) -> tuple[int, bytes]:
        self.auth_calls.append(mechanism)
        raise smtplib.SMTPAuthenticationError(
            535,
            b"Login fail. Account is abnormal, service is not open, password is incorrect",
        )


class EmailSenderTestCase(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(bind=engine)
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
        self.db: Session = self.SessionLocal()

    def tearDown(self) -> None:
        self.db.close()

    def add_lead(self) -> DomainLead:
        lead = DomainLead(domain="example.com", emails="buyer@example.test", lead_status="NEW")
        self.db.add(lead)
        self.db.commit()
        self.db.refresh(lead)
        return lead

    def save_email_settings(self, **overrides: object) -> None:
        data = {
            "receive_protocol": "imap",
            "receive_host": "imap.qq.com",
            "receive_port": 993,
            "receive_use_ssl": True,
            "smtp_host": "smtp.qq.com",
            "smtp_port": 465,
            "smtp_user": "sender@qq.com",
            "smtp_password": "authorization-code",
            "smtp_from": "sender@qq.com",
            "smtp_use_tls": False,
            "smtp_use_ssl": True,
        }
        data.update(overrides)
        self.db.add(AppSetting(key=EMAIL_SETTINGS_KEY, value=json.dumps(data, ensure_ascii=False)))
        self.db.commit()

    def test_qq_smtp_uses_auth_login_instead_of_default_login(self) -> None:
        self.save_email_settings()
        lead = self.add_lead()
        FakeQqSmtp.instances = []

        with patch("app.services.email_sender.smtplib.SMTP_SSL", FakeQqSmtp):
            log = send_lead_email(
                self.db,
                lead,
                to_email="buyer@example.test",
                subject="",
                body="hello",
            )

        smtp = FakeQqSmtp.instances[0]
        self.assertEqual(smtp.auth_calls, ["LOGIN"])
        self.assertEqual(smtp.login_calls, 0)
        self.assertEqual(len(smtp.sent_messages), 1)
        self.assertEqual(smtp.sent_from_addr, "sender@qq.com")
        self.assertEqual(smtp.sent_to_addrs, ["buyer@example.test"])
        self.assertEqual(log.status, "SENT")
        self.assertEqual(lead.lead_status, "CONTACTED")

    def test_chinese_sender_name_uses_smtp_user_as_envelope_from(self) -> None:
        self.save_email_settings(smtp_from="\u57df\u540d\u96f7\u8fbe")
        lead = self.add_lead()
        FakeQqSmtp.instances = []

        with patch("app.services.email_sender.smtplib.SMTP_SSL", FakeQqSmtp):
            log = send_lead_email(
                self.db,
                lead,
                to_email="\u5f20\u4e09 <buyer@example.test>",
                subject="\u54a8\u8be2\u57df\u540d",
                body="\u4e2d\u6587\u6b63\u6587",
            )

        smtp = FakeQqSmtp.instances[0]
        msg = smtp.sent_messages[0]
        self.assertEqual(smtp.sent_from_addr, "sender@qq.com")
        self.assertEqual(smtp.sent_to_addrs, ["buyer@example.test"])
        self.assertIn("sender@qq.com", str(msg["From"]))
        self.assertIn("buyer@example.test", str(msg["To"]))
        self.assertIsInstance(msg.as_bytes(), bytes)
        self.assertEqual(log.status, "SENT")

    def test_qq_smtp_auth_failure_is_actionable(self) -> None:
        self.save_email_settings()
        lead = self.add_lead()
        FakeQqSmtpAuthFailure.instances = []

        with patch("app.services.email_sender.smtplib.SMTP_SSL", FakeQqSmtpAuthFailure):
            with self.assertRaises(EmailSendError) as error:
                send_lead_email(
                    self.db,
                    lead,
                    to_email="buyer@example.test",
                    subject="",
                    body="hello",
                )

        self.assertIn("SMTP 认证失败", str(error.exception))
        self.assertIn("授权码", str(error.exception))
        log = self.db.scalar(select(EmailLog))
        self.assertIsNotNone(log)
        assert log is not None
        self.assertEqual(log.status, "FAILED")
        self.assertIn("SMTP 认证失败", log.error_message)

    def test_port_465_requires_ssl(self) -> None:
        self.save_email_settings(smtp_use_ssl=False, smtp_use_tls=True)
        lead = self.add_lead()

        with self.assertRaises(EmailSendError) as error:
            send_lead_email(
                self.db,
                lead,
                to_email="buyer@example.test",
                subject="",
                body="hello",
            )

        self.assertIn("465 端口通常必须开启 SSL", str(error.exception))
        self.assertIsNone(self.db.scalar(select(EmailLog)))

    def test_chinese_sender_name_requires_smtp_user_address(self) -> None:
        self.save_email_settings(
            smtp_user="",
            smtp_from="\u57df\u540d\u96f7\u8fbe",
        )
        lead = self.add_lead()

        with self.assertRaises(EmailSendError) as error:
            send_lead_email(
                self.db,
                lead,
                to_email="buyer@example.test",
                subject="",
                body="hello",
            )

        self.assertIn("有效发件邮箱", str(error.exception))
        self.assertIsNone(self.db.scalar(select(EmailLog)))


if __name__ == "__main__":
    unittest.main()
