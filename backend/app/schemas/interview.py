"""
interview.py — Pydantic schemas for request/response validation and DB mapping.

Following the FastAPI skill's RORO pattern (Receive an Object, Return an Object)
and the guideline to prefer Pydantic models over raw dicts.
"""

from __future__ import annotations

from datetime import datetime, timezone
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


# ═══════════════════════════════════════════════════════════════════════════
# MongoDB Document mapping schemas
# ═══════════════════════════════════════════════════════════════════════════


class InterviewLogDB(BaseModel):
    """Document schema representing a Q/A log inside MongoDB."""

    question: str
    answer: Optional[str] = None
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class InterviewSessionDB(BaseModel):
    """Document schema representing an entire interview session in MongoDB."""

    id: str = Field(..., alias="_id")
    role: str
    skills: list[str] = Field(default_factory=list)
    status: str = "ACTIVE"  # ACTIVE | COMPLETED
    current_step: int = 0
    max_questions: int = 5
    evaluation_summary: Optional[str] = None
    candidate_name: Optional[str] = None
    candidate_email: Optional[str] = None
    candidate_phone: Optional[str] = None
    resume_text: Optional[str] = None
    pregenerated_questions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    logs: list[InterviewLogDB] = Field(default_factory=list)
