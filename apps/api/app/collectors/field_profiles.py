"""
Source field profiles — Module 6D. The one genuinely source-specific
piece of the Company-creation/entity-resolution path, generalized from
a single hardcoded MCA-only field list (app.services.company_promotion_service's
own docstring already named this "the one genuinely source-specific
piece... isolated into module-level constants" — this module turns
that single tuple into one per collector_type, without changing what
it does for mca_data_gov_in at all).

WHY THIS EXISTS: before Module 6D, app.services.company_promotion_service
and app.services.entity_resolution_service both read raw_content using
literal MCA field names ("cin", "company_name", "registered_state",
"registered_office_address") hardcoded at three call sites. That meant
no other source's data could ever be promoted to a Company or reach
entity resolution correctly, regardless of the SourceAdapter/registry
abstraction Module 5B already generalized. This module is the minimal,
additive fix: one `SourceFieldProfile` per collector_type, each
providing its own `extract()` closure (since address/city parsing is
genuinely source-shaped — MCA's free-text Indian address heuristic
does not apply to SEC's already-structured US address fields) plus the
shared direct/extra field lists the provenance-creation loop already
used. Nothing about MCA's own behavior changes — see
tests/test_mca_pilot.py and tests/test_pilot.py, both still green
after this module was introduced.

NEVER conflates identifier types: `strong_id_field`, when set, is the
raw_content key whose value is treated as equivalent in verifiability
to Company.cin (India's CIN) and is written to that same column. SEC's
CIK is deliberately NOT wired here — CIK identifies a company in a
different registry than CIN's, and app.entity_resolution.matching's
own docstring already documents that extending AUTO_MATCH to a new
identifier type is "a deliberate, separately-documented decision," not
implied by adding a new source. SEC's CIK still participates in entity
resolution — via RawObservation.external_reference, Tier 2 of
app.entity_resolution.matching (cross-source identifier match,
REVIEW_REQUIRED) — without needing a Company column at all.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.normalization import attempt_city_from_address, normalize_company_name


def _get_str(content: dict[str, object], key: str) -> str | None:
    value = content.get(key)
    if value is None:
        return None
    return str(value)


@dataclass(frozen=True)
class ExtractedIdentity:
    """What a profile's `extract()` pulls out of one raw_content dict —
    exactly the fields app.services.company_promotion_service and
    app.entity_resolution.matching need, independent of which source
    produced them."""

    strong_id: str | None
    name: str | None
    industry: str | None
    country: str | None
    state: str | None
    city: str | None
    website: str | None


@dataclass(frozen=True)
class SourceFieldProfile:
    collector_type: str
    # raw_content keys that map onto a real Company column AND get a
    # ProvenanceRecord (extraction_method=rule_based, confidence=0.8) —
    # exactly _MCA_DIRECT_FIELDS's former role, now per-source.
    direct_fields: tuple[str, ...]
    # raw_content keys with no Company column equivalent, preserved as
    # provenance-only (extraction_method=manual, confidence=0.5) — never
    # silently discarded, per the architecture doc's own rule.
    extra_fields: tuple[str, ...]
    extract: Callable[[dict[str, object]], ExtractedIdentity]


def _extract_mca(content: dict[str, object]) -> ExtractedIdentity:
    """Byte-for-byte the same extraction
    app.services.company_promotion_service.promote_raw_observation_to_company
    and app.services.entity_resolution_service.generate_candidate_for_observation
    performed before this module existed."""
    cin = _get_str(content, "cin")
    raw_name = _get_str(content, "company_name")
    name = normalize_company_name(raw_name) if raw_name else None
    state = _get_str(content, "registered_state")
    address = _get_str(content, "registered_office_address")
    city = attempt_city_from_address(address, known_state=state)
    return ExtractedIdentity(
        strong_id=cin,
        name=name,
        industry=_get_str(content, "principal_business_activity"),
        country="India",
        state=state,
        city=city,
        website=_get_str(content, "website"),
    )


_MCA_PROFILE = SourceFieldProfile(
    collector_type="mca_data_gov_in",
    direct_fields=("cin", "company_name", "registered_state", "principal_business_activity"),
    extra_fields=(
        "company_status",
        "company_class",
        "company_category",
        "sub_category",
        "authorized_capital",
        "paid_up_capital",
        "date_of_registration",
        "registrar_of_companies",
        "registered_office_address",
        # Module 8A additions. Deliberately extra_fields, never
        # direct_fields: no Company column represents NIC/industrial
        # classification, and per this pilot's explicit CRITICAL
        # constraint, NIC classification must never be treated as
        # evidence of a ForgeX Capability/Offering — it becomes a
        # provenance-only, human-reviewable observation like every
        # other extra_field here, nothing more.
        "indian_foreign_classification",
        "nic_code",
        "industrial_classification",
    ),
    extract=_extract_mca,
)


def _extract_sec_edgar(content: dict[str, object]) -> ExtractedIdentity:
    """
    SEC's own JSON is already field-structured (see
    app.collectors.sec_edgar_adapter) — no free-text address parsing
    needed, unlike MCA. `strong_id` is deliberately None: CIK is never
    written to Company.cin (see this module's own docstring) — SEC
    participates in entity resolution via RawObservation.external_reference
    (Tier 2 of app.entity_resolution.matching) instead.
    """
    raw_name = _get_str(content, "name")
    return ExtractedIdentity(
        strong_id=None,
        name=normalize_company_name(raw_name) if raw_name else None,
        industry=_get_str(content, "sic_description"),
        country="United States",
        state=_get_str(content, "business_address_state"),
        city=_get_str(content, "business_address_city"),
        website=_get_str(content, "website"),
    )


_SEC_EDGAR_PROFILE = SourceFieldProfile(
    collector_type="sec_edgar",
    direct_fields=("name", "sic_description", "business_address_state"),
    extra_fields=(
        "cik",
        "sic",
        "entity_type",
        "ein",
        "category",
        "fiscal_year_end",
        "state_of_incorporation",
        "tickers",
        "exchanges",
        "phone",
        "business_address_city",
        "business_address_street1",
        "business_address_zip",
        "former_names",
    ),
    extract=_extract_sec_edgar,
)


def _extract_manual(content: dict[str, object]) -> ExtractedIdentity:
    """
    Manual entry (Module 6D) — the user IS the source; fields arrive
    already-labeled (see app.collectors.manual_entry_adapter), so no
    parsing/heuristics are needed, only a direct read. `entered_by`,
    `evidence_url`, and `notes` are deliberately NOT in this profile's
    direct/extra field lists — they describe the *submission*, not a
    fact about the company, so they never become a ProvenanceRecord;
    they remain visible on the raw observation itself
    (GET /acquisition/observations/{id}) for audit purposes.
    """
    raw_name = _get_str(content, "company_name")
    return ExtractedIdentity(
        strong_id=None,
        name=normalize_company_name(raw_name) if raw_name else None,
        industry=_get_str(content, "industry"),
        country=_get_str(content, "country"),
        state=_get_str(content, "state"),
        city=_get_str(content, "city"),
        website=_get_str(content, "website"),
    )


_MANUAL_ENTRY_PROFILE = SourceFieldProfile(
    collector_type="manual_entry",
    direct_fields=("company_name", "industry", "state"),
    extra_fields=("city", "website", "description"),
    extract=_extract_manual,
)


def _extract_mock(_content: dict[str, object]) -> ExtractedIdentity:
    """
    MockSourceAdapter (Module 5B) fixtures are shaped
    {"name": ..., "country": ...} — deliberately NOT read here. Before
    Module 6D, the hardcoded MCA-only extraction in
    entity_resolution_service/company_promotion_service only ever
    looked for a "company_name" key, which mock fixtures never had —
    so every mock-sourced candidate has always resolved as NO_MATCH
    (entity resolution) or failed with MissingRequiredFieldError
    (promotion), never as a "found" company. This profile exists so
    "mock" is looked up via real AcquisitionJob lineage like any other
    registered source (never silently defaulted to), while reproducing
    that exact, pre-existing behavior byte-for-byte — not a new,
    smarter mapping onto mock's "name" field.
    """
    return ExtractedIdentity(
        strong_id=None, name=None, industry=None, country=None, state=None, city=None, website=None
    )


_MOCK_PROFILE = SourceFieldProfile(
    collector_type="mock",
    direct_fields=(),
    extra_fields=(),
    extract=_extract_mock,
)


_PROFILES: dict[str, SourceFieldProfile] = {
    _MCA_PROFILE.collector_type: _MCA_PROFILE,
    _SEC_EDGAR_PROFILE.collector_type: _SEC_EDGAR_PROFILE,
    _MANUAL_ENTRY_PROFILE.collector_type: _MANUAL_ENTRY_PROFILE,
    _MOCK_PROFILE.collector_type: _MOCK_PROFILE,
}

# Census CBP / USITC DataWeb are deliberately NEVER added to _PROFILES —
# aggregate/trade data, never company identity (Module 6D Section 36).
# app.services.pilot_service's USA orchestration never calls entity
# resolution/promotion for those collector_types at all (the primary
# enforcement); resolve_profile_for_content below is the defense-in-depth
# backstop — their raw_content shape matches no registered profile and
# no legacy-MCA marker, so it raises UnknownSourceProfileError rather
# than being silently treated as company data.


class UnknownSourceProfileError(Exception):
    """Raised when a raw observation's collector_type/content cannot be
    mapped to a registered SourceFieldProfile — e.g. Census/USITC
    content (aggregate/trade data, never company identity), or a
    genuinely unrecognized shape with no AcquisitionJob lineage.
    Callers must treat this as "this observation cannot be promoted to
    a Company or entered into entity resolution," never as a reason to
    guess a field mapping."""


def get_profile(collector_type: str) -> SourceFieldProfile:
    profile = _PROFILES.get(collector_type)
    if profile is None:
        raise UnknownSourceProfileError(
            f"No SourceFieldProfile registered for collector_type={collector_type!r} — "
            "this source's data cannot be promoted to a Company or enter entity resolution."
        )
    return profile


def has_profile(collector_type: str | None) -> bool:
    return collector_type is not None and collector_type in _PROFILES


# The literal MCA field-name signature (app.collectors.mca_data_gov_in_adapter's
# own confirmed field names) — used ONLY by the narrow legacy-compatibility
# path below, never as a general-purpose "looks kind of like a company"
# heuristic.
_LEGACY_MCA_SHAPE_MARKERS = ("cin", "company_name", "registered_state")


def _is_legacy_mca_shaped(content: dict[str, object]) -> bool:
    return any(marker in content for marker in _LEGACY_MCA_SHAPE_MARKERS)


async def resolve_profile_for_content(
    db: AsyncSession, raw_observation_id: uuid.UUID, content: dict[str, object]
) -> SourceFieldProfile:
    """
    THE single, shared entry point entity_resolution_service and
    company_promotion_service both use to pick a profile. Lineage
    first, always — real AcquisitionJob-created observations (every
    production path, including the mca_data_gov_in/sec_edgar/manual_entry
    adapters and MockSourceAdapter's own dry-run jobs) are routed by
    their actual collector_type, authoritatively, via
    app.services.acquisition_service.get_collector_type_for_observation.
    Census/USITC jobs are routed correctly too — get_profile raises for
    them, exactly as intended (Module 6D Section 36) — nothing here
    special-cases them into silently succeeding.

    ONLY when an observation has no AcquisitionJob lineage at all (a
    real, narrow, pre-Module-6D pattern —
    tests/test_pilot.py's `_create_mca_shaped_observation` constructs
    RawObservations directly, bypassing acquisition_service entirely,
    to unit-test entity resolution in isolation) does this fall back —
    and even then, ONLY to the MCA profile, and ONLY when the content
    carries MCA's own literal field-name signature
    (_is_legacy_mca_shaped). This is a narrow, explicitly-labeled
    legacy-test-compatibility shim, not a general default: any other
    lineage-less, non-MCA-shaped content (which a production caller
    should never produce, since every real observation is created by
    acquisition_service and therefore has lineage) raises
    UnknownSourceProfileError rather than guessing.
    """
    from app.services import acquisition_service  # local import: avoids a module-load-time cycle

    collector_type = await acquisition_service.get_collector_type_for_observation(
        db, raw_observation_id
    )
    if collector_type is not None:
        return get_profile(collector_type)

    if _is_legacy_mca_shaped(content):
        return _MCA_PROFILE

    raise UnknownSourceProfileError(
        f"raw_observation_id={raw_observation_id} has no AcquisitionJob lineage and its "
        "content does not match any known legacy shape — refusing to guess a field profile."
    )
