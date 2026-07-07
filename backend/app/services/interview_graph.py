"""
interview_graph.py — Phase 2: LangGraph Interview State Machine
================================================================
Standalone state-machine that orchestrates a multi-turn technical
interview using LangGraph.  Runs entirely in the terminal — no web
server required.

Flow:
    ┌───────────────┐
    │  START         │
    └──────┬────────┘
           ▼
    ┌───────────────┐     question_count < max_questions
    │  generate_q   │────────────────── END (yield to caller)
    └──────┬────────┘
           │ question_count >= max_questions
           ▼
    ┌───────────────┐
    │  finalize     │──── END
    └───────────────┘

The graph pauses at END after each question so the caller (CLI REPL
or future API) can inject the candidate's answer via
`graph.update_state(config, …)` and then resume with
`graph.invoke(None, config)`.

Environment:
    GEMINI_API_KEY (or GOOGLE_API_KEY) must be set.

Skills used:
    - langgraph-persistence  (InMemorySaver, thread_id, update_state)
    - langchain-rag          (consistent model patterns)
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Third-party imports
# ---------------------------------------------------------------------------
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CHAT_MODEL: str = "gemini-3.1-flash-lite"


# ═══════════════════════════════════════════════════════════════════════════
# 1. STATE SCHEMA
# ═══════════════════════════════════════════════════════════════════════════


class InterviewState(BaseModel):
    """Shared memory of the interview state machine.

    Every field is serialisable so the checkpointer can persist it
    between graph invocations.
    """

    role: str = ""
    skills: list[str] = Field(default_factory=list)
    question_history: list[str] = Field(default_factory=list)
    answer_history: list[str] = Field(default_factory=list)
    current_question: Optional[str] = None
    question_count: int = 0
    max_questions: int = 5
    is_completed: bool = False
    evaluation_summary: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════
# 2. LLM HELPER
# ═══════════════════════════════════════════════════════════════════════════


def _get_llm() -> ChatGoogleGenerativeAI:
    """Return a ChatGoogleGenerativeAI instance using the env API key."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Neither GEMINI_API_KEY nor GOOGLE_API_KEY is set."
        )
    return ChatGoogleGenerativeAI(
        model=CHAT_MODEL,
        google_api_key=api_key,
        temperature=0.7,
    )


def _get_clean_content(response) -> str:
    """Safely extract and clean content from a LangChain LLM response.

    Handles cases where the response content is returned as a list of components
    instead of a raw string.
    """
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content.strip()
    elif isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict) and "text" in part:
                text_parts.append(part["text"])
        return "".join(text_parts).strip()
    return str(content).strip()


def parse_resume_and_generate_questions(role: str, resume_text: str, skills: list[str], session_id: str = "") -> dict:
    """Extract candidate credentials and pregenerate 5 screening questions via Gemini.
    
    Uses RAG retrieval from the session's ChromaDB collection to ground
    questions in specific resume content rather than relying solely on
    the raw text dump.
    """
    import json
    llm = _get_llm()

    # --- RAG Retrieval: fetch relevant resume chunks per skill ----------
    rag_context = ""
    all_retrieved_chunks: list[list[str]] = []
    if session_id:
        try:
            from app.rag.ingest import retrieve_context
            # Build queries from skills + role to retrieve targeted resume sections
            all_chunks = []
            for skill in skills[:5]:  # Limit to top 5 skills
                query = f"{skill} experience projects work {role}"
                chunks = retrieve_context(session_id, query, k=3)
                all_chunks.extend(chunks)
            # Deduplicate while preserving order
            seen = set()
            unique_chunks = []
            for chunk in all_chunks:
                if chunk not in seen:
                    seen.add(chunk)
                    unique_chunks.append(chunk)
            if unique_chunks:
                rag_context = "\n\n---\n\n".join(unique_chunks[:10])  # Cap at 10 chunks
                logger.info("[RAG] Retrieved %d unique resume chunks for question generation.", len(unique_chunks[:10]))
            # Store per-question context (distribute chunks across 5 questions)
            for i in range(5):
                start = (i * len(unique_chunks)) // 5
                end = ((i + 1) * len(unique_chunks)) // 5
                all_retrieved_chunks.append(unique_chunks[start:end] if unique_chunks else [])
        except Exception as exc:
            logger.warning("[RAG] Failed to retrieve context for question generation: %s", exc)
            all_retrieved_chunks = [[] for _ in range(5)]
    else:
        all_retrieved_chunks = [[] for _ in range(5)]

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an expert technical recruiter and interviewer. "
                "Your task is to parse the candidate's resume content and generate a structured screening plan for the role of **{role}** (skills: {skills}).\n\n"
                "Retrieved Resume Context (key sections from knowledge base):\n"
                "--- START RETRIEVED CONTEXT ---\n"
                "{rag_context}\n"
                "--- END RETRIEVED CONTEXT ---\n\n"
                "Instructions:\n"
                "1. Extract the candidate's personal details from the resume:\n"
                "   - Full Name (if not found, return null)\n"
                "   - Email Address (if not found, return null)\n"
                "   - Phone Number (if not found, return null)\n"
                "2. Pregenerate exactly 5 targeted technical screening questions:\n"
                "   - Ground the questions in the retrieved context above — reference specific projects, technologies, or claims from the resume.\n"
                "   - Structure them progressively in difficulty (Q1-Q2: core, Q3-Q4: scenario/system, Q5: optimization/trade-offs).\n"
                "   - Questions must probe whether the candidate truly understands what their resume claims.\n"
                "3. Output ONLY a valid JSON object with the following schema (no markdown formatting, no prefix/suffix text):\n"
                "{{\n"
                "  \"name\": \"Candidate Full Name or null\",\n"
                "  \"email\": \"candidate@email.com or null\",\n"
                "  \"phone\": \"+1-234-567-8900 or null\",\n"
                "  \"questions\": [\n"
                "    \"Question 1\",\n"
                "    \"Question 2\",\n"
                "    \"Question 3\",\n"
                "    \"Question 4\",\n"
                "    \"Question 5\"\n"
                "  ]\n"
                "}}"
            ),
            (
                "human",
                "Here is the candidate's full resume content to parse and generate questions for:\n"
                "--- START RESUME ---\n"
                "{resume_text}\n"
                "--- END RESUME ---"
            )
        ]
    )
    chain = prompt | llm
    try:
        response = chain.invoke({
            "role": role,
            "skills": ", ".join(skills),
            "rag_context": rag_context or "(No retrieved context available)",
            "resume_text": resume_text,
        })
        text = _get_clean_content(response)
        
        print("\n================== RAW GEMINI RESPONSE ==================")
        print(text)
        print("=========================================================\n")
        
        # Robust cleanup of markdown wrappers using regex
        import re
        if "```" in text:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
            if match:
                text = match.group(1).strip()
            else:
                text = text.replace("```json", "").replace("```", "").strip()
        
        data = json.loads(text)
        if isinstance(data, dict):
            qs = data.get("questions")
            if isinstance(qs, list) and len(qs) >= 5:
                print(">>> successfully parsed pregenerated questions: ", qs[:5])
                return {
                    "name": data.get("name"),
                    "email": data.get("email"),
                    "phone": data.get("phone"),
                    "questions": [str(q) for q in qs[:5]],
                    "retrieved_contexts": all_retrieved_chunks[:5],
                }
            else:
                print(">>> WARNING: questions key not found or less than 5 items in parsed dict")
        else:
            print(">>> WARNING: JSON did not parse as a dictionary")
    except Exception as exc:
        print("\n!!! ERROR PARSING LLM RESPONSE:")
        import traceback
        traceback.print_exc()
        logger.exception("Failed to parse resume and pre-generate questions via Gemini")
    
    # Fallback response
    return {
        "name": None,
        "email": None,
        "phone": None,
        "questions": [
            f"What is your approach to designing scalable structures as a {role}?",
            f"How do you manage complex data dependencies and ensure security for skills like {', '.join(skills[:3])}?",
            f"Can you explain a challenging technical trade-off you had to make in your recent role?",
            f"How do you ensure zero-downtime deployments and operational reliability in production?",
            f"Describe how you profile, debug, and optimize performance bottleneck latency constraints."
        ],
        "retrieved_contexts": [[] for _ in range(5)],
    }


def evaluate_interview_transcript(role: str, skills: list[str], logs: list, resume_text: str, session_id: str = "") -> str:
    """Use Gemini to evaluate candidate's answers against resume claims.
    
    For each Q&A pair, retrieves relevant resume chunks from ChromaDB
    to cross-reference what the resume claims vs what the candidate
    actually demonstrated in their answers.
    """
    llm = _get_llm()
    
    # --- RAG Retrieval: for each answer, find matching resume claims ------
    rag_verification = ""
    if session_id:
        try:
            from app.rag.ingest import retrieve_context
            verification_sections = []
            for i, log in enumerate(logs):
                if log.answer:
                    chunks = retrieve_context(session_id, log.answer, k=3)
                    if chunks:
                        section = f"Q{i+1} — Resume sections relevant to the answer:\n"
                        for j, chunk in enumerate(chunks):
                            section += f"  Chunk {j+1}: {chunk[:200]}...\n"
                        verification_sections.append(section)
            if verification_sections:
                rag_verification = "\n".join(verification_sections)
                logger.info("[RAG] Retrieved verification context for %d answers.", len(verification_sections))
        except Exception as exc:
            logger.warning("[RAG] Failed to retrieve verification context: %s", exc)

    # Format Q&A transcript
    transcript_lines = []
    for i, log in enumerate(logs):
        transcript_lines.append(f"Q{i+1}: {log.question}")
        transcript_lines.append(f"A{i+1}: {log.answer or '(no response)'}")
    transcript = "\n\n".join(transcript_lines)

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a strict, highly critical technical evaluator acting as a devil's advocate. "
                "Evaluate this candidate's interview performance for the role of **{role}** (skills: {skills}).\n\n"
                "Candidate's Resume:\n"
                "--- START RESUME ---\n"
                "{resume_text}\n"
                "--- END RESUME ---\n\n"
                "Resume Sections Matched to Each Answer (from vector database retrieval):\n"
                "--- START RAG VERIFICATION ---\n"
                "{rag_verification}\n"
                "--- END RAG VERIFICATION ---\n\n"
                "Interview Q&A Transcript:\n"
                "--- START TRANSCRIPT ---\n"
                "{transcript}\n"
                "--- END TRANSCRIPT ---\n\n"
                "CRITICAL EVALUATION INSTRUCTIONS:\n"
                "- Use the RAG VERIFICATION section above to cross-reference what the resume CLAIMS vs what the candidate ACTUALLY demonstrated.\n"
                "- If the resume claims expertise in X but the candidate's answer shows no depth, flag this as a discrepancy.\n"
                "- If the candidate's answer aligns well with their resume claims, note this as a strength.\n\n"
                "Produce a structured evaluation report that includes:\n"
                "1. **Overall Assessment** — 2–3 sentence critical analysis of candidate's core depth.\n"
                "2. **Strengths** — bullet points.\n"
                "3. **Areas for Improvement** — bullet points highlighting sparse explanations or failures.\n"
                "4. **Resume vs Reality** — explicitly compare resume claims against demonstrated knowledge.\n"
                "5. **Recommended Next Steps** — e.g. reject, re-evaluate, or advance.\n"
                "6. **Score** — a rating out of 10. Grading must be extremely strict and unforgiving. "
                "If the candidate gives bad, short, vague, placeholder, or superficial answers, "
                "be a devil's advocate and score them severely (e.g. 0.5/10, 1/10, or 2/10). "
                "Do not award high scores (8/10 or above) unless answers are exceptionally deep, precise, and correct.",
            ),
            (
                "human",
                "Please evaluate this candidate.",
            ),
        ]
    )
    
    chain = prompt | llm
    try:
        response = chain.invoke({
            "role": role,
            "skills": ", ".join(skills),
            "resume_text": resume_text,
            "rag_verification": rag_verification or "(No RAG verification data available)",
            "transcript": transcript,
        })
        eval_text = _get_clean_content(response)
        print("\n================== RAW EVALUATION REPORT ==================")
        print(eval_text)
        print("===========================================================\n")
        return eval_text
    except Exception as exc:
        print("\n!!! ERROR IN LLM EVALUATION GENERATION:")
        import traceback
        traceback.print_exc()
        logger.exception("Failed to generate strict evaluation summary")
        return "Failed to generate evaluation report."


# ═══════════════════════════════════════════════════════════════════════════
# 3. GRAPH NODES
# ═══════════════════════════════════════════════════════════════════════════


def generate_question_node(state: InterviewState) -> dict:
    """Generate the next interview question based on the candidate profile.

    Uses:
        - role & skills to tailor the question domain
        - question_history to avoid repeats
        - answer_history to adapt difficulty / follow-up

    Returns a *partial* state update dict (LangGraph convention).
    """
    logger.info(
        "[generate_question] Round %d/%d",
        state.question_count + 1,
        state.max_questions,
    )

    # --- RAG placeholder ---------------------------------------------------
    # In Phase 3 this will be replaced with a real retrieval step against
    # the ChromaDB vector store populated by ingest.py.
    rag_context = (
        "Placeholder: In production, the top-k chunks from the ML textbook "
        "vector store will be injected here to ground the question in "
        "authoritative source material."
    )

    # --- Prompt construction ------------------------------------------------
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a senior technical interviewer conducting a focused "
                "screening interview for the role of **{role}**.\n\n"
                "Candidate's key skills: {skills}\n\n"
                "Reference material (from knowledge base):\n{rag_context}\n\n"
                "Questions already asked (DO NOT repeat or rephrase these):\n"
                "{question_history}\n\n"
                "Candidate's previous answers (use these to calibrate "
                "difficulty and build follow-up depth):\n"
                "{answer_history}\n\n"
                "Guidelines:\n"
                "- Ask ONE clear, specific technical question.\n"
                "- Focus on conceptual understanding or applied problem "
                "solving — avoid trivia.\n"
                "- Progressively increase difficulty as the interview "
                "continues.\n"
                "- Output ONLY the question text, nothing else.",
            ),
            (
                "human",
                "Generate question #{question_number} for this interview.",
            ),
        ]
    )

    llm = _get_llm()
    chain = prompt | llm

    response = chain.invoke(
        {
            "role": state.role,
            "skills": ", ".join(state.skills),
            "rag_context": rag_context,
            "question_history": (
                "\n".join(
                    f"  Q{i+1}: {q}"
                    for i, q in enumerate(state.question_history)
                )
                or "  (none yet)"
            ),
            "answer_history": (
                "\n".join(
                    f"  A{i+1}: {a}"
                    for i, a in enumerate(state.answer_history)
                )
                or "  (none yet)"
            ),
            "question_number": state.question_count + 1,
        }
    )

    new_question = _get_clean_content(response)
    logger.info("   → Generated question: %s", new_question[:120])

    # Partial state update
    return {
        "current_question": new_question,
        "question_history": state.question_history + [new_question],
        "question_count": state.question_count + 1,
    }


def finalize_interview_node(state: InterviewState) -> dict:
    """Generate a structured evaluation summary from the full Q&A history.

    Triggered when `question_count >= max_questions` and the final
    answer has been recorded.
    """
    logger.info("[finalize_interview] Generating evaluation summary ...")

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a strict, highly critical technical evaluator acting as a devil's advocate. "
                "A candidate for the role of **{role}** (skills: {skills}) has completed a screening interview.\n\n"
                "Below is the full transcript.\n\n"
                "{transcript}\n\n"
                "Produce a structured evaluation that includes:\n"
                "1. **Overall Assessment** — 2–3 sentence critical analysis of candidate's core depth.\n"
                "2. **Strengths** — bullet points.\n"
                "3. **Areas for Improvement** — bullet points highlighting sparse explanations or failures.\n"
                "4. **Recommended Next Steps** — e.g. reject, re-evaluate, or advance.\n"
                "5. **Score** — a rating out of 10. Grading must be extremely strict and unforgiving. "
                "If the candidate gives bad, short, vague, placeholder, or superficial answers, "
                "be a devil's advocate and score them severely (e.g. 0.5/10, 1/10, or 2/10). "
                "Do not award high scores (8/10 or above) unless answers are exceptionally deep, precise, and correct.",
            ),
            (
                "human",
                "Please evaluate this candidate.",
            ),
        ]
    )

    # Build a readable transcript
    transcript_lines: list[str] = []
    for i in range(len(state.question_history)):
        transcript_lines.append(f"Q{i+1}: {state.question_history[i]}")
        if i < len(state.answer_history):
            transcript_lines.append(f"A{i+1}: {state.answer_history[i]}")
    transcript = "\n".join(transcript_lines)

    llm = _get_llm()
    chain = prompt | llm

    response = chain.invoke(
        {
            "role": state.role,
            "skills": ", ".join(state.skills),
            "transcript": transcript,
        }
    )

    summary = _get_clean_content(response)
    logger.info("   → Evaluation generated (%d chars).", len(summary))

    return {
        "evaluation_summary": summary,
        "is_completed": True,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. CONDITIONAL ROUTER
# ═══════════════════════════════════════════════════════════════════════════


def should_continue_router(state: InterviewState) -> str:
    """Decide the next step after a question has been generated.

    - If we've reached max_questions → route to 'finalize'.
    - Otherwise → route to END so the caller can inject the
      candidate's answer and re-invoke.
    """
    if state.question_count >= state.max_questions:
        logger.info("   → Routing to: finalize (all questions asked)")
        return "finalize"
    else:
        logger.info(
            "   → Routing to: END (awaiting candidate answer, %d/%d)",
            state.question_count,
            state.max_questions,
        )
        return END


# ═══════════════════════════════════════════════════════════════════════════
# 5. GRAPH COMPILATION
# ═══════════════════════════════════════════════════════════════════════════


def build_interview_graph(checkpointer=None):
    """Construct and compile the interview StateGraph.

    Parameters
    ----------
    checkpointer
        A LangGraph checkpointer instance.  Use ``InMemorySaver()``
        for local testing or ``PostgresSaver`` for production
        (per langgraph-persistence skill).

    Returns
    -------
    CompiledGraph
        The compiled, runnable graph.
    """
    builder = StateGraph(InterviewState)

    # --- Nodes ---
    builder.add_node("generate_question", generate_question_node)
    builder.add_node("finalize", finalize_interview_node)

    # --- Edges ---
    # Entry: always start by generating a question
    builder.add_edge(START, "generate_question")

    # After generating a question, decide what to do next
    builder.add_conditional_edges(
        "generate_question",
        should_continue_router,
        {
            "finalize": "finalize",
            END: END,
        },
    )

    # Finalize always ends
    builder.add_edge("finalize", END)

    # Compile with checkpointer (skill: always pass checkpointer at compile)
    return builder.compile(checkpointer=checkpointer)


# Pre-built graph with InMemorySaver for local testing
# (skill: InMemorySaver is fine for dev, use PostgresSaver in production)
_checkpointer = InMemorySaver()
interview_graph = build_interview_graph(checkpointer=_checkpointer)


# ═══════════════════════════════════════════════════════════════════════════
# 6. TERMINAL REPL
# ═══════════════════════════════════════════════════════════════════════════


def run_cli_interview() -> None:
    """Interactive CLI simulation of the interview state machine.

    Uses ``update_state`` + ``invoke(None, config)`` to inject answers
    and resume the graph, following the langgraph-persistence skill's
    recommended pattern.
    """
    logger.info("=" * 60)
    logger.info("  Phase 2 — Interview State Machine (CLI REPL)")
    logger.info("=" * 60)

    # Validate environment
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY / GOOGLE_API_KEY not set.")
        raise SystemExit(1)
    logger.info("API key detected.")

    # --- Initial state ------------------------------------------------------
    initial_state = {
        "role": "Backend Engineer",
        "skills": ["Python", "FastAPI", "SQL"],
        "question_history": [],
        "answer_history": [],
        "current_question": None,
        "question_count": 0,
        "max_questions": 5,
        "is_completed": False,
        "evaluation_summary": None,
    }

    # Always provide thread_id (skill: fix-thread-id-required)
    config = {"configurable": {"thread_id": "cli-interview-001"}}

    print("\n" + "=" * 60)
    print(f"  INTERVIEW SESSION")
    print(f"  Role  : {initial_state['role']}")
    print(f"  Skills: {', '.join(initial_state['skills'])}")
    print(f"  Questions: {initial_state['max_questions']}")
    print("=" * 60 + "\n")

    # --- First invocation: generates Q1 ------------------------------------
    logger.info("Starting graph — generating first question ...")
    result = interview_graph.invoke(initial_state, config)

    while not result.get("is_completed", False):
        # Display the current question
        q_num = result["question_count"]
        question = result["current_question"]

        print(f"\n{'─' * 60}")
        print(f"  QUESTION {q_num}/{result['max_questions']}")
        print(f"{'─' * 60}")
        print(f"\n  {question}\n")

        # Collect answer from terminal
        try:
            answer = input("  Your answer: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n  Interview cancelled by user.")
            return

        if not answer:
            answer = "(no answer provided)"

        logger.info("   → Answer recorded (%d chars).", len(answer))

        # Inject the answer into state using update_state
        # (skill: update_state + invoke(None, config) pattern)
        interview_graph.update_state(
            config,
            {
                "answer_history": result.get("answer_history", []) + [answer],
            },
        )

        # Resume the graph — it will generate the next question or finalize
        logger.info("Resuming graph ...")
        result = interview_graph.invoke(None, config)

    # --- Interview complete -------------------------------------------------
    print("\n" + "=" * 60)
    print("  INTERVIEW COMPLETE")
    print("=" * 60)

    print(f"\n  Questions asked : {result['question_count']}")
    print(f"  Answers given   : {len(result.get('answer_history', []))}")

    if result.get("evaluation_summary"):
        print(f"\n{'─' * 60}")
        print("  EVALUATION SUMMARY")
        print(f"{'─' * 60}\n")
        print(result["evaluation_summary"])

    print("\n" + "=" * 60 + "\n")
    logger.info("CLI interview session finished.")


# ═══════════════════════════════════════════════════════════════════════════
# Entry-point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        run_cli_interview()
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
        sys.exit(130)
    except Exception:
        logger.exception("Unexpected error during interview.")
        sys.exit(1)
