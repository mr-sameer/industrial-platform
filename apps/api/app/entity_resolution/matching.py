"""
Matching — Module 5D. The deterministic, explainable identity rules.
No LLM, no numeric blended score — per this module's own explicit
instructions ("do not invent a universal numerical score unless the
scoring model is explicitly documented and justified," and "the first
implementation must be deterministic and explainable"). Every signal
is evaluated independently and reported individually; the
resolution_state is decided by simple, fixed, documented rules over
those signals, not a weighted sum.

SIGNAL PRIORITY (as specified): CIN > exact source identifier >
verified domain > strong address match > phone/email > normalized
name > fuzzy name similarity. In this implementation, only CIN
actually reaches AUTO_MATCH — every other signal, even in
combination, produces REVIEW_REQUIRED at most. This is a deliberate,
conservative reading of Phase 9's safety principle ("favor false
negatives over dangerous false positives"): the ticket's own worked
example describes name+address agreement as "potentially high
confidence" language, not "auto match" language, and no second
identifier in this pilot's actual data (Module 5C) is as strong or as
verifiable as CIN. If a future source introduces another genuinely
government-issued, verifiable identifier, extending AUTO_MATCH to it
would be a deliberate, separately-documented decision — not implied by
this file's current behavior.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entity_resolution.normalization import (
    fuzzy_name_similarity,
    normalize_company_name_for_matching,
    normalize_domain,
    normalize_location_component,
)
from app.models.company import Company
from app.models.entity_resolution_candidate import ResolutionState
from app.models.provenance_record import ProvenanceRecord
from app.models.raw_observation import RawObservation

# Fuzzy similarity above this threshold is worth surfacing as a
# REVIEW_REQUIRED candidate at all; below it, two names are considered
# unrelated for matching purposes. A documented, fixed threshold — not
# a tuned/learned parameter, and never used to reach AUTO_MATCH under
# any circumstance (see this module's own docstring).
_FUZZY_NAME_REVIEW_THRESHOLD = 0.72


@dataclass
class MatchSignal:
    signal: str
    matched: bool
    strength: str  # "strong" | "medium" | "weak"
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "signal": self.signal,
            "matched": self.matched,
            "strength": self.strength,
            "detail": self.detail,
        }


@dataclass
class CandidateResult:
    resolution_state: ResolutionState
    candidate_company_id: uuid.UUID | None
    signals: list[MatchSignal] = field(default_factory=list)
    explanation: str = ""


async def _find_by_cin(db: AsyncSession, cin: str) -> Company | None:
    result = await db.execute(select(Company).where(Company.cin == cin))
    return result.scalar_one_or_none()


async def _find_by_exact_source_identifier(
    db: AsyncSession, external_identifier: str | None
) -> Company | None:
    """
    Tier 2 of the priority list: has this exact source identifier
    (regardless of which source) already been used to reach a Company
    via a prior ProvenanceRecord's originating RawObservation? A
    genuinely cross-source check — distinct from CIN, which is a
    specific field value, not "which raw record this came from."
    """
    if not external_identifier:
        return None
    result = await db.execute(
        select(Company)
        .join(ProvenanceRecord, ProvenanceRecord.company_id == Company.id)
        .join(RawObservation, RawObservation.id == ProvenanceRecord.raw_observation_id)
        .where(RawObservation.external_reference == external_identifier)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _find_by_normalized_name_and_address(
    db: AsyncSession,
    normalized_name: str,
    normalized_city: str | None,
    normalized_state: str | None,
) -> list[Company]:
    """Candidates sharing BOTH the normalized name and (city, state) —
    Phase 4's "same normalized name + same strong address" tier.
    Comparison happens in Python against normalized forms (not a SQL
    ILIKE) since Company.name/city/state are stored in their original,
    unnormalized form — matching this module's own "never overwrite
    raw/canonical values" principle; only the comparison is
    normalized, nothing stored is."""
    if not normalized_city or not normalized_state:
        return []
    result = await db.execute(select(Company))
    candidates = []
    for company in result.scalars().all():
        if normalize_company_name_for_matching(company.name) != normalized_name:
            continue
        if normalize_location_component(company.city) != normalized_city:
            continue
        if normalize_location_component(company.state) != normalized_state:
            continue
        candidates.append(company)
    return candidates


async def _find_by_normalized_name_only(db: AsyncSession, normalized_name: str) -> list[Company]:
    result = await db.execute(select(Company))
    return [
        c
        for c in result.scalars().all()
        if normalize_company_name_for_matching(c.name) == normalized_name
    ]


async def _find_by_domain(db: AsyncSession, normalized_domain: str | None) -> Company | None:
    if not normalized_domain:
        return None
    result = await db.execute(select(Company))
    for company in result.scalars().all():
        if normalize_domain(company.website) == normalized_domain:
            return company
    return None


async def generate_candidate(
    db: AsyncSession,
    *,
    cin: str | None,
    company_name: str | None,
    city: str | None,
    state: str | None,
    website: str | None,
    external_identifier: str | None,
) -> CandidateResult:
    """
    The one entry point this module exposes. Evaluates every signal
    independently (never short-circuits after the first match, so the
    explanation always reflects the FULL picture, including any
    conflicting signals — needed for the CONFLICT case, Phase 4/8 Case
    6), then applies fixed, documented rules to decide the overall
    resolution_state.
    """
    signals: list[MatchSignal] = []

    if not company_name:
        # No name at all means there is genuinely nothing to search
        # with — distinct from NEW (a confident "this looks like a
        # real, new company"): this is NO_MATCH, an honest "candidate
        # generation could not run meaningfully."
        return CandidateResult(
            resolution_state=ResolutionState.NO_MATCH,
            candidate_company_id=None,
            signals=[],
            explanation="No company name present in the observation — cannot search for candidates.",
        )

    normalized_name = normalize_company_name_for_matching(company_name)
    normalized_city = normalize_location_component(city)
    normalized_state = normalize_location_component(state)
    normalized_site = normalize_domain(website)

    cin_match: Company | None = None
    if cin:
        cin_match = await _find_by_cin(db, cin)
        signals.append(
            MatchSignal(
                "cin",
                matched=cin_match is not None,
                strength="strong",
                detail=f"cin={cin}"
                + (f" -> company_id={cin_match.id}" if cin_match else " -> no existing company"),
            )
        )

    source_id_match = await _find_by_exact_source_identifier(db, external_identifier)
    if external_identifier:
        signals.append(
            MatchSignal(
                "exact_source_identifier",
                matched=source_id_match is not None,
                strength="strong",
                detail=f"external_identifier={external_identifier}",
            )
        )

    domain_match = await _find_by_domain(db, normalized_site)
    if normalized_site:
        signals.append(
            MatchSignal(
                "verified_domain",
                matched=domain_match is not None,
                strength="medium",
                detail=normalized_site,
            )
        )

    name_address_matches = await _find_by_normalized_name_and_address(
        db, normalized_name, normalized_city, normalized_state
    )
    if normalized_city and normalized_state:
        signals.append(
            MatchSignal(
                "normalized_name_and_address",
                matched=len(name_address_matches) > 0,
                strength="medium",
                detail=f"{normalized_name} @ {normalized_city}, {normalized_state}",
            )
        )

    name_only_matches = await _find_by_normalized_name_only(db, normalized_name)
    signals.append(
        MatchSignal(
            "normalized_name",
            matched=len(name_only_matches) > 0,
            strength="weak",
            detail=normalized_name,
        )
    )

    # Fuzzy similarity is only computed against name-only matches that
    # weren't already an exact normalized-name match, and only
    # reported if it clears the review threshold — otherwise it adds
    # noise without adding a genuine candidate.
    fuzzy_candidates: list[tuple[Company, float]] = []
    if not name_only_matches:
        all_companies = (await db.execute(select(Company))).scalars().all()
        for company in all_companies:
            ratio = fuzzy_name_similarity(
                normalized_name, normalize_company_name_for_matching(company.name)
            )
            if ratio >= _FUZZY_NAME_REVIEW_THRESHOLD:
                fuzzy_candidates.append((company, ratio))
        if fuzzy_candidates:
            best = max(fuzzy_candidates, key=lambda pair: pair[1])
            signals.append(
                MatchSignal(
                    "fuzzy_name_similarity",
                    matched=True,
                    strength="weak",
                    detail=f"best_ratio={best[1]:.2f} against company_id={best[0].id}",
                )
            )

    return _decide(
        signals=signals,
        cin_match=cin_match,
        source_id_match=source_id_match,
        domain_match=domain_match,
        name_address_matches=name_address_matches,
        name_only_matches=name_only_matches,
        fuzzy_candidates=fuzzy_candidates,
    )


def _decide(
    *,
    signals: list[MatchSignal],
    cin_match: Company | None,
    source_id_match: Company | None,
    domain_match: Company | None,
    name_address_matches: list[Company],
    name_only_matches: list[Company],
    fuzzy_candidates: list[tuple[Company, float]],
) -> CandidateResult:
    """
    Fixed, documented rules — not a weighted score. Evaluated in strict
    priority order; the first rule that applies decides the outcome.
    """
    all_weaker_candidates = {
        c.id
        for c in (*name_address_matches, *name_only_matches, *[fc[0] for fc in fuzzy_candidates])
        if domain_match is None or c.id != domain_match.id
    }
    if domain_match is not None:
        all_weaker_candidates.add(domain_match.id)

    # Rule 1: CIN match found -> AUTO_MATCH, full stop, regardless of
    # any other signal (CIN is the strongest available identifier).
    if cin_match is not None:
        return CandidateResult(
            resolution_state=ResolutionState.AUTO_MATCH,
            candidate_company_id=cin_match.id,
            signals=signals,
            explanation=f"Exact CIN match against an existing company (company_id={cin_match.id}).",
        )

    # Rule 2: no CIN in the observation, but a DIFFERENT company was
    # otherwise matched (name/address/domain/fuzzy) AND that company
    # already has its OWN cin on file — this is a genuine identity
    # conflict (Phase 4/8 Case 6), never auto-resolved.
    conflicting_candidates = [
        c
        for c in (*name_address_matches, *name_only_matches, *[fc[0] for fc in fuzzy_candidates])
        if c.cin
    ]
    if conflicting_candidates:
        return CandidateResult(
            resolution_state=ResolutionState.REVIEW_REQUIRED,
            candidate_company_id=conflicting_candidates[0].id,
            signals=signals,
            explanation=(
                "Other signals (name/address) matched a company that already has a different, "
                "recorded CIN — this is a conflict, not a confirmed match. Never auto-merged."
            ),
        )

    # Rule 3: exact cross-source identifier match -> also treated as a
    # strong, but still human-reviewed, candidate (see this module's
    # own docstring for why this doesn't reach AUTO_MATCH in this
    # implementation).
    if source_id_match is not None:
        return CandidateResult(
            resolution_state=ResolutionState.REVIEW_REQUIRED,
            candidate_company_id=source_id_match.id,
            signals=signals,
            explanation=f"Same source identifier already linked to an existing company (company_id={source_id_match.id}).",
        )

    # Rule 4: any medium/weak signal matched -> REVIEW_REQUIRED.
    if all_weaker_candidates:
        candidate_id = next(iter(all_weaker_candidates))
        return CandidateResult(
            resolution_state=ResolutionState.REVIEW_REQUIRED,
            candidate_company_id=candidate_id,
            signals=signals,
            explanation="One or more non-strong signals (name, address, domain, or fuzzy similarity) matched an existing company — requires human review, never auto-merged.",
        )

    # Rule 5: nothing matched at all -> a confident NEW.
    return CandidateResult(
        resolution_state=ResolutionState.NEW,
        candidate_company_id=None,
        signals=signals,
        explanation="No existing company shares any identifying signal with this observation.",
    )
