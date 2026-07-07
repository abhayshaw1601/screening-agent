"""
resume_parser.py — PDF skill extraction utility.

Parses raw PDF bytes using pypdf, then matches text against a curated
list of tech keywords to produce a deduplicated skill list.
"""

from __future__ import annotations

import io
import logging
import re

from pypdf import PdfReader

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Curated keyword list (case-insensitive matching)
# ---------------------------------------------------------------------------
TECH_KEYWORDS: list[str] = [
    # Languages
    "Python", "JavaScript", "TypeScript", "Java", "C++", "C#", "Go", "Rust",
    "Kotlin", "Swift", "Ruby", "PHP", "Scala", "R",
    # Web frameworks
    "FastAPI", "Django", "Flask", "Express", "Next.js", "React", "Angular",
    "Vue", "Svelte", "Spring Boot", "NestJS",
    # Data / ML
    "PyTorch", "TensorFlow", "Keras", "Scikit-learn", "Pandas", "NumPy",
    "Hugging Face", "Transformers", "LangChain", "LangGraph", "OpenAI",
    "LLM", "RAG", "NLP", "Computer Vision", "Deep Learning",
    "Machine Learning",
    # Databases
    "SQL", "PostgreSQL", "MySQL", "SQLite", "MongoDB", "Redis", "Elasticsearch",
    "DynamoDB", "Cassandra", "Neo4j",
    # Cloud / DevOps
    "AWS", "GCP", "Azure", "Docker", "Kubernetes", "Terraform", "CI/CD",
    "GitHub Actions", "Jenkins", "Linux",
    # Tools / Misc
    "Git", "REST", "GraphQL", "gRPC", "Kafka", "RabbitMQ", "Celery",
    "Airflow", "Spark", "Hadoop",
]

# Pre-compile patterns: word-boundary match, case insensitive
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE), kw)
    for kw in TECH_KEYWORDS
]


def extract_skills_from_pdf(file_bytes: bytes) -> list[str]:
    """Extract tech skills from raw PDF bytes.

    Parameters
    ----------
    file_bytes : bytes
        Raw binary content of the uploaded PDF file.

    Returns
    -------
    list[str]
        Deduplicated list of matched skill keywords, preserving the
        canonical casing from ``TECH_KEYWORDS``.

    Raises
    ------
    ValueError
        If the PDF cannot be read or contains no extractable text.
    """
    logger.info("📄 Parsing PDF for skill extraction …")

    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except Exception as exc:
        logger.error("Failed to parse PDF: %s", exc)
        raise ValueError("Uploaded file is not a valid PDF.") from exc

    # Concatenate all page text
    full_text = "\n".join(
        page.extract_text() or "" for page in reader.pages
    )

    if not full_text.strip():
        logger.warning("PDF contains no extractable text.")
        raise ValueError("PDF contains no extractable text.")

    logger.info("   → Extracted %d characters from %d page(s).",
                len(full_text), len(reader.pages))

    # Match keywords
    found: list[str] = []
    seen: set[str] = set()
    for pattern, canonical in _PATTERNS:
        if canonical.lower() not in seen and pattern.search(full_text):
            found.append(canonical)
            seen.add(canonical.lower())

    logger.info("   → Matched %d skill(s): %s", len(found), found)
    return found
