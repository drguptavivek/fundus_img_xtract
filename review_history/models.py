from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from auth.utils import utcnow
from models import Base


class ReviewSubmissionHistory(Base):
    """Append-only snapshot of one committed discrepancy-review submission."""

    __tablename__ = "review_submission_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    task_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    actor_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    before_json: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"))
    after_json: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    version_tokens_json: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql")
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_review_submission_history_task_recorded", "task_id", "recorded_at"),
    )
