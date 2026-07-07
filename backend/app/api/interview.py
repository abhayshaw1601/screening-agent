"""
interview.py — FastAPI router for interview lifecycle management.

Endpoints:
    POST /api/interview/start          — start a new session from a resume PDF
    POST /api/interview/submit         — submit an answer and get the next question
    GET  /api/interview/summary/{id}   — fetch a completed session's full log

Follows the FastAPI skill guidelines:
    - Functional route handlers (not class-based)
    - Pydantic models for all I/O
    - Guard clauses / early returns for error paths
    - HTTPException for expected errors
    - Dependency injection for DB sessions
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.interview import InterviewLog, InterviewSession
from app.schemas.interview import (
    InterviewSummaryResponse,
    LogEntry,
    StartInterviewResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
)
from app.services.interview_graph import build_interview_graph
from app.services.resume_parser import extract_skills_from_pdf

# LangGraph checkpointer — InMemorySaver for dev (per langgraph-persistence skill)
from langgraph.checkpoint.memory import InMemorySaver

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/interview", tags=["Interview"])

# ---------------------------------------------------------------------------
# Shared LangGraph instance for the API process
# (InMemorySaver is fine for single-process dev; use PostgresSaver in prod)
# ---------------------------------------------------------------------------
_checkpointer = InMemorySaver()
_graph = build_interview_graph(checkpointer=_checkpointer)


# ═══════════════════════════════════════════════════════════════════════════
# POST /api/interview/start
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/start", response_model=StartInterviewResponse)
def start_interview(
    role: str = Form(..., description="Target job role"),
    file: UploadFile = File(..., description="Resume PDF"),
    db: Session = Depends(get_db),
) -> StartInterviewResponse:
    """Start a new interview session.

    1. Validate the uploaded file is a PDF.
    2. Extract skills from the resume.
    3. Persist a new InterviewSession row.
    4. Run the first LangGraph step to generate Q1.
    5. Persist the question to InterviewLog.
    6. Return session_id, question, and current_step.
    """
    # --- Guard: file type ---------------------------------------------------
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are accepted. Please upload a .pdf resume.",
        )

    # --- Read file bytes ----------------------------------------------------
    try:
        file_bytes = file.file.read()
    except Exception as exc:
        logger.error("Failed to read uploaded file: %s", exc)
        raise HTTPException(status_code=400, detail="Could not read uploaded file.")

    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # --- Extract skills -----------------------------------------------------
    try:
        skills = extract_skills_from_pdf(file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if not skills:
        skills = ["General"]  # fallback so the interview can still proceed
        logger.warning("No skills extracted; defaulting to ['General'].")

    # --- Create DB session --------------------------------------------------
    session_id = str(uuid.uuid4())
    db_session = InterviewSession(
        id=session_id,
        role=role.strip(),
        skills=",".join(skills),
        status="ACTIVE",
        current_step=0,
        max_questions=settings.max_interview_questions,
    )
    db.add(db_session)
    db.commit()
    logger.info("✔ Created session %s (role=%s, skills=%s)", session_id, role, skills)

    # --- Run LangGraph step 1 -----------------------------------------------
    thread_config = {"configurable": {"thread_id": session_id}}
    initial_state = {
        "role": role.strip(),
        "skills": skills,
        "question_history": [],
        "answer_history": [],
        "current_question": None,
        "question_count": 0,
        "max_questions": settings.max_interview_questions,
        "is_completed": False,
        "evaluation_summary": None,
    }

    try:
        result = _graph.invoke(initial_state, thread_config)
    except Exception as exc:
        logger.exception("LangGraph invocation failed for session %s", session_id)
        raise HTTPException(status_code=500, detail="Failed to generate first question.")

    first_question = result.get("current_question", "")

    # --- Persist Q1 to InterviewLog -----------------------------------------
    db_session.current_step = 1
    db.add(InterviewLog(session_id=session_id, question=first_question))
    db.commit()

    return StartInterviewResponse(
        session_id=session_id,
        role=role.strip(),
        skills=skills,
        question=first_question,
        current_step=1,
    )


# ═══════════════════════════════════════════════════════════════════════════
# POST /api/interview/submit
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/submit", response_model=SubmitAnswerResponse)
def submit_answer(
    body: SubmitAnswerRequest,
    db: Session = Depends(get_db),
) -> SubmitAnswerResponse:
    """Submit a candidate answer and advance the interview state.

    1. Validate session exists and is ACTIVE.
    2. Record the answer on the latest InterviewLog entry.
    3. Rebuild LangGraph state from DB logs.
    4. Inject answer via update_state and resume the graph.
    5. If the graph loops → persist next question, bump current_step.
    6. If the graph finalises → update session status to COMPLETED.
    """
    # --- Guard: session exists and is active --------------------------------
    db_session: InterviewSession | None = db.get(InterviewSession, body.session_id)

    if not db_session:
        raise HTTPException(status_code=404, detail="Interview session not found.")

    if db_session.status != "ACTIVE":
        raise HTTPException(
            status_code=400,
            detail="This interview session has already been completed.",
        )

    # --- Record the answer on the latest log entry --------------------------
    logs: list[InterviewLog] = (
        db.query(InterviewLog)
        .filter(InterviewLog.session_id == body.session_id)
        .order_by(InterviewLog.id)
        .all()
    )

    if not logs:
        raise HTTPException(status_code=400, detail="No questions found for this session.")

    latest_log = logs[-1]
    if latest_log.answer is not None:
        raise HTTPException(
            status_code=400,
            detail="The latest question has already been answered. Cannot submit again.",
        )

    latest_log.answer = body.answer
    db.commit()
    logger.info("✔ Answer saved for session %s, step %d", body.session_id, db_session.current_step)

    # --- Rebuild answer_history from DB ------------------------------------
    question_history = [log.question for log in logs]
    answer_history = [log.answer for log in logs if log.answer is not None]

    # --- Resume LangGraph ---------------------------------------------------
    thread_config = {"configurable": {"thread_id": body.session_id}}

    # Inject updated answer_history via update_state
    # (langgraph-persistence skill: update_state + invoke(None, config))
    _graph.update_state(
        thread_config,
        {"answer_history": answer_history},
    )

    try:
        result = _graph.invoke(None, thread_config)
    except Exception as exc:
        logger.exception("LangGraph resume failed for session %s", body.session_id)
        raise HTTPException(status_code=500, detail="Failed to advance interview.")

    is_completed = result.get("is_completed", False)

    if is_completed:
        # --- Finalise session -----------------------------------------------
        db_session.status = "COMPLETED"
        db_session.evaluation_summary = result.get("evaluation_summary")
        db.commit()
        logger.info("✅ Session %s COMPLETED.", body.session_id)

        return SubmitAnswerResponse(
            is_completed=True,
            next_question=None,
            current_step=db_session.current_step,
            evaluation_summary=result.get("evaluation_summary"),
        )

    # --- Loop: persist next question ----------------------------------------
    next_question = result.get("current_question", "")
    db_session.current_step += 1
    db.add(InterviewLog(session_id=body.session_id, question=next_question))
    db.commit()
    logger.info("→ Next question generated for session %s (step %d)",
                body.session_id, db_session.current_step)

    return SubmitAnswerResponse(
        is_completed=False,
        next_question=next_question,
        current_step=db_session.current_step,
        evaluation_summary=None,
    )


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/interview/summary/{session_id}
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/summary/{session_id}", response_model=InterviewSummaryResponse)
def get_interview_summary(
    session_id: str,
    db: Session = Depends(get_db),
) -> InterviewSummaryResponse:
    """Fetch a complete interview session overview with all Q/A logs."""
    db_session: InterviewSession | None = db.get(InterviewSession, session_id)

    if not db_session:
        raise HTTPException(status_code=404, detail="Interview session not found.")

    logs: list[InterviewLog] = (
        db.query(InterviewLog)
        .filter(InterviewLog.session_id == session_id)
        .order_by(InterviewLog.id)
        .all()
    )

    return InterviewSummaryResponse(
        session_id=db_session.id,
        role=db_session.role,
        skills=db_session.skills.split(",") if db_session.skills else [],
        status=db_session.status,
        current_step=db_session.current_step,
        evaluation_summary=db_session.evaluation_summary,
        logs=[
            LogEntry(
                question=log.question,
                answer=log.answer,
                timestamp=log.timestamp,
            )
            for log in logs
        ],
    )
