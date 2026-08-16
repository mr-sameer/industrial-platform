"""add provenance and source registry foundation

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-08 00:00:00 UTC

Module 5A (Provenance & Source Registry Foundation). Implements exactly
the four tables docs/product/phase-5-industrial-data-acquisition-architecture.md
scopes for this phase: source_registry (Section 3), raw_observations
(Section 5), provenance_records (Section 4/11), data_conflicts
(Section 14, detection/flagging only — no auto-resolution).

Deliberately does NOT touch companies, products, or any other existing
table — company_id/product_id on provenance_records and data_conflicts
are new *outbound* foreign keys pointing at those tables, not columns
added to them. Preserves Company/Product/Offering exactly as approved.

Column choices cross-referenced against the architecture doc:
- raw_observations carries no entity link at all (Section 6: raw
  collection precedes entity resolution) — only provenance_records and
  data_conflicts link to company_id/product_id, via a CHECK constraint
  ensuring exactly one is set (a real, referentially-integral answer to
  the "polymorphic association" problem, not a bare untyped UUID).
- provenance_records.status (observed/extracted/verified/claimed) is
  the ticket's core requirement — Section 11's four-way distinction.
  Nothing in this schema or the service layer that uses it ever
  transitions a row to 'verified' automatically; server_default is
  'observed'.
- The collection_method enum type is shared between source_registry
  and raw_observations — created once (source_registry's column,
  first in this migration) and referenced by name (create_type=False)
  for raw_observations' column, matching Postgres's requirement that a
  named enum TYPE only be created once even when used by multiple
  columns.

NOTE: matching migrations 0001-0003/0005's pattern — every other enum
column below creates its Postgres ENUM type implicitly as part of
create_table. Do not call .create() first for those.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_registry",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "source_class",
            sa.Enum(
                "company_owned",
                "public_government",
                "third_party_structured",
                "news_publication",
                "association_directory",
                "user_contribution",
                name="source_class",
                native_enum=True,
            ),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_url", sa.String(length=2048), nullable=True),
        sa.Column("reliability_weight", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column(
            "collection_method",
            sa.Enum(
                "manual",
                "api",
                "structured_file",
                "user_submission",
                "other",
                name="collection_method",
                native_enum=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "collection_policy_status",
            sa.Enum(
                "allowed",
                "restricted",
                "blocked",
                "pending_legal_review",
                name="collection_policy_status",
                native_enum=True,
            ),
            nullable=False,
            server_default="pending_legal_review",
        ),
        sa.Column("geographic_scope", sa.String(length=32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "raw_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_reference", sa.String(length=2048), nullable=True),
        sa.Column("raw_content", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        # Reuses the collection_method type created above — must NOT
        # create it again (Postgres does not allow a duplicate named
        # enum type), so create_type=False here.
        sa.Column(
            "collection_method_used",
            postgresql.ENUM(
                "manual",
                "api",
                "structured_file",
                "user_submission",
                "other",
                name="collection_method",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["source_registry.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_raw_observations_source_id", "raw_observations", ["source_id"])
    op.create_index("ix_raw_observations_content_hash", "raw_observations", ["content_hash"])

    op.create_table(
        "data_conflicts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("field_name", sa.String(length=120), nullable=False),
        sa.Column(
            "status",
            sa.Enum("open", "resolved", name="conflict_status", native_enum=True),
            nullable=False,
            server_default="open",
        ),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "(company_id IS NOT NULL AND product_id IS NULL) OR "
            "(company_id IS NULL AND product_id IS NOT NULL)",
            name="ck_data_conflict_exactly_one_entity",
        ),
    )
    op.create_index("ix_data_conflicts_company_id", "data_conflicts", ["company_id"])
    op.create_index("ix_data_conflicts_product_id", "data_conflicts", ["product_id"])
    op.create_index("ix_data_conflicts_field_name", "data_conflicts", ["field_name"])

    op.create_table(
        "provenance_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entity_type",
            sa.Enum("company", "product", name="provenance_entity_type", native_enum=True),
            nullable=False,
        ),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("field_name", sa.String(length=120), nullable=False),
        sa.Column("raw_observation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("value_observed", sa.Text(), nullable=False),
        sa.Column(
            "extraction_method",
            sa.Enum("manual", "rule_based", "ai_assisted", name="extraction_method", native_enum=True),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("observed", "extracted", "verified", "claimed", name="provenance_status", native_enum=True),
            nullable=False,
            server_default="observed",
        ),
        sa.Column("verified_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("conflict_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["raw_observation_id"], ["raw_observations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verified_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["conflict_id"], ["data_conflicts.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "(company_id IS NOT NULL AND product_id IS NULL) OR "
            "(company_id IS NULL AND product_id IS NOT NULL)",
            name="ck_provenance_exactly_one_entity",
        ),
    )
    op.create_index("ix_provenance_records_company_id", "provenance_records", ["company_id"])
    op.create_index("ix_provenance_records_product_id", "provenance_records", ["product_id"])
    op.create_index("ix_provenance_records_field_name", "provenance_records", ["field_name"])
    op.create_index("ix_provenance_records_raw_observation_id", "provenance_records", ["raw_observation_id"])
    op.create_index("ix_provenance_records_conflict_id", "provenance_records", ["conflict_id"])


def downgrade() -> None:
    op.drop_table("provenance_records")
    op.drop_table("data_conflicts")
    op.drop_table("raw_observations")
    op.drop_table("source_registry")
    sa.Enum(name="provenance_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="extraction_method").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="provenance_entity_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="conflict_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="collection_method").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="collection_policy_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="source_class").drop(op.get_bind(), checkfirst=True)
