"""
Company promotion service — Module 5C, generalized in Module 6D. The
explicit, human-gated "review -> canonical Company" step
(Section 5C.6/5C.7 of the approved architecture). Deliberately generic
in its control flow — not MCA-specific — so any future source's raw
observations can be promoted through the same path, matching this
ticket's own instruction not to hard-code source-specific logic
outside the adapter layer. The source-specific *field mapping* (which
raw_content keys map to which Company fields) now lives entirely in
app.collectors.field_profiles, one SourceFieldProfile per
collector_type — see that module's docstring for why this file used to
hardcode MCA's field names directly here, and why Module 6D moved that
mapping out rather than duplicating it a second time for SEC.

REAL ARCHITECTURAL CONSTRAINT FOUND WHILE BUILDING THIS (documented
here, and in this module's completion report, not silently worked
around): Module 5A's ProvenanceRecord (frozen, not modified) has a
real, enforced CHECK constraint requiring exactly one of
company_id/product_id to already exist — a ProvenanceRecord cannot be
created "standalone," pointing at nothing yet. This means the naive
reading of the pipeline diagram (RAW OBSERVATION -> PROVENANCE -> ... ->
CANONICAL COMPANY, provenance existing *before* the Company row) is not
achievable without modifying Module 5A, which this phase's instructions
prohibit. The order actually implemented here is: the Company row is
created first (directly from the raw observation's content, after the
CIN duplicate check), and ProvenanceRecords are then created
immediately afterward, retroactively linking each mapped field to the
company that was just created — both steps happen inside the same
promote_raw_observation_to_company call, so from the caller's
perspective a Company never exists even momentarily without its
provenance. This still fully preserves the OBSERVED/EXTRACTED/VERIFIED
distinction (nothing here is ever created as VERIFIED), which is the
property that actually matters — only the literal ordering in the
pipeline diagram is adjusted, and adjusted for a real, confirmed
reason, not a convenience shortcut.

DATA TRUST RULE, enforced directly: this function never sets
Company.verification_status to anything other than its own model
default — a promoted company is exactly as "ForgeX Verified" as one
created through the ordinary POST /companies flow (Module 3A), which
is to say: not automatically, at all. Source-backed existence (this
pilot), ForgeX verification (Module 3B's own, separate, self-reported-
completeness system), and a company's own future claim of its profile
(Module 3B's existing membership system) are three distinct things
this function is careful never to conflate.

Reuses app.services.company_service.create_company and
app.services.provenance_service.create_provenance_record completely
unchanged — no Company-domain or provenance logic is duplicated here.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.field_profiles import SourceFieldProfile, resolve_profile_for_content
from app.collectors.normalization import parse_registration_date
from app.models.company import Company
from app.models.provenance_record import EntityType, ExtractionMethod, ProvenanceStatus
from app.models.raw_observation import RawObservation
from app.schemas.company import CompanyCreate
from app.schemas.provenance import ProvenanceRecordCreate
from app.services import company_service, provenance_service

__all__ = [
    "DuplicateCinError",
    "RawObservationNotFoundForPromotionError",
    "MissingRequiredFieldError",
    "find_existing_company_by_cin",
    "promote_raw_observation_to_company",
]


class DuplicateCinError(Exception):
    """Raised when a Company already exists with the CIN this
    observation would introduce — the HIGH-confidence duplicate tier
    (architecture doc Section 7). Never auto-merged; this is always a
    hard stop requiring human decision-making outside this function."""


class RawObservationNotFoundForPromotionError(Exception):
    pass


class MissingRequiredFieldError(Exception):
    """Raised when the raw observation doesn't include the field
    Company creation genuinely requires (a name) — never silently
    defaulted or invented (architecture doc Section 4: "Do NOT invent
    missing values")."""


async def find_existing_company_by_cin(db: AsyncSession, cin: str) -> Company | None:
    result = await db.execute(select(Company).where(Company.cin == cin))
    return result.scalar_one_or_none()


def _get_str(content: dict[str, object], key: str) -> str | None:
    """RawObservation.raw_content is typed dict[str, object] (Module
    5A's own model) — this narrows a looked-up value to str | None
    explicitly, rather than assuming the runtime shape mypy can't see
    through a bare .get() call."""
    value = content.get(key)
    if value is None:
        return None
    return str(value)


async def _get_raw_observation(db: AsyncSession, raw_observation_id: uuid.UUID) -> RawObservation:
    observation = await provenance_service.get_raw_observation(db, raw_observation_id)
    if observation is None:
        raise RawObservationNotFoundForPromotionError(str(raw_observation_id))
    return observation


async def promote_raw_observation_to_company(
    db: AsyncSession, raw_observation_id: uuid.UUID, *, reviewer_id: uuid.UUID
) -> Company:
    """
    The one and only path in this module that creates a Company from
    acquired data — always explicit (a human reviewer's own API call,
    never triggered automatically by acquisition itself), always after
    the CIN duplicate check below.

    Module 6D: field extraction is now per-collector_type (see
    app.collectors.field_profiles) rather than hardcoded to MCA's field
    names — this function's own control flow (CIN check -> required-name
    check -> create -> set cin/registration_date -> provenance) is
    otherwise unchanged from Module 5C.
    """
    observation = await _get_raw_observation(db, raw_observation_id)
    content = observation.raw_content
    profile = await resolve_profile_for_content(db, raw_observation_id, content)
    identity = profile.extract(content)

    if identity.strong_id:
        existing = await find_existing_company_by_cin(db, identity.strong_id)
        if existing is not None:
            raise DuplicateCinError(
                f"cin={identity.strong_id} already exists as company_id={existing.id}"
            )

    if not identity.name:
        raise MissingRequiredFieldError(
            "No company name in this raw observation — cannot create a Company without a name."
        )

    payload = CompanyCreate(
        # Every profile's `name` is already the entity's registered/
        # legal name (not a separate trade name) — using it for both
        # Company fields is accurate, not a placeholder guess
        # (mirrors MCA's own Section 4 reasoning, generalized).
        name=identity.name,
        legal_name=identity.name,
        industry=identity.industry,
        country=identity.country,
        state=identity.state,
        city=identity.city,
        website=identity.website,
    )

    company = await company_service.create_company(db, owner_user_id=reviewer_id, payload=payload)

    # CompanyCreate has no cin/business_registration_date fields
    # (Module 3A's own schema, unmodified) — set directly on the
    # already-created ORM row rather than changing that schema's
    # contract, which would be exactly the kind of Company-domain
    # change this module's own instructions prohibit. Only ever set
    # from identity.strong_id — never from a non-CIN identifier (see
    # app.collectors.field_profiles's own docstring on why SEC's CIK
    # is deliberately never written here).
    if identity.strong_id:
        company.cin = identity.strong_id
    registration_date = parse_registration_date(_get_str(content, "date_of_registration"))
    if registration_date:
        company.business_registration_date = registration_date
    await db.commit()
    await db.refresh(company)

    await _create_provenance_for_promoted_company(db, company, observation, profile)
    return company


async def _create_provenance_for_promoted_company(
    db: AsyncSession, company: Company, observation: RawObservation, profile: SourceFieldProfile
) -> None:
    """
    Creates a ProvenanceRecord for every field present in the raw
    observation — both the ones that made it onto a real Company
    column (profile.direct_fields, extraction_method=rule_based, a
    direct or lightly-transformed mapping) and the ones that don't
    (profile.extra_fields, extraction_method=manual/observed,
    preserved for traceability per "Do NOT silently discard
    provenance" even though no Company column exists for them yet).
    Every record is created at status=observed or extracted — NEVER
    verified, matching provenance_service's own enforcement
    (verification is only ever a distinct, later,
    provenance_service.verify_provenance_record call).
    """
    content = observation.raw_content

    for field_name in (*profile.direct_fields, *profile.extra_fields):
        value = _get_str(content, field_name)
        if not value:
            continue
        is_direct = field_name in profile.direct_fields
        await provenance_service.create_provenance_record(
            db,
            ProvenanceRecordCreate(
                entity_type=EntityType.COMPANY,
                company_id=company.id,
                field_name=field_name,
                raw_observation_id=observation.id,
                value_observed=value,
                extraction_method=ExtractionMethod.RULE_BASED
                if is_direct
                else ExtractionMethod.MANUAL,
                confidence=0.8 if is_direct else 0.5,
                status=ProvenanceStatus.EXTRACTED if is_direct else ProvenanceStatus.OBSERVED,
            ),
        )
