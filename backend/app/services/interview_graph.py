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
CHAT_MODEL: str = "gemini-2.0-flash"


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

    new_question = response.content.strip()
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
                "You are a senior technical evaluator. A candidate for the "
                "role of **{role}** (skills: {skills}) has just completed a "
                "screening interview.\n\n"
                "Below is the full transcript.\n\n"
                "{transcript}\n\n"
                "Produce a structured evaluation that includes:\n"
                "1. **Overall Assessment** — 2–3 sentence summary.\n"
                "2. **Strengths** — bullet points.\n"
                "3. **Areas for Improvement** — bullet points with "
                "constructive feedback.\n"
                "4. **Recommended Next Steps** — e.g. advance to next "
                "round, revisit topics, etc.\n"
                "5. **Score** — a rating out of 10.\n\n"
                "Be fair, specific, and actionable.",
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

    summary = response.content.strip()
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
