"""add search telemetry

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-20 09:00:00 UTC

Module 7B (Search Telemetry). Two new tables: search_events,
search_result_candidates. ZERO changes to any existing table —
confirmed by this migration's own content: every operation below is
create_table/create_index, none touch an existing table or column.

search_events.requirement_id and search_result_candidates.offering_id
both use ON DELETE SET NULL, not CASCADE — a search telemetry row is
an immutable historical fact (its own requirement_snapshot /
result_snapshot JSONB columns are the durable source of truth) that
must survive the later deletion of the Requirement/Offering it
referenced. No delete endpoint exists for either today; this is a
defensive, deliberate choice, not the default. created_by keeps the
CASCADE-from-users.id convention already used everywhere else in this
codebase (e.g. requirements.created_by) — that is the real privacy/
retention lever: deleting a user's account still removes their search
telemetry.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "search_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("requirement_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_query_text", sa.Text(), nullable=False),
        sa.Column("requirement_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("total_candidates_considered", sa.Integer(), nullable=False),
        sa.Column("more_candidates_may_exist", sa.Boolean(), nullable=False),
        sa.Column("excluded_for_hard_criteria", sa.Integer(), nullable=False),
        sa.Column("returned_count", sa.Integer(), nullable=False),
        sa.Column(
            "searched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["requirement_id"], ["requirements.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_search_events_requirement_id", "search_events", ["requirement_id"])
    op.create_index("ix_search_events_created_by", "search_events", ["created_by"])

    op.create_table(
        "search_result_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("search_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("offering_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("result_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["search_event_id"], ["search_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["offering_id"], ["offerings.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_search_result_candidates_search_event_id",
        "search_result_candidates",
        ["search_event_id"],
    )
    op.create_index(
        "ix_search_result_candidates_offering_id", "search_result_candidates", ["offering_id"]
    )


def downgrade() -> None:
    op.drop_table("search_result_candidates")
    op.drop_table("search_events")
