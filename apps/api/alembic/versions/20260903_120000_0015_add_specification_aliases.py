"""add specification aliases

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-03 12:00:00 UTC

Approved deterministic specification-extraction design (audit -> design
-> revision -> sign-off). One new table, specification_aliases — zero
changes to product_specifications, product_attribute_evidence, or any
other existing table, confirmed by this migration's own content: the
only operation below is create_table against a brand new table with a
foreign key to the existing product_specifications.id.

Deliberately not a JSONB column on product_specifications (that shape
was considered and rejected during design review — see
app.models.specification_alias's own docstring for the reasoning): a
dedicated table gives every alias its own identity and created_at,
consistent with this codebase's established convention for anything
that can be added incrementally, by different actors, over time
(RawObservation, ProvenanceRecord, ProductAttributeEvidence), rather
than the atomic-list-authored-once shape enum_options uses.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "specification_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("specification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alias", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["specification_id"], ["product_specifications.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("specification_id", "alias", name="uq_specification_alias"),
    )
    op.create_index(
        "ix_specification_aliases_specification_id",
        "specification_aliases",
        ["specification_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_specification_aliases_specification_id", table_name="specification_aliases")
    op.drop_table("specification_aliases")
