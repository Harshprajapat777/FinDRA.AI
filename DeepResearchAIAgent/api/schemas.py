from typing import Optional
from pydantic import BaseModel, Field


class PlanRequest(BaseModel):
    query: str = Field(..., min_length=5, description="Financial research query")
    sector: str = Field("auto", description="IT | Pharma | auto")
    depth: str = Field("standard", description="standard | deep")


class PlanResponse(BaseModel):
    session_id: str
    query: str
    sector: str
    query_type: str
    depth: str
    aspects: list[str]
    tools: list[str]
    estimated_steps: int
    output_structure: list[str]


class ResearchStartRequest(BaseModel):
    session_id: str
    approved: bool
    modified_scope: Optional[str] = None


class ResearchStartResponse(BaseModel):
    session_id: str
    status: str
    message: str


class ReportResponse(BaseModel):
    session_id: str
    content: str
    report_path: Optional[str]
    step_count: int
