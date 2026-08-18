"""
Requirement matching service — Module 7A-2 (Requirement Matching &
Ranking Engine). Consumes the existing canonical Product/Offering/
Company graph and the existing verification_score_service — read-only,
deterministic, explainable. Implements
docs/product/phase-7a-requirement-intelligence-architecture.md exactly
(candidate retrieval, hard/soft signal split, scoring formula,
certification strictness, tie-breaking) — that document is the source
of truth for every constant and rule below; deviating from it here
without updating it there would be exactly the "silent architecture
change" this module was told not to make.

BOUNDARY: this file never imports or modifies
app.entity_resolution.matching, app.services.data_quality_service,
app.services.company_promotion_service, or anything from Modules
5A-6D. app.services.verification_score_service.calculate() is the one,
sole, read-only integration point with the trust pipeline — its
return value is read, never recomputed or second-guessed here.

THE FACT -> EVIDENCE -> SIGNAL -> SCORE CONTRIBUTION -> EXPLANATION
CONTRACT (architecture doc Section 7) is structural, not decorative:
every scoring function below either cites a real row it read (Evidence)
or returns zero points with a "missing" label — never a positive
contribution without a citable row.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.verification_rules import VerificationLevel
from app.models.company import Company
from app.models.offering import Offering, OfferingStatus
from app.models.product import Product, ProductStatus
from app.models.product_attribute import ProductAttribute
from app.models.requirement import CriterionOperator, Requirement, RequirementSpecificationCriterion
from app.models.verification_document import DocumentStatus, DocumentType, VerificationDocument
from app.services import verification_score_service

# Candidate retrieval bound (a work-budget safety limit, NOT a claim
# about the true candidate universe size — see the architecture doc's
# Section 5 distinction between "candidate retrieval" and "execution/
# work-budget limit"). Fetching one row beyond this lets
# _retrieve_candidates detect truncation without a separate COUNT(*).
_CANDIDATE_CEILING = 500

_TRUST_WEIGHT = 50.0
_LOCATION_WEIGHT = 30.0
_CERTIFICATION_WEIGHT = 20.0
_LOCATION_COUNTRY_POINTS = 15.0
_LOCATION_STATE_POINTS = 10.0
_LOCATION_CITY_POINTS = 5.0

_TRUST_POINTS: dict[VerificationLevel, float] = {
    VerificationLevel.UNVERIFIED: 0.0,
    VerificationLevel.EMAIL_VERIFIED: 12.5,
    VerificationLevel.BUSINESS_VERIFIED: 25.0,
    VerificationLevel.FACTORY_VERIFIED: 37.5,
    VerificationLevel.PREMIUM_VERIFIED: 50.0,
}

# Conservative, whole-word/whole-phrase correspondence ONLY — never a
# blind substring match (e.g. "ce" must never match inside the word
# "certificate"). DocumentType.OTHER is deliberately excluded: too
# generic for any safe correspondence, per the architecture doc's own
# "prefer false negatives" instruction.
_DOCUMENT_TYPE_LABELS: dict[DocumentType, frozenset[str]] = {
    DocumentType.ISO: frozenset({"iso"}),
    DocumentType.CE: frozenset({"ce"}),
    DocumentType.BIS: frozenset({"bis"}),
    DocumentType.GST_CERTIFICATE: frozenset({"gst"}),
    DocumentType.MSME: frozenset({"msme"}),
    DocumentType.FACTORY_LICENSE: frozenset({"factory license"}),
    DocumentType.IMPORT_EXPORT_CODE: frozenset({"iec", "import export code"}),
    DocumentType.BUSINESS_REGISTRATION: frozenset({"business registration"}),
}

_WORD_PATTERN = re.compile(r"[a-z0-9]+")


# --------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CriterionSignal:
    specification_id: uuid.UUID
    specification_name: str
    operator: CriterionOperator
    requirement_value: object
    candidate_value: str | None
    status: str  # always "matched" for a candidate that survives — see compute_matches


@dataclass(frozen=True)
class LocationSignal:
    requested: dict[str, str | None]
    candidate: dict[str, str | None]
    points_earned: float
    points_possible: float


@dataclass(frozen=True)
class CertificationSignal:
    requested: list[str]
    evidence_found: list[str]
    points_earned: float
    points_possible: float
    confidence: str
    note: str | None


@dataclass(frozen=True)
class TrustSignal:
    level: VerificationLevel
    points_earned: float
    points_possible: float


@dataclass(frozen=True)
class ScoreBreakdownEntry:
    signal: str
    weight: float
    points_earned: float


@dataclass(frozen=True)
class MatchCandidate:
    offering: Offering
    product: Product
    company: Company
    score: float
    criteria: list[CriterionSignal]
    location: LocationSignal
    certifications: CertificationSignal
    trust: TrustSignal
    score_breakdown: list[ScoreBreakdownEntry] = field(default_factory=list)


@dataclass(frozen=True)
class MatchesResult:
    status: str  # "computed" | "category_required"
    total_candidates_considered: int
    more_candidates_may_exist: bool
    excluded_for_hard_criteria: int
    candidates: list[MatchCandidate]  # already sorted, deterministic


# --------------------------------------------------------------------------
# Candidate retrieval (Section 5)
# --------------------------------------------------------------------------


async def _retrieve_candidates(
    db: AsyncSession, category_id: uuid.UUID
) -> tuple[list[Offering], bool]:
    stmt = (
        select(Offering)
        .join(Product, Offering.product_id == Product.id)
        .join(Company, Offering.company_id == Company.id)
        .where(
            Product.category_id == category_id,
            Product.status == ProductStatus.PUBLISHED,
            Offering.status == OfferingStatus.ACTIVE,
        )
        .options(selectinload(Offering.product), selectinload(Offering.company))
        .order_by(Offering.created_at.asc(), Offering.id.asc())
        .limit(_CANDIDATE_CEILING + 1)
    )
    result = await db.execute(stmt)
    offerings = list(result.scalars().all())
    more_candidates_may_exist = len(offerings) > _CANDIDATE_CEILING
    return offerings[:_CANDIDATE_CEILING], more_candidates_may_exist


async def _fetch_attributes(
    db: AsyncSession, product_ids: set[uuid.UUID], specification_ids: set[uuid.UUID]
) -> dict[tuple[uuid.UUID, uuid.UUID], str]:
    """Evidence source for the specification-criteria hard filter — one
    batched query, never N+1."""
    if not product_ids or not specification_ids:
        return {}
    result = await db.execute(
        select(ProductAttribute).where(
            ProductAttribute.product_id.in_(product_ids),
            ProductAttribute.specification_id.in_(specification_ids),
        )
    )
    return {(a.product_id, a.specification_id): a.value for a in result.scalars().all()}


async def _fetch_verified_document_types(
    db: AsyncSession, company_ids: set[uuid.UUID]
) -> dict[uuid.UUID, set[DocumentType]]:
    """Evidence source for the certification signal — ONLY
    status == VERIFIED rows are fetched at all; PENDING/REJECTED/EXPIRED
    documents never enter this dict, so they structurally cannot
    contribute a positive certification match (architecture doc
    Section 9)."""
    if not company_ids:
        return {}
    result = await db.execute(
        select(VerificationDocument).where(
            VerificationDocument.company_id.in_(company_ids),
            VerificationDocument.status == DocumentStatus.VERIFIED,
        )
    )
    by_company: dict[uuid.UUID, set[DocumentType]] = {}
    for doc in result.scalars().all():
        by_company.setdefault(doc.company_id, set()).add(doc.document_type)
    return by_company


async def _trust_levels_by_company(
    db: AsyncSession, companies_by_id: dict[uuid.UUID, Company]
) -> dict[uuid.UUID, VerificationLevel]:
    """Read-only integration point with the trust pipeline — calls the
    real, existing, unmodified verification_score_service.calculate()
    once per unique candidate company (deduplicated — a company with
    multiple offerings in the candidate set is scored once)."""
    levels: dict[uuid.UUID, VerificationLevel] = {}
    for company_id, company in companies_by_id.items():
        score = await verification_score_service.calculate(db, company)
        levels[company_id] = score.level
    return levels


# --------------------------------------------------------------------------
# Hard filter: specification criteria (Section 6)
# --------------------------------------------------------------------------


def _parse_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _evaluate_criterion(
    criterion: RequirementSpecificationCriterion, candidate_value: str | None
) -> bool:
    """
    True only if candidate_value is present AND satisfies the
    criterion. `candidate_value is None` (no ProductAttribute row for
    this specification) always evaluates False — missing evidence is
    never treated as a match, the same rule applied everywhere else in
    this file.
    """
    if candidate_value is None:
        return False
    operator = criterion.operator
    requirement_value = criterion.value

    if operator == CriterionOperator.EQ:
        if isinstance(requirement_value, str):
            return candidate_value.strip().lower() == requirement_value.strip().lower()
        parsed = _parse_float(candidate_value)
        return parsed is not None and parsed == float(requirement_value)

    if operator in (CriterionOperator.GTE, CriterionOperator.LTE):
        parsed = _parse_float(candidate_value)
        if parsed is None:
            return False
        threshold = float(requirement_value)
        return parsed >= threshold if operator == CriterionOperator.GTE else parsed <= threshold

    if operator == CriterionOperator.RANGE:
        parsed = _parse_float(candidate_value)
        if parsed is None:
            return False
        low, high = float(requirement_value[0]), float(requirement_value[1])
        return low <= parsed <= high

    if operator == CriterionOperator.IN:
        options = requirement_value if isinstance(requirement_value, list) else [requirement_value]
        string_options = [o for o in options if isinstance(o, str)]
        if string_options:
            return candidate_value.strip().lower() in {o.strip().lower() for o in string_options}
        parsed = _parse_float(candidate_value)
        if parsed is None:
            return False
        return any(parsed == float(o) for o in options)

    return False  # pragma: no cover — exhaustive over CriterionOperator


# --------------------------------------------------------------------------
# Soft signals (Section 6/8)
# --------------------------------------------------------------------------


def _location_fact(offering: Offering, company: Company) -> dict[str, str | None]:
    """Offering.country is primary; Company.country/state/city is the
    fallback — Offering itself has no state/city columns (confirmed
    against the real model, architecture doc Section 6)."""
    return {
        "country": offering.country or company.country,
        "state": company.state,
        "city": company.city,
    }


def _score_location(
    requirement: Requirement, offering: Offering, company: Company
) -> LocationSignal:
    requested = {
        "country": requirement.country,
        "state": requirement.state,
        "city": requirement.city,
    }
    if not any(v is not None for v in requested.values()):
        return LocationSignal(
            requested=requested, candidate={}, points_earned=0.0, points_possible=0.0
        )

    candidate = _location_fact(offering, company)
    points = 0.0

    country_matched = (
        requirement.country is not None
        and candidate["country"] is not None
        and requirement.country.strip().lower() == candidate["country"].strip().lower()
    )
    if country_matched:
        points += _LOCATION_COUNTRY_POINTS

    # State credit requires country to have ACTUALLY matched, per the
    # architecture doc's literal hierarchy — a requirement that omits
    # state entirely therefore also blocks city credit below, even if
    # the candidate happens to be in the right city. A documented,
    # deliberate consequence of the approved formula, not a bug.
    state_matched = (
        country_matched
        and requirement.state is not None
        and candidate["state"] is not None
        and requirement.state.strip().lower() == candidate["state"].strip().lower()
    )
    if state_matched:
        points += _LOCATION_STATE_POINTS

    city_matched = (
        state_matched
        and requirement.city is not None
        and candidate["city"] is not None
        and requirement.city.strip().lower() == candidate["city"].strip().lower()
    )
    if city_matched:
        points += _LOCATION_CITY_POINTS

    return LocationSignal(
        requested=requested,
        candidate=candidate,
        points_earned=points,
        points_possible=_LOCATION_WEIGHT,
    )


def _normalize_words(text: str) -> list[str]:
    return _WORD_PATTERN.findall(text.lower())


def _label_present(requirement_words: list[str], label: str) -> bool:
    label_words = _normalize_words(label)
    if not label_words:
        return False  # pragma: no cover — every configured label is non-empty
    n = len(label_words)
    if n == 1:
        return label_words[0] in requirement_words
    return any(
        requirement_words[i : i + n] == label_words for i in range(len(requirement_words) - n + 1)
    )


def _corresponding_document_types(requirement_certification: str) -> set[DocumentType]:
    words = _normalize_words(requirement_certification)
    return {
        doc_type
        for doc_type, labels in _DOCUMENT_TYPE_LABELS.items()
        if any(_label_present(words, label) for label in labels)
    }


def _score_certifications(
    requirement: Requirement, verified_types: set[DocumentType]
) -> CertificationSignal:
    requested = requirement.certifications or []
    if not requested:
        return CertificationSignal(
            requested=[],
            evidence_found=[],
            points_earned=0.0,
            points_possible=0.0,
            confidence="low",
            note=None,
        )

    evidence_found = [
        cert for cert in requested if _corresponding_document_types(cert) & verified_types
    ]
    points = _CERTIFICATION_WEIGHT * (len(evidence_found) / len(requested))
    note = None if evidence_found else "No VERIFIED evidence found for any requested certification."
    return CertificationSignal(
        requested=requested,
        evidence_found=evidence_found,
        points_earned=points,
        points_possible=_CERTIFICATION_WEIGHT,
        confidence="low",
        note=note,
    )


def _score_trust(level: VerificationLevel) -> TrustSignal:
    return TrustSignal(
        level=level, points_earned=_TRUST_POINTS[level], points_possible=_TRUST_WEIGHT
    )


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


async def compute_matches(db: AsyncSession, requirement: Requirement) -> MatchesResult:
    """
    Requires `requirement.criteria` (and each criterion's
    `.specification`) already eager-loaded — every real caller obtains
    the Requirement via
    app.services.requirement_service.get_requirement_for_user, which
    already selectinloads exactly that.
    """
    if requirement.product_category_id is None:
        # Section 11 — no unbounded global scan, ever.
        return MatchesResult(
            status="category_required",
            total_candidates_considered=0,
            more_candidates_may_exist=False,
            excluded_for_hard_criteria=0,
            candidates=[],
        )

    offerings, more_candidates_may_exist = await _retrieve_candidates(
        db, requirement.product_category_id
    )
    total_candidates_considered = len(offerings)

    criteria = list(requirement.criteria)
    product_ids = {o.product_id for o in offerings}
    specification_ids = {c.specification_id for c in criteria}
    attributes = await _fetch_attributes(db, product_ids, specification_ids)

    company_ids = {o.company_id for o in offerings}
    verified_types_by_company = await _fetch_verified_document_types(db, company_ids)
    companies_by_id = {o.company_id: o.company for o in offerings}
    trust_levels_by_company = await _trust_levels_by_company(db, companies_by_id)

    surviving: list[MatchCandidate] = []
    excluded_count = 0

    for offering in offerings:
        product = offering.product
        company = offering.company

        criterion_signals: list[CriterionSignal] = []
        all_matched = True
        for criterion in criteria:
            candidate_value = attributes.get((product.id, criterion.specification_id))
            if not _evaluate_criterion(criterion, candidate_value):
                all_matched = False
                break
            criterion_signals.append(
                CriterionSignal(
                    specification_id=criterion.specification_id,
                    specification_name=criterion.specification.name,
                    operator=criterion.operator,
                    requirement_value=criterion.value,
                    candidate_value=candidate_value,
                    status="matched",
                )
            )

        if not all_matched:
            excluded_count += 1
            continue

        location_signal = _score_location(requirement, offering, company)
        certification_signal = _score_certifications(
            requirement, verified_types_by_company.get(company.id, set())
        )
        trust_signal = _score_trust(trust_levels_by_company[company.id])

        applicable_weight = _TRUST_WEIGHT
        if location_signal.points_possible > 0:
            applicable_weight += _LOCATION_WEIGHT
        if certification_signal.points_possible > 0:
            applicable_weight += _CERTIFICATION_WEIGHT

        points_earned = (
            trust_signal.points_earned
            + location_signal.points_earned
            + certification_signal.points_earned
        )
        # applicable_weight is always >= _TRUST_WEIGHT (50) — trust is
        # unconditionally included above — so it can never be 0; no
        # zero-division guard needed here.
        final_score = (points_earned / applicable_weight) * 100

        surviving.append(
            MatchCandidate(
                offering=offering,
                product=product,
                company=company,
                score=round(final_score, 2),
                criteria=criterion_signals,
                location=location_signal,
                certifications=certification_signal,
                trust=trust_signal,
                score_breakdown=[
                    ScoreBreakdownEntry("trust_tier", _TRUST_WEIGHT, trust_signal.points_earned),
                    ScoreBreakdownEntry(
                        "location", location_signal.points_possible, location_signal.points_earned
                    ),
                    ScoreBreakdownEntry(
                        "certifications",
                        certification_signal.points_possible,
                        certification_signal.points_earned,
                    ),
                ],
            )
        )

    # Deterministic tie-break — architecture doc Section 12. UUID
    # supports ordering in Python, so offering.id is a valid final key.
    surviving.sort(
        key=lambda m: (
            -m.score,
            -_TRUST_POINTS[m.trust.level],
            m.offering.created_at,
            m.offering.id,
        )
    )

    return MatchesResult(
        status="computed",
        total_candidates_considered=total_candidates_considered,
        more_candidates_may_exist=more_candidates_may_exist,
        excluded_for_hard_criteria=excluded_count,
        candidates=surviving,
    )
