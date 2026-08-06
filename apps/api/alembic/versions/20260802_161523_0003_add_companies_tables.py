"""add companies and company_members tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-02 16:15:23 UTC

Module 3A (Company Core). See docs/domain/03-core-entities.md and
docs/domain/04-entity-relationship-diagram.md for the business shape,
and docs/adr/0022 (CompanyRole naming) / docs/adr/0023 (scope
simplifications) for why this migration's columns look the way they do
(e.g. `industry` is a plain string, not a foreign key).

NOTE: as with migrations 0001/0002, do NOT explicitly call
`<enum>.create(...)` before `create_table` — the enum columns below
create their Postgres ENUM types implicitly as part of `create_table`,
and calling `.create()` first raises DuplicateObject (see migration
0001's note, which first documented this).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("legal_name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("industry", sa.String(length=120), nullable=True),
        sa.Column("website", sa.String(length=2048), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("year_established", sa.Integer(), nullable=True),
        sa.Column(
            "company_size",
            sa.Enum("1-10", "11-50", "51-200", "201-1000", "1000+", name="company_size"),
            nullable=True,
        ),
        sa.Column("gst_number", sa.String(length=32), nullable=True),
        sa.Column("country", sa.String(length=120), nullable=True),
        sa.Column("state", sa.String(length=120), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "active", "suspended", "archived", name="company_status"),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "verification_status",
            sa.Enum("unverified", "verified", name="company_verification_status"),
            nullable=False,
            server_default="unverified",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_companies_slug", "companies", ["slug"], unique=True)
    op.create_index("ix_companies_name", "companies", ["name"])
    op.create_index("ix_companies_industry", "companies", ["industry"])
    op.create_index("ix_companies_city", "companies", ["city"])
    op.create_index("ix_companies_country", "companies", ["country"])

    op.create_table(
        "company_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.Enum("owner", "admin", "editor", "viewer", name="company_role"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("pending", "active", "suspended", name="company_member_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "invited_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("company_id", "user_id", name="uq_company_members_company_user"),
    )
    op.create_index("ix_company_members_user_id", "company_members", ["user_id"])
    # Partial unique index — enforces "exactly one Owner per company"
    # (docs/domain/08-business-rules.md) at the database level.
    op.create_index(
        "uq_company_members_one_owner",
        "company_members",
        ["company_id"],
        unique=True,
        postgresql_where=sa.text("role = 'owner'"),
    )


def downgrade() -> None:
    op.drop_table("company_members")
    op.drop_table("companies")
    for enum_name in (
        "company_role",
        "company_member_status",
        "company_size",
        "company_status",
        "company_verification_status",
    ):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
