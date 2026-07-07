"""
interview.py — Pydantic schemas for request/response validation.

Following the FastAPI skill's RORO pattern (Receive an Object, Return an Object)
and the guideline to prefer Pydantic models over raw dicts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════
# Request schemas
# ═══════════════════════════════════════════════════════════════════════════


class SubmitAnswerRequest(BaseModel):
    """Body for POST /api/interview/submit."""

    session_id: str = Field(..., description="UUID of the interview session")
    answer: str = Field(..., min_length=1, description="Candidate's answer text")


# ═══════════════════════════════════════════════════════════════════════════
# Response schemas
# ═══════════════════════════════════════════════════════════════════════════


class StartInterviewResponse(BaseModel):
    """Response from POST /api/interview/start."""

    session_id: str
    role: str
    skills: list[str]
    question: str
    current_step: int


class SubmitAnswerResponse(BaseModel):
    """Response from POST /api/interview/submit."""

    is_completed: bool
    next_question: Optional[str] = None
    current_step: int
    evaluation_summary: Optional[str] = None


class LogEntry(BaseModel):
    """Single Q/A turn in the interview log."""

    question: str
    answer: Optional[str] = None
    timestamp: datetime


class InterviewSummaryResponse(BaseModel):
    """Response from GET /api/interview/summary/{session_id}."""

    session_id: str
    role: str
    skills: list[str]
    status: str
    current_step: int
    evaluation_summary: Optional[str] = None
    logs: list[LogEntry]
