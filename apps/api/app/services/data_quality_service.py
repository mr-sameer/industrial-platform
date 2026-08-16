"""
Data quality & verification operations service — Module 5E. Reads and
extends ProvenanceRecord (the sanctioned Module 5A extension) and
DataConflict (read-only, unmodified) to provide field-level quality
metadata, a review queue, and new status-transition actions
(mark_under_review, reject, mark_expired/mark_stale, link_evidence).

DOES NOT TOUCH Company.verification_status OR VerificationScoreService
ANYWHERE IN THIS FILE — confirmed by construction: no import of
app.services.verification_score_service, no reference to
Company.verification_status. That field's existing, real,
completeness-based auto-sync behavior (sync_legacy_verification_status)
is completely unaffected by anything in this module — see this
module's own completion report for the explicit regression test
proving this.

DATA TRUST RULE, restated for this module specifically: VERIFIED is
still only ever reachable through provenance_service.verify_provenance_record
(Module 5A, unchanged) — nothing added here creates a second path to
VERIFIED. This file's new transitions are UNDER_REVIEW, REJECTED, and
EXPIRED only.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_quality.freshness import classify_freshness
from app.data_quality.risk_classification import RiskLevel, classify_field
from app.models.data_conflict import ConflictStatus, DataConflict
from app.models.provenance_record import ProvenanceRecord, ProvenanceStatus
from app.models.verification_document import VerificationDocument
from app.services import audit_service, provenance_service

# The field set VerificationScoreService's own completeness scoring
# already weights (Module 3B) — reused here as the "relevant fields"
# set for the composite score (Section 15), rather than inventing a
# second, competing definition of "relevant."
_RELEVANT_COMPANY_FIELDS = frozenset(
    {"name", "legal_name", "cin", "registered_state", "industry", "website"}
)


class RecordNotUnderReviewableStateError(Exception):
    """Raised when a requested transition doesn't make sense from the
    record's current status — e.g. REJECT on an already-VERIFIED
    record, or mark-stale on a record that was never VERIFIED."""


class NoDocumentEvidenceError(Exception):
    pass


# --------------------------------------------------------------------
# Field-level quality metadata (Sections 3/4)
# --------------------------------------------------------------------


async def get_field_quality(
    db: AsyncSession, *, entity_type: str, entity_id: uuid.UUID
) -> list[dict[str, object]]:
    """
    One entry per (field_name), summarizing its current evidence —
    never a single blended number for the whole entity, per Section 3's
    explicit rule. Each entry is independently inspectable.
    """
    records, _total = await provenance_service.list_provenance_for_entity(
        db, entity_type=entity_type, entity_id=entity_id, page=1, page_size=200
    )
    # Most recent record per field_name — a field can have multiple
    # ProvenanceRecords (one per source/observation); the quality view
    # summarizes the current, most-recently-observed one.
    latest_by_field: dict[str, ProvenanceRecord] = {}
    for record in records:
        existing = latest_by_field.get(record.field_name)
        if existing is None or record.last_observed_at > existing.last_observed_at:
            latest_by_field[record.field_name] = record

    entries: list[dict[str, object]] = []
    for field_name, record in latest_by_field.items():
        freshness = classify_freshness(field_name, record.last_observed_at)
        entries.append(
            {
                "field_name": field_name,
                "value_observed": record.value_observed,
                "status": record.status.value,
                "confidence": record.confidence,
                "risk_level": classify_field(entity_type, field_name).value,
                "freshness": freshness.value,
                "has_open_conflict": record.conflict_id is not None,
                "provenance_record_id": record.id,
                "last_observed_at": record.last_observed_at,
                "expires_at": record.expires_at,
            }
        )
    return entries


async def get_quality_score(
    db: AsyncSession, *, entity_type: str, entity_id: uuid.UUID
) -> dict[str, object]:
    """
    Section 15's composite score — ALWAYS returned alongside the
    field-level breakdown it summarizes (get_field_quality), never
    standalone; the API layer (app.api.v1.data_quality) enforces this
    by always including both in the same response, not by convention
    alone.

    Meaning, exactly as the architecture requires: "% of relevant
    fields with recent, traceable evidence" — never "% true."
    VERIFIED fields count fully (weight 1.0); CLAIMED/OBSERVED/EXTRACTED
    count partially (weight 0.5, since evidence exists but isn't
    independently confirmed); REJECTED or entirely-missing fields count
    zero. High-risk relevant fields count double, per the architecture
    doc's own proposed weighting.
    """
    if entity_type != "company":
        # Section 15 is scoped to the fields VerificationScoreService
        # already weights (Company only, Module 3B) — a Product/Offering
        # equivalent would need its own relevant-field definition,
        # deliberately not invented here without a real basis.
        return {
            "score": None,
            "meaning": "Composite scoring is only defined for Company entities in this phase.",
        }

    field_quality = await get_field_quality(db, entity_type=entity_type, entity_id=entity_id)
    by_field = {entry["field_name"]: entry for entry in field_quality}

    total_weight = 0.0
    earned_weight = 0.0
    for field_name in _RELEVANT_COMPANY_FIELDS:
        risk = classify_field("company", field_name)
        field_weight = 2.0 if risk == RiskLevel.HIGH else 1.0
        total_weight += field_weight

        entry = by_field.get(field_name)
        if entry is None:
            continue  # no evidence at all -> contributes 0, per the weighting rule
        status = entry["status"]
        if status == ProvenanceStatus.VERIFIED.value:
            earned_weight += field_weight
        elif status in (
            ProvenanceStatus.OBSERVED.value,
            ProvenanceStatus.EXTRACTED.value,
            ProvenanceStatus.CLAIMED.value,
        ):
            earned_weight += field_weight * 0.5
        # REJECTED / UNDER_REVIEW / EXPIRED contribute 0 — evidence
        # exists but is explicitly not currently trustworthy.

    score = round((earned_weight / total_weight) * 100, 1) if total_weight > 0 else None
    return {
        "score": score,
        "meaning": (
            f"{score}% of relevant fields have recent, traceable evidence — "
            "this is NOT a measure of factual truth. See the accompanying "
            "field-level breakdown for what specifically backs this number."
            if score is not None
            else "No relevant fields defined."
        ),
    }


# --------------------------------------------------------------------
# Review queue (Section 10)
# --------------------------------------------------------------------


async def list_review_queue(
    db: AsyncSession, *, page: int, page_size: int
) -> tuple[list[ProvenanceRecord], int]:
    """
    Items needing review: explicitly UNDER_REVIEW, OR a high-risk field
    still sitting at OBSERVED/EXTRACTED/CLAIMED (Section 10's "important
    unverified claim" reason), OR any record currently in an open
    conflict. Conflicts themselves remain independently visible via
    Module 5A's own GET /provenance/conflicts (unchanged) — this queue
    surfaces the ProvenanceRecord side of the same information for a
    unified reviewer view, not a duplicate conflict-tracking mechanism.
    """
    conflicted_record_ids = (
        select(ProvenanceRecord.id)
        .join(DataConflict, DataConflict.id == ProvenanceRecord.conflict_id)
        .where(DataConflict.status == ConflictStatus.OPEN)
    )

    query = select(ProvenanceRecord).where(
        or_(
            ProvenanceRecord.status == ProvenanceStatus.UNDER_REVIEW,
            ProvenanceRecord.id.in_(conflicted_record_ids),
        )
    )

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = int(count_result.scalar_one())

    query = (
        query.order_by(ProvenanceRecord.created_at.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    records = list(result.scalars().all())

    # High-risk unverified claims, appended after the primary (already
    # explicit) queue items — a second, real pass rather than folding
    # into the same SQL query, since risk classification for Company
    # fields is a Python-side lookup (app.data_quality.risk_classification),
    # not something a single SQL WHERE clause can express directly.
    if page == 1:
        candidates_result = await db.execute(
            select(ProvenanceRecord).where(
                ProvenanceRecord.status.in_(
                    [
                        ProvenanceStatus.OBSERVED,
                        ProvenanceStatus.EXTRACTED,
                        ProvenanceStatus.CLAIMED,
                    ]
                )
            )
        )
        high_risk_unverified = [
            r
            for r in candidates_result.scalars().all()
            if classify_field(r.entity_type.value, r.field_name) == RiskLevel.HIGH
            and r.id not in {existing.id for existing in records}
        ]
        records.extend(high_risk_unverified)
        total += len(high_risk_unverified)

    return records, total


# --------------------------------------------------------------------
# Review actions — the only functions in this codebase that can set
# UNDER_REVIEW / REJECTED / EXPIRED.
# --------------------------------------------------------------------


async def mark_under_review(
    db: AsyncSession, record: ProvenanceRecord, *, reviewer_id: uuid.UUID
) -> ProvenanceRecord:
    if record.status not in (
        ProvenanceStatus.OBSERVED,
        ProvenanceStatus.EXTRACTED,
        ProvenanceStatus.CLAIMED,
    ):
        raise RecordNotUnderReviewableStateError(
            f"Cannot mark under review from status {record.status.value!r}."
        )
    previous_status = record.status
    record.status = ProvenanceStatus.UNDER_REVIEW
    await db.commit()
    await db.refresh(record)
    await audit_service.log_event(
        db,
        "provenance_marked_under_review",
        user_id=str(reviewer_id),
        metadata={
            "provenance_record_id": str(record.id),
            "field_name": record.field_name,
            "previous_status": previous_status.value,
            "new_status": record.status.value,
        },
    )
    return record


async def reject(
    db: AsyncSession, record: ProvenanceRecord, *, reviewer_id: uuid.UUID, note: str
) -> ProvenanceRecord:
    if record.status == ProvenanceStatus.VERIFIED:
        raise RecordNotUnderReviewableStateError(
            "A VERIFIED record cannot be directly rejected — use mark_expired instead."
        )
    if record.status in (ProvenanceStatus.REJECTED, ProvenanceStatus.EXPIRED):
        raise RecordNotUnderReviewableStateError(f"Record is already {record.status.value!r}.")
    previous_status = record.status
    record.status = ProvenanceStatus.REJECTED
    record.review_note = note
    record.verified_by = (
        reviewer_id  # the reviewer who made THIS decision, reusing the existing column
    )
    record.verified_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(record)
    await audit_service.log_event(
        db,
        "provenance_rejected",
        user_id=str(reviewer_id),
        metadata={
            "provenance_record_id": str(record.id),
            "field_name": record.field_name,
            "previous_status": previous_status.value,
            "new_status": record.status.value,
            "reason": note,
        },
    )
    return record


async def mark_expired(
    db: AsyncSession, record: ProvenanceRecord, *, reviewer_id: uuid.UUID, note: str
) -> ProvenanceRecord:
    """The "MARK STALE" reviewer action (Section 10) — only reachable
    from VERIFIED, since marking something stale presumes it was
    previously trusted."""
    if record.status != ProvenanceStatus.VERIFIED:
        raise RecordNotUnderReviewableStateError(
            f"Only a VERIFIED record can be marked expired/stale (current status: {record.status.value!r})."
        )
    record.status = ProvenanceStatus.EXPIRED
    record.review_note = note
    await db.commit()
    await db.refresh(record)
    await audit_service.log_event(
        db,
        "provenance_marked_expired",
        user_id=str(reviewer_id),
        metadata={
            "provenance_record_id": str(record.id),
            "field_name": record.field_name,
            "previous_status": ProvenanceStatus.VERIFIED.value,
            "new_status": record.status.value,
            "reason": note,
        },
    )
    return record


async def link_evidence(
    db: AsyncSession, record: ProvenanceRecord, *, document_id: uuid.UUID, linked_by: uuid.UUID
) -> ProvenanceRecord:
    """
    Attaches a VerificationDocument as evidence — per Section 9's
    central rule, this NEVER changes the record's status by itself.
    Linking evidence and verifying a claim remain two distinct actions;
    a reviewer still calls provenance_service.verify_provenance_record
    (Module 5A, unchanged) separately, deliberately, to actually verify.
    """
    doc_result = await db.execute(
        select(VerificationDocument).where(VerificationDocument.id == document_id)
    )
    document = doc_result.scalar_one_or_none()
    if document is None:
        raise NoDocumentEvidenceError(str(document_id))

    record.verification_document_id = document.id
    if document.expiry_date is not None:
        # Keeps the two expiry concepts in sync, per this model's own
        # column docstring — the claim's expiry mirrors its evidence's
        # expiry when evidence exists.
        record.expires_at = datetime.combine(document.expiry_date, datetime.min.time(), tzinfo=UTC)
    await db.commit()
    await db.refresh(record)
    await audit_service.log_event(
        db,
        "provenance_evidence_linked",
        user_id=str(linked_by),
        metadata={
            "provenance_record_id": str(record.id),
            "field_name": record.field_name,
            "verification_document_id": str(document.id),
        },
    )
    return record
