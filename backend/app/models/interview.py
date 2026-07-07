"""
interview.py — SQLAlchemy ORM models for interview persistence.

Tables:
    InterviewSession — one row per screening interview.
    InterviewLog     — one row per question/answer exchange within a session.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class InterviewSession(Base):
    """Represents a single interview screening session."""

    __tablename__ = "interview_sessions"

    id = Column(String(36), primary_key=True, index=True)
    role = Column(String(100), nullable=False)
    skills = Column(Text, nullable=False, default="")          # comma-separated
    status = Column(
        String(20),
        nullable=False,
        default="ACTIVE",                                       # ACTIVE | COMPLETED
    )
    current_step = Column(Integer, nullable=False, default=0)
    max_questions = Column(Integer, nullable=False, default=5)
    evaluation_summary = Column(Text, nullable=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationship — cascade delete logs when session is removed
    logs = relationship(
        "InterviewLog",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="InterviewLog.id",
    )


class InterviewLog(Base):
    """One question/answer turn inside a session."""

    __tablename__ = "interview_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        String(36),
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    timestamp = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    session = relationship("InterviewSession", back_populates="logs")
