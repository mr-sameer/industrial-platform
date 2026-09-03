"""add product attribute evidence

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-03 09:00:00 UTC

Approved ProductAttribute Evidence design (read-only audit -> design ->
sign-off). One new table, product_attribute_evidence, extending the
Module 5A/5F evidence pattern to ProductAttribute (Phase 4B's EAV
specification-value table) — ZERO changes to provenance_records,
raw_observations, or data_conflicts, confirmed by this migration's own
content: every operation below is create_table/add_column/create_index
against a NEW table plus one additive, nullable column on
product_attributes.

product_attribute_evidence.extraction_method and .status reuse the
EXISTING extraction_method and provenance_status Postgres enum types
(create_type=False) — the same conceptual system Module 5A already
established, not a redefinition. Module 5E's status extensions
(under_review/rejected/expired) are therefore already available here
with zero further schema change.

product_attributes.latest_evidence_id is a nullable, additive
convenience pointer only ("which evidence row currently backs this
value") — existing rows (there are none in production data as of this
migration) read as NULL, meaning exactly what's true today: no
evidence trail recorded yet.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_attribute_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("specification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_observation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("value_observed", sa.Text(), nullable=False),
        sa.Column(
            "extraction_method",
            postgresql.ENUM(
                "manual",
                "rule_based",
                "ai_assisted",
                name="extraction_method",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "observed",
                "extracted",
                "verified",
                "claimed",
                "under_review",
                "rejected",
                "expired",
                name="provenance_status",
                create_type=False,
            ),
            nullable=False,
            server_default="observed",
        ),
        sa.Column("verified_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("conflict_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("verification_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("extraction_context", postgresql.JSONB(), nullable=True),
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
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["specification_id"], ["product_specifications.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["raw_observation_id"], ["raw_observations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["verified_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["conflict_id"], ["data_conflicts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["verification_document_id"], ["verification_documents.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "product_id",
            "specification_id",
            "raw_observation_id",
            name="uq_product_attribute_evidence_source",
        ),
    )
    op.create_index(
        "ix_product_attribute_evidence_product_id", "product_attribute_evidence", ["product_id"]
    )
    op.create_index(
        "ix_product_attribute_evidence_specification_id",
        "product_attribute_evidence",
        ["specification_id"],
    )
    op.create_index(
        "ix_product_attribute_evidence_raw_observation_id",
        "product_attribute_evidence",
        ["raw_observation_id"],
    )
    op.create_index(
        "ix_product_attribute_evidence_conflict_id",
        "product_attribute_evidence",
        ["conflict_id"],
    )

    op.add_column(
        "product_attributes",
        sa.Column("latest_evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_product_attributes_latest_evidence_id",
        "product_attributes",
        "product_attribute_evidence",
        ["latest_evidence_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_product_attributes_latest_evidence_id", "product_attributes", type_="foreignkey"
    )
    op.drop_column("product_attributes", "latest_evidence_id")
    op.drop_table("product_attribute_evidence")
    # extraction_method and provenance_status are NOT dropped — both are
    # Module 5A's existing types, reused here with create_type=False;
    # this migration never created either and must never drop them.
