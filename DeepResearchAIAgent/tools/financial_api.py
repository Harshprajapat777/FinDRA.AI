import json
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from database.repository import get_db, get_or_create_company, upsert_metric


@dataclass
class StockSnapshot:
    ticker: str
    name: str
    price: float
    currency: str
    market_cap: Optional[float]
    exchange: Optional[str]


@dataclass
class FinancialSummary:
    ticker: str
    name: str
    sector: str
    # Income statement
    revenue: Optional[float] = None
    ebitda: Optional[float] = None
    net_income: Optional[float] = None
    eps: Optional[float] = None
    # Margins (programmatic — not LLM)
    gross_margin: Optional[float] = None
    ebitda_margin: Optional[float] = None
    net_margin: Optional[float] = None
    # Balance sheet
    total_assets: Optional[float] = None
    total_debt: Optional[float] = None
    cash: Optional[float] = None
    # Ratios (programmatic — not LLM)
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    debt_to_equity: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None
    current_ratio: Optional[float] = None
    # Meta
    period: Optional[str] = None
    currency: Optional[str] = None
    errors: list[str] = field(default_factory=list)


class FinancialAPITool:

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _fetch_ticker(self, ticker: str) -> yf.Ticker:
        return yf.Ticker(ticker)

    def get_stock_snapshot(self, ticker: str) -> StockSnapshot:
        """Current price and market cap."""
        t = self._fetch_ticker(ticker)
        info = t.info
        return StockSnapshot(
            ticker=ticker,
            name=info.get("longName", ticker),
            price=info.get("currentPrice") or info.get("regularMarketPrice", 0.0),
            currency=info.get("currency", "INR"),
            market_cap=info.get("marketCap"),
            exchange=info.get("exchange"),
        )

    def get_financial_summary(self, ticker: str, sector: str = "Unknown") -> FinancialSummary:
        """
        Pull income statement + balance sheet, compute all ratios
        programmatically — zero LLM math.
        """
        summary = FinancialSummary(ticker=ticker, name=ticker, sector=sector)
        errors = []

        try:
            t = self._fetch_ticker(ticker)
            info = t.info
            summary.name = info.get("longName", ticker)
            summary.currency = info.get("currency", "INR")
            summary.period = "TTM"

            # ── Income Statement ────────────────────────────────────────────
            summary.revenue = info.get("totalRevenue")
            summary.ebitda = info.get("ebitda")
            summary.net_income = info.get("netIncomeToCommon")
            summary.eps = info.get("trailingEps")

            # ── Balance Sheet ───────────────────────────────────────────────
            summary.total_assets = info.get("totalAssets")
            summary.total_debt = info.get("totalDebt")
            summary.cash = info.get("totalCash")

            # ── Ratios — all programmatic ───────────────────────────────────
            summary.pe_ratio = self._safe_divide(
                info.get("currentPrice") or info.get("regularMarketPrice"),
                summary.eps,
            )
            summary.pb_ratio = info.get("priceToBook")
            summary.debt_to_equity = info.get("debtToEquity")
            summary.roe = info.get("returnOnEquity")
            summary.roa = info.get("returnOnAssets")
            summary.current_ratio = info.get("currentRatio")

            # Margins — programmatic from revenue
            summary.gross_margin = info.get("grossMargins")
            if summary.revenue and summary.ebitda:
                summary.ebitda_margin = self._safe_divide(summary.ebitda, summary.revenue)
            if summary.revenue and summary.net_income:
                summary.net_margin = self._safe_divide(summary.net_income, summary.revenue)

        except Exception as e:
            errors.append(f"yfinance error for {ticker}: {str(e)}")

        summary.errors = errors
        return summary

    def get_historical_data(self, ticker: str, period: str = "5y") -> pd.DataFrame:
        """
        OHLCV history for trend analysis.
        period: 1y | 3y | 5y | 10y
        """
        t = self._fetch_ticker(ticker)
        df = t.history(period=period)
        return df[["Open", "High", "Low", "Close", "Volume"]].dropna()

    def get_revenue_trend(self, ticker: str) -> dict:
        """
        Annual revenue trend from income statement.
        Returns {year: revenue_value} dict for charting.
        """
        t = self._fetch_ticker(ticker)
        try:
            income = t.financials  # columns = fiscal year dates
            if income is None or income.empty:
                return {}
            row = income.loc["Total Revenue"] if "Total Revenue" in income.index else None
            if row is None:
                return {}
            return {str(col.year): float(val) for col, val in row.items() if pd.notna(val)}
        except Exception:
            return {}

    def compare_companies(self, tickers: list[str], sector: str = "Unknown") -> pd.DataFrame:
        """
        Build a side-by-side comparison DataFrame for multiple tickers.
        All arithmetic is pandas — no LLM involved.
        """
        rows = []
        for ticker in tickers:
            s = self.get_financial_summary(ticker, sector)
            rows.append({
                "Company": s.name,
                "Ticker": s.ticker,
                "Revenue": s.revenue,
                "EBITDA": s.ebitda,
                "Net Income": s.net_income,
                "EBITDA Margin %": round(s.ebitda_margin * 100, 2) if s.ebitda_margin else None,
                "Net Margin %": round(s.net_margin * 100, 2) if s.net_margin else None,
                "P/E Ratio": s.pe_ratio,
                "P/B Ratio": s.pb_ratio,
                "ROE %": round(s.roe * 100, 2) if s.roe else None,
                "Debt/Equity": s.debt_to_equity,
            })
        return pd.DataFrame(rows).set_index("Company")

    def persist_metrics(self, summary: FinancialSummary, sector: str) -> None:
        """Save fetched metrics to the SQL database."""
        metric_map = {
            "revenue": (summary.revenue, "USD"),
            "ebitda": (summary.ebitda, "USD"),
            "net_income": (summary.net_income, "USD"),
            "ebitda_margin": (summary.ebitda_margin, "%"),
            "net_margin": (summary.net_margin, "%"),
            "pe_ratio": (summary.pe_ratio, "x"),
            "pb_ratio": (summary.pb_ratio, "x"),
            "roe": (summary.roe, "%"),
            "roa": (summary.roa, "%"),
            "debt_to_equity": (summary.debt_to_equity, "x"),
            "current_ratio": (summary.current_ratio, "x"),
        }
        with get_db() as db:
            company = get_or_create_company(
                db, name=summary.name, sector=sector, ticker=summary.ticker
            )
            for metric_name, (value, unit) in metric_map.items():
                if value is not None:
                    upsert_metric(
                        db,
                        company_id=company.id,
                        metric_name=metric_name,
                        value=float(value),
                        period=summary.period or "TTM",
                        unit=unit,
                        source="yfinance",
                    )

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _safe_divide(numerator, denominator) -> Optional[float]:
        """Division that returns None instead of ZeroDivisionError."""
        if numerator is None or denominator is None:
            return None
        try:
            result = float(numerator) / float(denominator)
            return None if np.isinf(result) or np.isnan(result) else result
        except (TypeError, ZeroDivisionError):
            return None

    def format_summary_for_llm(self, summary: FinancialSummary) -> str:
        """Render a FinancialSummary as clean text for LLM context injection."""
        def fmt(val, unit=""):
            if val is None:
                return "N/A"
            if unit == "%":
                return f"{val * 100:.1f}%"
            if abs(val) >= 1e9:
                return f"{val / 1e9:.2f}B {unit}".strip()
            if abs(val) >= 1e6:
                return f"{val / 1e6:.2f}M {unit}".strip()
            return f"{val:.2f} {unit}".strip()

        return (
            f"Company: {summary.name} ({summary.ticker})\n"
            f"Period: {summary.period} | Currency: {summary.currency}\n"
            f"Revenue: {fmt(summary.revenue, summary.currency or '')}\n"
            f"EBITDA: {fmt(summary.ebitda, summary.currency or '')} | "
            f"EBITDA Margin: {fmt(summary.ebitda_margin, '%')}\n"
            f"Net Income: {fmt(summary.net_income, summary.currency or '')} | "
            f"Net Margin: {fmt(summary.net_margin, '%')}\n"
            f"P/E: {fmt(summary.pe_ratio)} | P/B: {fmt(summary.pb_ratio)} | "
            f"ROE: {fmt(summary.roe, '%')}\n"
            f"Debt/Equity: {fmt(summary.debt_to_equity)} | "
            f"Current Ratio: {fmt(summary.current_ratio)}\n"
        )


# Module-level singleton
financial_api = FinancialAPITool()
