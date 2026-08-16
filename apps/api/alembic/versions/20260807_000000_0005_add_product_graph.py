"""add industrial product graph tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-07 00:00:00 UTC

Phase 4B (Industrial Product Graph). Implements exactly the five
entities docs/product/phase-4a-industrial-product-graph-architecture.md
scoped for this phase: ProductCategory, Product, ProductSpecification,
ProductAttribute, Offering. See that document's Section 2 for why
Offering — not Product — is where company-specific facts (role, MOQ,
lead time, capacity, country, per-offering verification status) live.

Column choices this migration makes concrete, cross-referenced against
the architecture doc:
- ProductCategory is a single-parent tree (self-referencing FK,
  nullable at the root) — Section 4's deliberate trade-off; Industry is
  NOT a column here, it's free text directly on `products.industry`,
  matching `companies.industry`'s existing Module 3A pattern (see
  docs/adr/0023) rather than introducing a new linked entity, which is
  out of this phase's explicit "Only these" entity scope.
- ProductSpecification.enum_options is JSONB, not a child table — a
  small, category-author-defined list with no independent relational
  identity of its own.
- ProductAttribute.value is always a string regardless of the
  specification's declared datatype — the EAV trade-off the
  architecture doc names explicitly in its self-review (schema
  flexibility over database-level type safety); type enforcement
  happens in the service layer, not the schema.

NOTE: as with migrations 0001–0003 (not 0004's `add_column` case — see
that migration's own note on why `add_column` needs an explicit
`<enum>.create()` call first, which `create_table` does NOT), every
enum column below creates its Postgres ENUM type implicitly as part of
`create_table`. Do not call `.create()` first here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["parent_id"], ["product_categories.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("slug", name="uq_product_categories_slug"),
    )
    op.create_index("ix_product_categories_slug", "product_categories", ["slug"])
    op.create_index("ix_product_categories_parent_id", "product_categories", ["parent_id"])

    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("product_family", sa.String(length=255), nullable=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("industry", sa.String(length=120), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "published", "archived", name="product_status", native_enum=True),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["category_id"], ["product_categories.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("slug", name="uq_products_slug"),
    )
    op.create_index("ix_products_slug", "products", ["slug"])
    op.create_index("ix_products_category_id", "products", ["category_id"])
    op.create_index("ix_products_industry", "products", ["industry"])

    op.create_table(
        "product_specifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("unit", sa.String(length=40), nullable=True),
        sa.Column(
            "datatype",
            sa.Enum("number", "text", "enum", "boolean", "range", name="specification_datatype", native_enum=True),
            nullable=False,
        ),
        sa.Column("enum_options", postgresql.JSONB(), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["category_id"], ["product_categories.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_product_specifications_category_id", "product_specifications", ["category_id"])

    op.create_table(
        "product_attributes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("specification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("value", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["specification_id"], ["product_specifications.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("product_id", "specification_id", name="uq_product_attribute"),
    )
    op.create_index("ix_product_attributes_product_id", "product_attributes", ["product_id"])
    op.create_index("ix_product_attributes_specification_id", "product_attributes", ["specification_id"])

    op.create_table(
        "offerings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "manufacturer",
                "supplier",
                "distributor",
                "exporter",
                "service_provider",
                name="offering_role",
                native_enum=True,
            ),
            nullable=False,
        ),
        sa.Column("moq", sa.String(length=120), nullable=True),
        sa.Column("lead_time", sa.String(length=120), nullable=True),
        sa.Column("capacity", sa.String(length=120), nullable=True),
        sa.Column("country", sa.String(length=120), nullable=True),
        sa.Column(
            "verification_status",
            sa.Enum("unverified", "verified", name="offering_verification_status", native_enum=True),
            nullable=False,
            server_default="unverified",
        ),
        sa.Column(
            "status",
            sa.Enum("active", "inactive", name="offering_status", native_enum=True),
            nullable=False,
            server_default="active",
        ),
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
        sa.UniqueConstraint("company_id", "product_id", "role", name="uq_offering_company_product_role"),
    )
    op.create_index("ix_offerings_company_id", "offerings", ["company_id"])
    op.create_index("ix_offerings_product_id", "offerings", ["product_id"])
    op.create_index("ix_offerings_country", "offerings", ["country"])


def downgrade() -> None:
    op.drop_table("offerings")
    op.drop_table("product_attributes")
    op.drop_table("product_specifications")
    op.drop_table("products")
    op.drop_table("product_categories")
    # Explicit enum drops — create_table's implicit enum creation
    # doesn't get automatically undone by drop_table alone.
    sa.Enum(name="offering_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="offering_verification_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="offering_role").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="specification_datatype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="product_status").drop(op.get_bind(), checkfirst=True)
