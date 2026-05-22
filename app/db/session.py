from collections.abc import Generator
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return
    db_path = database_url.replace("sqlite:///", "", 1)
    if db_path.startswith("./"):
        db_path = db_path[2:]
    parent = Path(db_path).parent
    parent.mkdir(parents=True, exist_ok=True)


settings = get_settings()
_ensure_sqlite_dir(settings.database_url)

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_sqlite_columns() -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    with engine.begin() as conn:
        existing_tables = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='domain_leads'"
        ).fetchall()
        if not existing_tables:
            return

        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(domain_leads)").fetchall()}
        migrations = {
            "source_provider": "ALTER TABLE domain_leads ADD COLUMN source_provider VARCHAR(100) DEFAULT ''",
            "source_url": "ALTER TABLE domain_leads ADD COLUMN source_url VARCHAR(1000) DEFAULT ''",
            "crawl_status": "ALTER TABLE domain_leads ADD COLUMN crawl_status VARCHAR(50) DEFAULT 'PENDING'",
            "crawl_error": "ALTER TABLE domain_leads ADD COLUMN crawl_error TEXT DEFAULT ''",
            "crawl_pages_done": "ALTER TABLE domain_leads ADD COLUMN crawl_pages_done INTEGER DEFAULT 0",
            "crawl_pages_total": "ALTER TABLE domain_leads ADD COLUMN crawl_pages_total INTEGER DEFAULT 0",
            "last_crawled_at": "ALTER TABLE domain_leads ADD COLUMN last_crawled_at DATETIME",
            "analysis_status": "ALTER TABLE domain_leads ADD COLUMN analysis_status VARCHAR(50) DEFAULT 'PENDING'",
            "analysis_error": "ALTER TABLE domain_leads ADD COLUMN analysis_error TEXT DEFAULT ''",
            "dns_resolved": "ALTER TABLE domain_leads ADD COLUMN dns_resolved BOOLEAN DEFAULT 0",
            "resolved_ips": "ALTER TABLE domain_leads ADD COLUMN resolved_ips TEXT DEFAULT ''",
            "ssl_status": "ALTER TABLE domain_leads ADD COLUMN ssl_status VARCHAR(50) DEFAULT ''",
            "ssl_expires_at": "ALTER TABLE domain_leads ADD COLUMN ssl_expires_at DATETIME",
            "ssl_days_left": "ALTER TABLE domain_leads ADD COLUMN ssl_days_left INTEGER DEFAULT 0",
            "icp_number": "ALTER TABLE domain_leads ADD COLUMN icp_number VARCHAR(255) DEFAULT ''",
            "public_security_record": "ALTER TABLE domain_leads ADD COLUMN public_security_record VARCHAR(255) DEFAULT ''",
            "site_health": "ALTER TABLE domain_leads ADD COLUMN site_health VARCHAR(80) DEFAULT ''",
            "enhanced_risk_flags": "ALTER TABLE domain_leads ADD COLUMN enhanced_risk_flags TEXT DEFAULT ''",
            "last_analyzed_at": "ALTER TABLE domain_leads ADD COLUMN last_analyzed_at DATETIME",
            "discovered_from": "ALTER TABLE domain_leads ADD COLUMN discovered_from VARCHAR(255) DEFAULT ''",
            "registration_status": "ALTER TABLE domain_leads ADD COLUMN registration_status VARCHAR(50) DEFAULT 'UNCHECKED'",
            "registrar_name": "ALTER TABLE domain_leads ADD COLUMN registrar_name VARCHAR(255) DEFAULT ''",
            "registrar_handle": "ALTER TABLE domain_leads ADD COLUMN registrar_handle VARCHAR(255) DEFAULT ''",
            "domain_registered_at": "ALTER TABLE domain_leads ADD COLUMN domain_registered_at DATETIME",
            "domain_expires_at": "ALTER TABLE domain_leads ADD COLUMN domain_expires_at DATETIME",
            "domain_age_days": "ALTER TABLE domain_leads ADD COLUMN domain_age_days INTEGER DEFAULT 0",
            "days_until_expiry": "ALTER TABLE domain_leads ADD COLUMN days_until_expiry INTEGER DEFAULT 0",
            "rdap_status": "ALTER TABLE domain_leads ADD COLUMN rdap_status TEXT DEFAULT ''",
            "rdap_source_url": "ALTER TABLE domain_leads ADD COLUMN rdap_source_url VARCHAR(1200) DEFAULT ''",
            "rdap_error": "ALTER TABLE domain_leads ADD COLUMN rdap_error TEXT DEFAULT ''",
            "last_registration_checked_at": "ALTER TABLE domain_leads ADD COLUMN last_registration_checked_at DATETIME",
            "buyability_score": "ALTER TABLE domain_leads ADD COLUMN buyability_score INTEGER DEFAULT 0",
            "buyability_grade": "ALTER TABLE domain_leads ADD COLUMN buyability_grade VARCHAR(50) DEFAULT 'UNKNOWN'",
            "buyability_reasons": "ALTER TABLE domain_leads ADD COLUMN buyability_reasons TEXT DEFAULT '[]'",
            "history_status": "ALTER TABLE domain_leads ADD COLUMN history_status VARCHAR(50) DEFAULT 'UNCHECKED'",
            "archive_first_seen_at": "ALTER TABLE domain_leads ADD COLUMN archive_first_seen_at DATETIME",
            "archive_last_seen_at": "ALTER TABLE domain_leads ADD COLUMN archive_last_seen_at DATETIME",
            "archive_snapshot_count": "ALTER TABLE domain_leads ADD COLUMN archive_snapshot_count INTEGER DEFAULT 0",
            "archive_active_years": "ALTER TABLE domain_leads ADD COLUMN archive_active_years INTEGER DEFAULT 0",
            "archive_source_url": "ALTER TABLE domain_leads ADD COLUMN archive_source_url VARCHAR(1200) DEFAULT ''",
            "history_error": "ALTER TABLE domain_leads ADD COLUMN history_error TEXT DEFAULT ''",
            "last_history_checked_at": "ALTER TABLE domain_leads ADD COLUMN last_history_checked_at DATETIME",
            "history_score": "ALTER TABLE domain_leads ADD COLUMN history_score INTEGER DEFAULT 0",
            "history_grade": "ALTER TABLE domain_leads ADD COLUMN history_grade VARCHAR(50) DEFAULT 'UNKNOWN'",
            "history_reasons": "ALTER TABLE domain_leads ADD COLUMN history_reasons TEXT DEFAULT '[]'",
            "score_breakdown": "ALTER TABLE domain_leads ADD COLUMN score_breakdown TEXT DEFAULT '[]'",
            "sogou_weight": "ALTER TABLE domain_leads ADD COLUMN sogou_weight INTEGER DEFAULT 0",
            "so_weight": "ALTER TABLE domain_leads ADD COLUMN so_weight INTEGER DEFAULT 0",
            "sm_weight": "ALTER TABLE domain_leads ADD COLUMN sm_weight INTEGER DEFAULT 0",
            "toutiao_weight": "ALTER TABLE domain_leads ADD COLUMN toutiao_weight INTEGER DEFAULT 0",
            "bing_weight": "ALTER TABLE domain_leads ADD COLUMN bing_weight INTEGER DEFAULT 0",
            "sogou_indexed_count": "ALTER TABLE domain_leads ADD COLUMN sogou_indexed_count INTEGER DEFAULT 0",
            "so_indexed_count": "ALTER TABLE domain_leads ADD COLUMN so_indexed_count INTEGER DEFAULT 0",
            "sm_indexed_count": "ALTER TABLE domain_leads ADD COLUMN sm_indexed_count INTEGER DEFAULT 0",
            "toutiao_indexed_count": "ALTER TABLE domain_leads ADD COLUMN toutiao_indexed_count INTEGER DEFAULT 0",
            "bing_indexed_count": "ALTER TABLE domain_leads ADD COLUMN bing_indexed_count INTEGER DEFAULT 0",
            "contact_message": "ALTER TABLE domain_leads ADD COLUMN contact_message TEXT DEFAULT ''",
            "next_action": "ALTER TABLE domain_leads ADD COLUMN next_action VARCHAR(255) DEFAULT ''",
            "next_follow_up_at": "ALTER TABLE domain_leads ADD COLUMN next_follow_up_at DATETIME",
            "last_contacted_at": "ALTER TABLE domain_leads ADD COLUMN last_contacted_at DATETIME",
            "last_email_to": "ALTER TABLE domain_leads ADD COLUMN last_email_to VARCHAR(500) DEFAULT ''",
            "last_email_subject": "ALTER TABLE domain_leads ADD COLUMN last_email_subject VARCHAR(500) DEFAULT ''",
            "last_emailed_at": "ALTER TABLE domain_leads ADD COLUMN last_emailed_at DATETIME",
        }
        for column_name, sql in migrations.items():
            if column_name not in columns:
                conn.exec_driver_sql(sql)


def init_db() -> None:
    from app.models.domain_lead import AppSetting, CrawlLog, CrawlTask, DiscoveryTask, DomainCandidate, DomainLead, EmailLog, LeadActivity  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_columns()
