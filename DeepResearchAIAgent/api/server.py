import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from database.repository import init_db
from api.routes import router

# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="FinResearchAI",
    description="Financial Deep Research Agent API",
    version="1.0.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ─────────────────────────────────────────────────────────────────────

app.include_router(router)

# Serve UI static files
ui_path = Path(__file__).parent.parent / "ui"
if ui_path.exists():
    app.mount("/static", StaticFiles(directory=str(ui_path)), name="static")

    @app.get("/")
    async def serve_ui():
        return FileResponse(str(ui_path / "index.html"))


# ── Startup ────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def on_startup():
    # Ensure output dirs and DB tables exist
    for d in ["outputs/reports", "data/documents", "chroma_db"]:
        Path(d).mkdir(parents=True, exist_ok=True)
    init_db()
    print("FinResearchAI API ready — http://localhost:8000")
