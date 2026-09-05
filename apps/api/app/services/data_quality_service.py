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
from app.models.company import Company
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

# Module 8C — the 8 ARRAY(String) Company columns allowlisted for
# apply_reviewed_field_to_company's array-append branch, mapped to
# their list-count cap. Six of eight reuse BusinessInfoUpdate's own
# Pydantic max_length exactly (Module 3B, confirmed by direct
# inspection of app.schemas.company_verification); ai_tags has no
# existing schema exposure to inherit from, so 30 is established here
# explicitly (see ArrayLimitExceededError's own docstring).
_ARRAY_FIELD_LIMITS: dict[str, int] = {
    "core_values": 20,
    "capabilities": 30,
    "manufacturing_expertise": 30,
    "secondary_industries": 20,
    "product_categories": 30,
    "manufacturing_categories": 30,
    "export_categories": 30,
    "ai_tags": 30,
}


class RecordNotUnderReviewableStateError(Exception):
    """Raised when a requested transition doesn't make sense from the
    record's current status — e.g. REJECT on an already-VERIFIED
    record, or mark-stale on a record that was never VERIFIED."""


class NoDocumentEvidenceError(Exception):
    pass


class RecordNotVerifiedError(Exception):
    """Raised when attempting to apply a record to a Company that is
    not yet VERIFIED — an OBSERVED/EXTRACTED/CLAIMED claim must never
    reach the canonical Company record, automatically or otherwise."""


class FieldNotAllowlistedError(Exception):
    """Raised when a ProvenanceRecord's field_name is not one of the
    explicit, reviewed field_name -> Company attribute mappings
    apply_reviewed_field_to_company will ever write through. There is
    no generic fallback — a new applyable field means adding a new,
    deliberate branch in that function, not widening a data-driven
    allowlist."""


class RecordCompanyMismatchError(Exception):
    """Raised when the ProvenanceRecord being applied does not belong
    to the target Company — this must never write one company's
    evidence onto another's canonical record."""


class EmptyValueError(Exception):
    """Raised when a ProvenanceRecord's value_observed is empty or
    whitespace-only — there is nothing usable to apply."""


class ValueTooLongError(Exception):
    """Raised when a value would exceed the target Company column's
    real length bound — checked here, before the database ever sees
    it, rather than surfacing a raw constraint failure."""


class ArrayLimitExceededError(Exception):
    """Raised when appending a new value to an ARRAY(String) Company
    column would exceed that field's list-count cap (Module 8C). Six
    of the eight fields reuse the same cap already enforced on
    BusinessInfoUpdate's Pydantic schema for direct edits (Module 3B) —
    not reinvented here. `ai_tags` has no existing schema exposure to
    inherit a cap from (confirmed: absent from both BusinessInfoUpdate
    and BusinessInfoDetail); this module establishes 30 for it
    explicitly, matching the majority convention among the other
    seven — a deliberate choice, not a discovered constraint."""


class ArrayFieldOverwriteNotSupportedError(Exception):
    """Raised when overwrite=True is passed while applying one of the
    8 ARRAY(String) allowlisted fields (Module 8C). Array fields are
    append-only and have no destructive-replace semantics — silently
    ignoring the flag would be misleading, so this fails loudly
    instead, before any value is touched."""


class ConflictingValueError(Exception):
    """Raised when the Company field already holds a different,
    non-empty value and the caller did not explicitly pass
    overwrite=True. This function never silently overwrites existing
    canonical data — matches this codebase's established rule (see
    provenance_service._detect_and_flag_conflict's own docstring:
    "never silently overwrite conflicting information")."""


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


# --------------------------------------------------------------------
# Apply reviewed evidence to the canonical Company record (Module 8B)
# --------------------------------------------------------------------


async def apply_reviewed_field_to_company(
    db: AsyncSession,
    record: ProvenanceRecord,
    company: Company,
    *,
    reviewer_id: uuid.UUID,
    overwrite: bool = False,
) -> Company:
    """
    Closes the one real gap Module 8B's architectural review found: a
    VERIFIED ProvenanceRecord about an EXISTING company (the
    CONFIRM_MATCH path,
    app.services.entity_resolution_service._attach_observation_to_existing_company)
    never wrote anything to the canonical Company row — only
    company_promotion_service, at Company-*creation* time, ever did.
    This is that missing, explicit, human-triggered step — never
    automatic, never a side effect of verify_provenance_record itself.

    Deliberately NOT a generic setattr(company, record.field_name,
    value_observed): ProvenanceRecord.field_name is free text (see
    that model's own docstring — "Free text, not an enum"), and
    company_promotion_service already proves field_name does not
    generally equal the Company attribute name (e.g. field_name=
    "company_name" maps to Company.name). This function instead
    dispatches on a small, closed, explicitly-reviewed set of
    field_name values — adding a new applyable field means adding a
    new branch here deliberately, never widening a data-driven
    allowlist. Five branches are plain string Company columns with a
    real, enforced length bound (description/industry/short_description
    — unchanged since Module 8B; state/city — added for the pump
    supplier coverage pilot's location-intelligence activation, same
    VARCHAR(120) bound as industry, same scalar overwrite semantics,
    no new column, no new field-name convention). The 8 ARRAY(String)
    columns (secondary_industries, product_categories,
    manufacturing_categories, manufacturing_expertise, capabilities,
    core_values, export_categories, ai_tags) are reachable too, as of
    Module 8C, but through a deliberately distinct, append-only branch
    (_apply_array_field_to_company) — never the same single-value
    overwrite semantics as the five scalar fields, and never a
    destructive replace; see that helper's own docstring for the full
    array-specific rules (exact-match idempotency, list-count cap,
    overwrite=True rejected outright). Identity/legal fields (cin, pan,
    legal_name, gst_number, ...), Company.country, Company.status, and
    Company.verification_status are likewise never reachable here —
    they are not in scope for website-sourced evidence. Country is
    deliberately excluded even though state/city are now included: the
    real pilot evidence found so far only ever states a city/state
    (e.g. "Pune-411002"), never restates the country on the same
    letterhead in a form worth a separate provenance row — a future,
    real, sourced need for it should get its own deliberate branch here
    too, not a speculative one added ahead of any actual evidence.
    """
    if record.status != ProvenanceStatus.VERIFIED:
        raise RecordNotVerifiedError(
            f"ProvenanceRecord {record.id} is not VERIFIED (status={record.status.value!r})."
        )
    if record.company_id != company.id:
        raise RecordCompanyMismatchError(
            f"ProvenanceRecord {record.id} belongs to company_id={record.company_id}, "
            f"not company_id={company.id}."
        )

    value = record.value_observed.strip()
    if not value:
        raise EmptyValueError(f"ProvenanceRecord {record.id} has no usable value to apply.")

    if record.field_name in _ARRAY_FIELD_LIMITS:
        return await _apply_array_field_to_company(
            db, record, company, value, reviewer_id=reviewer_id, overwrite=overwrite
        )

    if record.field_name == "description":
        current_value = company.description
        max_length = None
    elif record.field_name == "industry":
        current_value = company.industry
        max_length = 120
    elif record.field_name == "short_description":
        current_value = company.short_description
        max_length = 500
    elif record.field_name == "state":
        current_value = company.state
        max_length = 120
    elif record.field_name == "city":
        current_value = company.city
        max_length = 120
    else:
        raise FieldNotAllowlistedError(
            f"field_name {record.field_name!r} is not allowlisted for apply-to-company — "
            "only 'description', 'industry', 'short_description', 'state', 'city', and the "
            f"8 ARRAY(String) fields ({', '.join(sorted(_ARRAY_FIELD_LIMITS))}) are."
        )

    if max_length is not None and len(value) > max_length:
        raise ValueTooLongError(
            f"value is {len(value)} characters; Company.{record.field_name} allows at most "
            f"{max_length}."
        )
    if current_value and current_value != value and not overwrite:
        raise ConflictingValueError(
            f"Company.{record.field_name} already has a different value "
            f"({current_value!r} vs {value!r}) — pass overwrite=True to replace it."
        )

    if record.field_name == "description":
        company.description = value
    elif record.field_name == "industry":
        company.industry = value
    elif record.field_name == "short_description":
        company.short_description = value
    elif record.field_name == "state":
        company.state = value
    else:
        company.city = value

    # No dedicated applied_by/applied_at column exists on either model
    # (a confirmed, accepted gap — see Module 8B's architectural
    # review) — recorded as a plain audit line on the record's own
    # review_note instead, matching this field's established use (only
    # ever set by this module's own review-decision functions), rather
    # than adding a migration for this phase.
    timestamp = datetime.now(UTC).isoformat()
    audit_line = (
        f"Applied to Company.{record.field_name} by {reviewer_id} at {timestamp} "
        f"(previous value: {current_value!r})."
    )
    record.review_note = (
        f"{record.review_note}\n{audit_line}" if record.review_note else audit_line
    )

    await db.commit()
    await db.refresh(company)
    await db.refresh(record)
    await audit_service.log_event(
        db,
        "provenance_applied_to_company",
        user_id=str(reviewer_id),
        metadata={
            "provenance_record_id": str(record.id),
            "company_id": str(company.id),
            "field_name": record.field_name,
            "overwrite": overwrite,
        },
    )
    return company


async def _apply_array_field_to_company(
    db: AsyncSession,
    record: ProvenanceRecord,
    company: Company,
    value: str,
    *,
    reviewer_id: uuid.UUID,
    overwrite: bool,
) -> Company:
    """
    The ARRAY(String) branch of apply_reviewed_field_to_company
    (Module 8C) — only ever called once the caller has already
    confirmed VERIFIED status, company/record match, and a non-empty
    stripped value; record.field_name is already confirmed present in
    _ARRAY_FIELD_LIMITS.

    Deliberately NOT the same overwrite/conflict semantics as the
    three scalar fields above: an array field has no single "current
    value" to conflict with, so there is no destructive-replace path
    at all — overwrite=True is rejected outright rather than silently
    ignored, since accepting it without effect would be misleading
    about what the call actually did.

    Exact, case-sensitive match against the existing list is this
    function's only notion of "already present" — reusing
    graph_service.create_capability's own exact-name idempotency
    convention rather than inventing fuzzy matching. A duplicate value
    is a true no-op: no commit, no audit event, matching
    apply_reviewed_field_to_company's own sibling idempotent patterns
    elsewhere in this codebase (e.g.
    graph_service.sync_company_capabilities_from_graph).
    """
    if overwrite:
        raise ArrayFieldOverwriteNotSupportedError(
            f"field_name {record.field_name!r} is an ARRAY(String) field — overwrite=True is "
            "not supported. Array fields are append-only and are never destructively replaced."
        )

    existing = list(getattr(company, record.field_name) or [])
    if value in existing:
        return company  # idempotent no-op — exact, case-sensitive match already present

    limit = _ARRAY_FIELD_LIMITS[record.field_name]
    if len(existing) + 1 > limit:
        raise ArrayLimitExceededError(
            f"Company.{record.field_name} already has {len(existing)} entries; appending "
            f"{value!r} would exceed the {limit}-entry cap for this field."
        )

    setattr(company, record.field_name, existing + [value])

    timestamp = datetime.now(UTC).isoformat()
    audit_line = (
        f"Appended {value!r} to Company.{record.field_name} by {reviewer_id} at {timestamp} "
        f"(list length {len(existing)} -> {len(existing) + 1})."
    )
    record.review_note = (
        f"{record.review_note}\n{audit_line}" if record.review_note else audit_line
    )

    await db.commit()
    await db.refresh(company)
    await db.refresh(record)
    await audit_service.log_event(
        db,
        "provenance_applied_to_company",
        user_id=str(reviewer_id),
        metadata={
            "provenance_record_id": str(record.id),
            "company_id": str(company.id),
            "field_name": record.field_name,
            "value_kind": "array_append",
            "resulting_length": len(existing) + 1,
        },
    )
    return company
