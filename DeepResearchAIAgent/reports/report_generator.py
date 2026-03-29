"""
Report Generator — produces structured Markdown reports from ResearchState.
Three report types: company deep-dive | sector analysis | comparative study.
"""
from datetime import datetime
from pathlib import Path
from typing import Optional

from agents.base import ResearchState
from analysis.financial_calculator import (
    compare_companies, compute_growth_rate, compute_margins, detect_trend
)
import pandas as pd


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text.lower())[:40]


def _fmt_pct(val) -> str:
    if val is None:
        return "N/A"
    v = float(val)
    if abs(v) < 2:
        v *= 100
    return f"{v:.1f}%"


def _fmt_val(val, suffix="") -> str:
    if val is None:
        return "N/A"
    v = float(val)
    if abs(v) >= 1e9:
        return f"{v / 1e9:.2f}B{suffix}"
    if abs(v) >= 1e6:
        return f"{v / 1e6:.2f}M{suffix}"
    return f"{v:,.2f}{suffix}"


def _sources_section(sources: list[str]) -> str:
    if not sources:
        return "_No external sources recorded._\n"
    unique = list(dict.fromkeys(sources))[:15]
    lines = "\n".join(f"{i}. {url}" for i, url in enumerate(unique, 1))
    return lines + "\n"


def _findings_to_steps(findings: list[str]) -> str:
    if not findings:
        return "_No research steps recorded._\n"
    lines = []
    for f in findings:
        # Strip the [Step N | Tool] prefix for cleaner display
        clean = f.split("]", 1)[-1].strip() if "]" in f else f
        lines.append(f"- {clean[:300]}")
    return "\n".join(lines) + "\n"


def _financial_table(financial_data: dict) -> str:
    """Render financial_data dict as a Markdown table."""
    if not financial_data:
        return "_No financial data retrieved._\n"

    headers = ["Company", "Revenue", "EBITDA Margin", "Net Margin", "P/E", "ROE"]
    rows = [f"| {' | '.join(headers)} |", f"|{'|'.join(['---'] * len(headers))}|"]

    for ticker, d in financial_data.items():
        row = [
            d.get("name", ticker),
            _fmt_val(d.get("revenue")),
            _fmt_pct(d.get("ebitda_margin")),
            _fmt_pct(d.get("net_margin")),
            f"{float(d['pe_ratio']):.1f}x" if d.get("pe_ratio") else "N/A",
            _fmt_pct(d.get("roe")),
        ]
        rows.append(f"| {' | '.join(row)} |")

    return "\n".join(rows) + "\n"


# ── Report types ───────────────────────────────────────────────────────────────

def generate_company_report(state: ResearchState) -> str:
    """Deep-dive report for a single company query."""
    query    = state["query"]
    sector   = state["sector"]
    findings = state.get("findings", [])
    sources  = state.get("sources", [])
    fin_data = state.get("financial_data", {})
    synthesis = state.get("final_synthesis", "")
    steps    = state.get("step_count", 0)

    md = f"""# Company Research Report
**Query:** {query}
**Sector:** {sector} | **Generated:** {_now()} | **Research Steps:** {steps}

---

## Executive Summary
{synthesis if synthesis else "_Synthesis pending._"}

---

## Financial Snapshot
{_financial_table(fin_data)}

"""

    # Growth analysis if we have revenue data
    for ticker, d in fin_data.items():
        if d.get("revenue"):
            md += f"### {d.get('name', ticker)} — Key Metrics\n"
            md += f"- **Revenue:** {_fmt_val(d.get('revenue'))}\n"
            md += f"- **EBITDA Margin:** {_fmt_pct(d.get('ebitda_margin'))}\n"
            md += f"- **Net Margin:** {_fmt_pct(d.get('net_margin'))}\n"
            md += f"- **P/E Ratio:** {_fmt_val(d.get('pe_ratio'), 'x')}\n"
            md += f"- **ROE:** {_fmt_pct(d.get('roe'))}\n\n"

    md += f"""---

## Research Findings
{_findings_to_steps(findings)}

---

## Competitive Positioning
_{sector} sector context from research steps above._

---

## Future Outlook
_Derived from synthesis and research findings above._

---

## Sources
{_sources_section(sources)}
"""
    return md


def generate_sector_report(state: ResearchState) -> str:
    """Sector-wide analysis report."""
    query    = state["query"]
    sector   = state["sector"]
    findings = state.get("findings", [])
    sources  = state.get("sources", [])
    fin_data = state.get("financial_data", {})
    synthesis = state.get("final_synthesis", "")
    steps    = state.get("step_count", 0)

    # Build metrics list for comparison
    metrics_list = [
        {
            "name": d.get("name", ticker),
            "revenue": d.get("revenue"),
            "ebitda_margin": d.get("ebitda_margin"),
            "net_margin": d.get("net_margin"),
            "pe_ratio": d.get("pe_ratio"),
            "pb_ratio": d.get("pb_ratio"),
            "roe": d.get("roe"),
            "debt_to_equity": d.get("debt_to_equity"),
        }
        for ticker, d in fin_data.items()
    ]
    comparison = compare_companies(metrics_list)

    md = f"""# {sector} Sector Research Report
**Query:** {query}
**Generated:** {_now()} | **Research Steps:** {steps}

---

## Executive Summary
{synthesis if synthesis else "_Synthesis pending._"}

---

## Market Overview
_{sector} sector analysis based on {steps} research steps across web, documents, and financial APIs._

---

## Key Players — Financial Snapshot
{_financial_table(fin_data)}

"""

    if not comparison.dataframe.empty:
        md += "### Comparative Metrics\n"
        md += comparison.dataframe.to_markdown() + "\n\n"

    if comparison.insights:
        md += "### Key Observations\n"
        for insight in comparison.insights:
            md += f"- {insight}\n"
        md += "\n"

    md += f"""---

## Trend Analysis
{_findings_to_steps([f for f in findings if "| Analysis]" in f])}

---

## Regulatory Environment
_Covered in research findings below._

---

## Investment Opportunities & Risk Factors
_Derived from synthesis and research steps._

---

## Research Log
{_findings_to_steps(findings)}

---

## Sources
{_sources_section(sources)}
"""
    return md


def generate_comparative_report(states: list[ResearchState] | ResearchState) -> str:
    """Side-by-side comparison report — works with one or two ResearchStates."""
    if isinstance(states, dict):
        states = [states]

    # Merge data from all states
    all_findings = []
    all_sources  = []
    all_fin_data = {}
    for s in states:
        all_findings.extend(s.get("findings", []))
        all_sources.extend(s.get("sources", []))
        all_fin_data.update(s.get("financial_data", {}))

    query     = states[0]["query"]
    sectors   = " & ".join(sorted(set(s["sector"] for s in states)))
    synthesis = states[0].get("final_synthesis", "")
    steps     = sum(s.get("step_count", 0) for s in states)

    metrics_list = [
        {
            "name": d.get("name", ticker),
            "revenue": d.get("revenue"),
            "ebitda_margin": d.get("ebitda_margin"),
            "net_margin": d.get("net_margin"),
            "pe_ratio": d.get("pe_ratio"),
            "pb_ratio": d.get("pb_ratio"),
            "roe": d.get("roe"),
            "debt_to_equity": d.get("debt_to_equity"),
        }
        for ticker, d in all_fin_data.items()
    ]
    comparison = compare_companies(metrics_list)

    md = f"""# Comparative Research Report
**Query:** {query}
**Sectors:** {sectors} | **Generated:** {_now()} | **Research Steps:** {steps}

---

## Executive Summary
{synthesis if synthesis else "_Synthesis pending._"}

---

## Comparison Criteria
- Revenue scale and growth trajectory
- Profitability (EBITDA margin, net margin)
- Valuation multiples (P/E, P/B)
- Capital efficiency (ROE, Debt/Equity)

---

## Side-by-Side Metrics
{_financial_table(all_fin_data)}

"""

    if not comparison.dataframe.empty:
        md += "### Full Comparison Table\n"
        md += comparison.dataframe.to_markdown() + "\n\n"

    if comparison.insights:
        md += "### Best-in-Class\n"
        if comparison.best_ebitda_margin:
            md += f"- **Best EBITDA Margin:** {comparison.best_ebitda_margin}\n"
        if comparison.best_roe:
            md += f"- **Best ROE:** {comparison.best_roe}\n"
        if comparison.best_revenue_growth:
            md += f"- **Best Revenue Growth:** {comparison.best_revenue_growth}\n"
        md += "\n### Insights\n"
        for i in comparison.insights:
            md += f"- {i}\n"
        md += "\n"

    md += f"""---

## Individual Analysis
{_findings_to_steps(all_findings)}

---

## Recommendations
_Based on the comparative analysis above. Refer to individual metrics for investment decisions._

---

## Sources
{_sources_section(all_sources)}
"""
    return md


# ── Save & dispatch ────────────────────────────────────────────────────────────

def generate_report(state: ResearchState | list[ResearchState]) -> str:
    """
    Auto-select report type based on state query_type and dispatch.
    Works with single state or list (cross-sector).
    """
    if isinstance(state, list):
        return generate_comparative_report(state)

    query_type = state.get("query_type", "sector")

    if query_type == "company":
        return generate_company_report(state)
    elif query_type == "comparative":
        return generate_comparative_report(state)
    else:
        return generate_sector_report(state)


def save_report(content: str, topic: str, output_dir: str = "outputs/reports") -> str:
    """
    Write report to outputs/reports/YYYYMMDD_<topic>.md

    Returns:
        Absolute path of saved file
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    date_str = datetime.utcnow().strftime("%Y%m%d_%H%M")
    filename = f"{date_str}_{_slug(topic)}.md"
    path = Path(output_dir) / filename
    path.write_text(content, encoding="utf-8")
    return str(path.resolve())
