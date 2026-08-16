"""add acquisition job and event tables

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-08 12:00:00 UTC

Module 5B (Industrial Data Acquisition Foundation). Exactly the two
tables docs/product/phase-5-industrial-data-acquisition-architecture.md's
Module 5B scope calls for: acquisition_jobs and acquisition_job_events.

Deliberately does NOT touch source_registry, raw_observations,
provenance_records, or data_conflicts — all four Module 5A tables are
frozen as approved. acquisition_jobs.source_id and
acquisition_job_events.raw_observation_id are new *outbound* foreign
keys pointing at those tables, not columns added to them.

Job execution in this phase is synchronous (no background task queue
exists yet) — started_at/completed_at are still independently nullable
columns, since validate_config can fail before started_at is ever set,
and a job can fail before completed_at reflects a real finish.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "acquisition_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collector_type", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "running", "succeeded", "failed", "cancelled",
                name="acquisition_job_status", native_enum=True,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("requested_scope", postgresql.JSONB(), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["source_registry.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_acquisition_jobs_source_id", "acquisition_jobs", ["source_id"])
    op.create_index("ix_acquisition_jobs_collector_type", "acquisition_jobs", ["collector_type"])

    op.create_table(
        "acquisition_job_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "outcome",
            sa.Enum("created", "skipped_duplicate", "failed", name="acquisition_event_outcome", native_enum=True),
            nullable=False,
        ),
        sa.Column("external_identifier", sa.String(length=2048), nullable=True),
        sa.Column("raw_observation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["acquisition_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["raw_observation_id"], ["raw_observations.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_acquisition_job_events_job_id", "acquisition_job_events", ["job_id"])


def downgrade() -> None:
    op.drop_table("acquisition_job_events")
    op.drop_table("acquisition_jobs")
    sa.Enum(name="acquisition_event_outcome").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="acquisition_job_status").drop(op.get_bind(), checkfirst=True)
