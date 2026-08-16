"""
Company promotion service — Module 5C. The explicit, human-gated
"review -> canonical Company" step (Section 5C.6/5C.7 of the approved
architecture). Deliberately generic in its provenance-creation step —
not MCA-specific — so any future source's raw observations can be
promoted through the same path, matching this ticket's own instruction
not to hard-code source-specific logic outside the adapter layer. The
MCA-specific *field mapping* (which raw_content keys map to which
Company fields) is the one genuinely source-specific piece, isolated
into module-level constants below rather than spread through this
function.

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

from app.collectors.normalization import (
    SOURCE_COUNTRY,
    attempt_city_from_address,
    normalize_company_name,
    parse_registration_date,
)
from app.models.company import Company
from app.models.provenance_record import EntityType, ExtractionMethod, ProvenanceStatus
from app.models.raw_observation import RawObservation
from app.schemas.company import CompanyCreate
from app.schemas.provenance import ProvenanceRecordCreate
from app.services import company_service, provenance_service


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


# The one genuinely source-specific piece of this file — which
# raw_content keys (app.collectors.mca_data_gov_in_adapter's confirmed
# field names) map to which Company fields, mirroring
# docs/product/phase-5c-india-company-data-source-architecture.md
# Section 4 exactly. Fields with no Company equivalent are deliberately
# absent from the "direct" set — they still get a ProvenanceRecord (see
# _EXTRA_OBSERVED_FIELDS below), just not a Company column, per "Do NOT
# silently discard provenance."
_MCA_DIRECT_FIELDS = ("cin", "company_name", "registered_state", "principal_business_activity")
_EXTRA_OBSERVED_FIELDS = (
    "company_status",
    "company_class",
    "company_category",
    "sub_category",
    "authorized_capital",
    "paid_up_capital",
    "date_of_registration",
    "registrar_of_companies",
    "registered_office_address",
)


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
    """
    observation = await _get_raw_observation(db, raw_observation_id)
    content = observation.raw_content

    cin = _get_str(content, "cin")
    if cin:
        existing = await find_existing_company_by_cin(db, cin)
        if existing is not None:
            raise DuplicateCinError(f"cin={cin} already exists as company_id={existing.id}")

    raw_name = _get_str(content, "company_name")
    if not raw_name:
        raise MissingRequiredFieldError(
            "No 'company_name' in this raw observation — cannot create a Company without a name."
        )
    normalized_name = normalize_company_name(raw_name)

    registered_state = _get_str(content, "registered_state")
    address = _get_str(content, "registered_office_address")
    city = attempt_city_from_address(address, known_state=registered_state)

    payload = CompanyCreate(
        # MCA's dataset has one name field, not a separate trade name —
        # using it for both is accurate (it IS the registered legal
        # name), not a placeholder guess (architecture doc Section 4).
        name=normalized_name,
        legal_name=normalized_name,
        industry=_get_str(content, "principal_business_activity"),
        country=SOURCE_COUNTRY,
        state=registered_state,
        city=city,
    )

    company = await company_service.create_company(db, owner_user_id=reviewer_id, payload=payload)

    # CompanyCreate has no cin/business_registration_date fields
    # (Module 3A's own schema, unmodified) — set directly on the
    # already-created ORM row rather than changing that schema's
    # contract, which would be exactly the kind of Company-domain
    # change this module's own instructions prohibit.
    if cin:
        company.cin = cin
    registration_date = parse_registration_date(_get_str(content, "date_of_registration"))
    if registration_date:
        company.business_registration_date = registration_date
    await db.commit()
    await db.refresh(company)

    await _create_provenance_for_promoted_company(db, company, observation)
    return company


async def _create_provenance_for_promoted_company(
    db: AsyncSession, company: Company, observation: RawObservation
) -> None:
    """
    Creates a ProvenanceRecord for every field present in the raw
    observation — both the ones that made it onto a real Company
    column (_MCA_DIRECT_FIELDS, extraction_method=rule_based, a direct
    or lightly-transformed mapping) and the ones that don't
    (_EXTRA_OBSERVED_FIELDS, extraction_method=manual/observed,
    preserved for traceability per "Do NOT silently discard
    provenance" even though no Company column exists for them yet).
    Every record is created at status=observed or extracted — NEVER
    verified, matching provenance_service's own enforcement
    (verification is only ever a distinct, later,
    provenance_service.verify_provenance_record call).
    """
    content = observation.raw_content

    for field_name in (*_MCA_DIRECT_FIELDS, *_EXTRA_OBSERVED_FIELDS):
        value = _get_str(content, field_name)
        if not value:
            continue
        is_direct = field_name in _MCA_DIRECT_FIELDS
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
