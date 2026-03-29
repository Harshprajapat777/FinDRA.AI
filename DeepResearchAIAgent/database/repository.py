from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Generator

from config.settings import settings
from database.models import Base, Company, FinancialMetric, ResearchSession, ResearchStep


# ── Engine & session factory ───────────────────────────────────────────────────

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Context manager for DB sessions — auto-closes on exit."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── Company ────────────────────────────────────────────────────────────────────

def get_or_create_company(db: Session, name: str, sector: str, ticker: str = None, exchange: str = None) -> Company:
    company = db.query(Company).filter_by(name=name).first()
    if not company:
        company = Company(name=name, sector=sector, ticker=ticker, exchange=exchange)
        db.add(company)
        db.flush()
    return company


def get_companies_by_sector(db: Session, sector: str) -> list[Company]:
    return db.query(Company).filter_by(sector=sector).all()


# ── Financial Metrics ──────────────────────────────────────────────────────────

def upsert_metric(
    db: Session,
    company_id: int,
    metric_name: str,
    value: float,
    period: str,
    unit: str = None,
    source: str = None,
) -> FinancialMetric:
    metric = (
        db.query(FinancialMetric)
        .filter_by(company_id=company_id, metric_name=metric_name, period=period)
        .first()
    )
    if metric:
        metric.value = value
        metric.source = source
    else:
        metric = FinancialMetric(
            company_id=company_id,
            metric_name=metric_name,
            value=value,
            unit=unit,
            period=period,
            source=source,
        )
        db.add(metric)
    db.flush()
    return metric


def get_metrics_for_company(db: Session, company_id: int, period: str = None) -> list[FinancialMetric]:
    q = db.query(FinancialMetric).filter_by(company_id=company_id)
    if period:
        q = q.filter_by(period=period)
    return q.order_by(FinancialMetric.period).all()


# ── Research Session ───────────────────────────────────────────────────────────

def create_session(db: Session, session_id: str, query: str, sector: str, query_type: str, depth: str) -> ResearchSession:
    session = ResearchSession(
        session_id=session_id,
        query=query,
        sector=sector,
        query_type=query_type,
        depth=depth,
        status="pending",
    )
    db.add(session)
    db.flush()
    return session


def get_session(db: Session, session_id: str) -> ResearchSession | None:
    return db.query(ResearchSession).filter_by(session_id=session_id).first()


def update_session_status(db: Session, session_id: str, status: str, report_path: str = None) -> None:
    from datetime import datetime
    session = get_session(db, session_id)
    if session:
        session.status = status
        if report_path:
            session.report_path = report_path
        if status in ("done", "failed"):
            session.completed_at = datetime.utcnow()
        db.flush()


# ── Research Step ──────────────────────────────────────────────────────────────

def add_step(
    db: Session,
    session_db_id: int,
    step_number: int,
    tool_used: str,
    query_used: str,
    result_summary: str,
    sources: str = None,
) -> ResearchStep:
    step = ResearchStep(
        session_id=session_db_id,
        step_number=step_number,
        tool_used=tool_used,
        query_used=query_used,
        result_summary=result_summary,
        sources=sources,
    )
    db.add(step)
    db.flush()
    return step


def get_steps_for_session(db: Session, session_db_id: int) -> list[ResearchStep]:
    return (
        db.query(ResearchStep)
        .filter_by(session_id=session_db_id)
        .order_by(ResearchStep.step_number)
        .all()
    )
