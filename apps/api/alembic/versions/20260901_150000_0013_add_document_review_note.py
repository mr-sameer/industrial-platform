"""add document review note

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-01 15:00:00 UTC

Phase 1 of the admin document-verification review workflow (see
docs/adr/0029-module-3b-verification-and-identity.md decision #3, and
the ForgeX Product Audit's "Trust" finding). Adds exactly one nullable
column, `review_note`, to `verification_documents` — the place a
platform admin records why a document was rejected (or leaves blank on
approval). `verified_by`/`verified_at`/`status` already exist on this
table (migration 0004) and need no schema change; only new code paths
that set them are being added in later commits of this phase. No new
enum is introduced — DocumentStatus already has every value this
workflow needs (PENDING/VERIFIED/REJECTED/EXPIRED).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "verification_documents",
        sa.Column("review_note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("verification_documents", "review_note")
