"""
add users table

Revision ID: 0001
Revises:
Create Date: 2026-07-29 03:09:18 UTC

First real migration — Module 2 (Authentication). Creates the `users`
table backing app.models.user.User. No indexes beyond the unique email
index are added speculatively; add them when a real query pattern needs
one.

NOTE: the `user_role` Postgres ENUM type is created implicitly by
`create_table` below (SQLAlchemy auto-creates enum types referenced by a
column) — do NOT also call `user_role.create(...)` explicitly here, that
raises `DuplicateObject` since both would try to create the same type.
`downgrade()` DOES need an explicit `.drop()` though, since dropping the
table does not drop the enum type.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

user_role = postgresql.ENUM("admin", "analyst", "viewer", name="user_role")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            user_role,
            nullable=False,
            server_default="viewer",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    user_role.drop(op.get_bind(), checkfirst=True)
