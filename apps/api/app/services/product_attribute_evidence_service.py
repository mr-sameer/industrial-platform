"""
ProductAttribute evidence service — the approved additive extension of
Module 5A's provenance pattern to ProductAttribute (Phase 4B). Mirrors
app.services.provenance_service (creation + conflict detection +
explicit verify) and app.services.graph_service (reject) exactly, and
app.services.data_quality_service.apply_reviewed_field_to_company's
"apply" shape — adapted to ProductAttribute's own (product_id,
specification_id) identity instead of a free-text field_name against a
Company column.

DATA TRUST RULE, restated for this module specifically (identical to
every other evidence/provenance service in this codebase): VERIFIED is
only ever reachable through verify_product_attribute_evidence below —
never a side effect of creation, never set by AI-assisted extraction
(extraction_method has no bearing on authority — see
create_attribute_evidence's own guard), never a side effect of
conflict detection or of apply_reviewed_attribute_to_product itself
(which requires an ALREADY-VERIFIED row and never changes its status).

CONFLICT DETECTION reuses DataConflict (Module 5A, unmodified schema)
via the same field_name string convention
app.services.graph_service.flag_relationship_conflict already
established for relationship-level conflicts
(f"attribute:{specification_id}") — no new DataConflict column, no new
conflict model.
"""

import math
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extraction.ocr_confidence import apply_ocr_confidence_ceiling
from app.models.data_conflict import ConflictStatus, DataConflict
from app.models.product import Product
from app.models.product_attribute import ProductAttribute
from app.models.product_attribute_evidence import ProductAttributeEvidence
from app.models.product_specification import ProductSpecification
from app.models.provenance_record import ExtractionMethod, ProvenanceStatus
from app.schemas.product_attribute_evidence import ProductAttributeEvidenceCreate
from app.services import audit_service, ocr_result_service, provenance_service

__all__ = [
    "AlreadyVerifiedError",
    "EmptyValueError",
    "EvidenceConfidenceTooLowError",
    "EvidenceNotReviewableStateError",
    "EvidenceNotVerifiedError",
    "MIN_VERIFIABLE_CONFIDENCE",
    "OCRResultNotFoundForEvidenceError",
    "ProductNotFoundForEvidenceError",
    "RawObservationNotFoundForEvidenceError",
    "RawObservationOcrResultMismatchError",
    "SpecificationNotFoundForEvidenceError",
    "SpecificationNotInProductCategoryError",
    "apply_reviewed_attribute_to_product",
    "create_attribute_evidence",
    "create_ocr_derived_attribute_evidence",
    "get_attribute_evidence",
    "list_attribute_evidence",
    "reject_product_attribute_evidence",
    "total_pages",
    "verify_product_attribute_evidence",
]

# P0 verification safety guard (approved design audit, see this
# module's own docstring's DATA TRUST RULE): the four fixed confidence
# tiers in app.extraction.confidence are 0.90/0.70/0.45/0.20, and 0.20
# ("TIER_AMBIGUOUS") is reachable ONLY when a deterministic extraction
# found multiple, disagreeing occurrences of the same specification in
# one document — never for any other reason (see that module's own
# compute_confidence, whose ambiguous branch is checked first and
# unconditionally returns 0.20). 0.45 ("TIER_WEAK") is therefore the
# correct floor: it blocks exactly the self-contradicting tier while
# leaving every other existing tier (including a merely weakly-matched
# but non-contradictory reading) verifiable by a human as before.
# Deliberately a plain module-level float, not a per-specification or
# per-category setting — this is a global safety floor on what may
# ever become VERIFIED, not an extraction-tuning knob.
MIN_VERIFIABLE_CONFIDENCE = 0.45


class ProductNotFoundForEvidenceError(Exception):
    pass


class SpecificationNotFoundForEvidenceError(Exception):
    pass


class SpecificationNotInProductCategoryError(Exception):
    """Raised when the submitted specification_id doesn't belong to the
    product's own category — mirrors product_service's
    InvalidSpecificationError guard on ProductAttribute itself; an
    evidence claim against a mismatched spec would be just as invalid
    as an attribute value would."""


class RawObservationNotFoundForEvidenceError(Exception):
    pass


class OCRResultNotFoundForEvidenceError(Exception):
    pass


class RawObservationOcrResultMismatchError(Exception):
    """Raised when the caller's raw_observation_id doesn't match
    ocr_result.raw_observation_id — see
    create_ocr_derived_attribute_evidence's own docstring. An OCRResult
    is always a transformation of ONE specific original document; this
    guard exists so a caller bug (e.g. an OCRResult accidentally
    sourced from a different document) can never silently attach
    evidence to the wrong RawObservation."""


class AlreadyVerifiedError(Exception):
    """Mirrors provenance_service.AlreadyVerifiedError — verification is
    a one-time, attributable action, not idempotent."""


class EvidenceConfidenceTooLowError(Exception):
    """Raised when verify is attempted on evidence whose confidence is
    below MIN_VERIFIABLE_CONFIDENCE — see that constant's own docstring.
    Not a terminal state: the row is left exactly as it was (still
    EXTRACTED/OBSERVED/CLAIMED, still reject-able, still fully queryable
    for its extraction_context). A human who independently confirms the
    correct value submits a fresh, higher-confidence evidence claim via
    the existing create endpoint — this guard blocks only the
    unreliable row itself from ever becoming the vehicle for
    canonicalization, never the (product, specification) attribute as a
    whole."""


class EvidenceNotReviewableStateError(Exception):
    """Raised when reject is attempted on evidence that is already
    VERIFIED or already REJECTED — mirrors
    graph_service.RelationshipNotUnderReviewableStateError."""


class EvidenceNotVerifiedError(Exception):
    """Raised when apply_reviewed_attribute_to_product is attempted
    against evidence that is not VERIFIED — an OBSERVED/EXTRACTED/
    CLAIMED/UNDER_REVIEW claim must never reach the canonical
    ProductAttribute value, automatically or otherwise."""


class EmptyValueError(Exception):
    """Raised when evidence.value_observed is empty or whitespace-only
    — there is nothing usable to apply."""


async def _detect_and_flag_conflict(
    db: AsyncSession, evidence: ProductAttributeEvidence
) -> DataConflict | None:
    """
    Same shape as provenance_service._detect_and_flag_conflict, keyed
    on (product_id, specification_id) instead of (entity, field_name).
    Agreeing evidence rows are left completely untouched — only a
    genuinely disagreeing value_observed creates or reuses a conflict.
    Never deletes or overwrites any row.
    """
    result = await db.execute(
        select(ProductAttributeEvidence).where(
            ProductAttributeEvidence.product_id == evidence.product_id,
            ProductAttributeEvidence.specification_id == evidence.specification_id,
            ProductAttributeEvidence.id != evidence.id,
            ProductAttributeEvidence.value_observed != evidence.value_observed,
        )
    )
    disagreeing = list(result.scalars().all())
    if not disagreeing:
        return None

    existing_conflict_id = next(
        (e.conflict_id for e in disagreeing if e.conflict_id is not None), None
    )
    if existing_conflict_id is not None:
        evidence.conflict_id = existing_conflict_id
        await db.flush()
        result2 = await db.execute(
            select(DataConflict).where(DataConflict.id == existing_conflict_id)
        )
        return result2.scalar_one()

    conflict = DataConflict(
        product_id=evidence.product_id,
        field_name=f"attribute:{evidence.specification_id}",
        status=ConflictStatus.OPEN,
    )
    db.add(conflict)
    await db.flush()

    evidence.conflict_id = conflict.id
    for other in disagreeing:
        other.conflict_id = conflict.id
    await db.flush()
    return conflict


async def _validate_product_and_specification(
    db: AsyncSession, *, product_id: uuid.UUID, specification_id: uuid.UUID
) -> tuple[Product, ProductSpecification]:
    """Shared by create_attribute_evidence and
    create_ocr_derived_attribute_evidence — extracted verbatim, no
    behavior change, so both creation paths enforce the identical
    product-exists / specification-exists / specification-belongs-to-
    product's-category rule."""
    product_result = await db.execute(select(Product).where(Product.id == product_id))
    product = product_result.scalar_one_or_none()
    if product is None:
        raise ProductNotFoundForEvidenceError(str(product_id))

    spec_result = await db.execute(
        select(ProductSpecification).where(ProductSpecification.id == specification_id)
    )
    specification = spec_result.scalar_one_or_none()
    if specification is None:
        raise SpecificationNotFoundForEvidenceError(str(specification_id))
    if specification.category_id != product.category_id:
        raise SpecificationNotInProductCategoryError(
            f"specification {specification_id} belongs to category "
            f"{specification.category_id}, not product {product_id}'s category "
            f"{product.category_id}."
        )
    return product, specification


async def create_attribute_evidence(
    db: AsyncSession, payload: ProductAttributeEvidenceCreate
) -> tuple[ProductAttributeEvidence, DataConflict | None]:
    """
    Creates one source's evidence claim. status must be OBSERVED,
    EXTRACTED, or CLAIMED — enforced already at the schema layer
    (ProductAttributeEvidenceCreate.model_post_init) and re-affirmed
    here as a second, independent guard, exactly matching
    provenance_service.create_provenance_record's own two-layer
    enforcement.

    Idempotent on (product_id, specification_id, raw_observation_id) —
    a retried ingestion of the same source's claim for the same
    attribute returns the existing row rather than creating a
    duplicate, matching this codebase's established idempotent-create
    pattern (graph_service.create_relationship/create_capability).

    Also runs conflict detection: if another, still-relevant evidence
    row for the same (product_id, specification_id) disagrees, a
    DataConflict is created/reused and every disagreeing row's
    conflict_id is set — detection and flagging only, nothing here
    picks a winner.
    """
    if payload.status == ProvenanceStatus.VERIFIED:
        raise ValueError(
            "status must not be 'verified' at creation — use verify_product_attribute_evidence"
        )

    await _validate_product_and_specification(
        db, product_id=payload.product_id, specification_id=payload.specification_id
    )

    observation = await provenance_service.get_raw_observation(db, payload.raw_observation_id)
    if observation is None:
        raise RawObservationNotFoundForEvidenceError(str(payload.raw_observation_id))

    existing_result = await db.execute(
        select(ProductAttributeEvidence).where(
            ProductAttributeEvidence.product_id == payload.product_id,
            ProductAttributeEvidence.specification_id == payload.specification_id,
            ProductAttributeEvidence.raw_observation_id == payload.raw_observation_id,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        return existing, None

    now = datetime.now(UTC)
    evidence = ProductAttributeEvidence(
        product_id=payload.product_id,
        specification_id=payload.specification_id,
        raw_observation_id=payload.raw_observation_id,
        value_observed=payload.value_observed,
        extraction_method=payload.extraction_method,
        confidence=payload.confidence,
        status=payload.status,
        last_observed_at=now,
        extraction_context=payload.extraction_context,
        verification_document_id=payload.verification_document_id,
    )
    db.add(evidence)
    await db.flush()  # evidence.id needed before it can be referenced by a conflict

    conflict = await _detect_and_flag_conflict(db, evidence)

    await db.commit()
    await db.refresh(evidence)
    return evidence, conflict


async def create_ocr_derived_attribute_evidence(
    db: AsyncSession,
    *,
    product_id: uuid.UUID,
    specification_id: uuid.UUID,
    raw_observation_id: uuid.UUID,
    ocr_result_id: uuid.UUID,
    value_observed: str,
    extraction_method: ExtractionMethod,
    extraction_confidence: float,
    status: ProvenanceStatus = ProvenanceStatus.EXTRACTED,
    extraction_context: dict[str, object] | None = None,
) -> tuple[ProductAttributeEvidence, DataConflict | None]:
    """
    The OCR-derived counterpart to create_attribute_evidence — internal
    service-layer entry point for a future deterministic-extraction
    pipeline that read its source text from an OCRResult rather than a
    native PDF text layer. Not exposed via the API in this milestone
    (see the approved OCR Architecture Design Proposal's explicit
    non-goals).

    raw_observation_id is taken explicitly from the caller (not derived
    from ocr_result.raw_observation_id) and then validated to match —
    see RawObservationOcrResultMismatchError — so a caller bug (e.g. an
    OCRResult accidentally sourced from a different document than the
    one being processed) is rejected loudly rather than silently
    accepted or silently "corrected".

    extraction_confidence is the deterministic-extraction tier (see
    app.extraction.confidence) computed against the OCR text — this
    function combines it with ocr_result.confidence via
    app.extraction.ocr_confidence.apply_ocr_confidence_ceiling before
    storing the result as ProductAttributeEvidence.confidence. Only the
    ceiling'd value is ever stored; raw ocr_result.confidence stays on
    OCRResult itself, reachable via evidence.ocr_result, never
    duplicated onto this row.

    Idempotent on (product_id, specification_id, raw_observation_id,
    ocr_result_id) — matches uq_pae_source_ocr exactly, mirroring
    create_attribute_evidence's own idempotent-create pattern one
    dimension over (per OCRResult run instead of per RawObservation).
    Runs the identical conflict detection as create_attribute_evidence.
    """
    if status == ProvenanceStatus.VERIFIED:
        raise ValueError(
            "status must not be 'verified' at creation — use verify_product_attribute_evidence"
        )

    await _validate_product_and_specification(
        db, product_id=product_id, specification_id=specification_id
    )

    ocr_result = await ocr_result_service.get_ocr_result(db, ocr_result_id)
    if ocr_result is None:
        raise OCRResultNotFoundForEvidenceError(str(ocr_result_id))
    if ocr_result.raw_observation_id != raw_observation_id:
        raise RawObservationOcrResultMismatchError(
            f"raw_observation_id {raw_observation_id} does not match "
            f"ocr_result {ocr_result_id}'s own raw_observation_id "
            f"{ocr_result.raw_observation_id}."
        )

    existing_result = await db.execute(
        select(ProductAttributeEvidence).where(
            ProductAttributeEvidence.product_id == product_id,
            ProductAttributeEvidence.specification_id == specification_id,
            ProductAttributeEvidence.raw_observation_id == raw_observation_id,
            ProductAttributeEvidence.ocr_result_id == ocr_result_id,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        return existing, None

    final_confidence = apply_ocr_confidence_ceiling(extraction_confidence, ocr_result.confidence)

    now = datetime.now(UTC)
    evidence = ProductAttributeEvidence(
        product_id=product_id,
        specification_id=specification_id,
        raw_observation_id=raw_observation_id,
        ocr_result_id=ocr_result_id,
        value_observed=value_observed,
        extraction_method=extraction_method,
        confidence=final_confidence,
        status=status,
        last_observed_at=now,
        extraction_context=extraction_context,
    )
    db.add(evidence)
    await db.flush()  # evidence.id needed before it can be referenced by a conflict

    conflict = await _detect_and_flag_conflict(db, evidence)

    await db.commit()
    await db.refresh(evidence)
    return evidence, conflict


async def get_attribute_evidence(
    db: AsyncSession, evidence_id: uuid.UUID
) -> ProductAttributeEvidence | None:
    result = await db.execute(
        select(ProductAttributeEvidence).where(ProductAttributeEvidence.id == evidence_id)
    )
    return result.scalar_one_or_none()


async def list_attribute_evidence(
    db: AsyncSession,
    *,
    product_id: uuid.UUID,
    specification_id: uuid.UUID,
    page: int,
    page_size: int,
) -> tuple[list[ProductAttributeEvidence], int]:
    """Every evidence row ever submitted for one (product, specification)
    pair — the full, append-only ledger behind a single ProductAttribute
    value, including rows never applied and rows on the losing side of
    a conflict."""
    query = select(ProductAttributeEvidence).where(
        ProductAttributeEvidence.product_id == product_id,
        ProductAttributeEvidence.specification_id == specification_id,
    )

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = int(count_result.scalar_one())

    query = (
        query.order_by(ProductAttributeEvidence.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    return list(result.scalars().all()), total


async def verify_product_attribute_evidence(
    db: AsyncSession, evidence: ProductAttributeEvidence, *, verified_by: uuid.UUID
) -> ProductAttributeEvidence:
    """
    THE enforcement point — the only function anywhere in this codebase
    that sets ProductAttributeEvidence.status = VERIFIED. Mirrors
    provenance_service.verify_provenance_record exactly: requires a
    real, attributable verified_by, never reachable automatically,
    regardless of extraction_method (an ai_assisted row is verified
    through this exact same call, with no shortcut).

    P0 safety guard (approved design audit): also refuses evidence
    whose confidence is below MIN_VERIFIABLE_CONFIDENCE — see that
    constant's own docstring for why a numeric floor, not
    extraction_context.ambiguous, is the enforcement condition, and why
    0.45 is the correct cut line. Checked after the AlreadyVerifiedError
    guard (re-verifying already-VERIFIED evidence is always a 409,
    regardless of its confidence) and before any state is mutated.
    """
    if evidence.status == ProvenanceStatus.VERIFIED:
        raise AlreadyVerifiedError(str(evidence.id))
    if evidence.confidence < MIN_VERIFIABLE_CONFIDENCE:
        raise EvidenceConfidenceTooLowError(
            f"ProductAttributeEvidence {evidence.id} has confidence {evidence.confidence!r}, "
            f"below the minimum verifiable confidence {MIN_VERIFIABLE_CONFIDENCE!r}."
        )

    evidence.status = ProvenanceStatus.VERIFIED
    evidence.verified_by = verified_by
    evidence.verified_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(evidence)
    return evidence


async def reject_product_attribute_evidence(
    db: AsyncSession, evidence: ProductAttributeEvidence, *, reviewer_id: uuid.UUID, note: str
) -> ProductAttributeEvidence:
    """Mirrors graph_service.reject_relationship exactly. The row is
    never deleted — it remains queryable, permanently, with its
    rejection reason attached."""
    if evidence.status in (ProvenanceStatus.VERIFIED, ProvenanceStatus.REJECTED):
        raise EvidenceNotReviewableStateError(
            f"Cannot reject evidence {evidence.id} in status {evidence.status.value!r}."
        )
    evidence.status = ProvenanceStatus.REJECTED
    evidence.review_note = note
    evidence.verified_by = reviewer_id
    evidence.verified_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(evidence)
    return evidence


async def apply_reviewed_attribute_to_product(
    db: AsyncSession, evidence: ProductAttributeEvidence, *, reviewer_id: uuid.UUID
) -> ProductAttribute:
    """
    The one and only function that writes ProductAttribute.value from
    evidence — mirrors
    data_quality_service.apply_reviewed_field_to_company's role
    exactly, adapted to ProductAttribute's (product_id,
    specification_id) identity instead of a Company column.

    Requires the evidence row to already be VERIFIED (a distinct, prior
    action — never a side effect of this call) and a real, attributable
    reviewer_id. Get-or-creates the ProductAttribute row for this
    (product_id, specification_id) — apply is often the FIRST time a
    value is set for this attribute, since evidence can exist before
    any ProductAttribute row does. Never deletes or mutates any other
    evidence row: the losing/uninvolved rows for this attribute remain
    exactly as they were, still queryable via list_attribute_evidence.
    """
    if evidence.status != ProvenanceStatus.VERIFIED:
        raise EvidenceNotVerifiedError(
            f"ProductAttributeEvidence {evidence.id} is not VERIFIED "
            f"(status={evidence.status.value!r})."
        )

    value = evidence.value_observed.strip()
    if not value:
        raise EmptyValueError(f"ProductAttributeEvidence {evidence.id} has no usable value.")

    result = await db.execute(
        select(ProductAttribute).where(
            ProductAttribute.product_id == evidence.product_id,
            ProductAttribute.specification_id == evidence.specification_id,
        )
    )
    attribute = result.scalar_one_or_none()
    previous_value = attribute.value if attribute is not None else None

    if attribute is None:
        attribute = ProductAttribute(
            product_id=evidence.product_id,
            specification_id=evidence.specification_id,
            value=value,
            latest_evidence_id=evidence.id,
        )
        db.add(attribute)
    else:
        attribute.value = value
        attribute.latest_evidence_id = evidence.id

    # No dedicated applied_by/applied_at column exists on
    # ProductAttribute (matching the accepted gap
    # apply_reviewed_field_to_company already lives with for Company) —
    # recorded as a plain audit line on the evidence row's own
    # review_note instead, plus a real AuditLog entry below.
    timestamp = datetime.now(UTC).isoformat()
    audit_line = (
        f"Applied to ProductAttribute(product_id={evidence.product_id}, "
        f"specification_id={evidence.specification_id}) by {reviewer_id} at {timestamp} "
        f"(previous value: {previous_value!r})."
    )
    evidence.review_note = (
        f"{evidence.review_note}\n{audit_line}" if evidence.review_note else audit_line
    )

    await db.commit()
    await db.refresh(attribute)
    await db.refresh(evidence)
    await audit_service.log_event(
        db,
        "product_attribute_evidence_applied",
        user_id=str(reviewer_id),
        metadata={
            "evidence_id": str(evidence.id),
            "product_id": str(evidence.product_id),
            "specification_id": str(evidence.specification_id),
            "value": value,
            "previous_value": previous_value,
        },
    )
    return attribute


def total_pages(total: int, page_size: int) -> int:
    return max(1, math.ceil(total / page_size))
