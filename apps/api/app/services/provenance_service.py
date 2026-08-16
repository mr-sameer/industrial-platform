"""
Provenance / Source Registry service layer — Module 5A. This is where
the architecture doc's Section 11 rule is actually enforced in code:
"Do not allow OBSERVED or EXTRACTED information to automatically
become VERIFIED." Every function that could plausibly touch `status`
is written so that VERIFIED is reachable only through
`verify_provenance_record` — never as a side effect of creation,
conflict detection, or any other operation in this file.
"""

import math
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_conflict import ConflictStatus, DataConflict
from app.models.product import Product
from app.models.provenance_record import ProvenanceRecord, ProvenanceStatus
from app.models.raw_observation import RawObservation
from app.models.source_registry import SourceRegistry
from app.schemas.provenance import (
    ProvenanceRecordCreate,
    RawObservationCreate,
    SourceRegistryCreate,
)


class SourceNotFoundError(Exception):
    pass


class RawObservationNotFoundError(Exception):
    pass


class AlreadyVerifiedError(Exception):
    """Raised when attempting to verify a record that's already verified
    — verification is a one-time, attributable action, not idempotent
    the way a plain status update would be."""


# ---- Source Registry ----


async def create_source(db: AsyncSession, payload: SourceRegistryCreate) -> SourceRegistry:
    source = SourceRegistry(
        name=payload.name,
        source_class=payload.source_class,
        description=payload.description,
        base_url=payload.base_url,
        reliability_weight=payload.reliability_weight,
        collection_method=payload.collection_method,
        geographic_scope=payload.geographic_scope,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


async def get_source(db: AsyncSession, source_id: uuid.UUID) -> SourceRegistry | None:
    result = await db.execute(select(SourceRegistry).where(SourceRegistry.id == source_id))
    return result.scalar_one_or_none()


async def list_sources(db: AsyncSession, *, active_only: bool = False) -> list[SourceRegistry]:
    query = select(SourceRegistry).order_by(SourceRegistry.name)
    if active_only:
        query = query.where(SourceRegistry.is_active.is_(True))
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_source(
    db: AsyncSession,
    source: SourceRegistry,
    *,
    description: str | None = None,
    reliability_weight: float | None = None,
    collection_policy_status: str | None = None,
    is_active: bool | None = None,
) -> SourceRegistry:
    if description is not None:
        source.description = description
    if reliability_weight is not None:
        source.reliability_weight = reliability_weight
    if collection_policy_status is not None:
        source.collection_policy_status = collection_policy_status  # type: ignore[assignment]
    if is_active is not None:
        source.is_active = is_active
    await db.commit()
    await db.refresh(source)
    return source


# ---- Raw Observations ----


async def create_raw_observation(db: AsyncSession, payload: RawObservationCreate) -> RawObservation:
    """
    Deliberately no update/delete counterpart anywhere in this file —
    raw observations are append-only per the architecture doc's
    Section 5. A repeated call with the same source_id+content_hash is
    not deduplicated automatically here (that idempotency check belongs
    to a future collector, which does not exist yet in this phase) —
    this function only guards that the referenced source is real.
    """
    source = await get_source(db, payload.source_id)
    if source is None:
        raise SourceNotFoundError(str(payload.source_id))

    observation = RawObservation(
        source_id=payload.source_id,
        external_reference=payload.external_reference,
        raw_content=payload.raw_content,
        content_hash=payload.content_hash,
        collection_method_used=payload.collection_method_used,
        collected_at=payload.collected_at,
    )
    db.add(observation)
    await db.commit()
    await db.refresh(observation)
    return observation


async def get_raw_observation(db: AsyncSession, observation_id: uuid.UUID) -> RawObservation | None:
    result = await db.execute(select(RawObservation).where(RawObservation.id == observation_id))
    return result.scalar_one_or_none()


# ---- Provenance Records ----


async def _entity_exists(db: AsyncSession, payload: ProvenanceRecordCreate) -> bool:
    if payload.entity_type.value == "company":
        from app.models.company import Company

        result = await db.execute(select(Company.id).where(Company.id == payload.company_id))
    else:
        result = await db.execute(select(Product.id).where(Product.id == payload.product_id))
    return result.scalar_one_or_none() is not None


async def create_provenance_record(
    db: AsyncSession, payload: ProvenanceRecordCreate
) -> tuple[ProvenanceRecord, DataConflict | None]:
    """
    Creates a provenance record — status is OBSERVED, EXTRACTED, or
    CLAIMED only, enforced already at the schema layer
    (ProvenanceRecordCreate.model_post_init) and re-affirmed here as a
    second, independent guard rather than trusting the schema alone.

    Also runs the Section 14 conflict-detection step: if an existing,
    non-conflicted provenance record already exists for the same
    (entity, field_name) with a *different* value_observed, a
    DataConflict is created and both records' conflict_id are set to
    point at it. This is detection and flagging only — nothing here
    picks a "winning" value or resolves anything automatically,
    matching the architecture doc's "never silently overwrite
    conflicting information."
    """
    if payload.status == ProvenanceStatus.VERIFIED:
        raise ValueError("status must not be 'verified' at creation — use verify_provenance_record")

    raw_observation = await get_raw_observation(db, payload.raw_observation_id)
    if raw_observation is None:
        raise RawObservationNotFoundError(str(payload.raw_observation_id))
    if not await _entity_exists(db, payload):
        entity_id = (
            payload.company_id if payload.entity_type.value == "company" else payload.product_id
        )
        raise ValueError(f"No {payload.entity_type.value} exists with id {entity_id}")

    now = datetime.now(UTC)
    record = ProvenanceRecord(
        entity_type=payload.entity_type,
        company_id=payload.company_id,
        product_id=payload.product_id,
        field_name=payload.field_name,
        raw_observation_id=payload.raw_observation_id,
        value_observed=payload.value_observed,
        extraction_method=payload.extraction_method,
        confidence=payload.confidence,
        status=payload.status,
        last_observed_at=now,
    )
    db.add(record)
    await db.flush()  # record.id needed before it can be referenced by a conflict

    conflict = await _detect_and_flag_conflict(db, record)

    await db.commit()
    await db.refresh(record)
    return record, conflict


async def _detect_and_flag_conflict(
    db: AsyncSession, record: ProvenanceRecord
) -> DataConflict | None:
    entity_column = (
        ProvenanceRecord.company_id
        if record.company_id is not None
        else ProvenanceRecord.product_id
    )
    entity_value = record.company_id if record.company_id is not None else record.product_id

    result = await db.execute(
        select(ProvenanceRecord).where(
            entity_column == entity_value,
            ProvenanceRecord.field_name == record.field_name,
            ProvenanceRecord.id != record.id,
            ProvenanceRecord.value_observed != record.value_observed,
        )
    )
    disagreeing_records = list(result.scalars().all())
    if not disagreeing_records:
        return None

    # Reuse an existing open conflict for this (entity, field) if one
    # already exists, rather than creating a second, redundant one.
    existing_conflict_id = next(
        (r.conflict_id for r in disagreeing_records if r.conflict_id is not None), None
    )
    if existing_conflict_id is not None:
        record.conflict_id = existing_conflict_id
        await db.flush()
        result2 = await db.execute(
            select(DataConflict).where(DataConflict.id == existing_conflict_id)
        )
        return result2.scalar_one()

    conflict = DataConflict(
        company_id=record.company_id,
        product_id=record.product_id,
        field_name=record.field_name,
        status=ConflictStatus.OPEN,
    )
    db.add(conflict)
    await db.flush()

    record.conflict_id = conflict.id
    for other in disagreeing_records:
        other.conflict_id = conflict.id
    await db.flush()
    return conflict


async def get_provenance_record(db: AsyncSession, record_id: uuid.UUID) -> ProvenanceRecord | None:
    result = await db.execute(select(ProvenanceRecord).where(ProvenanceRecord.id == record_id))
    return result.scalar_one_or_none()


async def list_provenance_for_entity(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    page: int,
    page_size: int,
) -> tuple[list[ProvenanceRecord], int]:
    """The lineage view — Section 6 (Data Lineage) — every provenance
    record ever created for one Company or Product, in one query."""
    column = (
        ProvenanceRecord.company_id if entity_type == "company" else ProvenanceRecord.product_id
    )
    query = select(ProvenanceRecord).where(column == entity_id)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = int(count_result.scalar_one())

    query = (
        query.order_by(ProvenanceRecord.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    return list(result.scalars().all()), total


async def verify_provenance_record(
    db: AsyncSession, record: ProvenanceRecord, *, verified_by: uuid.UUID
) -> ProvenanceRecord:
    """
    THE enforcement point for Section 11's core rule. This is the
    *only* function anywhere in this codebase that sets
    status=VERIFIED — it is never set by create_provenance_record,
    never set implicitly by conflict detection, and never set by any
    other path. Requires a real, attributable verified_by (see
    app.core.dependencies.CurrentUser at the router layer) — there is
    no "system-verified" or anonymous path.
    """
    if record.status == ProvenanceStatus.VERIFIED:
        raise AlreadyVerifiedError(str(record.id))

    record.status = ProvenanceStatus.VERIFIED
    record.verified_by = verified_by
    record.verified_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(record)
    return record


# ---- Data Conflicts ----


async def get_conflict(db: AsyncSession, conflict_id: uuid.UUID) -> DataConflict | None:
    result = await db.execute(select(DataConflict).where(DataConflict.id == conflict_id))
    return result.scalar_one_or_none()


async def list_conflicts(
    db: AsyncSession, *, status_filter: ConflictStatus | None, page: int, page_size: int
) -> tuple[list[DataConflict], int]:
    query = select(DataConflict)
    if status_filter is not None:
        query = query.where(DataConflict.status == status_filter)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = int(count_result.scalar_one())

    query = (
        query.order_by(DataConflict.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    return list(result.scalars().all()), total


async def resolve_conflict(
    db: AsyncSession, conflict: DataConflict, *, resolved_by: uuid.UUID, resolution_note: str
) -> DataConflict:
    """
    Marks a conflict resolved — a human decision, recorded with a
    mandatory note (never a bare status flip with no explanation).
    Deliberately does NOT touch any ProvenanceRecord's value_observed
    or status — resolving a conflict is a record-keeping act ("a human
    looked at this and decided X"), not an automatic data mutation.
    Which value (if any) becomes canonical is Module 5A's explicit
    non-scope (this module never writes to Company/Product at all).
    """
    conflict.status = ConflictStatus.RESOLVED
    conflict.resolved_by = resolved_by
    conflict.resolved_at = datetime.now(UTC)
    conflict.resolution_note = resolution_note
    await db.commit()
    await db.refresh(conflict)
    return conflict


def total_pages(total: int, page_size: int) -> int:
    return max(1, math.ceil(total / page_size))
