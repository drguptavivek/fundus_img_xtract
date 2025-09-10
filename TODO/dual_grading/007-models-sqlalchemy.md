# SQLAlchemy Models — Draft Definitions (PEP 8/484)

Note: These are draft class definitions aligned with the project’s style. They are designed to be added to `models.py` with minimal collateral changes. All sessions must be explicitly closed (`with Session() as db:` where applicable in routes/services).

Imports used (shared with existing file):

```python
from sqlalchemy import (
    CheckConstraint, DateTime, Integer, String, ForeignKey,
    Boolean, Text, UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
```

Helper: reuse existing `utcnow` function from models.

## GradingTask

```python
class GradingTask(Base):
    __tablename__ = 'grading_tasks'

    id: Mapped[int] = mapped_column(primary_key=True)

    # Exactly one of these must be non-null
    encounter_file_id: Mapped[int | None] = mapped_column(ForeignKey('encounter_files.id'), nullable=True, index=True)
    direct_image_upload_id: Mapped[int | None] = mapped_column(ForeignKey('direct_image_uploads.id'), nullable=True, index=True)

    disease_id: Mapped[int] = mapped_column(ForeignKey('diseases.id'), nullable=False, index=True)
    # lab_unit_id is used strictly for grading assignment and queue scoping.
    # It does not redefine image identity; uniqueness is enforced across labs.
    lab_unit_id: Mapped[int] = mapped_column(ForeignKey('lab_units.id'), nullable=False, index=True)

    state: Mapped[str] = mapped_column(String(24), default='pending', nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships (no back_populates on existing models to avoid touching them)
    disease: Mapped['Disease'] = relationship('Disease')
    lab_unit: Mapped['LabUnit'] = relationship('LabUnit')
    encounter_file: Mapped['EncounterFile'] = relationship('EncounterFile')
    direct_image: Mapped['DirectImageUpload'] = relationship('DirectImageUpload')
    grades: Mapped[list['Grade']] = relationship('Grade', cascade="all, delete-orphan")
    consensus: Mapped['Consensus | None'] = relationship('Consensus', uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        # Ensure one and only one image reference is set
        CheckConstraint(
            "(encounter_file_id IS NOT NULL AND direct_image_upload_id IS NULL) OR "
            "(encounter_file_id IS NULL AND direct_image_upload_id IS NOT NULL)",
            name='ck_grading_task_either_encounter_or_direct'
        ),
        # Unique per image×disease across all lab units (enforces single task/gold standard globally).
        # SQLite treats NULLs as distinct; works with the one-of-two FK check above.
        UniqueConstraint('encounter_file_id', 'disease_id', name='uq_task_encounter_disease'),
        UniqueConstraint('direct_image_upload_id', 'disease_id', name='uq_task_direct_disease'),
        CheckConstraint(
            "state IN ('pending','resident_done','faculty_done','arbitration','final')",
            name='ck_task_state_valid'
        ),
        Index('ix_task_disease_lab_state', 'disease_id', 'lab_unit_id', 'state'),
    )
```

## Grade

```python
class Grade(Base):
    __tablename__ = 'grades'

    id: Mapped[int] = mapped_column(primary_key=True)

    task_id: Mapped[int] = mapped_column(ForeignKey('grading_tasks.id', ondelete='CASCADE'), nullable=False, index=True)
    grader_user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)

    # resident | faculty | arbitrator
    role_slot: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    # Normalized to master labels for the disease
    disease_grading_id: Mapped[int] = mapped_column(ForeignKey('disease_gradings.id'), nullable=False, index=True)

    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    task: Mapped['GradingTask'] = relationship('GradingTask')
    grader: Mapped['User'] = relationship('User')
    label: Mapped['DiseaseGrading'] = relationship('DiseaseGrading')

    __table_args__ = (
        CheckConstraint("role_slot IN ('resident','faculty','arbitrator')", name='ck_grade_role_slot_valid'),
        Index('ix_grade_task_slot', 'task_id', 'role_slot'),
        Index('ix_grade_user_slot', 'grader_user_id', 'role_slot'),
        # App enforces: one active grade per (task_id, grader_user_id, role_slot). If desired, add a UniqueConstraint here.
    )
```

## Consensus

```python
class Consensus(Base):
    __tablename__ = 'consensus'

    id: Mapped[int] = mapped_column(primary_key=True)

    task_id: Mapped[int] = mapped_column(ForeignKey('grading_tasks.id', ondelete='CASCADE'), nullable=False, unique=True)

    final_disease_grading_id: Mapped[int] = mapped_column(ForeignKey('disease_gradings.id'), nullable=False)

    method: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    decided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    task: Mapped['GradingTask'] = relationship('GradingTask')
    final_label: Mapped['DiseaseGrading'] = relationship('DiseaseGrading')
    decided_by: Mapped['User | None'] = relationship('User')

    __table_args__ = (
        CheckConstraint("method IN ('match','adjudication')", name='ck_consensus_method_valid'),
    )
```

## UserDiseaseUnitRole (grading eligibility matrix)

```python
class UserDiseaseUnitRole(Base):
    __tablename__ = 'user_disease_unit_role'

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey('diseases.id', ondelete='CASCADE'), nullable=False, index=True)
    lab_unit_id: Mapped[int] = mapped_column(ForeignKey('lab_units.id', ondelete='CASCADE'), nullable=False, index=True)

    can_grade_resident: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_grade_faculty: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_arbitrate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped['User'] = relationship('User')
    disease: Mapped['Disease'] = relationship('Disease')
    lab_unit: Mapped['LabUnit'] = relationship('LabUnit')

    __table_args__ = (
        UniqueConstraint('user_id', 'disease_id', 'lab_unit_id', name='uq_user_disease_unit_role'),
        CheckConstraint(
            '(can_grade_resident = 1) OR (can_grade_faculty = 1) OR (can_arbitrate = 1)',
            name='ck_user_dur_has_any_permission'
        ),
        Index('ix_user_dur_unit_disease', 'lab_unit_id', 'disease_id'),
        Index('ix_user_dur_user_active', 'user_id', 'active'),
    )
```

## AIGrade (optional)

```python
class AIGrade(Base):
    __tablename__ = 'ai_grades'

    id: Mapped[int] = mapped_column(primary_key=True)

    encounter_file_id: Mapped[int | None] = mapped_column(ForeignKey('encounter_files.id'), nullable=True, index=True)
    direct_image_upload_id: Mapped[int | None] = mapped_column(ForeignKey('direct_image_uploads.id'), nullable=True, index=True)

    disease_id: Mapped[int] = mapped_column(ForeignKey('diseases.id'), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)

    label_disease_grading_id: Mapped[int | None] = mapped_column(ForeignKey('disease_gradings.id'), nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    probabilities_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    inference_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    disease: Mapped['Disease'] = relationship('Disease')
    label: Mapped['DiseaseGrading'] = relationship('DiseaseGrading')

    __table_args__ = (
        CheckConstraint(
            "(encounter_file_id IS NOT NULL AND direct_image_upload_id IS NULL) OR "
            "(encounter_file_id IS NULL AND direct_image_upload_id IS NOT NULL)",
            name='ck_ai_grade_either_encounter_or_direct'
        ),
        UniqueConstraint('encounter_file_id', 'disease_id', 'model_name', 'model_version', 'run_id', name='uq_ai_encounter_model_run'),
        UniqueConstraint('direct_image_upload_id', 'disease_id', 'model_name', 'model_version', 'run_id', name='uq_ai_direct_model_run'),
    )
```

## Notes
- Do not modify existing global roles. Slot permissions are enforced via `UserDiseaseUnitRole` + `user_roles` at request time.
- Keep `ImageGrading` for legacy history if desired; new flows should write into `Grade` with normalized `disease_grading_id`.
- Consider adding lightweight helpers for slot checks and verification gating in services.
 - Do not mutate `lab_unit_id` on an existing task; reassignment across lab units is not allowed once created. A final task (state = `final`) represents the gold standard and must not be recreated or moved for the same image×disease in any lab.

