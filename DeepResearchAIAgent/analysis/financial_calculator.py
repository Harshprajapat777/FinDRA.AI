"""
Financial Calculator — all arithmetic done with pandas/numpy.
Zero LLM math. Every function takes raw numbers and returns computed results.
"""
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


# ── Result types ───────────────────────────────────────────────────────────────

@dataclass
class GrowthResult:
    cagr: Optional[float]           # compound annual growth rate
    yoy_rates: list[float]          # year-over-year % changes
    trend: str                      # "growing" | "declining" | "flat" | "volatile"
    avg_growth: Optional[float]


@dataclass
class MarginResult:
    gross_margin: Optional[float]
    ebitda_margin: Optional[float]
    net_margin: Optional[float]
    operating_leverage: Optional[float]   # delta EBITDA margin / delta revenue growth
    flag: Optional[str]                   # warning if margins look inconsistent


@dataclass
class CompanyComparison:
    dataframe: pd.DataFrame
    best_revenue_growth: Optional[str]
    best_ebitda_margin: Optional[str]
    best_roe: Optional[str]
    insights: list[str]


@dataclass
class ValidationResult:
    passed: bool
    discrepancies: list[str]
    warnings: list[str]


# ── Core functions ─────────────────────────────────────────────────────────────

def compute_growth_rate(values: list[float], periods_per_year: int = 1) -> GrowthResult:
    """
    Compute CAGR and YoY growth rates from a time-ordered list of values.

    Args:
        values:           Time-ordered values (oldest first)
        periods_per_year: 1 for annual, 4 for quarterly

    Returns:
        GrowthResult with CAGR, YoY list, trend label, avg growth
    """
    arr = np.array([v for v in values if v is not None and v > 0], dtype=float)

    if len(arr) < 2:
        return GrowthResult(cagr=None, yoy_rates=[], trend="insufficient data", avg_growth=None)

    # YoY rates
    yoy = list(((arr[1:] - arr[:-1]) / arr[:-1]) * 100)

    # CAGR
    n_years = (len(arr) - 1) / periods_per_year
    try:
        cagr = ((arr[-1] / arr[0]) ** (1 / n_years) - 1) * 100
        cagr = float(cagr) if not np.isnan(cagr) and not np.isinf(cagr) else None
    except (ZeroDivisionError, FloatingPointError):
        cagr = None

    avg_growth = float(np.mean(yoy)) if yoy else None

    # Trend classification
    if avg_growth is None:
        trend = "flat"
    elif avg_growth > 5:
        trend = "growing"
    elif avg_growth < -5:
        trend = "declining"
    else:
        std = float(np.std(yoy))
        trend = "volatile" if std > 15 else "flat"

    return GrowthResult(cagr=cagr, yoy_rates=[round(r, 2) for r in yoy], trend=trend, avg_growth=avg_growth)


def compute_margins(
    revenue: Optional[float],
    gross_profit: Optional[float] = None,
    ebitda: Optional[float] = None,
    net_income: Optional[float] = None,
    prev_ebitda_margin: Optional[float] = None,
    prev_revenue_growth: Optional[float] = None,
) -> MarginResult:
    """
    Compute gross / EBITDA / net margins and operating leverage.
    All division is safe — returns None on zero/None denominator.
    """
    def safe_pct(numerator, denominator) -> Optional[float]:
        if numerator is None or denominator is None or denominator == 0:
            return None
        result = (numerator / denominator) * 100
        return round(float(result), 2) if not np.isnan(result) and not np.isinf(result) else None

    gross_margin  = safe_pct(gross_profit, revenue)
    ebitda_margin = safe_pct(ebitda, revenue)
    net_margin    = safe_pct(net_income, revenue)

    # Operating leverage: change in EBITDA margin / change in revenue growth
    op_leverage = None
    if prev_ebitda_margin is not None and ebitda_margin is not None and prev_revenue_growth:
        delta_margin = ebitda_margin - prev_ebitda_margin
        try:
            op_leverage = round(delta_margin / prev_revenue_growth, 2)
        except ZeroDivisionError:
            pass

    # Sanity flag
    flag = None
    if gross_margin is not None and ebitda_margin is not None:
        if ebitda_margin > gross_margin:
            flag = "WARNING: EBITDA margin exceeds gross margin — verify inputs"

    return MarginResult(
        gross_margin=gross_margin,
        ebitda_margin=ebitda_margin,
        net_margin=net_margin,
        operating_leverage=op_leverage,
        flag=flag,
    )


def compare_companies(metrics_list: list[dict]) -> CompanyComparison:
    """
    Build a side-by-side comparison DataFrame from a list of metric dicts.

    Each dict should have keys: name, revenue, ebitda_margin, net_margin,
    pe_ratio, pb_ratio, roe, debt_to_equity, revenue_growth_cagr (optional)

    Returns:
        CompanyComparison with DataFrame + best-in-class labels + insights
    """
    if not metrics_list:
        return CompanyComparison(
            dataframe=pd.DataFrame(),
            best_revenue_growth=None,
            best_ebitda_margin=None,
            best_roe=None,
            insights=["No data available for comparison."],
        )

    rows = []
    for m in metrics_list:
        rows.append({
            "Company":          m.get("name", "Unknown"),
            "Revenue (M)":      _fmt_millions(m.get("revenue")),
            "EBITDA Margin %":  _fmt_pct(m.get("ebitda_margin")),
            "Net Margin %":     _fmt_pct(m.get("net_margin")),
            "P/E Ratio":        _fmt_num(m.get("pe_ratio")),
            "P/B Ratio":        _fmt_num(m.get("pb_ratio")),
            "ROE %":            _fmt_pct(m.get("roe")),
            "Debt/Equity":      _fmt_num(m.get("debt_to_equity")),
        })

    df = pd.DataFrame(rows).set_index("Company")

    # Best-in-class (raw values for comparison)
    best_rev_growth = _best_in(metrics_list, "revenue_growth_cagr")
    best_ebitda     = _best_in(metrics_list, "ebitda_margin")
    best_roe        = _best_in(metrics_list, "roe")

    # Auto-insights
    insights = []
    if best_ebitda:
        val = next((m.get("ebitda_margin") for m in metrics_list if m.get("name") == best_ebitda), None)
        if val:
            insights.append(f"{best_ebitda} leads on EBITDA margin at {_fmt_pct(val)}%")
    if best_roe:
        val = next((m.get("roe") for m in metrics_list if m.get("name") == best_roe), None)
        if val:
            insights.append(f"{best_roe} has the highest ROE at {_fmt_pct(val)}%")

    # Flag high P/E outliers
    pe_vals = [(m.get("name"), m.get("pe_ratio")) for m in metrics_list if m.get("pe_ratio")]
    if pe_vals:
        max_pe = max(pe_vals, key=lambda x: x[1])
        if max_pe[1] > 40:
            insights.append(f"{max_pe[0]} trades at a premium P/E of {_fmt_num(max_pe[1])}x — monitor growth delivery")

    return CompanyComparison(
        dataframe=df,
        best_revenue_growth=best_rev_growth,
        best_ebitda_margin=best_ebitda,
        best_roe=best_roe,
        insights=insights,
    )


def detect_trend(series: pd.Series) -> str:
    """
    Classify a numeric time series as growing / declining / flat / volatile.

    Args:
        series: pandas Series with numeric values (time-ordered, oldest first)

    Returns:
        Trend label string
    """
    clean = series.dropna()
    if len(clean) < 2:
        return "insufficient data"

    pct_changes = clean.pct_change().dropna() * 100
    avg = float(pct_changes.mean())
    std = float(pct_changes.std())

    if std > 20:
        return "volatile"
    if avg > 5:
        return "growing"
    if avg < -5:
        return "declining"
    return "flat"


def cross_validate(
    api_value: Optional[float],
    scraped_value: Optional[float],
    metric_name: str,
    threshold_pct: float = 5.0,
) -> ValidationResult:
    """
    Flag if two sources of the same metric diverge by more than threshold_pct %.
    """
    if api_value is None or scraped_value is None:
        return ValidationResult(passed=True, discrepancies=[], warnings=[f"{metric_name}: one source missing"])

    if scraped_value == 0:
        return ValidationResult(passed=True, discrepancies=[], warnings=[f"{metric_name}: scraped value is zero"])

    diff_pct = abs((api_value - scraped_value) / scraped_value) * 100

    if diff_pct > threshold_pct:
        msg = (
            f"{metric_name}: API={_fmt_num(api_value)}, "
            f"scraped={_fmt_num(scraped_value)}, "
            f"divergence={diff_pct:.1f}%"
        )
        return ValidationResult(passed=False, discrepancies=[msg], warnings=[])

    return ValidationResult(passed=True, discrepancies=[], warnings=[])


# ── Formatting helpers (private) ───────────────────────────────────────────────

def _fmt_millions(val) -> str:
    if val is None:
        return "N/A"
    v = float(val)
    if abs(v) >= 1e9:
        return f"{v / 1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"{v / 1e6:.2f}M"
    return f"{v:,.0f}"


def _fmt_pct(val) -> str:
    if val is None:
        return "N/A"
    v = float(val)
    # Handle both decimal (0.245) and percentage (24.5) forms
    if abs(v) < 2:
        v = v * 100
    return f"{v:.1f}"


def _fmt_num(val) -> str:
    if val is None:
        return "N/A"
    return f"{float(val):.2f}"


def _best_in(metrics_list: list[dict], key: str) -> Optional[str]:
    """Return company name with highest non-None value for a given key."""
    candidates = [(m.get("name"), m.get(key)) for m in metrics_list if m.get(key) is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda x: x[1])[0]
