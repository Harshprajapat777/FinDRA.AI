from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text, Enum
)
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


class Base(DeclarativeBase):
    pass


class SectorEnum(str, enum.Enum):
    IT = "IT"
    PHARMA = "Pharma"
    CROSS = "cross-sector"


class SessionStatusEnum(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class QueryTypeEnum(str, enum.Enum):
    COMPANY = "company"
    SECTOR = "sector"
    COMPARATIVE = "comparative"


# ── Company ───────────────────────────────────────────────────────────────────

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    ticker = Column(String(20), nullable=True)
    sector = Column(String(50), nullable=False)
    exchange = Column(String(20), nullable=True)  # NSE / BSE / NASDAQ
    created_at = Column(DateTime, default=datetime.utcnow)

    metrics = relationship("FinancialMetric", back_populates="company", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Company {self.name} ({self.ticker})>"


# ── Financial Metric ──────────────────────────────────────────────────────────

class FinancialMetric(Base):
    __tablename__ = "financial_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    metric_name = Column(String(100), nullable=False)   # e.g. "revenue", "ebitda_margin"
    value = Column(Float, nullable=True)
    unit = Column(String(20), nullable=True)            # e.g. "INR_Cr", "USD_M", "%"
    period = Column(String(20), nullable=True)          # e.g. "FY2024", "Q3FY24"
    source = Column(String(200), nullable=True)         # URL or "yfinance"
    fetched_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="metrics")

    def __repr__(self):
        return f"<FinancialMetric {self.metric_name}={self.value} ({self.period})>"


# ── Research Session ──────────────────────────────────────────────────────────

class ResearchSession(Base):
    __tablename__ = "research_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), unique=True, nullable=False)  # UUID
    query = Column(Text, nullable=False)
    sector = Column(String(50), nullable=True)
    query_type = Column(String(20), nullable=True)
    depth = Column(String(10), default="standard")      # standard | deep
    status = Column(String(20), default=SessionStatusEnum.PENDING)
    report_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    steps = relationship("ResearchStep", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ResearchSession {self.session_id} [{self.status}]>"


# ── Research Step ─────────────────────────────────────────────────────────────

class ResearchStep(Base):
    __tablename__ = "research_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("research_sessions.id"), nullable=False)
    step_number = Column(Integer, nullable=False)
    tool_used = Column(String(50), nullable=True)       # web_search | rag | financial_api
    query_used = Column(Text, nullable=True)
    result_summary = Column(Text, nullable=True)
    sources = Column(Text, nullable=True)               # JSON list of URLs
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ResearchSession", back_populates="steps")

    def __repr__(self):
        return f"<ResearchStep {self.step_number} [{self.tool_used}]>"
