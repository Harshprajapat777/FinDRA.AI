# Financial Deep Research Agent — Implementation Roadmap

> Build a financial research agent that replicates Claude/OpenAI "Deep Research" mode,
> specialised for IT and Pharma sectors, with multi-step iterative research loops,
> RAG on financial documents, live data APIs, and structured report generation.

---

## Pipeline Overview

```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 7
 Setup    Data Acq   RAG Sys   Agents   Orchestr.   Output    UI + API
```

---

## Phase 1 — Project Setup & Configuration

**Goal:** Establish the foundation — environment, secrets, database schema, and shared config.

### Tasks
- [ ] Set up `.env` with all API keys (Anthropic, Tavily, Alpha Vantage, etc.)
- [ ] Configure `config/settings.py` — load env vars via `pydantic-settings`
- [ ] Define SQLAlchemy models in `database/models.py`
  - `Company` — name, sector, ticker, metadata
  - `FinancialMetric` — company_id, metric_name, value, period, source
  - `ResearchSession` — query, sector, status, created_at
  - `ResearchStep` — session_id, step_number, query, result_summary
- [ ] Initialize SQLite DB (dev) / PostgreSQL (prod) via `database/repository.py`
- [ ] Write `outputs/reports/` directory auto-creation logic in `main.py`
- [ ] Confirm all packages install cleanly from `Requirements.txt`

### Files to build
```
config/settings.py
database/models.py
database/repository.py
main.py  (entry point skeleton)
.env.example
```

### Exit Criteria
Running `python main.py` starts without errors and DB tables are created.

---

## Phase 2 — Data Acquisition Layer

**Goal:** Build the three live data tools the research engine will call — web search,
financial APIs, and document processing.

### Tasks

#### 2a — Web Search (`tools/web_search.py`)
- [ ] Integrate Tavily API for financial news search
- [ ] Implement `search(query, max_results)` returning structured results
- [ ] Add retry logic with `tenacity` (3 attempts, exponential backoff)
- [ ] Strip and clean HTML from results before returning

#### 2b — Financial API (`tools/financial_api.py`)
- [ ] `get_stock_price(ticker)` — yfinance real-time price
- [ ] `get_financials(ticker)` — revenue, EBITDA, margins, EPS (yfinance)
- [ ] `get_market_cap(ticker)` — yfinance
- [ ] `get_historical_data(ticker, period)` — time-series for trend analysis
- [ ] `calculate_ratios(financials_dict)` — programmatic calculation only, **no LLM math**
  - P/E, P/B, Debt/Equity, ROE, ROA, Current Ratio
- [ ] Persist fetched metrics to SQL DB via `database/repository.py`

#### 2c — Document Processor (`tools/document_processor.py`)
- [ ] `load_pdf(path)` — extract text from annual reports / investor presentations
- [ ] `chunk_text(text, chunk_size, overlap)` — split into RAG-ready chunks
- [ ] Return list of `{text, source, page}` dicts

### Files to build
```
tools/web_search.py
tools/financial_api.py
tools/document_processor.py
```

### Exit Criteria
Each tool can be called standalone and returns clean, structured data.

---

## Phase 3 — RAG System (Document Intelligence)

**Goal:** Build a vector store that ingests annual reports and answers document-grounded
questions during the research loop.

### Tasks
- [ ] Set up ChromaDB persistent client in `rag/vector_store.py`
- [ ] `add_documents(chunks, collection_name)` — embed and store with metadata
- [ ] `query(question, collection_name, n_results)` — semantic search, return top-k chunks
- [ ] Use `sentence-transformers` (`all-MiniLM-L6-v2`) for embeddings (no API cost)
- [ ] Create separate collections per sector: `it_sector_docs`, `pharma_sector_docs`
- [ ] `rag/document_loader.py` — walk a `data/documents/` folder, auto-ingest all PDFs
- [ ] Test retrieval with a sample annual report (e.g., TCS / Infosys AR)

### Files to build
```
rag/vector_store.py
rag/document_loader.py
data/documents/   (folder for ingesting PDFs — gitignored)
```

### Exit Criteria
Querying "What is Infosys revenue for FY24?" returns relevant chunks from ingested AR.

---

## Phase 4 — Sector Agents (IT & Pharma)

**Goal:** Build the two specialised sector agents that execute deep iterative research
within their domain using all three data tools + RAG.

### Tasks

#### Shared Base Logic
- [ ] Define `ResearchState` TypedDict in `agents/` — holds query, findings, step_count,
  sources, sector, report_type
- [ ] Build reusable `research_loop` function using LangGraph `StateGraph`
  - Node: `search_web` — Tavily query based on current focus
  - Node: `query_rag` — retrieve from vector store
  - Node: `fetch_financials` — call financial API for any companies found
  - Node: `analyse_findings` — LLM synthesises and decides next query
  - Node: `check_depth` — stop if step_count >= 10 (or 20 for deep mode)
  - Edge: conditional loop back to `search_web` until depth reached

#### 4a — IT Sector Agent (`agents/it_sector_agent.py`)
- [ ] Sector context: TCS, Infosys, Wipro, HCL, Tech Mahindra, LTIMindtree
- [ ] Domain keywords: digital transformation, cloud, AI/ML deals, attrition, visa costs
- [ ] Override system prompt with IT-specific financial KPIs (revenue per employee, deal TCV)
- [ ] `run(query, depth) → ResearchState`

#### 4b — Pharma Sector Agent (`agents/pharma_sector_agent.py`)
- [ ] Sector context: Sun Pharma, Dr. Reddy's, Cipla, Divi's, Biocon
- [ ] Domain keywords: ANDA filings, USFDA approvals, R&D spend, biosimilars, API margins
- [ ] Override system prompt with Pharma-specific KPIs (R&D-to-revenue ratio, pipeline count)
- [ ] `run(query, depth) → ResearchState`

### Files to build
```
agents/it_sector_agent.py
agents/pharma_sector_agent.py
```

### Exit Criteria
Running an agent with a test query executes 5+ research steps and returns populated
findings with web + RAG + financial data sources.

---

## Phase 5 — Orchestrator & Research Plan Approval

**Goal:** Build the top-level orchestrator that routes queries, presents a research plan
to the user, awaits approval, then dispatches to the correct sector agent.

### Tasks

#### Query Analysis & Routing
- [ ] `classify_sector(query)` → `"IT"` | `"Pharma"` | `"cross-sector"` | `"out-of-scope"`
  - Use keyword matching + LLM fallback for ambiguous queries
- [ ] `decline_non_financial(query)` — politely reject off-topic queries
- [ ] `detect_query_type(query)` → `"company"` | `"sector"` | `"comparative"`

#### Research Plan Generation (Step 1 from PDF)
- [ ] `build_research_plan(query, sector, query_type)` → `ResearchPlan` dict
  - What aspects will be investigated (bullet list)
  - Which tools will be used (web / RAG / API)
  - Estimated steps (5–10 standard, 15–20 deep)
  - Expected output structure
- [ ] `present_plan(plan)` — print formatted plan to terminal using `rich`

#### User Approval (Step 2 from PDF)
- [ ] `await_approval(plan)` → `approved: bool, modified_scope: str | None`
  - Prompt: `[A]pprove / [M]odify / [C]ancel`
  - If modify: accept new scope and regenerate plan
  - If cancel: graceful exit

#### Dispatch & Synthesis
- [ ] Route approved plan to `ITSectorAgent` or `PharmaSectorAgent`
- [ ] For cross-sector: run both agents, merge findings
- [ ] `synthesise_results(state)` — final LLM pass to create coherent narrative

### Files to build
```
agents/orchestrator.py
```

### Exit Criteria
Full interactive flow works end-to-end:
`query → plan displayed → user approves → agent runs → findings returned`

---

## Phase 6 — Financial Analysis Module & Report Generation

**Goal:** Apply programmatic financial calculations on gathered data and render the
final structured report in `.md` format.

### Tasks

#### Financial Calculator (`analysis/financial_calculator.py`)
- [ ] `compute_growth_rate(values: list[float]) → float` — CAGR
- [ ] `compute_margins(revenue, ebitda, net_profit) → dict`
- [ ] `compare_companies(metrics: list[dict]) → pd.DataFrame` — cross-company table
- [ ] `detect_trend(time_series: pd.Series) → str` — up / down / flat
- [ ] All calculations use `pandas` / `numpy` — **zero LLM math**
- [ ] Cross-validate: if API value differs >5% from scraped value, flag discrepancy

#### Report Generator (`reports/report_generator.py`)
- [ ] `generate_company_report(state) → str` — markdown
  - Executive summary · Company overview · Financial analysis ·
    Competitive positioning · Future outlook
- [ ] `generate_sector_report(state) → str` — markdown
  - Market overview · Key players · Trend analysis ·
    Regulatory environment · Investment opportunities · Risk factors
- [ ] `generate_comparative_report(state) → str` — markdown
  - Comparison criteria · Per-company analysis · Comparison table · Recommendations
- [ ] `save_report(content, filename)` — write to `outputs/reports/YYYYMMDD_<topic>.md`
- [ ] Include source attribution section at end of every report

### Files to build
```
analysis/financial_calculator.py
reports/report_generator.py
outputs/reports/   (auto-created, gitignored)
```

### Exit Criteria
A complete `.md` report is written to `outputs/reports/` with:
- At least 3 sections populated with real data
- A comparison table (for comparative queries)
- Source list at the bottom

---

## Phase 7 — UI + API Layer

**Goal:** Expose the entire agent pipeline through a FastAPI backend and serve a
browser-based UI that shows the research plan, live step feed, financial charts,
and the final rendered report.

### Tasks

#### 7a — FastAPI Backend (`api/`)
- [ ] `api/schemas.py` — Pydantic request/response models
  - `PlanRequest` — query, sector, depth
  - `PlanResponse` — plan dict, session_id, sector, query_type
  - `ResearchStartRequest` — session_id, approved, modified_scope
  - `FinancialDataEvent` — metrics dict, chart data arrays
  - `ReportDoneEvent` — markdown content, report path
- [ ] `api/routes.py` — all endpoint definitions
  - `POST /api/plan` — generate & return research plan
  - `POST /api/research/start` — approve plan, kick off agent in background
  - `GET  /api/research/stream/{session_id}` — SSE stream of research events
    - event types: `step`, `financial_data`, `report_done`, `error`
  - `GET  /api/report/{session_id}` — fetch saved `.md` report content
  - `GET  /api/health` — liveness check
- [ ] `api/server.py` — FastAPI app init, CORS config, static file mount, router include
- [ ] Run with `uvicorn api.server:app --reload --port 8000`

#### 7b — Frontend (`ui/`)
- [ ] `ui/index.html` — single-page layout: sidebar + main content area
  - Query input, sector select, depth select, Generate Plan button
  - Research plan panel with Approve / Modify / Cancel actions
  - Live steps feed sidebar (updates via SSE)
  - Financial snapshot section: metric cards + 2 Chart.js charts
  - Report section: markdown rendered via Marked.js + Copy / Download buttons
  - Example query buttons for quick testing
- [ ] `ui/css/style.css` — dark theme, responsive layout
  - CSS variables for consistent colour palette
  - Sidebar + content two-column layout
  - Animated progress bar, step item states (pending / active / done)
  - Metric cards, chart containers, markdown body styling
- [ ] `ui/js/app.js` — all UI logic, zero dependencies beyond CDN scripts
  - `generatePlan()` — POST /api/plan, render plan panel
  - `approvePlan()` — POST /api/research/start, open SSE stream
  - `listenToStream(sessionId)` — EventSource, handle all event types
  - `renderFinancials(data)` — draw metric cards + Chart.js charts
  - `renderReport(markdown)` — Marked.js parse + inject into DOM
  - `downloadReport(content)` — trigger `.md` file download
  - `showToast(message, type)` — non-blocking notifications

### Files to build
```
api/schemas.py
api/routes.py
api/server.py
ui/index.html
ui/css/style.css
ui/js/app.js
```

### API ↔ UI Event Flow
```
UI                          FastAPI                     Agent
│                               │                          │
│── POST /api/plan ────────────>│                          │
│<─ {plan, session_id} ─────────│                          │
│                               │                          │
│── POST /api/research/start ──>│── run agent (bg task) ──>│
│── GET  /api/research/stream ──│<─ SSE: step events ──────│
│   (EventSource open)          │<─ SSE: financial_data ───│
│                               │<─ SSE: report_done ──────│
│<─ live step feed update       │                          │
│<─ metric cards + charts       │                          │
│<─ rendered markdown report    │                          │
```

### Exit Criteria
- Opening `http://localhost:8000` shows the UI
- Submitting a query flows end-to-end: plan → approval → live steps → charts → report
- Report can be downloaded as `.md`

---

## Full Flow Summary (end-to-end)

```
[Browser UI — index.html]
    │  user types query, selects sector & depth
    │  POST /api/plan
    ▼
[FastAPI — api/server.py]
    │  routes.py validates request via schemas.py
    ▼
[Orchestrator — agents/orchestrator.py]
    │  classify sector → build research plan
    │  GET /api/plan  →  plan JSON returned to UI
    ▼
[Browser UI]
    │  displays plan, user clicks Approve / Modify / Cancel
    │  POST /api/research/start
    ▼
[FastAPI — SSE stream  GET /api/research/stream/{session_id}]
    │  streams live step events → UI updates step feed in real time
    ▼
[Sector Agent — LangGraph loop (5–20 steps)]
    ├── Web Search (Tavily)
    ├── RAG Query (ChromaDB)
    └── Financial API (yfinance)
    │  each step emitted as SSE event → UI step counter updates
    ▼
[Financial Calculator — pandas/numpy, zero LLM math]
    │  metrics + ratios computed programmatically
    │  SSE event: financial_data → UI renders metric cards + Chart.js charts
    ▼
[Report Generator — reports/report_generator.py]
    │  structured .md report saved to outputs/reports/
    │  SSE event: report_done → UI renders markdown report
    ▼
[Browser UI]
    │  displays financial snapshot, charts, full report
    │  Copy / Download .md buttons available
    ▼
outputs/reports/YYYYMMDD_<topic>.md
```

---

## Deliverables Checklist (from PDF)

- [ ] Two functional sector agents — IT and Pharma
- [ ] Complete workflow: query → plan → approval → research → report
- [ ] 5–20 iterative research steps per query (not parallel — each informs the next)
- [ ] Programmatic financial calculations (no LLM math)
- [ ] 2–3 sample output reports demonstrating different query types
- [ ] Modular architecture — adding a new sector = one new file in `agents/`
- [ ] Web UI with real-time step feed, financial charts, and report renderer
- [ ] FastAPI backend serving all agent functionality as REST + SSE endpoints

---

## Tech Stack

| Layer | Choice |
|---|---|
| LLM | Claude (Anthropic) via `langchain-anthropic` |
| Orchestration | LangGraph `StateGraph` |
| Vector DB | ChromaDB (local persistent) |
| Embeddings | `sentence-transformers` (local, free) |
| Web Search | Tavily API |
| Financial Data | yfinance + Alpha Vantage |
| Database | SQLite (dev) via SQLAlchemy |
| Math / Analysis | pandas + numpy |
| CLI Output | rich |
| Report Format | Markdown (`.md`) |
| API Server | FastAPI + uvicorn |
| Live Streaming | Server-Sent Events via `sse-starlette` |
| UI | HTML + CSS + Vanilla JS (no framework) |
| Charts | Chart.js (CDN) |
| Markdown Render | Marked.js (CDN) |
