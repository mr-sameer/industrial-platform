"""add module 5e data quality fields

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-09 00:00:00 UTC

Module 5E (Data Quality & Verification Operations). The one
explicitly-sanctioned exception to "do not modify Module 5A" (per that
module's own approval ticket's "Most Important Architectural Decision"
section): extends provenance_status with three new values
(under_review, rejected, expired) and adds three new columns to
provenance_records (expires_at, review_note, verification_document_id).
Also adds one new column to product_specifications (risk_tier), per
the approved architecture's Section 12 (apply the same quality
architecture to Product/ProductSpecification, without mixing
Product/Offering semantics).

No new tables. The review queue is queries over the now-extended
provenance_records and the existing, unmodified data_conflicts table —
confirmed during architecture (Section 10) that no new persisted queue
table is needed, matching this phase's own "do not duplicate existing
provenance or conflict infrastructure" instruction.

Postgres requires ALTER TYPE ... ADD VALUE to run outside an explicit
transaction block in older versions; Alembic's default transactional
DDL handles this correctly on modern Postgres (16, this project's
target) via autocommit for this specific statement type — verified by
actually running the migration, not assumed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Postgres enum extension — cannot run inside the same transaction
    # as later statements that might use the new values, so this is
    # its own connection.execute with autocommit isolation.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE provenance_status ADD VALUE IF NOT EXISTS 'under_review'")
        op.execute("ALTER TYPE provenance_status ADD VALUE IF NOT EXISTS 'rejected'")
        op.execute("ALTER TYPE provenance_status ADD VALUE IF NOT EXISTS 'expired'")

    op.add_column("provenance_records", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("provenance_records", sa.Column("review_note", sa.Text(), nullable=True))
    op.add_column(
        "provenance_records", sa.Column("verification_document_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_provenance_records_verification_document_id",
        "provenance_records",
        "verification_documents",
        ["verification_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_provenance_records_verification_document_id",
        "provenance_records",
        ["verification_document_id"],
    )

    risk_tier_enum = sa.Enum("low", "medium", "high", name="risk_tier", native_enum=True)
    risk_tier_enum.create(op.get_bind())
    op.add_column(
        "product_specifications",
        sa.Column("risk_tier", risk_tier_enum, nullable=False, server_default="low"),
    )


def downgrade() -> None:
    op.drop_column("product_specifications", "risk_tier")
    sa.Enum(name="risk_tier").drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_provenance_records_verification_document_id", table_name="provenance_records")
    op.drop_constraint(
        "fk_provenance_records_verification_document_id", "provenance_records", type_="foreignkey"
    )
    op.drop_column("provenance_records", "verification_document_id")
    op.drop_column("provenance_records", "review_note")
    op.drop_column("provenance_records", "expires_at")

    # Postgres cannot remove enum values (no DROP VALUE) — downgrading
    # past this migration leaves provenance_status with the three
    # extra values present but unused by any code after downgrade.
    # This is a real, documented Postgres limitation, not an
    # oversight — the same constraint every Postgres-backed Alembic
    # project hits when adding enum values, and reverting it fully
    # would require recreating the type and every column that uses
    # it, which is a materially riskier operation than leaving three
    # harmless, unused labels in place.
