"""
main.py — FastAPI application entry point.

Uses a lifespan context manager (per FastAPI skill guideline) to
initialise the database on startup.

Run with:
    uvicorn main:app --reload
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load .env before anything reads os.environ
load_dotenv()

from app.core.config import settings
from app.core.database import get_client, close_db
from app.api.interview import router as interview_router

# Ensure Gemini key is visible as env var for LangChain/LangGraph
# (pydantic-settings loads it, but the LLM wrappers read os.environ)
if settings.gemini_api_key:
    os.environ.setdefault("GEMINI_API_KEY", settings.gemini_api_key)
if settings.google_api_key:
    os.environ.setdefault("GOOGLE_API_KEY", settings.google_api_key)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — manage MongoDB connection lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    logger.info("Starting %s ...", settings.app_title)
    
    # Ping MongoDB to verify connection
    try:
        client = get_client()
        await client.admin.command('ping')
        logger.info("Successfully connected to MongoDB.")
    except Exception as exc:
        logger.exception("Failed to connect to MongoDB.")
        raise SystemExit(1) from exc

    yield

    logger.info("Shutting down database connections.")
    close_db()
    logger.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title=settings.app_title,
    version="0.3.0",
    lifespan=lifespan,
)

# CORS — wide open for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(interview_router)


@app.get("/")
def read_root() -> dict[str, str]:
    """Health check."""
    return {"message": f"Welcome to {settings.app_title}"}
