"""add requirement intelligence foundation

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-18 09:00:00 UTC

Module 7A-1 (Requirement Intelligence foundation). Two new tables:
requirements, requirement_specification_criteria. ZERO changes to any
existing table — confirmed by this migration's own content: every
operation below is create_table/create_index, none touch an existing
table or column.

requirement_specification_criteria.specification_id references the
existing product_specifications table (Phase 4B, unmodified) — the
real, existing Industrial Taxonomy is reused, not duplicated.
requirement_specification_criteria.value is JSONB (a scalar for
eq/gte/lte, a 2-element array for range, an N-element array for in) —
see app/models/requirement.py's own docstring for why this was chosen
over a delimited string during this module's design review.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "requirements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_query", sa.Text(), nullable=False),
        sa.Column("product_category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("industry", sa.String(length=120), nullable=True),
        sa.Column("country", sa.String(length=120), nullable=True),
        sa.Column("state", sa.String(length=120), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("certifications", postgresql.JSONB(), nullable=True),
        sa.Column("quantity", sa.String(length=120), nullable=True),
        sa.Column("budget", sa.String(length=120), nullable=True),
        sa.Column("timeline", sa.String(length=120), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "submitted", "archived", name="requirement_status", native_enum=True),
            nullable=False,
            server_default="submitted",
        ),
        sa.Column("extraction_confidence", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["product_category_id"], ["product_categories.id"], ondelete="SET NULL"
        ),
    )
    op.create_index("ix_requirements_created_by", "requirements", ["created_by"])
    op.create_index(
        "ix_requirements_category_status", "requirements", ["product_category_id", "status"]
    )

    op.create_table(
        "requirement_specification_criteria",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("requirement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("specification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "operator",
            sa.Enum("eq", "gte", "lte", "range", "in", name="criterion_operator", native_enum=True),
            nullable=False,
        ),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["requirement_id"], ["requirements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["specification_id"], ["product_specifications.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "requirement_id", "specification_id", name="uq_requirement_criterion_specification"
        ),
    )
    op.create_index(
        "ix_requirement_specification_criteria_requirement_id",
        "requirement_specification_criteria",
        ["requirement_id"],
    )
    op.create_index(
        "ix_requirement_specification_criteria_specification_id",
        "requirement_specification_criteria",
        ["specification_id"],
    )


def downgrade() -> None:
    op.drop_table("requirement_specification_criteria")
    op.drop_table("requirements")
    sa.Enum(name="criterion_operator").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="requirement_status").drop(op.get_bind(), checkfirst=True)
