"""
Orchestrator — entry point for every research query.

Flow:
  1. classify_sector()     → IT | Pharma | cross-sector | out-of-scope
  2. detect_query_type()   → company | sector | comparative
  3. build_research_plan() → structured plan dict shown to user
  4. await_approval()      → user approves / modifies / cancels  (CLI mode)
  5. dispatch()            → run ITSectorAgent or PharmaSectorAgent
  6. synthesise_results()  → final LLM narrative over all findings
"""
import json
import uuid
from dataclasses import dataclass, field
from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from config.settings import settings
from agents.base import ResearchState
from agents.it_sector_agent import ITSectorAgent
from agents.pharma_sector_agent import PharmaSectorAgent
from database.repository import get_db, create_session, update_session_status, add_step

console = Console()

# ── Constants ──────────────────────────────────────────────────────────────────

SECTOR_KEYWORDS = {
    "IT": [
        "it ", "software", "infosys", "tcs", "wipro", "hcl", "tech mahindra",
        "ltimindtree", "mphasis", "coforge", "digital", "cloud", "saas",
        "outsourcing", "it services", "technology services",
    ],
    "Pharma": [
        "pharma", "drug", "medicine", "sun pharma", "cipla", "dr reddy",
        "biocon", "lupin", "aurobindo", "divi", "anda", "usfda", "biosimilar",
        "generics", "api ", "formulation", "clinical", "r&d",
    ],
}

OUT_OF_SCOPE_TRIGGERS = [
    "recipe", "food", "cook", "movie", "sport", "cricket", "football",
    "weather", "travel", "fashion", "music", "game", "politics",
]


# ── Data models ────────────────────────────────────────────────────────────────

@dataclass
class ResearchPlan:
    session_id: str
    query: str
    sector: str
    query_type: str
    depth: str
    aspects: list[str]
    tools: list[str]
    estimated_steps: int
    output_structure: list[str]
    modified_scope: Optional[str] = None


# ── Orchestrator ───────────────────────────────────────────────────────────────

class Orchestrator:

    def __init__(self):
        self._llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=1024,
            temperature=0.2,
        )
        self._it_agent = ITSectorAgent()
        self._pharma_agent = PharmaSectorAgent()

    # ── Step 1: Classify ───────────────────────────────────────────────────────

    def classify_sector(self, query: str) -> str:
        """Returns: IT | Pharma | cross-sector | out-of-scope"""
        q = query.lower()

        # Hard reject non-financial queries
        if any(t in q for t in OUT_OF_SCOPE_TRIGGERS):
            return "out-of-scope"

        it_score = sum(1 for kw in SECTOR_KEYWORDS["IT"] if kw in q)
        ph_score = sum(1 for kw in SECTOR_KEYWORDS["Pharma"] if kw in q)

        if it_score > 0 and ph_score > 0:
            return "cross-sector"
        if it_score > 0:
            return "IT"
        if ph_score > 0:
            return "Pharma"

        # LLM fallback for ambiguous queries
        return self._classify_with_llm(query)

    def _classify_with_llm(self, query: str) -> str:
        prompt = (
            f"Classify this financial research query into exactly one category.\n"
            f"Query: {query}\n"
            f"Categories: IT, Pharma, cross-sector, out-of-scope\n"
            f"Respond with ONLY the category name."
        )
        try:
            resp = self._llm.invoke([HumanMessage(content=prompt)])
            result = resp.content.strip()
            if result in ("IT", "Pharma", "cross-sector", "out-of-scope"):
                return result
        except Exception:
            pass
        return "IT"  # safe default for financial queries

    def detect_query_type(self, query: str) -> str:
        """Returns: company | sector | comparative"""
        q = query.lower()
        if any(w in q for w in ["compare", "vs ", "versus", "comparison", "relative"]):
            return "comparative"
        if any(w in q for w in ["sector", "industry", "market", "overall", "outlook", "trend"]):
            return "sector"
        return "company"

    # ── Step 2: Build plan ─────────────────────────────────────────────────────

    def build_research_plan(
        self,
        query: str,
        sector: str,
        query_type: str,
        depth: str = "standard",
    ) -> ResearchPlan:
        session_id = str(uuid.uuid4())
        max_steps = (
            settings.deep_research_depth if depth == "deep"
            else settings.standard_research_depth
        )

        # Aspect + structure are LLM-generated for quality, everything else is deterministic
        aspects, output_structure = self._generate_plan_details(query, sector, query_type)

        tools = ["Web Search (Tavily)", "RAG — Annual Reports (ChromaDB)", "Financial API (yfinance)"]

        return ResearchPlan(
            session_id=session_id,
            query=query,
            sector=sector,
            query_type=query_type,
            depth=depth,
            aspects=aspects,
            tools=tools,
            estimated_steps=max_steps,
            output_structure=output_structure,
        )

    def _generate_plan_details(self, query: str, sector: str, query_type: str) -> tuple[list, list]:
        prompt = f"""You are planning a financial deep research task.
Query: "{query}"
Sector: {sector}
Query type: {query_type}

Return a JSON with exactly two keys:
- "aspects": list of 4-6 specific research aspects to investigate (short bullet phrases)
- "output_structure": list of 3-5 report sections to produce

Respond ONLY with valid JSON."""

        try:
            resp = self._llm.invoke([
                SystemMessage(content="You are a financial research planner."),
                HumanMessage(content=prompt),
            ])
            data = json.loads(resp.content)
            return data.get("aspects", []), data.get("output_structure", [])
        except Exception:
            pass

        # Fallback
        aspects = [
            f"Current {sector} sector financial performance",
            "Key company metrics and comparisons",
            "Recent news and market developments",
            "Regulatory and macro environment",
            "Investment risks and opportunities",
        ]
        output_structure = ["Executive Summary", "Financial Analysis", "Sector Trends", "Risk Factors", "Outlook"]
        return aspects, output_structure

    # ── Step 3: Present plan ───────────────────────────────────────────────────

    def present_plan(self, plan: ResearchPlan) -> None:
        """Render the research plan to the terminal using rich."""
        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        table.add_column(style="dim", width=18)
        table.add_column(style="white")

        table.add_row("Query", f"[cyan]{plan.query}[/cyan]")
        table.add_row("Sector", f"[green]{plan.sector}[/green]")
        table.add_row("Type", plan.query_type)
        table.add_row("Depth", f"{plan.depth} ({plan.estimated_steps} steps)")
        table.add_row("Tools", " | ".join(plan.tools))

        aspects_text = "\n".join(f"  - {a}" for a in plan.aspects)
        table.add_row("Will investigate", aspects_text)

        sections_text = "\n".join(f"  - {s}" for s in plan.output_structure)
        table.add_row("Report sections", sections_text)

        console.print(Panel(table, title="[bold cyan]Research Plan[/bold cyan]", border_style="cyan"))

    # ── Step 4: Await approval (CLI) ───────────────────────────────────────────

    def await_approval(self, plan: ResearchPlan) -> tuple[bool, Optional[str]]:
        """
        Interactive CLI approval gate.
        Returns (approved: bool, modified_scope: str | None)
        """
        console.print("\n[bold]What would you like to do?[/bold]")
        console.print("  [green][A][/green] Approve and start research")
        console.print("  [yellow][M][/yellow] Modify scope")
        console.print("  [red][C][/red] Cancel\n")

        while True:
            choice = input("Your choice (A/M/C): ").strip().upper()

            if choice == "A":
                return True, None

            elif choice == "M":
                scope = input("Enter modified scope or focus: ").strip()
                if scope:
                    plan.modified_scope = scope
                    plan.query = scope
                    console.print(f"\n[yellow]Scope updated to:[/yellow] {scope}")
                    self.present_plan(plan)
                    confirm = input("Approve updated plan? (A/C): ").strip().upper()
                    if confirm == "A":
                        return True, scope
                return False, None

            elif choice == "C":
                console.print("[dim]Research cancelled.[/dim]")
                return False, None

            console.print("[red]Invalid choice. Enter A, M, or C.[/red]")

    # ── Step 5: Dispatch ───────────────────────────────────────────────────────

    def dispatch(self, plan: ResearchPlan) -> ResearchState | list[ResearchState]:
        """Route the approved plan to the correct sector agent(s)."""
        query = plan.modified_scope or plan.query

        # Persist session to DB
        with get_db() as db:
            create_session(
                db,
                session_id=plan.session_id,
                query=query,
                sector=plan.sector,
                query_type=plan.query_type,
                depth=plan.depth,
            )
            update_session_status(db, plan.session_id, "running")

        console.print(f"\n[bold cyan]Starting research — {plan.estimated_steps} steps...[/bold cyan]\n")

        if plan.sector == "IT":
            state = self._it_agent.run(query, plan.depth, plan.session_id)
            self._persist_steps(plan.session_id, state)
            return state

        elif plan.sector == "Pharma":
            state = self._pharma_agent.run(query, plan.depth, plan.session_id)
            self._persist_steps(plan.session_id, state)
            return state

        elif plan.sector == "cross-sector":
            # Run both agents, return list
            it_state = self._it_agent.run(query, plan.depth, plan.session_id + "_it")
            ph_state = self._pharma_agent.run(query, plan.depth, plan.session_id + "_ph")
            return [it_state, ph_state]

        else:
            console.print("[red]Query is outside the financial domain. Please ask about IT or Pharma sectors.[/red]")
            return None

    def _persist_steps(self, session_id: str, state: ResearchState) -> None:
        """Write each research step to the DB."""
        with get_db() as db:
            from database.repository import get_session
            session_record = get_session(db, session_id)
            if not session_record:
                return
            for i, finding in enumerate(state.get("findings", []), 1):
                add_step(
                    db,
                    session_db_id=session_record.id,
                    step_number=i,
                    tool_used=_parse_tool(finding),
                    query_used=state.get("current_focus", ""),
                    result_summary=finding[:500],
                    sources=json.dumps(state.get("sources", [])[:3]),
                )

    # ── Step 6: Synthesise ─────────────────────────────────────────────────────

    def synthesise_results(self, state: ResearchState | list[ResearchState]) -> str:
        """Final LLM pass — weave all findings into a coherent executive narrative."""
        if isinstance(state, list):
            combined_findings = []
            for s in state:
                combined_findings.extend(s.get("findings", []))
            query = state[0]["query"]
            sector = "IT and Pharma"
        else:
            combined_findings = state.get("findings", [])
            query = state["query"]
            sector = state["sector"]

        findings_text = "\n\n".join(combined_findings[-10:])  # last 10 for synthesis

        prompt = f"""You have completed a deep financial research task.

Original query: {query}
Sector: {sector}

Research findings (latest steps):
{findings_text}

Write a concise executive synthesis (3-5 paragraphs) that:
1. Directly answers the original query
2. Highlights the most important financial insights discovered
3. Mentions specific companies, metrics, and figures where available
4. Identifies key risks and opportunities
5. Provides a forward-looking perspective

Be specific, data-driven, and professional."""

        try:
            resp = self._llm.invoke([
                SystemMessage(content="You are a senior financial research analyst writing an executive summary."),
                HumanMessage(content=prompt),
            ])
            return resp.content
        except Exception as e:
            return f"Synthesis unavailable: {e}"

    # ── Full pipeline (CLI) ────────────────────────────────────────────────────

    def run(self, query: str, depth: str = "standard") -> Optional[ResearchState]:
        """
        Execute the complete research pipeline interactively via CLI.
        Use this for terminal usage; API routes call individual steps directly.
        """
        console.print(f"\n[bold cyan]Analysing query...[/bold cyan]")

        sector = self.classify_sector(query)

        if sector == "out-of-scope":
            console.print(
                "[red]This query is outside the financial research domain.[/red]\n"
                "Please ask about IT services or Pharma sector companies and trends."
            )
            return None

        query_type = self.detect_query_type(query)
        plan = self.build_research_plan(query, sector, query_type, depth)
        self.present_plan(plan)

        approved, modified_scope = self.await_approval(plan)
        if not approved:
            return None

        state = self.dispatch(plan)
        if state is None:
            return None

        console.print("\n[bold cyan]Synthesising findings...[/bold cyan]")
        synthesis = self.synthesise_results(state)

        if isinstance(state, list):
            state[0]["final_synthesis"] = synthesis
            final = state[0]
        else:
            state["final_synthesis"] = synthesis
            final = state

        with get_db() as db:
            update_session_status(db, plan.session_id, "done")

        console.print(Panel(synthesis, title="[bold green]Research Complete[/bold green]", border_style="green"))
        return final


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_tool(finding: str) -> str:
    if "| Web]" in finding:
        return "web_search"
    if "| RAG]" in finding:
        return "rag"
    if "| API]" in finding:
        return "financial_api"
    if "| Analysis]" in finding:
        return "llm_analysis"
    return "unknown"
