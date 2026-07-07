"""
interview.py — FastAPI router for interview lifecycle management using MongoDB.

Following the updated pregenerated question workflow:
1. Ingest PDF resume text and target role.
2. Pregenerate 5 candidate-specific technical questions all at once via Gemini.
3. Conduct sequential chat responses turn-by-turn.
4. Pass the full transcript of questions/answers and resume text to Gemini for grading.
5. Save the final report in MongoDB along with candidate name, email, and phone number.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

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
from app.services.interview_graph import (
    parse_resume_and_generate_questions,
    evaluate_interview_transcript,
)
from app.services.resume_parser import (
    extract_skills_from_pdf,
    extract_resume_text_from_pdf,
)
from app.rag.ingest import (
    create_session_store,
    cleanup_session_store,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/interview", tags=["Interview"])


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
    2. Extract skills and raw text content from the resume PDF.
    3. Call LLM to parse resume credentials (name, email, phone) and pregenerate questions.
    4. Save session document including parsed credentials.
    5. Return first question and session details.
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

    # --- Extract skills and resume text -------------------------------------
    try:
        skills = extract_skills_from_pdf(file_bytes)
        resume_text = extract_resume_text_from_pdf(file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if not skills:
        skills = ["General"]
        logger.warning("No skills extracted; defaulting to ['General'].")

    session_id = str(uuid.uuid4())

    # --- RAG: Ingest resume into per-session ChromaDB collection -----------
    try:
        stored_chunks = create_session_store(session_id, resume_text)
        logger.info("Ingested %d resume chunks into ChromaDB for session %s", len(stored_chunks), session_id)
    except Exception as exc:
        logger.warning("RAG ingestion failed for session %s: %s (continuing without RAG)", session_id, exc)

    # --- LLM Parsing & Pregeneration (now with RAG context) ----------------
    try:
        result = parse_resume_and_generate_questions(role.strip(), resume_text, skills, session_id=session_id)
    except Exception as exc:
        logger.exception("Failed to parse resume and pregenerate questions for session %s", session_id)
        raise HTTPException(status_code=500, detail="Failed to initialize screening questions.")

    pregenerated = result.get("questions")
    if not pregenerated or len(pregenerated) < 5:
        logger.error("Pregeneration failed to yield 5 questions: %s", pregenerated)
        raise HTTPException(status_code=500, detail="Failed to initialize 5 technical screening questions.")

    first_question = pregenerated[0]
    candidate_name = result.get("name")
    candidate_email = result.get("email")
    candidate_phone = result.get("phone")
    retrieved_contexts = result.get("retrieved_contexts", [[] for _ in range(5)])

    # --- Create embedded log & document ------------------------------------
    first_log = InterviewLogDB(
        question=first_question,
        retrieved_context=retrieved_contexts[0] if retrieved_contexts else [],
        timestamp=datetime.now(timezone.utc),
    )

    session_doc = InterviewSessionDB(
        _id=session_id,
        role=role.strip(),
        skills=skills,
        status="ACTIVE",
        current_step=1,
        max_questions=5,
        candidate_name=candidate_name,
        candidate_email=candidate_email,
        candidate_phone=candidate_phone,
        resume_text=resume_text,
        pregenerated_questions=pregenerated,
        retrieved_contexts_per_question=retrieved_contexts,
        logs=[first_log],
    )

    # --- Persist to MongoDB -------------------------------------------------
    try:
        await db["sessions"].insert_one(session_doc.model_dump(by_alias=True))
    except Exception as exc:
        logger.exception("Failed to write to MongoDB for session %s", session_id)
        raise HTTPException(status_code=500, detail="Database write failed.")

    logger.info("Created MongoDB session %s (name=%s, email=%s, role=%s)", session_id, candidate_name, candidate_email, role)

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
    3. If step < 5 → Fetch pregenerated question #current_step, increment step, update DB.
    4. If finalising (step == 5) → trigger full evaluation via Gemini, update status to COMPLETED, update DB.
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
    logger.info("Answer saved for session %s, step %d", body.session_id, session_doc.current_step)

    # --- Check loop vs finalize --------------------------------------------
    if session_doc.current_step >= len(session_doc.pregenerated_questions):
        # --- Finalise session & Grade via Gemini ----------------------------
        logger.info("Final turn completed. Conducting LLM strict evaluation summary...")
        try:
            summary = evaluate_interview_transcript(
                role=session_doc.role,
                skills=session_doc.skills,
                logs=session_doc.logs,
                resume_text=session_doc.resume_text or "",
                session_id=body.session_id,
            )
        except Exception as exc:
            logger.exception("LLM evaluation execution failed: %s", exc)
            summary = "Evaluation report generation failed. All turns were completed successfully."

        # Clean up ChromaDB session collection after evaluation
        try:
            cleanup_session_store(body.session_id)
        except Exception as exc:
            logger.warning("Failed to clean up ChromaDB for session %s: %s", body.session_id, exc)

        session_doc.status = "COMPLETED"
        session_doc.evaluation_summary = summary

        try:
            await db["sessions"].update_one(
                {"_id": body.session_id},
                {
                    "$set": {
                        "status": "COMPLETED",
                        "evaluation_summary": summary,
                        "logs": [log.model_dump() for log in session_doc.logs],
                    }
                },
            )
        except Exception as exc:
            logger.exception("Failed to update final session state in MongoDB: %s", body.session_id)
            raise HTTPException(status_code=500, detail="Database write failed.")

        logger.info("MongoDB Session %s COMPLETED.", body.session_id)

        return SubmitAnswerResponse(
            is_completed=True,
            next_question=None,
            current_step=session_doc.current_step,
            evaluation_summary=summary,
        )

    # --- Loop: advance to next pregenerated question -----------------------
    next_question = session_doc.pregenerated_questions[session_doc.current_step]
    next_step = session_doc.current_step + 1

    # Get retrieved context for this question (if available)
    next_q_context = []
    if hasattr(session_doc, 'retrieved_contexts_per_question') and session_doc.retrieved_contexts_per_question:
        idx = session_doc.current_step
        if idx < len(session_doc.retrieved_contexts_per_question):
            next_q_context = session_doc.retrieved_contexts_per_question[idx]

    next_log = InterviewLogDB(
        question=next_question,
        retrieved_context=next_q_context,
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

    logger.info("Advanced to pregenerated question #%d for session %s", next_step, body.session_id)

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
                retrieved_context=log.retrieved_context,
                timestamp=log.timestamp,
            )
            for log in session_doc.logs
        ],
    )
