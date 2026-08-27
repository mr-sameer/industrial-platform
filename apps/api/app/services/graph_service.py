"""
Graph service — Module 5F. Orchestrates Factory/Capability creation,
relationship creation/verification/rejection, manual conflict
flagging, and the unified query layer combining graph_relationships
with Offering-derived edges.

DATA TRUST RULE: VERIFIED is only ever reachable through
verify_relationship below — never a side effect of creation, never set
by AI-assisted extraction (none exists in this phase — no AI import
anywhere in this file).

CONFLICT DETECTION — A DELIBERATE, DOCUMENTED SCOPE DECISION: unlike
Module 5A's field-level conflict detection (a simple string
inequality), an edge's "disagreement" has no equally simple automatic
definition — a company genuinely can own multiple factories or have
multiple capabilities, so two relationship rows sharing a
subject+relationship_type are not inherently a conflict. Rather than
build a fragile, likely-wrong automatic heuristic, this phase
implements REAL, MANUAL conflict flagging instead
(flag_relationship_conflict) — a human reviewer explicitly links two
specific relationship rows as conflicting, creating a genuine
DataConflict (Module 5A, reused unchanged). This is honestly not the
same as Module 5A's automatic field-level detection, and this module's
own completion report states that distinction directly.
"""

import math
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capability import Capability
from app.models.company import Company
from app.models.data_conflict import ConflictStatus, DataConflict
from app.models.factory import Factory
from app.models.graph_relationship import GraphEntityType, GraphRelationship, RelationshipType
from app.models.offering import Offering, OfferingRole
from app.models.product import Product
from app.models.product_category import ProductCategory
from app.models.provenance_record import ProvenanceStatus
from app.schemas.graph import (
    CapabilityCreate,
    FactoryCreate,
    GraphRelationshipCreate,
    OfferingEdgePublic,
)
from app.services import audit_service


class InvalidRelationshipError(Exception):
    pass


class RelationshipNotUnderReviewableStateError(Exception):
    pass


class CompanyNotFoundError(Exception):
    pass


# --------------------------------------------------------------------
# Factory
# --------------------------------------------------------------------


async def create_factory(db: AsyncSession, payload: FactoryCreate) -> Factory:
    company_result = await db.execute(select(Company.id).where(Company.id == payload.company_id))
    if company_result.scalar_one_or_none() is None:
        raise CompanyNotFoundError(str(payload.company_id))

    factory = Factory(
        company_id=payload.company_id,
        name=payload.name,
        country=payload.country,
        state=payload.state,
        city=payload.city,
    )
    db.add(factory)
    await db.commit()
    await db.refresh(factory)
    return factory


async def get_factory(db: AsyncSession, factory_id: uuid.UUID) -> Factory | None:
    result = await db.execute(select(Factory).where(Factory.id == factory_id))
    return result.scalar_one_or_none()


async def list_factories_for_company(db: AsyncSession, company_id: uuid.UUID) -> list[Factory]:
    result = await db.execute(select(Factory).where(Factory.company_id == company_id))
    return list(result.scalars().all())


# --------------------------------------------------------------------
# Capability
# --------------------------------------------------------------------


async def create_capability(db: AsyncSession, payload: CapabilityCreate) -> Capability:
    existing = await db.execute(select(Capability).where(Capability.name == payload.name))
    found = existing.scalar_one_or_none()
    if found is not None:
        return found  # idempotent — the controlled vocabulary has no duplicate names

    capability = Capability(name=payload.name)
    db.add(capability)
    await db.commit()
    await db.refresh(capability)
    return capability


async def list_capabilities(db: AsyncSession) -> list[Capability]:
    result = await db.execute(select(Capability).order_by(Capability.name))
    return list(result.scalars().all())


async def get_capability(db: AsyncSession, capability_id: uuid.UUID) -> Capability | None:
    result = await db.execute(select(Capability).where(Capability.id == capability_id))
    return result.scalar_one_or_none()


async def sync_company_capabilities_from_graph(
    db: AsyncSession, company: Company, *, triggered_by: uuid.UUID
) -> Company:
    """
    Module 8C — the explicit, human-triggered bridge between the
    Capability/GraphRelationship graph (this module) and
    Company.capabilities (Module 3B's plain string array) — closes the
    exact gap app.services.evidence_service's own docstring flags as
    "distinct, currently-unsynced." Never automatic, never a side
    effect of verify_relationship — a reviewer must call this
    deliberately, matching apply_reviewed_field_to_company's own
    "never automatic" rule for the field-level equivalent.

    Derives strictly from VERIFIED HAS_CAPABILITY relationships for
    this company — OBSERVED/EXTRACTED/CLAIMED/UNDER_REVIEW/REJECTED/
    EXPIRED relationships are never a source, checked directly in the
    query below, not filtered after the fact.

    Append-only, never a destructive replace: existing
    Company.capabilities entries — including any manually entered
    value with no backing graph relationship at all — are preserved
    untouched. Only capability names not already present (exact,
    case-sensitive match) are appended.

    Idempotent: a GraphRelationship, once VERIFIED, has no "unverify"
    path anywhere in this codebase (reject_relationship explicitly
    refuses to touch an already-VERIFIED row), so the verified-capability
    set for a company only ever grows. Repeated calls with no new
    verified relationships since the last sync are true no-ops — no
    commit, no audit event — mirroring create_capability/
    create_relationship's own idempotent-return pattern above.

    Never touches Company.status or Company.verification_status —
    neither is referenced anywhere in this function; verification_status
    is written exclusively by
    verification_score_service.sync_legacy_verification_status, a
    separate, unmodified code path.
    """
    result = await db.execute(
        select(Capability.name)
        .join(GraphRelationship, GraphRelationship.capability_object_id == Capability.id)
        .where(
            GraphRelationship.company_subject_id == company.id,
            GraphRelationship.relationship_type == RelationshipType.HAS_CAPABILITY,
            GraphRelationship.status == ProvenanceStatus.VERIFIED,
        )
    )
    verified_names = list(result.scalars().all())

    existing = list(company.capabilities or [])
    existing_set = set(existing)
    added: list[str] = []
    for name in verified_names:
        if name not in existing_set and name not in added:
            added.append(name)

    if not added:
        return company

    company.capabilities = existing + added
    await db.commit()
    await db.refresh(company)
    await audit_service.log_event(
        db,
        "company_capabilities_synced",
        user_id=str(triggered_by),
        metadata={
            "company_id": str(company.id),
            "added": added,
            "resulting_capabilities": company.capabilities,
        },
    )
    return company


# --------------------------------------------------------------------
# Relationships
# --------------------------------------------------------------------


async def create_relationship(
    db: AsyncSession, payload: GraphRelationshipCreate
) -> GraphRelationship:
    """
    Idempotent on the (company_subject_id, relationship_type,
    object_type, object_id) triple — a second, identical claim returns
    the existing row rather than creating a duplicate.
    """
    company_result = await db.execute(
        select(Company.id).where(Company.id == payload.company_subject_id)
    )
    if company_result.scalar_one_or_none() is None:
        raise CompanyNotFoundError(str(payload.company_subject_id))

    if payload.object_type == GraphEntityType.FACTORY:
        if payload.factory_object_id is None:
            raise InvalidRelationshipError(
                "factory_object_id is required when object_type is 'factory'."
            )
        object_filter = GraphRelationship.factory_object_id == payload.factory_object_id
    elif payload.object_type == GraphEntityType.CAPABILITY:
        if payload.capability_object_id is None:
            raise InvalidRelationshipError(
                "capability_object_id is required when object_type is 'capability'."
            )
        object_filter = GraphRelationship.capability_object_id == payload.capability_object_id
    else:
        raise InvalidRelationshipError(f"Unsupported object_type: {payload.object_type.value}")

    existing_result = await db.execute(
        select(GraphRelationship).where(
            GraphRelationship.company_subject_id == payload.company_subject_id,
            GraphRelationship.relationship_type == payload.relationship_type,
            GraphRelationship.object_type == payload.object_type,
            object_filter,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        return existing

    relationship = GraphRelationship(
        subject_type=GraphEntityType.COMPANY,
        company_subject_id=payload.company_subject_id,
        relationship_type=payload.relationship_type,
        object_type=payload.object_type,
        factory_object_id=payload.factory_object_id,
        capability_object_id=payload.capability_object_id,
        status=payload.status,
        confidence=payload.confidence,
        raw_observation_id=payload.raw_observation_id,
    )
    db.add(relationship)
    await db.commit()
    await db.refresh(relationship)
    return relationship


async def get_relationship(
    db: AsyncSession, relationship_id: uuid.UUID
) -> GraphRelationship | None:
    result = await db.execute(
        select(GraphRelationship).where(GraphRelationship.id == relationship_id)
    )
    return result.scalar_one_or_none()


async def list_relationships_for_company(
    db: AsyncSession, company_id: uuid.UUID
) -> list[GraphRelationship]:
    result = await db.execute(
        select(GraphRelationship).where(GraphRelationship.company_subject_id == company_id)
    )
    return list(result.scalars().all())


async def verify_relationship(
    db: AsyncSession, relationship: GraphRelationship, *, verified_by: uuid.UUID
) -> GraphRelationship:
    """THE only function that can set status=VERIFIED for a
    relationship — mirrors provenance_service.verify_provenance_record
    exactly (Module 5A, unchanged), applied to an edge."""
    if relationship.status == ProvenanceStatus.VERIFIED:
        raise RelationshipNotUnderReviewableStateError("This relationship is already verified.")
    relationship.status = ProvenanceStatus.VERIFIED
    relationship.verified_by = verified_by
    relationship.verified_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(relationship)
    return relationship


async def reject_relationship(
    db: AsyncSession, relationship: GraphRelationship, *, reviewer_id: uuid.UUID, note: str
) -> GraphRelationship:
    if relationship.status in (ProvenanceStatus.VERIFIED, ProvenanceStatus.REJECTED):
        raise RelationshipNotUnderReviewableStateError(
            f"Cannot reject a relationship in status {relationship.status.value!r}."
        )
    relationship.status = ProvenanceStatus.REJECTED
    relationship.review_note = note
    relationship.verified_by = reviewer_id
    relationship.verified_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(relationship)
    return relationship


async def flag_relationship_conflict(
    db: AsyncSession, relationship_a: GraphRelationship, relationship_b: GraphRelationship
) -> DataConflict:
    """Manual conflict flagging — see this module's own docstring for
    why this is a deliberate, honest alternative to automatic
    detection. Reuses DataConflict (Module 5A) exactly as field-level
    conflicts do."""
    conflict = DataConflict(
        company_id=relationship_a.company_subject_id,
        field_name=f"relationship:{relationship_a.relationship_type.value}",
        status=ConflictStatus.OPEN,
    )
    db.add(conflict)
    await db.flush()

    relationship_a.conflict_id = conflict.id
    relationship_b.conflict_id = conflict.id
    await db.commit()
    await db.refresh(conflict)
    return conflict


# --------------------------------------------------------------------
# Unified query layer (architecture Section 19)
# --------------------------------------------------------------------


_ROLE_TO_RELATIONSHIP = {
    "manufacturer": "manufactures",
    "supplier": "supplies",
    "distributor": "distributes",
    "exporter": "exports",
    "service_provider": "provides_service_for",
}


async def get_offering_edges_for_company(
    db: AsyncSession, company_id: uuid.UUID
) -> list[OfferingEdgePublic]:
    """Offering (Module 4B, unmodified) already IS the graph edge for
    manufactures/supplies/distributes/exports/provides_service_for —
    read directly, never duplicated into graph_relationships."""
    result = await db.execute(select(Offering).where(Offering.company_id == company_id))
    return [
        OfferingEdgePublic(
            offering_id=o.id,
            company_id=o.company_id,
            product_id=o.product_id,
            relationship_type=_ROLE_TO_RELATIONSHIP[o.role.value],
            moq=o.moq,
            lead_time=o.lead_time,
            capacity=o.capacity,
            country=o.country,
            status=o.status.value,
        )
        for o in result.scalars().all()
    ]


async def find_manufacturers_of_product(db: AsyncSession, product_id: uuid.UUID) -> list[uuid.UUID]:
    """'Which companies manufacture Product X.'"""
    result = await db.execute(
        select(Offering.company_id).where(
            Offering.product_id == product_id, Offering.role == OfferingRole.MANUFACTURER
        )
    )
    return list(result.scalars().all())


async def find_distributors_of_product_in_country(
    db: AsyncSession, product_id: uuid.UUID, country: str
) -> list[uuid.UUID]:
    """'Find distributors of Product X in Delhi' — uses Offering.country
    directly (architecture Section 9's own conclusion: no separate
    Location entity needed for this MVP's actual query needs)."""
    result = await db.execute(
        select(Offering.company_id).where(
            Offering.product_id == product_id,
            Offering.role == OfferingRole.DISTRIBUTOR,
            Offering.country == country,
        )
    )
    return list(result.scalars().all())


async def find_companies_by_capability(
    db: AsyncSession,
    capability_id: uuid.UUID,
    *,
    city: str | None = None,
    verified_only: bool = False,
) -> list[uuid.UUID]:
    """'Find CNC manufacturers in Pune' / 'which companies have a
    verified CNC machining capability.'"""
    query = (
        select(GraphRelationship.company_subject_id)
        .join(Company, Company.id == GraphRelationship.company_subject_id)
        .where(
            GraphRelationship.relationship_type == RelationshipType.HAS_CAPABILITY,
            GraphRelationship.capability_object_id == capability_id,
        )
    )
    if city:
        query = query.where(Company.city == city)
    if verified_only:
        query = query.where(GraphRelationship.status == ProvenanceStatus.VERIFIED)
    result = await db.execute(query)
    return [cid for cid in result.scalars().all() if cid is not None]


async def traverse_company_offering_product_category(
    db: AsyncSession, company_id: uuid.UUID
) -> list[dict[str, object]]:
    """Company -> Offering -> Product -> Category."""
    query = (
        select(Offering, Product, ProductCategory)
        .join(Product, Product.id == Offering.product_id)
        .join(ProductCategory, ProductCategory.id == Product.category_id)
        .where(Offering.company_id == company_id)
    )
    result = await db.execute(query)
    return [
        {
            "offering_id": offering.id,
            "product_id": product.id,
            "product_name": product.name,
            "category_id": category.id,
            "category_name": category.name,
        }
        for offering, product, category in result.all()
    ]


def total_pages(total: int, page_size: int) -> int:
    return max(1, math.ceil(total / page_size))
