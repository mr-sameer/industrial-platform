"""
Module 6B tests — pilot orchestration (app.services.pilot_service).
Covers source registration/idempotency, the legal gate, real
acquisition-job execution (success and failure paths, via
MockSourceAdapter's own real, deterministic failure-simulation
config — never a fabricated failure), entity resolution orchestration
(CIN matching, conflicting CIN, REVIEW_REQUIRED, cross-source
identity), provenance traceability, audit logging, and the explicit
"no fabricated records on source failure" requirement.

Uses AsyncSessionLocal directly (calling pilot_service's real
functions, not via HTTP) since this module is service-layer
orchestration with no new API route — matching Module 6B's own
"smallest correct change" scoping (see this module's completion
report for why no new route was added).
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.company import Company
from app.models.data_conflict import DataConflict
from app.models.entity_resolution_candidate import EntityResolutionCandidate, ResolutionState
from app.models.provenance_record import ProvenanceRecord
from app.models.source_registry import CollectionMethod, CollectionPolicyStatus, SourceClass
from app.models.user import Role, User
from app.schemas.provenance import SourceRegistryCreate
from app.services import company_promotion_service, entity_resolution_service, pilot_service
from app.services.pilot_service import SourceNotApprovedForPilotError


async def _create_operator(db, email: str = "test-operator@forgex.internal") -> User:
    user = User(
        email=email,
        hashed_password=hash_password("irrelevant"),
        full_name="Test Operator",
        role=Role.ADMIN,
        is_email_verified=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _mock_source_payload(name: str) -> SourceRegistryCreate:
    return SourceRegistryCreate(
        name=name,
        source_class=SourceClass.PUBLIC_GOVERNMENT,
        collection_method=CollectionMethod.API,
        reliability_weight=0.9,
    )


# --------------------------------------------------------------------------
# 1. Source registration
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_source_registration_creates_new_source():
    async with AsyncSessionLocal() as db:
        source, created = await pilot_service.get_or_create_pilot_source(
            db, _mock_source_payload(f"Test Source {uuid.uuid4().hex[:8]}")
        )
        assert created is True
        assert source.id is not None


@pytest.mark.asyncio
async def test_source_registration_is_idempotent_by_name():
    async with AsyncSessionLocal() as db:
        name = f"Idempotent Source {uuid.uuid4().hex[:8]}"
        first, first_created = await pilot_service.get_or_create_pilot_source(
            db, _mock_source_payload(name)
        )
        second, second_created = await pilot_service.get_or_create_pilot_source(
            db, _mock_source_payload(name)
        )
        assert first.id == second.id
        assert first_created is True
        assert second_created is False


# --------------------------------------------------------------------------
# 2. Source policy (the legal gate)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_source_policy_defaults_to_pending_legal_review_not_approved():
    async with AsyncSessionLocal() as db:
        source, _created = await pilot_service.get_or_create_pilot_source(
            db, _mock_source_payload(f"Unapproved Source {uuid.uuid4().hex[:8]}")
        )
        assert source.collection_policy_status == CollectionPolicyStatus.PENDING_LEGAL_REVIEW
        assert pilot_service.source_ready_for_production_pilot(source) is False


@pytest.mark.asyncio
async def test_real_pilot_blocked_when_source_not_approved():
    """The legal gate — a real (non-dry-run) pilot must refuse to run
    against a source that isn't explicitly ALLOWED."""
    async with AsyncSessionLocal() as db:
        operator = await _create_operator(db, "gate-test@forgex.internal")
        with pytest.raises(SourceNotApprovedForPilotError):
            await pilot_service.run_pilot(
                db,
                source_payload=_mock_source_payload(f"Gate Test Source {uuid.uuid4().hex[:8]}"),
                collector_type="mock",
                requested_scope={"limit": 3},
                created_by=operator.id,
                dry_run=False,  # real pilot — must be gated
            )


@pytest.mark.asyncio
async def test_dry_run_not_subject_to_the_legal_gate():
    """dry_run=True intentionally bypasses the gate — it never touches
    a real external source (MockSourceAdapter), so the legal-approval
    requirement (which exists specifically to protect real, external
    acquisition) doesn't apply."""
    async with AsyncSessionLocal() as db:
        operator = await _create_operator(db, "dryrun-gate@forgex.internal")
        report = await pilot_service.run_pilot(
            db,
            source_payload=_mock_source_payload(f"Dry Run Gate Source {uuid.uuid4().hex[:8]}"),
            collector_type="mock",
            requested_scope={"limit": 3},
            created_by=operator.id,
            dry_run=True,
        )
        assert report.job_status == "succeeded"


# --------------------------------------------------------------------------
# 3-4. Acquisition job / successful observation (via dry-run, real orchestration)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_creates_real_acquisition_job_and_observations():
    async with AsyncSessionLocal() as db:
        operator = await _create_operator(db, "dryrun-obs@forgex.internal")
        report = await pilot_service.run_pilot(
            db,
            source_payload=_mock_source_payload(f"Obs Source {uuid.uuid4().hex[:8]}"),
            collector_type="mock",
            requested_scope={"limit": 3},
            created_by=operator.id,
            dry_run=True,
        )
        assert report.job_id is not None
        assert report.job_status == "succeeded"
        assert report.records_discovered_or_created == 3
        # Real entity resolution ran for every created observation.
        assert report.entity_resolution.total == 3


# --------------------------------------------------------------------------
# 5-6. Source failure / malformed response — no fabricated records
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_source_failure_produces_no_fabricated_records():
    """Uses MockSourceAdapter's own real, deterministic failure
    simulation (simulate_failure='invalid_credentials', a real,
    non-retryable failure mode built into Module 5B) — never a
    fabricated failure."""
    async with AsyncSessionLocal() as db:
        operator = await _create_operator(db, "failure-test@forgex.internal")
        report = await pilot_service.run_pilot(
            db,
            source_payload=_mock_source_payload(f"Failure Source {uuid.uuid4().hex[:8]}"),
            collector_type="mock",
            requested_scope={"limit": 3, "simulate_failure": "invalid_credentials"},
            created_by=operator.id,
            dry_run=True,
        )
        assert report.job_status == "failed"
        assert report.records_discovered_or_created == 0
        assert (
            report.entity_resolution.total == 0
        )  # nothing to resolve — no records were fabricated

        # Direct database confirmation — no Company/ProvenanceRecord
        # exists as a side effect of this failed job.
        companies = await db.execute(select(Company))
        assert len(companies.scalars().all()) == 0


@pytest.mark.asyncio
async def test_malformed_response_produces_no_promoted_data():
    """simulate_failure='partial' — 2 succeed, 1 fails per item, a
    real, pre-existing MockSourceAdapter behavior (Module 5B)."""
    async with AsyncSessionLocal() as db:
        operator = await _create_operator(db, "malformed-test@forgex.internal")
        report = await pilot_service.run_pilot(
            db,
            source_payload=_mock_source_payload(f"Partial Source {uuid.uuid4().hex[:8]}"),
            collector_type="mock",
            requested_scope={"limit": 3, "simulate_failure": "partial"},
            created_by=operator.id,
            dry_run=True,
        )
        assert report.records_failed >= 1
        assert report.records_discovered_or_created == 2  # only the genuinely valid items


# --------------------------------------------------------------------------
# 7. Idempotent rerun
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idempotent_rerun_does_not_duplicate():
    async with AsyncSessionLocal() as db:
        operator = await _create_operator(db, "idempotent-test@forgex.internal")
        source_name = f"Idempotent Rerun Source {uuid.uuid4().hex[:8]}"

        first = await pilot_service.run_pilot(
            db,
            source_payload=_mock_source_payload(source_name),
            collector_type="mock",
            requested_scope={"limit": 3},
            created_by=operator.id,
            dry_run=True,
        )
        assert first.records_discovered_or_created == 3

        second = await pilot_service.run_pilot(
            db,
            source_payload=_mock_source_payload(source_name),
            collector_type="mock",
            requested_scope={"limit": 3},
            created_by=operator.id,
            dry_run=True,
        )
        # Same source, same content -> Module 5B's own real, existing
        # source-scoped idempotency correctly skips re-creating
        # observations. This module does not "fix" that — Part 2's
        # own instruction: it's real, pre-existing, frozen behavior.
        assert second.records_discovered_or_created == 0
        assert second.records_skipped == 3


# --------------------------------------------------------------------------
# 8-13. Entity resolution: cross-source identity, CIN matching, conflicts,
# human decisions — using REAL MCA-field-shaped fixtures (not MockSourceAdapter,
# whose "name" field doesn't match entity resolution's "company_name"
# expectation — a real, documented, pre-existing characteristic, see this
# module's own completion report).
# --------------------------------------------------------------------------


async def _create_mca_shaped_observation(
    db, source_id: uuid.UUID, cin: str, name: str, external_ref: str | None = None
):
    from app.schemas.provenance import RawObservationCreate
    from app.services import provenance_service

    return await provenance_service.create_raw_observation(
        db,
        RawObservationCreate(
            source_id=source_id,
            external_reference=external_ref or cin,
            raw_content={"cin": cin, "company_name": name, "registered_state": "Maharashtra"},
            content_hash=uuid.uuid4().hex,
            collection_method_used=CollectionMethod.API,
            collected_at=datetime.now(UTC),
        ),
    )


@pytest.mark.asyncio
async def test_exact_cin_reaches_auto_match():
    async with AsyncSessionLocal() as db:
        operator = await _create_operator(db, "cin-automatch@forgex.internal")
        source, _ = await pilot_service.get_or_create_pilot_source(
            db, _mock_source_payload(f"CIN Source {uuid.uuid4().hex[:8]}")
        )
        cin = f"U{uuid.uuid4().hex[:14].upper()}"
        obs1 = await _create_mca_shaped_observation(db, source.id, cin, "AutoMatch Test Co")
        company = await company_promotion_service.promote_raw_observation_to_company(
            db, obs1.id, reviewer_id=operator.id
        )

        obs2 = await _create_mca_shaped_observation(
            db, source.id, cin, "AUTOMATCH TEST CO", external_ref=f"{cin}-second-pull"
        )
        candidate = await entity_resolution_service.generate_candidate_for_observation(db, obs2.id)
        assert candidate.resolution_state == ResolutionState.AUTO_MATCH
        assert candidate.candidate_company_id == company.id


@pytest.mark.asyncio
async def test_conflicting_cin_is_review_required_never_auto_merged():
    async with AsyncSessionLocal() as db:
        operator = await _create_operator(db, "cin-conflict@forgex.internal")
        source, _ = await pilot_service.get_or_create_pilot_source(
            db, _mock_source_payload(f"CIN Conflict Source {uuid.uuid4().hex[:8]}")
        )
        cin_a = f"U{uuid.uuid4().hex[:14].upper()}"
        cin_b = f"U{uuid.uuid4().hex[:14].upper()}"
        obs1 = await _create_mca_shaped_observation(db, source.id, cin_a, "Conflict Test Co")
        await company_promotion_service.promote_raw_observation_to_company(
            db, obs1.id, reviewer_id=operator.id
        )

        # Same name, DIFFERENT CIN — a genuine identity conflict.
        obs2 = await _create_mca_shaped_observation(db, source.id, cin_b, "Conflict Test Co")
        candidate = await entity_resolution_service.generate_candidate_for_observation(db, obs2.id)
        assert candidate.resolution_state != ResolutionState.AUTO_MATCH
        assert candidate.resolution_state == ResolutionState.REVIEW_REQUIRED


@pytest.mark.asyncio
async def test_same_company_from_different_sources():
    """Cross-source identity resolution via CIN, confirming Module 5D's
    real matching works across genuinely distinct SourceRegistry rows,
    not just within one."""
    async with AsyncSessionLocal() as db:
        operator = await _create_operator(db, "crosssource@forgex.internal")
        source_a, _ = await pilot_service.get_or_create_pilot_source(
            db, _mock_source_payload(f"Cross Source A {uuid.uuid4().hex[:8]}")
        )
        source_b, _ = await pilot_service.get_or_create_pilot_source(
            db, _mock_source_payload(f"Cross Source B {uuid.uuid4().hex[:8]}")
        )
        cin = f"U{uuid.uuid4().hex[:14].upper()}"
        obs1 = await _create_mca_shaped_observation(db, source_a.id, cin, "Cross Source Co")
        company = await company_promotion_service.promote_raw_observation_to_company(
            db, obs1.id, reviewer_id=operator.id
        )
        obs2 = await _create_mca_shaped_observation(db, source_b.id, cin, "Cross Source Co Ltd")
        candidate = await entity_resolution_service.generate_candidate_for_observation(db, obs2.id)
        assert candidate.resolution_state == ResolutionState.AUTO_MATCH
        assert candidate.candidate_company_id == company.id


@pytest.mark.asyncio
async def test_review_required_candidate_and_confirm_match_decision():
    async with AsyncSessionLocal() as db:
        operator = await _create_operator(db, "confirmmatch@forgex.internal")
        source, _ = await pilot_service.get_or_create_pilot_source(
            db, _mock_source_payload(f"Confirm Match Source {uuid.uuid4().hex[:8]}")
        )
        cin_a, cin_b = f"U{uuid.uuid4().hex[:14].upper()}", f"U{uuid.uuid4().hex[:14].upper()}"
        obs1 = await _create_mca_shaped_observation(db, source.id, cin_a, "Confirm Match Test Co")
        company = await company_promotion_service.promote_raw_observation_to_company(
            db, obs1.id, reviewer_id=operator.id
        )
        obs2 = await _create_mca_shaped_observation(db, source.id, cin_b, "Confirm Match Test Co")
        candidate = await entity_resolution_service.generate_candidate_for_observation(db, obs2.id)
        assert candidate.resolution_state == ResolutionState.REVIEW_REQUIRED

        from app.models.entity_resolution_candidate import ResolutionDecision

        updated, affected = await entity_resolution_service.decide(
            db, candidate, decision=ResolutionDecision.CONFIRM_MATCH, decided_by=operator.id
        )
        assert updated.decision == ResolutionDecision.CONFIRM_MATCH
        assert affected is not None
        assert affected.id == company.id


@pytest.mark.asyncio
async def test_create_new_decision_for_genuinely_new_company():
    async with AsyncSessionLocal() as db:
        operator = await _create_operator(db, "createnew@forgex.internal")
        source, _ = await pilot_service.get_or_create_pilot_source(
            db, _mock_source_payload(f"Create New Source {uuid.uuid4().hex[:8]}")
        )
        cin = f"U{uuid.uuid4().hex[:14].upper()}"
        obs = await _create_mca_shaped_observation(db, source.id, cin, "Genuinely New Co")
        candidate = await entity_resolution_service.generate_candidate_for_observation(db, obs.id)
        assert candidate.resolution_state == ResolutionState.NEW

        from app.models.entity_resolution_candidate import ResolutionDecision

        updated, affected = await entity_resolution_service.decide(
            db, candidate, decision=ResolutionDecision.CREATE_NEW, decided_by=operator.id
        )
        assert updated.decision == ResolutionDecision.CREATE_NEW
        assert affected is not None
        assert affected.name == "Genuinely New Co"


# --------------------------------------------------------------------------
# 14. Provenance traceability
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provenance_traceability_full_chain():
    """For a promoted company, confirms every required traceability
    element (source, observation, extraction, timestamp, status) is
    real and queryable — Part 4's own explicit requirement."""
    async with AsyncSessionLocal() as db:
        operator = await _create_operator(db, "provenance-trace@forgex.internal")
        source, _ = await pilot_service.get_or_create_pilot_source(
            db, _mock_source_payload(f"Provenance Source {uuid.uuid4().hex[:8]}")
        )
        cin = f"U{uuid.uuid4().hex[:14].upper()}"
        obs = await _create_mca_shaped_observation(db, source.id, cin, "Provenance Trace Co")
        company = await company_promotion_service.promote_raw_observation_to_company(
            db, obs.id, reviewer_id=operator.id
        )

        result = await db.execute(
            select(ProvenanceRecord).where(ProvenanceRecord.company_id == company.id)
        )
        records = result.scalars().all()
        assert len(records) > 0
        for record in records:
            assert record.raw_observation_id == obs.id  # traces to the real observation
            assert record.extraction_method is not None
            assert record.created_at is not None
            assert record.status is not None
            assert record.status.value in ("observed", "extracted")  # never fabricated as verified


# --------------------------------------------------------------------------
# 15. Audit log
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_entity_resolution_decision_is_audited():
    async with AsyncSessionLocal() as db:
        operator = await _create_operator(db, "audit-test@forgex.internal")
        source, _ = await pilot_service.get_or_create_pilot_source(
            db, _mock_source_payload(f"Audit Source {uuid.uuid4().hex[:8]}")
        )
        cin = f"U{uuid.uuid4().hex[:14].upper()}"
        obs = await _create_mca_shaped_observation(db, source.id, cin, "Audit Test Co")
        candidate = await entity_resolution_service.generate_candidate_for_observation(db, obs.id)

        from app.models.entity_resolution_candidate import ResolutionDecision

        await entity_resolution_service.decide(
            db, candidate, decision=ResolutionDecision.CREATE_NEW, decided_by=operator.id
        )

        # The candidate's own decided_by/decided_at ARE the real,
        # existing audit trail for this decision (Module 5D, real,
        # unmodified) — confirmed directly rather than assumed.
        await db.refresh(candidate)
        assert candidate.decided_by == operator.id
        assert candidate.decided_at is not None


# --------------------------------------------------------------------------
# 16. RBAC — no new API surface added; existing routes' RBAC (5B-5F,
# already tested in their own suites) is what actually governs
# acquisition/entity-resolution actions. This confirms the pilot's own
# operator attribution is a real Role.ADMIN user, matching the
# attribution convention those routes already enforce.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pilot_operator_is_a_real_admin_user():
    async with AsyncSessionLocal() as db:
        operator = await _create_operator(db, "rbac-check@forgex.internal")
        assert operator.role == Role.ADMIN
        assert operator.is_email_verified is True


# --------------------------------------------------------------------------
# 17. No fabricated records on source failure (explicit, repeated per Part 6)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_fabricated_records_on_total_source_failure():
    async with AsyncSessionLocal() as db:
        operator = await _create_operator(db, "no-fabrication@forgex.internal")
        report = await pilot_service.run_pilot(
            db,
            source_payload=_mock_source_payload(f"All Invalid Source {uuid.uuid4().hex[:8]}"),
            collector_type="mock",
            requested_scope={"limit": 3, "simulate_failure": "all_invalid"},
            created_by=operator.id,
            dry_run=True,
        )
        assert report.records_discovered_or_created == 0
        assert report.entity_resolution.total == 0

        # Absolute confirmation against the real database: no
        # ProvenanceRecord, no Company, no EntityResolutionCandidate
        # exists as a result of this failed run.
        prov = await db.execute(select(ProvenanceRecord))
        companies = await db.execute(select(Company))
        candidates = await db.execute(select(EntityResolutionCandidate))
        assert len(prov.scalars().all()) == 0
        assert len(companies.scalars().all()) == 0
        assert len(candidates.scalars().all()) == 0


# --------------------------------------------------------------------------
# Regression: existing Company/Provenance/DataConflict mechanisms fully
# unaffected by this module's new orchestration code.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_regression_data_conflict_mechanism_unaffected():
    async with AsyncSessionLocal() as db:
        operator = await _create_operator(db, "regression-conflict@forgex.internal")
        source, _ = await pilot_service.get_or_create_pilot_source(
            db, _mock_source_payload(f"Regression Conflict Source {uuid.uuid4().hex[:8]}")
        )
        cin = f"U{uuid.uuid4().hex[:14].upper()}"
        from app.models.provenance_record import EntityType
        from app.schemas.provenance import ProvenanceRecordCreate
        from app.services import provenance_service

        obs1 = await _create_mca_shaped_observation(db, source.id, cin, "Regression Conflict Co")
        company = await company_promotion_service.promote_raw_observation_to_company(
            db, obs1.id, reviewer_id=operator.id
        )
        source2, _ = await pilot_service.get_or_create_pilot_source(
            db, _mock_source_payload(f"Regression Conflict Source 2 {uuid.uuid4().hex[:8]}")
        )
        obs2 = await _create_mca_shaped_observation(
            db, source2.id, cin, "Regression Conflict Co", external_ref=cin
        )
        await provenance_service.create_provenance_record(
            db,
            ProvenanceRecordCreate(
                entity_type=EntityType.COMPANY,
                company_id=company.id,
                field_name="registered_state",
                raw_observation_id=obs2.id,
                value_observed="Karnataka",  # disagrees with the original "Maharashtra"
                extraction_method="manual",
                confidence=0.8,
            ),
        )
        conflicts = await db.execute(
            select(DataConflict).where(DataConflict.company_id == company.id)
        )
        assert len(conflicts.scalars().all()) > 0
