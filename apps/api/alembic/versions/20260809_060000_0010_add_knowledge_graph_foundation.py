"""add industrial knowledge graph foundation

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-09 06:00:00 UTC

Module 5F (Industrial Knowledge Graph). Three new tables: factories,
capabilities, graph_relationships. ZERO changes to provenance_records
or any other existing table — confirmed by this migration's own
content: every operation below is create_table/create_index, none
touch an existing table.

graph_relationships.status reuses the EXISTING provenance_status
Postgres enum type (create_type=False) rather than defining a new one
— the same conceptual system Module 5A already established, not a
redefinition. Module 5E's three status extensions
(under_review/rejected/expired, migration 0009) are therefore already
available to relationships with zero further schema change here.

Offering (Module 4B, unmodified) remains the graph edge for
manufactures/supplies/distributes/exports/provides_service_for —
graph_relationships only covers owns/operates (Company->Factory) and
has_capability (Company->Capability), the relationship types nothing
else in the existing schema already represents.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "factories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("country", sa.String(length=120), nullable=True),
        sa.Column("state", sa.String(length=120), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_factories_company_id", "factories", ["company_id"])

    op.create_table(
        "capabilities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "graph_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "subject_type",
            sa.Enum("company", "factory", "capability", name="graph_entity_type", native_enum=True),
            nullable=False,
        ),
        sa.Column("company_subject_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "relationship_type",
            sa.Enum("owns", "operates", "has_capability", name="relationship_type", native_enum=True),
            nullable=False,
        ),
        sa.Column(
            "object_type",
            postgresql.ENUM(
                "company", "factory", "capability", name="graph_entity_type", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("factory_object_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("capability_object_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("raw_observation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("verified_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("conflict_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_subject_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["factory_object_id"], ["factories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["capability_object_id"], ["capabilities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["raw_observation_id"], ["raw_observations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["verified_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["conflict_id"], ["data_conflicts.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "(subject_type = 'company' AND company_subject_id IS NOT NULL)",
            name="ck_graph_relationship_subject_is_company",
        ),
        sa.CheckConstraint(
            "(object_type = 'factory' AND factory_object_id IS NOT NULL AND capability_object_id IS NULL) OR "
            "(object_type = 'capability' AND capability_object_id IS NOT NULL AND factory_object_id IS NULL)",
            name="ck_graph_relationship_exactly_one_object",
        ),
    )
    op.create_index("ix_graph_relationships_company_subject_id", "graph_relationships", ["company_subject_id"])
    op.create_index("ix_graph_relationships_factory_object_id", "graph_relationships", ["factory_object_id"])
    op.create_index(
        "ix_graph_relationships_capability_object_id", "graph_relationships", ["capability_object_id"]
    )
    op.create_index("ix_graph_relationships_conflict_id", "graph_relationships", ["conflict_id"])


def downgrade() -> None:
    op.drop_table("graph_relationships")
    op.drop_table("capabilities")
    op.drop_table("factories")
    sa.Enum(name="relationship_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="graph_entity_type").drop(op.get_bind(), checkfirst=True)
    # provenance_status is NOT dropped — it's Module 5A's existing
    # type, reused here with create_type=False; this migration never
    # created it and must never drop it.
