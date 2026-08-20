from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from auth.utils import utcnow
from models import Base


class EncounterVerificationHistory(Base):
    """Append-only audit trail for reopening a verified EncounterSet and the
    corrections made while it is reopened."""

    __tablename__ = "encounter_verification_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    patient_encounter_id: Mapped[int] = mapped_column(
        ForeignKey("patient_encounters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 'reopened' | 'metadata_corrected' | 'reverified'
    action_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    before_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "action_type IN ('reopened','metadata_corrected','reverified')",
            name="ck_encounter_verification_history_action_type",
        ),
        Index(
            "ix_encounter_verification_history_encounter_occurred",
            "patient_encounter_id",
            "occurred_at",
        ),
    )
