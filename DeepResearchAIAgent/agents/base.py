"""
Base research agent — shared LangGraph StateGraph loop used by every sector agent.

Flow:
  search_web → query_rag → fetch_financials → analyse_findings → check_depth
       ^____________________________________________________|  (loop back if depth not reached)
"""
import json
from typing import TypedDict, Annotated, Optional
import operator

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END

from config.settings import settings
from tools.web_search import web_search
from tools.financial_api import financial_api
from rag.vector_store import vector_store


# ── State ──────────────────────────────────────────────────────────────────────

class ResearchState(TypedDict):
    # Input
    query: str
    sector: str
    depth: str                          # "standard" | "deep"
    query_type: str                     # "company" | "sector" | "comparative"
    session_id: str

    # Accumulating research data
    findings: Annotated[list[str], operator.add]      # each step appends a summary
    sources: Annotated[list[str], operator.add]        # URLs collected
    companies_found: Annotated[list[str], operator.add]  # tickers/names discovered
    financial_data: dict                               # ticker -> FinancialSummary dict

    # Loop control
    step_count: int
    current_focus: str                  # what the next search step should dig into
    max_steps: int

    # Output
    report_type: str
    final_synthesis: str
    status: str                         # "running" | "done" | "failed"


# ── LLM ───────────────────────────────────────────────────────────────────────

def _get_llm() -> ChatAnthropic:
    return ChatAnthropic(
        model="claude-sonnet-4-6",
        api_key=settings.anthropic_api_key,
        max_tokens=2048,
        temperature=0.3,
    )


# ── Node helpers ───────────────────────────────────────────────────────────────

def _extract_tickers(text: str, sector_tickers: dict) -> list[str]:
    """Find known sector tickers mentioned in a block of text."""
    found = []
    text_upper = text.upper()
    for name, ticker in sector_tickers.items():
        if name.upper() in text_upper or ticker.upper() in text_upper:
            if ticker not in found:
                found.append(ticker)
    return found


# ── Base Agent Class ───────────────────────────────────────────────────────────

class BaseResearchAgent:
    """
    Subclass this and define:
      - sector_name: str
      - sector_tickers: dict  {company_name: exchange_ticker}
      - system_prompt: str
      - domain_kpis: list[str]
    """
    sector_name: str = "general"
    sector_tickers: dict = {}
    system_prompt: str = "You are a financial research analyst."
    domain_kpis: list[str] = []

    def __init__(self):
        self._llm = _get_llm()
        self._graph = self._build_graph()

    # ── Graph construction ─────────────────────────────────────────────────────

    def _build_graph(self) -> StateGraph:
        g = StateGraph(ResearchState)

        g.add_node("search_web", self._node_search_web)
        g.add_node("query_rag", self._node_query_rag)
        g.add_node("fetch_financials", self._node_fetch_financials)
        g.add_node("analyse_findings", self._node_analyse_findings)
        g.add_node("check_depth", self._node_check_depth)

        g.set_entry_point("search_web")
        g.add_edge("search_web", "query_rag")
        g.add_edge("query_rag", "fetch_financials")
        g.add_edge("fetch_financials", "analyse_findings")
        g.add_edge("analyse_findings", "check_depth")
        g.add_conditional_edges(
            "check_depth",
            self._should_continue,
            {"continue": "search_web", "done": END},
        )

        return g.compile()

    # ── Nodes ──────────────────────────────────────────────────────────────────

    def _node_search_web(self, state: ResearchState) -> dict:
        focus = state.get("current_focus") or state["query"]
        results = web_search.search_financial_news(focus, max_results=settings.max_search_results)

        sources = [r.url for r in results]
        summary = web_search.format_for_llm(results)

        tickers = []
        for r in results:
            tickers += _extract_tickers(r.title + " " + r.content, self.sector_tickers)

        return {
            "findings": [f"[Step {state['step_count'] + 1} | Web] Query: '{focus}'\n{summary[:1000]}"],
            "sources": sources,
            "companies_found": list(set(tickers)),
            "step_count": state["step_count"] + 1,
        }

    def _node_query_rag(self, state: ResearchState) -> dict:
        focus = state.get("current_focus") or state["query"]
        chunks = vector_store.query(focus, sector=self.sector_name, n_results=3)

        if not chunks:
            return {"findings": [f"[Step {state['step_count']} | RAG] No document passages found for: '{focus}'"]}

        rag_text = vector_store.format_for_llm(chunks)
        return {
            "findings": [f"[Step {state['step_count']} | RAG] Retrieved passages:\n{rag_text[:800]}"],
        }

    def _node_fetch_financials(self, state: ResearchState) -> dict:
        tickers = list(set(state.get("companies_found", [])))
        if not tickers:
            return {}

        financial_data = dict(state.get("financial_data") or {})
        new_findings = []

        for ticker in tickers[:3]:  # cap at 3 per step to avoid rate limits
            if ticker in financial_data:
                continue
            try:
                summary = financial_api.get_financial_summary(ticker, self.sector_name)
                financial_api.persist_metrics(summary, self.sector_name)
                financial_data[ticker] = {
                    "name": summary.name,
                    "revenue": summary.revenue,
                    "ebitda_margin": summary.ebitda_margin,
                    "net_margin": summary.net_margin,
                    "pe_ratio": summary.pe_ratio,
                    "roe": summary.roe,
                    "period": summary.period,
                    "currency": summary.currency,
                }
                new_findings.append(
                    f"[Step {state['step_count']} | API] {ticker}:\n"
                    + financial_api.format_summary_for_llm(summary)
                )
            except Exception as e:
                new_findings.append(f"[Step {state['step_count']} | API] {ticker}: fetch failed — {e}")

        return {"findings": new_findings, "financial_data": financial_data}

    def _node_analyse_findings(self, state: ResearchState) -> dict:
        """
        LLM synthesises latest findings and decides what to research next.
        This drives the iterative deepening — each finding informs the next query.
        """
        recent = "\n\n".join(state["findings"][-4:])  # last 4 entries for context
        kpis = ", ".join(self.domain_kpis) if self.domain_kpis else "standard financial metrics"

        prompt = f"""You are a {self.sector_name} sector financial analyst.

Original query: {state['query']}
Steps completed: {state['step_count']} / {state['max_steps']}

Recent research findings:
{recent}

Based on these findings, identify:
1. The single most important aspect still uninvestigated
2. A precise search query (under 12 words) to dig deeper into it

Focus on {self.sector_name}-specific KPIs: {kpis}

Respond in this exact JSON format:
{{"insight": "one sentence summary of what you just learned", "next_focus": "precise search query for next step"}}"""

        try:
            response = self._llm.invoke([
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=prompt),
            ])
            data = json.loads(response.content)
            insight = data.get("insight", "")
            next_focus = data.get("next_focus", state["query"])
        except Exception:
            insight = "Continuing research..."
            next_focus = f"{self.sector_name} sector {state['query']} latest trends"

        return {
            "findings": [f"[Step {state['step_count']} | Analysis] {insight}"],
            "current_focus": next_focus,
        }

    def _node_check_depth(self, state: ResearchState) -> dict:
        return {}

    def _should_continue(self, state: ResearchState) -> str:
        if state["step_count"] >= state["max_steps"]:
            return "done"
        return "continue"

    # ── Public API ─────────────────────────────────────────────────────────────

    def run(self, query: str, depth: str = "standard", session_id: str = "") -> ResearchState:
        """
        Execute the full research loop and return the final state.

        Args:
            query:      User's research question
            depth:      "standard" (10 steps) or "deep" (20 steps)
            session_id: UUID from the research session DB record

        Returns:
            Completed ResearchState with all findings + financial data
        """
        max_steps = (
            settings.deep_research_depth
            if depth == "deep"
            else settings.standard_research_depth
        )

        initial_state: ResearchState = {
            "query": query,
            "sector": self.sector_name,
            "depth": depth,
            "query_type": "sector",
            "session_id": session_id,
            "findings": [],
            "sources": [],
            "companies_found": [],
            "financial_data": {},
            "step_count": 0,
            "current_focus": query,
            "max_steps": max_steps,
            "report_type": "sector",
            "final_synthesis": "",
            "status": "running",
        }

        final_state = self._graph.invoke(initial_state)
        final_state["status"] = "done"
        return final_state
