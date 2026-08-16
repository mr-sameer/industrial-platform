"""
Acquisition service — Module 5B. Orchestrates one job's run:
source -> adapter.collect() -> idempotency check -> RawObservation
(via Module 5A's provenance_service, unchanged) -> AcquisitionJobEvent.

DATA TRUST RULE, enforced by omission: this file never creates a
ProvenanceRecord, never sets any status to VERIFIED, and never writes
to Company or Product. Everything this module produces is a
RawObservation — an OBSERVATION, per the architecture doc's Section 5
raw/canonical separation. Turning an observation into a
ProvenanceRecord (let alone a verified one) is a separate, later,
human- or extraction-driven action (Module 5A's own
create_provenance_record / verify_provenance_record) — deliberately
not invoked anywhere in this file.

IDEMPOTENCY STRATEGY (documented here, not just implemented): the key
is source_id + external_identifier when the adapter provides one —
this is the "stable external identifier" the ticket asks for, and
matches how a real source would naturally dedupe (the same URL, the
same registry record ID, collected again, is unambiguously "the same
thing"). Only when an adapter has no natural external identifier does
this fall back to source_id + content_hash — content_hash ALONE,
un-scoped to a source, is deliberately never used as a key: two
different sources could coincidentally produce byte-identical content
for two genuinely different real-world records (e.g. two companies
both submitting an empty/templated field), and a global hash key would
incorrectly treat them as the same observation. Scoping to source_id
first is what makes this safe.

RETRY STRATEGY (documented here): RetryableCollectorError triggers up
to MAX_RETRIES additional attempts (bounded, never infinite) with the
job's retry_count incremented each time; NonRetryableCollectorError
fails the job immediately with zero retries — retrying a failure
retrying cannot fix only delays an honest FAILED state.
"""

import hashlib
import json
import math
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import CollectedItem, NonRetryableCollectorError, RetryableCollectorError
from app.collectors.registry import UnknownCollectorTypeError, get_adapter
from app.collectors.secrets import redact_config
from app.models.acquisition_job import AcquisitionJob, AcquisitionJobStatus
from app.models.acquisition_job_event import AcquisitionEventOutcome, AcquisitionJobEvent
from app.models.raw_observation import RawObservation
from app.schemas.acquisition import AcquisitionJobCreate
from app.schemas.provenance import RawObservationCreate
from app.services import provenance_service
from app.services.provenance_service import SourceNotFoundError

MAX_RETRIES = 3


class InvalidJobConfigurationError(Exception):
    pass


def _content_hash_of(raw_content: dict[str, object]) -> str:
    canonical = json.dumps(raw_content, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _find_existing_observation(
    db: AsyncSession, source_id: uuid.UUID, item: CollectedItem
) -> RawObservation | None:
    """The idempotency check — see this module's own docstring for the
    full strategy and why content_hash is never used un-scoped to a
    source."""
    if item.external_identifier is not None:
        result = await db.execute(
            select(RawObservation).where(
                RawObservation.source_id == source_id,
                RawObservation.external_reference == item.external_identifier,
            )
        )
    else:
        result = await db.execute(
            select(RawObservation).where(
                RawObservation.source_id == source_id,
                RawObservation.content_hash == item.content_hash,
            )
        )
    return result.scalar_one_or_none()


async def create_and_run_job(
    db: AsyncSession, payload: AcquisitionJobCreate, *, created_by: uuid.UUID
) -> AcquisitionJob:
    """
    Creates a job and runs it to a deterministic terminal state
    (SUCCEEDED, FAILED, or — for a structurally invalid request caught
    before any row is even written — raises before a job exists at
    all) within this single call. Synchronous by design in this
    phase — no background task queue exists yet (an explicitly
    documented limitation, not an oversight; see this module's
    completion report).
    """
    source = await provenance_service.get_source(db, payload.source_id)
    if source is None:
        raise SourceNotFoundError(str(payload.source_id))

    try:
        adapter = get_adapter(payload.collector_type)
    except UnknownCollectorTypeError as exc:
        raise InvalidJobConfigurationError(str(exc)) from exc

    safe_scope = redact_config(payload.requested_scope)
    job = AcquisitionJob(
        source_id=payload.source_id,
        collector_type=payload.collector_type,
        status=AcquisitionJobStatus.PENDING,
        requested_scope=safe_scope,
        created_by=created_by,
    )
    db.add(job)
    await db.flush()  # job.id needed before any event can reference it

    try:
        adapter.validate_config(payload.requested_scope)
    except NonRetryableCollectorError as exc:
        job.status = AcquisitionJobStatus.FAILED
        job.error_message = _safe_error_message(exc, payload.requested_scope)
        job.completed_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(job)
        return job

    job.status = AcquisitionJobStatus.RUNNING
    job.started_at = datetime.now(UTC)
    await db.flush()

    items: list[CollectedItem] | None = None
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            items = adapter.collect(payload.requested_scope)
            break
        except RetryableCollectorError as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                job.retry_count += 1
                await db.flush()
                continue
            # Retries exhausted — falls through to the FAILED branch below.
        except NonRetryableCollectorError as exc:
            last_error = exc
            break
        except Exception as exc:  # noqa: BLE001 — an unexpected collector bug must still reach a deterministic FAILED state, never an unhandled 500 that leaves the job stuck RUNNING
            last_error = exc
            break

    if items is None:
        job.status = AcquisitionJobStatus.FAILED
        job.error_message = _safe_error_message(last_error, payload.requested_scope)
        job.completed_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(job)
        return job

    created = 0
    skipped = 0
    failed = 0
    for item in items:
        try:
            existing = await _find_existing_observation(db, payload.source_id, item)
            if existing is not None:
                db.add(
                    AcquisitionJobEvent(
                        job_id=job.id,
                        outcome=AcquisitionEventOutcome.SKIPPED_DUPLICATE,
                        external_identifier=item.external_identifier,
                        raw_observation_id=existing.id,
                    )
                )
                skipped += 1
                continue

            observation = await provenance_service.create_raw_observation(
                db,
                RawObservationCreate(
                    source_id=payload.source_id,
                    external_reference=item.external_identifier,
                    raw_content=item.raw_content,
                    content_hash=item.content_hash,
                    collection_method_used=source.collection_method,
                    collected_at=datetime.now(UTC),
                ),
            )
            db.add(
                AcquisitionJobEvent(
                    job_id=job.id,
                    outcome=AcquisitionEventOutcome.CREATED,
                    external_identifier=item.external_identifier,
                    raw_observation_id=observation.id,
                )
            )
            created += 1
        except Exception as exc:  # noqa: BLE001 — one bad item must not abort the whole job; every item gets its own deterministic outcome (partial failure handling)
            db.add(
                AcquisitionJobEvent(
                    job_id=job.id,
                    outcome=AcquisitionEventOutcome.FAILED,
                    external_identifier=item.external_identifier,
                    error_message=_safe_error_message(exc, payload.requested_scope),
                )
            )
            failed += 1

    job.result_count = created
    job.skipped_count = skipped
    job.failed_count = failed
    # A job that collected nothing but real, individually-recorded
    # per-item failures is honestly FAILED, not SUCCEEDED — never
    # fabricate success when every single item failed.
    job.status = (
        AcquisitionJobStatus.FAILED
        if created == 0 and failed > 0 and skipped == 0
        else AcquisitionJobStatus.SUCCEEDED
    )
    if job.status == AcquisitionJobStatus.FAILED:
        job.error_message = (
            f"All {failed} collected item(s) failed to process — see job events for detail."
        )
    job.completed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(job)
    return job


def _safe_error_message(exc: Exception | None, config: dict[str, object]) -> str:
    """
    Never includes raw config (which may contain credential-shaped
    values even though this phase's MockSourceAdapter has none) —
    always routes through redact_config first, matching this module's
    security requirement that credentials never appear in error
    messages.
    """
    redacted = redact_config(config)
    base = str(exc) if exc is not None else "Unknown error"
    return f"{base} (config: {redacted})" if redacted else base


async def get_job(db: AsyncSession, job_id: uuid.UUID) -> AcquisitionJob | None:
    result = await db.execute(select(AcquisitionJob).where(AcquisitionJob.id == job_id))
    return result.scalar_one_or_none()


async def list_jobs(
    db: AsyncSession,
    *,
    source_id: uuid.UUID | None,
    status_filter: AcquisitionJobStatus | None,
    page: int,
    page_size: int,
) -> tuple[list[AcquisitionJob], int]:
    query = select(AcquisitionJob)
    if source_id is not None:
        query = query.where(AcquisitionJob.source_id == source_id)
    if status_filter is not None:
        query = query.where(AcquisitionJob.status == status_filter)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = int(count_result.scalar_one())

    query = (
        query.order_by(AcquisitionJob.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    return list(result.scalars().all()), total


async def list_job_events(
    db: AsyncSession, job_id: uuid.UUID, *, page: int, page_size: int
) -> tuple[list[AcquisitionJobEvent], int]:
    query = select(AcquisitionJobEvent).where(AcquisitionJobEvent.job_id == job_id)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = int(count_result.scalar_one())

    query = (
        query.order_by(AcquisitionJobEvent.created_at.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    return list(result.scalars().all()), total


def total_pages(total: int, page_size: int) -> int:
    return max(1, math.ceil(total / page_size))
