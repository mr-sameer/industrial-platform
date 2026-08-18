"""
Pilot orchestration service — Module 6B. Ties together Modules 5A–5F's
real, frozen, individually-tested primitives (source registration,
acquisition, entity resolution) into the sequence a real controlled
company pilot actually needs — nothing here duplicates or bypasses any
of them.

ZERO changes to any Module 5A-5F file. Every function below calls
into existing, unmodified service functions
(provenance_service.create_source/get_source,
acquisition_service.create_and_run_job,
entity_resolution_service.generate_candidate_for_observation) and
composes their results — this file contains no new persistence, no
new model, no new table.

THE LEGAL GATE (Part 4/7's requirement — "if a source is blocked/
restricted/pending review, do not execute production acquisition")
is enforced HERE, not inside acquisition_service.create_and_run_job.
Reasoning, checked directly before deciding: every existing test
across Modules 5B-5F creates sources without ever setting
collection_policy_status away from its real default
(PENDING_LEGAL_REVIEW) — enforcing this gate inside the frozen
acquisition service would break that entire established test pattern.
Enforcing it here, in new orchestration code that only a real pilot
run goes through, achieves the same real safety property (a
non-approved source never gets a production acquisition run against
it) without altering frozen 5A-5F behavior at all.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors import field_profiles
from app.models.entity_resolution_candidate import ResolutionState
from app.models.source_registry import CollectionPolicyStatus, SourceRegistry
from app.schemas.acquisition import AcquisitionJobCreate
from app.schemas.provenance import SourceRegistryCreate
from app.services import acquisition_service, entity_resolution_service, provenance_service


class SourceNotApprovedForPilotError(Exception):
    """Raised when a real (non-dry-run) pilot is attempted against a
    source whose collection_policy_status is not explicitly ALLOWED —
    the concrete enforcement of Part 4/7's legal gate for this specific
    orchestration path."""


@dataclass
class EntityResolutionSummary:
    total: int = 0
    new: int = 0
    auto_match: int = 0
    review_required: int = 0
    no_match: int = 0
    candidate_ids: list[uuid.UUID] = field(default_factory=list)


@dataclass
class PilotRunReport:
    source_id: uuid.UUID
    source_name: str
    collector_type: str
    dry_run: bool
    job_id: uuid.UUID | None
    job_status: str | None
    records_discovered_or_created: int
    records_skipped: int
    records_failed: int
    job_retry_count: int
    job_error_message: str | None
    entity_resolution: EntityResolutionSummary


async def get_or_create_pilot_source(
    db: AsyncSession, payload: SourceRegistryCreate
) -> tuple[SourceRegistry, bool]:
    """
    Idempotent by name — a real pilot re-run must not register a
    duplicate SourceRegistry row for the same real source. Returns
    (source, created) so a caller can distinguish "this source was
    already registered" from "just registered now," matching Part 6's
    own requirement to inspect and report source registration status
    before running anything.
    """
    existing = await provenance_service.list_sources(db)
    for source in existing:
        if source.name == payload.name:
            return source, False
    source = await provenance_service.create_source(db, payload)
    return source, True


def source_ready_for_production_pilot(source: SourceRegistry) -> bool:
    """THE legal gate check — see this module's own docstring."""
    return source.collection_policy_status == CollectionPolicyStatus.ALLOWED


async def resolve_entities_for_job(db: AsyncSession, job_id: uuid.UUID) -> EntityResolutionSummary:
    """
    The genuine orchestration gap this module closes: nothing in
    Module 5D provides "generate a candidate for every observation an
    acquisition job created" as a single operation — only "generate a
    candidate for one specific raw_observation_id" (real, unchanged,
    Module 5D's own entry point, called here once per CREATED event).
    """
    summary = EntityResolutionSummary()
    events, total = await acquisition_service.list_job_events(db, job_id, page=1, page_size=200)
    if total > len(events):
        # A real pilot is capped at 50 records (Section 9's own
        # enforced ceiling in MCADataGovInAdapter), so 200 is already
        # a generous single-page size — this branch exists only to
        # fail loudly, not silently under-report, if that assumption
        # is ever violated.
        raise RuntimeError(
            f"job {job_id} has more events ({total}) than this function paginated for (200)"
        )

    for event in events:
        if event.outcome.value != "created" or event.raw_observation_id is None:
            continue
        candidate = await entity_resolution_service.generate_candidate_for_observation(
            db, event.raw_observation_id
        )
        summary.total += 1
        summary.candidate_ids.append(candidate.id)
        if candidate.resolution_state == ResolutionState.NEW:
            summary.new += 1
        elif candidate.resolution_state == ResolutionState.AUTO_MATCH:
            summary.auto_match += 1
        elif candidate.resolution_state == ResolutionState.REVIEW_REQUIRED:
            summary.review_required += 1
        elif candidate.resolution_state == ResolutionState.NO_MATCH:
            summary.no_match += 1
    return summary


async def run_pilot(
    db: AsyncSession,
    *,
    source_payload: SourceRegistryCreate,
    collector_type: str,
    requested_scope: dict[str, object],
    created_by: uuid.UUID,
    dry_run: bool,
) -> PilotRunReport:
    """
    The full, real orchestration: register-or-reuse the source, apply
    the legal gate (real pilots only), run one real AcquisitionJob
    (Module 5B, unchanged), then run entity resolution for every
    observation it created (this module's own new, but purely
    orchestrating, function above).

    dry_run=True runs the identical sequence against whatever
    collector_type was actually passed (typically "mock",
    MockSourceAdapter — Module 5B's own real, deterministic test
    adapter) — this is not a separate, parallel "simulation" code
    path; it is the exact same function, exercised against a
    source/adapter that makes no real external network call, which is
    precisely what proves the orchestration logic itself is correct
    without needing live access.
    """
    source, _created = await get_or_create_pilot_source(db, source_payload)

    if not dry_run and not source_ready_for_production_pilot(source):
        raise SourceNotApprovedForPilotError(
            f"Source {source.name!r} has collection_policy_status="
            f"{source.collection_policy_status.value!r}, not 'allowed' — "
            "a real pilot must not run production acquisition against an "
            "unapproved source (Part 4/7's legal gate)."
        )

    job = await acquisition_service.create_and_run_job(
        db,
        AcquisitionJobCreate(
            source_id=source.id, collector_type=collector_type, requested_scope=requested_scope
        ),
        created_by=created_by,
    )

    # Module 6D Section 36: aggregate/trade sources (Census CBP, USITC
    # DataWeb — no registered app.collectors.field_profiles entry, by
    # design) never enter entity resolution at all, not even to
    # generate a harmless NO_MATCH row. Company-identity sources
    # (mca_data_gov_in, sec_edgar, manual_entry, mock) are unaffected —
    # this is the single guard that keeps every collector_type on the
    # one real pipeline (Section 85: "do not create a parallel
    # pipeline"), not a second orchestration path for USA sources.
    er_summary = EntityResolutionSummary()
    if (
        job.status.value == "succeeded"
        and job.result_count > 0
        and field_profiles.has_profile(collector_type)
    ):
        er_summary = await resolve_entities_for_job(db, job.id)

    return PilotRunReport(
        source_id=source.id,
        source_name=source.name,
        collector_type=collector_type,
        dry_run=dry_run,
        job_id=job.id,
        job_status=job.status.value,
        records_discovered_or_created=job.result_count,
        records_skipped=job.skipped_count,
        records_failed=job.failed_count,
        job_retry_count=job.retry_count,
        job_error_message=job.error_message,
        entity_resolution=er_summary,
    )
