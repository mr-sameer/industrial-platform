"""add entity resolution candidate table

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-08 18:00:00 UTC

Module 5D (Data Normalization & Entity Resolution). Exactly one new
table: entity_resolution_candidates — the review-queue foundation.

Deliberately does NOT touch companies, source_registry,
raw_observations, provenance_records, data_conflicts,
acquisition_jobs, or acquisition_job_events — every one of those
remains exactly as Modules 3A/5A/5B left it.
entity_resolution_candidates.raw_observation_id and
.candidate_company_id are new *outbound* foreign keys, not columns
added to those tables.

This is the one new table this phase introduces, per its own
instruction to determine whether the existing schema could support the
workflow before adding anything — it could not: nothing in the
existing schema tracks "which Company (if any) does this raw
observation appear to be," a genuinely new question Module 5A/5B/5C's
tables were never designed to answer, since none of them existed prior
to a Company already being resolved.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "entity_resolution_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("raw_observation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "resolution_state",
            sa.Enum("new", "auto_match", "review_required", "no_match", name="resolution_state", native_enum=True),
            nullable=False,
        ),
        sa.Column("match_signals", postgresql.JSONB(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "decision",
            sa.Enum(
                "confirm_match", "reject_match", "create_new", name="resolution_decision", native_enum=True
            ),
            nullable=True,
        ),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["raw_observation_id"], ["raw_observations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_entity_resolution_candidates_raw_observation_id",
        "entity_resolution_candidates",
        ["raw_observation_id"],
    )
    op.create_index(
        "ix_entity_resolution_candidates_candidate_company_id",
        "entity_resolution_candidates",
        ["candidate_company_id"],
    )


def downgrade() -> None:
    op.drop_table("entity_resolution_candidates")
    sa.Enum(name="resolution_decision").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="resolution_state").drop(op.get_bind(), checkfirst=True)
