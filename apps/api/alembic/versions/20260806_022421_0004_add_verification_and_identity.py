"""add company verification, business info, branding, and social links

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-06 02:24:21 UTC

Module 3B (Company Verification & Industrial Identity). Purely additive
to Module 3A's schema — no existing column on `companies` is altered or
dropped, only new nullable columns added, plus two new tables.

NOTE (see migrations 0001/0002/0003): do NOT explicitly call
`<enum>.create(...)` before `add_column`/`create_table` for any of the
enum types below — each Enum-typed column creates its Postgres ENUM type
implicitly as part of its own DDL statement. Pre-creating raises
DuplicateObject, exactly as documented in migration 0001's note.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ARRAY_COLUMNS = [
    "core_values",
    "capabilities",
    "manufacturing_expertise",
    "secondary_industries",
    "product_categories",
    "manufacturing_categories",
    "export_categories",
    "ai_tags",
]


def upgrade() -> None:
    # ---- companies: business information ----
    # NOTE: unlike create_table (see migrations 0001-0003's notes),
    # add_column on an EXISTING table does NOT auto-create the enum type
    # it references — ALTER TABLE ... ADD COLUMN assumes the type already
    # exists. Confirmed by actually running this migration: omitting the
    # explicit .create() calls below raised
    # `psycopg.errors.UndefinedObject: type "legal_entity_type" does not
    # exist`. This is the opposite of create_table's behavior, and is
    # exactly why every enum-DDL decision in this codebase has been
    # verified by actually running the migration rather than assumed
    # from the previous rule.
    legal_entity_type_enum = sa.Enum(
        "private_limited",
        "llp",
        "proprietorship",
        "partnership",
        "public_limited",
        "government",
        "ngo",
        "other",
        name="legal_entity_type",
    )
    business_type_enum = sa.Enum("manufacturer", "trader", "both", name="business_type")
    legal_entity_type_enum.create(op.get_bind(), checkfirst=True)
    business_type_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "companies",
        sa.Column("legal_entity_type", legal_entity_type_enum, nullable=True),
    )
    op.add_column(
        "companies",
        sa.Column("business_type", business_type_enum, nullable=True),
    )
    op.add_column(
        "companies",
        sa.Column("export_capable", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("companies", sa.Column("pan", sa.String(length=16), nullable=True))
    op.add_column("companies", sa.Column("cin", sa.String(length=32), nullable=True))
    op.add_column("companies", sa.Column("msme_number", sa.String(length=32), nullable=True))
    op.add_column("companies", sa.Column("iec_number", sa.String(length=32), nullable=True))
    op.add_column("companies", sa.Column("tax_registration", sa.String(length=64), nullable=True))
    op.add_column(
        "companies", sa.Column("business_registration_date", sa.Date(), nullable=True)
    )

    # ---- companies: branding ----
    op.add_column("companies", sa.Column("logo_url", sa.String(length=2048), nullable=True))
    op.add_column(
        "companies", sa.Column("logo_thumbnail_url", sa.String(length=2048), nullable=True)
    )
    op.add_column(
        "companies", sa.Column("cover_image_url", sa.String(length=2048), nullable=True)
    )

    # ---- companies: description ----
    op.add_column(
        "companies", sa.Column("short_description", sa.String(length=500), nullable=True)
    )
    op.add_column("companies", sa.Column("mission", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("vision", sa.Text(), nullable=True))

    # ---- companies: array columns (description lists + industry classification) ----
    for column_name in _ARRAY_COLUMNS:
        op.add_column(
            "companies",
            sa.Column(column_name, postgresql.ARRAY(sa.String()), nullable=True),
        )
    op.add_column("companies", sa.Column("naics_sic_code", sa.String(length=16), nullable=True))

    # ---- verification_documents ----
    op.create_table(
        "verification_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_type",
            sa.Enum(
                "gst_certificate",
                "msme",
                "iso",
                "ce",
                "bis",
                "factory_license",
                "import_export_code",
                "business_registration",
                "other",
                name="document_type",
            ),
            nullable=False,
        ),
        sa.Column(
            "file_type", sa.Enum("pdf", "image", name="document_file_type"), nullable=False
        ),
        sa.Column("file_url", sa.String(length=2048), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "verified", "rejected", "expired", name="document_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "verified_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "superseded_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("verification_documents.id"),
            nullable=True,
        ),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "deleted_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
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
    op.create_index(
        "ix_verification_documents_company_id", "verification_documents", ["company_id"]
    )
    op.create_index(
        "ix_verification_documents_document_type", "verification_documents", ["document_type"]
    )

    # ---- company_social_links ----
    op.create_table(
        "company_social_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "platform",
            sa.Enum("linkedin", "youtube", "facebook", "instagram", "x", name="social_platform"),
            nullable=False,
        ),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "company_id", "platform", name="uq_company_social_links_company_platform"
        ),
    )


def downgrade() -> None:
    op.drop_table("company_social_links")
    op.drop_table("verification_documents")

    for column_name in reversed(_ARRAY_COLUMNS):
        op.drop_column("companies", column_name)
    op.drop_column("companies", "naics_sic_code")
    op.drop_column("companies", "vision")
    op.drop_column("companies", "mission")
    op.drop_column("companies", "short_description")
    op.drop_column("companies", "cover_image_url")
    op.drop_column("companies", "logo_thumbnail_url")
    op.drop_column("companies", "logo_url")
    op.drop_column("companies", "business_registration_date")
    op.drop_column("companies", "tax_registration")
    op.drop_column("companies", "iec_number")
    op.drop_column("companies", "msme_number")
    op.drop_column("companies", "cin")
    op.drop_column("companies", "pan")
    op.drop_column("companies", "export_capable")
    op.drop_column("companies", "business_type")
    op.drop_column("companies", "legal_entity_type")

    for enum_name in (
        "social_platform",
        "document_status",
        "document_file_type",
        "document_type",
        "business_type",
        "legal_entity_type",
    ):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
