import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, BackgroundTasks
from sse_starlette.sse import EventSourceResponse

from agents.orchestrator import Orchestrator
from agents.base import ResearchState
from reports.report_generator import generate_report, save_report
from database.repository import get_db, update_session_status
from api.schemas import (
    PlanRequest, PlanResponse,
    ResearchStartRequest, ResearchStartResponse,
    ReportResponse,
)

router = APIRouter(prefix="/api")

# In-memory store: session_id -> asyncio.Queue of SSE events
_event_queues: dict[str, asyncio.Queue] = {}
# session_id -> final ResearchState (stored after completion)
_session_results: dict[str, ResearchState] = {}
# Shared orchestrator
_orchestrator = Orchestrator()


# ── Health ─────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {"status": "ok", "service": "FinResearchAI"}


# ── Plan ───────────────────────────────────────────────────────────────────────

@router.post("/plan", response_model=PlanResponse)
async def generate_plan(req: PlanRequest):
    """Analyse query and return a research plan for user review."""
    sector = _orchestrator.classify_sector(req.query)

    if sector == "out-of-scope":
        raise HTTPException(
            status_code=422,
            detail="Query is outside the financial domain. Please ask about IT or Pharma sectors.",
        )

    # Honour explicit sector override
    if req.sector in ("IT", "Pharma"):
        sector = req.sector

    query_type = _orchestrator.detect_query_type(req.query)
    plan = _orchestrator.build_research_plan(req.query, sector, query_type, req.depth)

    return PlanResponse(
        session_id=plan.session_id,
        query=plan.query,
        sector=plan.sector,
        query_type=plan.query_type,
        depth=plan.depth,
        aspects=plan.aspects,
        tools=plan.tools,
        estimated_steps=plan.estimated_steps,
        output_structure=plan.output_structure,
    )


# ── Start research ─────────────────────────────────────────────────────────────

@router.post("/research/start", response_model=ResearchStartResponse)
async def start_research(req: ResearchStartRequest, background_tasks: BackgroundTasks):
    """Approve plan and kick off research in background."""
    if not req.approved:
        return ResearchStartResponse(
            session_id=req.session_id, status="cancelled", message="Research cancelled by user."
        )

    queue: asyncio.Queue = asyncio.Queue()
    _event_queues[req.session_id] = queue

    background_tasks.add_task(
        _run_research,
        req.session_id,
        req.modified_scope,
        queue,
    )

    return ResearchStartResponse(
        session_id=req.session_id,
        status="started",
        message="Research started. Connect to /api/research/stream/{session_id} for live updates.",
    )


# ── SSE stream ─────────────────────────────────────────────────────────────────

@router.get("/research/stream/{session_id}")
async def stream_research(session_id: str):
    """Server-Sent Events stream — push step updates, financial data, and final report."""
    queue = _event_queues.get(session_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="Session not found or not started.")

    async def event_generator() -> AsyncGenerator:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=120.0)
                yield event
                if event.get("event") in ("report_done", "error"):
                    break
            except asyncio.TimeoutError:
                yield {"event": "ping", "data": "{}"}

    return EventSourceResponse(event_generator())


# ── Get report ─────────────────────────────────────────────────────────────────

@router.get("/report/{session_id}", response_model=ReportResponse)
async def get_report(session_id: str):
    """Fetch the final report for a completed session."""
    state = _session_results.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Report not found. Research may still be running.")

    states = state if isinstance(state, list) else [state]
    content = generate_report(state)
    path = save_report(content, states[0].get("query", session_id))

    return ReportResponse(
        session_id=session_id,
        content=content,
        report_path=path,
        step_count=sum(s.get("step_count", 0) for s in states),
    )


# ── Background research task ───────────────────────────────────────────────────

async def _run_research(session_id: str, modified_scope: str | None, queue: asyncio.Queue):
    """
    Runs in background. Patches the sector agent's nodes to emit SSE events,
    then stores final state and emits report_done.
    """
    loop = asyncio.get_event_loop()

    async def emit(event_type: str, data: dict):
        await queue.put({"event": event_type, "data": json.dumps(data)})

    try:
        # Retrieve the plan stored during /api/plan
        # Re-classify to get sector + type (plan is rebuilt here)
        sector = _orchestrator.classify_sector(modified_scope or session_id)
        query_type = _orchestrator.detect_query_type(modified_scope or "sector analysis")

        # Emit started
        await emit("status", {"message": "Research started", "session_id": session_id})

        # Wrap agent run — inject step callback
        original_it  = _orchestrator._it_agent._node_analyse_findings
        original_ph  = _orchestrator._pharma_agent._node_analyse_findings

        step_counter = {"n": 0}

        def patched_analyse_it(state):
            result = original_it(state)
            asyncio.run_coroutine_threadsafe(
                emit("step", {
                    "step": state["step_count"],
                    "tool": "analysis",
                    "summary": (result.get("findings") or [""])[0][:200],
                    "focus": result.get("current_focus", ""),
                }),
                loop,
            )
            return result

        def patched_analyse_ph(state):
            result = original_ph(state)
            asyncio.run_coroutine_threadsafe(
                emit("step", {
                    "step": state["step_count"],
                    "tool": "analysis",
                    "summary": (result.get("findings") or [""])[0][:200],
                    "focus": result.get("current_focus", ""),
                }),
                loop,
            )
            return result

        _orchestrator._it_agent._node_analyse_findings  = patched_analyse_it
        _orchestrator._pharma_agent._node_analyse_findings = patched_analyse_ph

        # Run synchronously in thread pool to not block event loop
        state = await loop.run_in_executor(
            None,
            lambda: _dispatch_by_session(session_id, modified_scope, sector),
        )

        # Restore originals
        _orchestrator._it_agent._node_analyse_findings  = original_it
        _orchestrator._pharma_agent._node_analyse_findings = original_ph

        if state is None:
            await emit("error", {"message": "Research failed or out of scope."})
            return

        # Emit financial snapshot
        fin_data = {}
        states = state if isinstance(state, list) else [state]
        for s in states:
            fin_data.update(s.get("financial_data", {}))

        if fin_data:
            chart_data = _build_chart_data(fin_data)
            await emit("financial_data", {"metrics": _serialise_fin(fin_data), "chart": chart_data})

        # Synthesis + report
        synthesis = _orchestrator.synthesise_results(state)
        if isinstance(state, list):
            state[0]["final_synthesis"] = synthesis
        else:
            state["final_synthesis"] = synthesis

        _session_results[session_id] = state

        report_md = generate_report(state)
        report_path = save_report(report_md, states[0].get("query", session_id))

        with get_db() as db:
            update_session_status(db, session_id, "done", report_path)

        await emit("report_done", {
            "session_id": session_id,
            "report": report_md,
            "synthesis": synthesis,
            "step_count": sum(s.get("step_count", 0) for s in states),
        })

    except Exception as e:
        await emit("error", {"message": str(e)})
        with get_db() as db:
            update_session_status(db, session_id, "failed")


def _dispatch_by_session(session_id: str, modified_scope: str | None, sector: str):
    """Synchronous dispatch — called from thread executor."""
    query = modified_scope or "financial sector analysis"
    if sector == "Pharma":
        return _orchestrator._pharma_agent.run(query, "standard", session_id)
    elif sector == "cross-sector":
        it_state = _orchestrator._it_agent.run(query, "standard", session_id + "_it")
        ph_state = _orchestrator._pharma_agent.run(query, "standard", session_id + "_ph")
        return [it_state, ph_state]
    else:
        return _orchestrator._it_agent.run(query, "standard", session_id)


def _serialise_fin(fin_data: dict) -> dict:
    """Convert financial_data dict to JSON-safe format."""
    result = {}
    for ticker, d in fin_data.items():
        result[ticker] = {k: (float(v) if isinstance(v, (int, float)) and v is not None else v)
                          for k, v in d.items()}
    return result


def _build_chart_data(fin_data: dict) -> dict:
    """Build Chart.js-ready data arrays from financial_data."""
    companies = [d.get("name", t) for t, d in fin_data.items()]
    revenues  = [round(d.get("revenue", 0) / 1e9, 2) if d.get("revenue") else 0 for d in fin_data.values()]
    ebitda_m  = [round(d.get("ebitda_margin", 0) * 100, 1) if d.get("ebitda_margin") else 0 for d in fin_data.values()]
    net_m     = [round(d.get("net_margin", 0) * 100, 1) if d.get("net_margin") else 0 for d in fin_data.values()]

    return {
        "labels": companies,
        "revenue_bn": revenues,
        "ebitda_margins": ebitda_m,
        "net_margins": net_m,
    }
