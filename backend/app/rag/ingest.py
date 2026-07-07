"""
ingest.py — Phase 1: Knowledge-Base Ingestion Pipeline
=======================================================
Standalone script that parses a role-specific ML textbook PDF,
chunks its text, generates embeddings via Gemini, and persists
them into a local ChromaDB vector store.

Usage:
    # First run  → full pipeline (load → chunk → embed → store)
    python app/rag/ingest.py

    # Subsequent runs → skips ingestion, loads existing DB, runs demo query
    python app/rag/ingest.py

Environment:
    GEMINI_API_KEY (or GOOGLE_API_KEY) must be set.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging — single, consistent format for every log line
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Third-party / LangChain imports
# ---------------------------------------------------------------------------
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenAIEmbeddings
from langchain_chroma import Chroma


# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------
BACKEND_DIR: Path = Path(__file__).resolve().parents[2]          # …/backend

PDF_PATH: Path = BACKEND_DIR / "knowledge_base" / "ml_book.pdf"
CHROMA_PERSIST_DIR: Path = BACKEND_DIR / "chroma_db"

# Chunking hyper-parameters
CHUNK_SIZE: int = 600
CHUNK_OVERLAP: int = 60

# Embedding model — Google GenAI default
EMBEDDING_MODEL: str = "models/text-embedding-004"

# Chroma collection
COLLECTION_NAME: str = "ml_textbook"

# Demo query for the CLI smoke-test
DEMO_QUERY: str = (
    "What is gradient descent and how does it optimize a loss function?"
)
TOP_K: int = 3


# ═══════════════════════════════════════════════════════════════════════════
# Shared helpers
# ═══════════════════════════════════════════════════════════════════════════


def _validate_environment() -> str:
    """Ensure a Gemini API key is available before making any API calls."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        logger.error(
            "Neither GEMINI_API_KEY nor GOOGLE_API_KEY is set. "
            "Export it in your shell or add it to a .env file."
        )
        raise SystemExit(1)
    logger.info("✔ Gemini API Key detected.")
    return api_key


def _get_embeddings(api_key: str) -> GoogleGenAIEmbeddings:
    """Return a configured GoogleGenAIEmbeddings instance."""
    return GoogleGenAIEmbeddings(
        model=EMBEDDING_MODEL,
        google_api_key=api_key,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline stages
# ═══════════════════════════════════════════════════════════════════════════


def load_pdf(pdf_path: Path) -> list:
    """Load a PDF file page-by-page using PyPDFLoader.

    Each page becomes one LangChain ``Document`` with ``metadata["page"]``.
    """
    if not pdf_path.exists():
        logger.error("PDF not found at: %s", pdf_path)
        raise FileNotFoundError(f"PDF not found at: {pdf_path}")

    logger.info("📄 Loading PDF from: %s", pdf_path)
    loader = PyPDFLoader(str(pdf_path))
    pages = loader.load()
    logger.info("   → Loaded %d page(s).", len(pages))
    return pages


def chunk_documents(
    documents: list,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list:
    """Split page-level documents into smaller chunks."""
    logger.info(
        "✂️  Chunking documents (size=%d, overlap=%d) …",
        chunk_size,
        chunk_overlap,
    )
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""],
    )
    chunks = splitter.split_documents(documents)
    logger.info("   → Produced %d chunk(s).", len(chunks))
    return chunks


def create_vector_store(
    chunks: list,
    embeddings: GoogleGenAIEmbeddings,
    persist_dir: Path,
) -> Chroma:
    """Embed chunks and persist them into a local ChromaDB collection."""
    logger.info("🧠 Generating Gemini embeddings and storing in ChromaDB …")
    logger.info("   → Persist directory : %s", persist_dir)
    logger.info("   → Collection name   : %s", COLLECTION_NAME)

    vector_store = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(persist_dir),
        collection_name=COLLECTION_NAME,
    )

    logger.info(
        "   → Successfully stored %d chunk(s) in collection '%s'.",
        len(chunks),
        COLLECTION_NAME,
    )
    return vector_store


def load_existing_store(
    embeddings: GoogleGenAIEmbeddings,
    persist_dir: Path,
) -> Chroma:
    """Load an already-persisted ChromaDB collection from disk."""
    logger.info("📂 Loading existing ChromaDB from: %s", persist_dir)

    vector_store = Chroma(
        persist_directory=str(persist_dir),
        embedding_function=embeddings,
        collection_name=COLLECTION_NAME,
    )

    count = vector_store._collection.count()
    logger.info(
        "   → Collection '%s' contains %d chunk(s).",
        COLLECTION_NAME,
        count,
    )
    return vector_store


def run_demo_query(vector_store: Chroma, query: str, k: int = TOP_K) -> None:
    """Execute a similarity search and pretty-print the results."""
    logger.info("🔍 Running demo similarity search (k=%d) …", k)
    logger.info('   Query: "%s"', query)

    results = vector_store.similarity_search(query, k=k)

    if not results:
        logger.warning("   ⚠ No results returned. Is the collection empty?")
        return

    print("\n" + "=" * 80)
    print(f'  TOP-{k} RESULTS for: "{query}"')
    print("=" * 80)

    for idx, doc in enumerate(results, start=1):
        page_number = doc.metadata.get("page", "N/A")
        source = doc.metadata.get("source", "N/A")
        print(
            f"\n--- Result #{idx}  |  Page: {page_number}  "
            f"|  Source: {source} ---"
        )
        print(doc.page_content)

    print("\n" + "=" * 80 + "\n")
    logger.info("✅ Demo query complete.")


# ═══════════════════════════════════════════════════════════════════════════
# Orchestrator
# ═══════════════════════════════════════════════════════════════════════════


def main() -> None:
    """Run the full ingestion pipeline or load an existing database."""
    logger.info("=" * 60)
    logger.info("  Phase 1 — Gemini Knowledge-Base Ingestion Pipeline")
    logger.info("=" * 60)

    # 1. Environment check
    api_key = _validate_environment()

    # 2. Embeddings instance
    embeddings = _get_embeddings(api_key)

    # 3. Decide: ingest from scratch or reuse existing DB
    if CHROMA_PERSIST_DIR.exists() and any(CHROMA_PERSIST_DIR.iterdir()):
        logger.info(
            "⏩ ChromaDB directory already exists at '%s'. "
            "Skipping ingestion to save API costs.",
            CHROMA_PERSIST_DIR,
        )
        vector_store = load_existing_store(embeddings, CHROMA_PERSIST_DIR)
    else:
        logger.info("🆕 No existing database found. Starting full pipeline …")

        # Step A — Load PDF
        pages = load_pdf(PDF_PATH)

        # Step B — Chunk
        chunks = chunk_documents(pages)

        # Step C — Embed & Store
        vector_store = create_vector_store(
            chunks, embeddings, CHROMA_PERSIST_DIR
        )

    # 4. Smoke-test: similarity search
    run_demo_query(vector_store, query=DEMO_QUERY, k=TOP_K)

    logger.info("🏁 Pipeline finished successfully.")


# ═══════════════════════════════════════════════════════════════════════════
# Entry-point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
        sys.exit(130)
    except FileNotFoundError as exc:
        logger.error("File error: %s", exc)
        sys.exit(1)
    except Exception:
        logger.exception("Unexpected error during ingestion.")
        sys.exit(1)
