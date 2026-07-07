"""
interview.py — FastAPI router for interview lifecycle management using MongoDB.

Endpoints:
    POST /api/interview/start          — start a new session from a resume PDF
    POST /api/interview/submit         — submit an answer and get the next question
    GET  /api/interview/summary/{id}   — fetch a completed session's full log

Follows the FastAPI skill guidelines:
    - Asynchronous route handlers (async def) for non-blocking I/O
    - Pydantic models for request/response validation and DB documents
    - Guard clauses / early returns for error paths
    - HTTPException for expected errors
    - Dependency injection for MongoDB database sessions
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.database import get_db
from app.schemas.interview import (
    InterviewLogDB,
    InterviewSessionDB,
    InterviewSummaryResponse,
    LogEntry,
    StartInterviewResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
)
from app.services.interview_graph import build_interview_graph
from app.services.resume_parser import extract_skills_from_pdf

# LangGraph checkpointer — InMemorySaver for dev
from langgraph.checkpoint.memory import InMemorySaver

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/interview", tags=["Interview"])

# ---------------------------------------------------------------------------
# Shared LangGraph instance for the API process
# ---------------------------------------------------------------------------
_checkpointer = InMemorySaver()
_graph = build_interview_graph(checkpointer=_checkpointer)


# ═══════════════════════════════════════════════════════════════════════════
# POST /api/interview/start
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/start", response_model=StartInterviewResponse)
async def start_interview(
    role: str = Form(..., description="Target job role"),
    file: UploadFile = File(..., description="Resume PDF"),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> StartInterviewResponse:
    """Start a new interview session.

    1. Validate the uploaded file is a PDF.
    2. Extract skills from the resume.
    3. Run the first LangGraph step to generate Q1.
    4. Persist a new rich InterviewSession document with embedded log.
    5. Return session_id, question, and current_step.
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

    session_id = str(uuid.uuid4())

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

    # --- Create embedded log & document ------------------------------------
    first_log = InterviewLogDB(
        question=first_question,
        timestamp=datetime.now(timezone.utc),
    )

    session_doc = InterviewSessionDB(
        _id=session_id,
        role=role.strip(),
        skills=skills,
        status="ACTIVE",
        current_step=1,
        max_questions=settings.max_interview_questions,
        logs=[first_log],
    )

    # --- Persist to MongoDB -------------------------------------------------
    try:
        await db["sessions"].insert_one(session_doc.model_dump(by_alias=True))
    except Exception as exc:
        logger.exception("Failed to write to MongoDB for session %s", session_id)
        raise HTTPException(status_code=500, detail="Database write failed.")

    logger.info("✔ Created MongoDB session %s (role=%s, skills=%s)", session_id, role, skills)

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
async def submit_answer(
    body: SubmitAnswerRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> SubmitAnswerResponse:
    """Submit a candidate answer and advance the interview state.

    1. Fetch session from MongoDB and validate ACTIVE status.
    2. Record answer into the latest embedded log item.
    3. Rebuild histories and trigger LangGraph.
    4. If the graph loops → embed next question, increment step, update DB.
    5. If finalising → update status to COMPLETED and save report.
    """
    # --- Fetch session ------------------------------------------------------
    try:
        session_data = await db["sessions"].find_one({"_id": body.session_id})
    except Exception as exc:
        logger.exception("Failed to query MongoDB for session %s", body.session_id)
        raise HTTPException(status_code=500, detail="Database query failed.")

    if not session_data:
        raise HTTPException(status_code=404, detail="Interview session not found.")

    session_doc = InterviewSessionDB.model_validate(session_data)

    # --- Guard: is active ---------------------------------------------------
    if session_doc.status != "ACTIVE":
        raise HTTPException(
            status_code=400,
            detail="This interview session has already been completed.",
        )

    # --- Guard: contains logs -----------------------------------------------
    if not session_doc.logs:
        raise HTTPException(status_code=400, detail="No questions found for this session.")

    # --- Record the answer on the latest log entry --------------------------
    latest_log = session_doc.logs[-1]
    if latest_log.answer is not None:
        raise HTTPException(
            status_code=400,
            detail="The latest question has already been answered. Cannot submit again.",
        )

    latest_log.answer = body.answer
    logger.info("✔ Answer saved for session %s, step %d", body.session_id, session_doc.current_step)

    # --- Rebuild answer_history/question_history from logs -----------------
    question_history = [log.question for log in session_doc.logs]
    answer_history = [log.answer for log in session_doc.logs if log.answer is not None]

    # --- Resume LangGraph ---------------------------------------------------
    thread_config = {"configurable": {"thread_id": body.session_id}}

    _graph.update_state(
        thread_config,
        {"answer_history": answer_history},
    )

    try:
        result = _graph.invoke(None, thread_config)
    except Exception as exc:
        logger.exception("LangGraph resume failed for session %s", body.session_id)
        raise HTTPException(status_code=500, detail="Failed to advance interview state machine.")

    is_completed = result.get("is_completed", False)

    if is_completed:
        # --- Finalise session -----------------------------------------------
        session_doc.status = "COMPLETED"
        session_doc.evaluation_summary = result.get("evaluation_summary")

        try:
            await db["sessions"].update_one(
                {"_id": body.session_id},
                {
                    "$set": {
                        "status": "COMPLETED",
                        "evaluation_summary": session_doc.evaluation_summary,
                        "logs": [log.model_dump() for log in session_doc.logs],
                    }
                },
            )
        except Exception as exc:
            logger.exception("Failed to update final session state in MongoDB: %s", body.session_id)
            raise HTTPException(status_code=500, detail="Database write failed.")

        logger.info("✅ MongoDB Session %s COMPLETED.", body.session_id)

        return SubmitAnswerResponse(
            is_completed=True,
            next_question=None,
            current_step=session_doc.current_step,
            evaluation_summary=session_doc.evaluation_summary,
        )

    # --- Loop: persist next question ----------------------------------------
    next_question = result.get("current_question", "")
    next_step = session_doc.current_step + 1

    next_log = InterviewLogDB(
        question=next_question,
        timestamp=datetime.now(timezone.utc),
    )
    session_doc.logs.append(next_log)

    try:
        await db["sessions"].update_one(
            {"_id": body.session_id},
            {
                "$set": {
                    "current_step": next_step,
                    "logs": [log.model_dump() for log in session_doc.logs],
                }
            },
        )
    except Exception as exc:
        logger.exception("Failed to add next question to MongoDB session %s", body.session_id)
        raise HTTPException(status_code=500, detail="Database write failed.")

    logger.info("→ Next question generated for session %s (step %d)", body.session_id, next_step)

    return SubmitAnswerResponse(
        is_completed=False,
        next_question=next_question,
        current_step=next_step,
        evaluation_summary=None,
    )


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/interview/summary/{session_id}
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/summary/{session_id}", response_model=InterviewSummaryResponse)
async def get_interview_summary(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> InterviewSummaryResponse:
    """Fetch a complete interview session overview with all Q/A logs."""
    try:
        session_data = await db["sessions"].find_one({"_id": session_id})
    except Exception as exc:
        logger.exception("Failed to query MongoDB for session %s", session_id)
        raise HTTPException(status_code=500, detail="Database query failed.")

    if not session_data:
        raise HTTPException(status_code=404, detail="Interview session not found.")

    session_doc = InterviewSessionDB.model_validate(session_data)

    return InterviewSummaryResponse(
        session_id=session_doc.id,
        role=session_doc.role,
        skills=session_doc.skills,
        status=session_doc.status,
        current_step=session_doc.current_step,
        evaluation_summary=session_doc.evaluation_summary,
        logs=[
            LogEntry(
                question=log.question,
                answer=log.answer,
                timestamp=log.timestamp,
            )
            for log in session_doc.logs
        ],
    )
