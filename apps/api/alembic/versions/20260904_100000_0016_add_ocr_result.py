"""add ocr result

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-04 10:00:00 UTC

Approved OCR Architecture Design Proposal (design -> refinement A/B ->
sign-off) — V1 data model + OCR result foundation only, no OCR engine,
no rendering engine, no table/region extraction. One new table,
ocr_results, plus one additive nullable column on
product_attribute_evidence — ZERO changes to raw_observations,
provenance_records, product_attributes, data_conflicts, or any enum
type, confirmed by this migration's own content.

ocr_results.raw_observation_id is RESTRICT, matching every other FK
into raw_observations in this schema (product_attribute_evidence's own
raw_observation_id, provenance_records'): an OCRResult is always a
transformation of an existing RawObservation, never deletable out from
under one that's referenced.

product_attribute_evidence's original 3-column
uq_product_attribute_evidence_source (product_id, specification_id,
raw_observation_id) is replaced by two partial unique indexes rather
than widened in place — see app.models.product_attribute_evidence's
own "OCR foundation" docstring for the full reasoning. The
ocr_result_id IS NULL index is byte-for-byte the same constraint the
original enforced, scoped to rows that don't involve OCR (i.e. every
row that existed before this migration, and every non-OCR row created
after it) — this migration does not change what was previously
uniquely enforced for those rows, only adds a second, independent
uniqueness rule for the new ocr_result_id IS NOT NULL case.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ocr_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("raw_observation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("confidence_detail", postgresql.JSONB(), nullable=True),
        sa.Column("engine_name", sa.String(length=120), nullable=False),
        sa.Column("engine_version", sa.String(length=60), nullable=False),
        sa.Column("render_dpi", sa.Integer(), nullable=False),
        sa.Column("render_params", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["raw_observation_id"], ["raw_observations.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index("ix_ocr_results_raw_observation_id", "ocr_results", ["raw_observation_id"])
    op.create_index(
        "ix_ocr_results_raw_observation_page",
        "ocr_results",
        ["raw_observation_id", "page_number"],
    )

    op.add_column(
        "product_attribute_evidence",
        sa.Column("ocr_result_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_product_attribute_evidence_ocr_result_id",
        "product_attribute_evidence",
        "ocr_results",
        ["ocr_result_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_product_attribute_evidence_ocr_result_id",
        "product_attribute_evidence",
        ["ocr_result_id"],
    )

    op.drop_constraint(
        "uq_product_attribute_evidence_source",
        "product_attribute_evidence",
        type_="unique",
    )
    op.create_index(
        "uq_pae_source_manual",
        "product_attribute_evidence",
        ["product_id", "specification_id", "raw_observation_id"],
        unique=True,
        postgresql_where=sa.text("ocr_result_id IS NULL"),
    )
    op.create_index(
        "uq_pae_source_ocr",
        "product_attribute_evidence",
        ["product_id", "specification_id", "raw_observation_id", "ocr_result_id"],
        unique=True,
        postgresql_where=sa.text("ocr_result_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_pae_source_ocr", table_name="product_attribute_evidence")
    op.drop_index("uq_pae_source_manual", table_name="product_attribute_evidence")
    op.create_unique_constraint(
        "uq_product_attribute_evidence_source",
        "product_attribute_evidence",
        ["product_id", "specification_id", "raw_observation_id"],
    )

    op.drop_index(
        "ix_product_attribute_evidence_ocr_result_id", table_name="product_attribute_evidence"
    )
    op.drop_constraint(
        "fk_product_attribute_evidence_ocr_result_id",
        "product_attribute_evidence",
        type_="foreignkey",
    )
    op.drop_column("product_attribute_evidence", "ocr_result_id")

    op.drop_index("ix_ocr_results_raw_observation_page", table_name="ocr_results")
    op.drop_index("ix_ocr_results_raw_observation_id", table_name="ocr_results")
    op.drop_table("ocr_results")
