"""
VerificationScoreService — Module 3B. Computes a Company's verification
percentage, level, and missing requirements **live, from current data**
— never stored/cached as a mutable field a client could edit. This is
what "Verification must be calculated automatically. No manual editing."
(the module brief) means in practice: there is no `PATCH
.../verification` endpoint anywhere, and there never should be — see
docs/adr/0029-module-3b-verification-and-identity.md.

All weights/thresholds come from app.core.verification_rules — nothing
here is a bare number.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.verification_rules import (
    LEVEL_ORDER,
    LEVEL_THRESHOLDS,
    VERIFICATION_REQUIREMENTS,
    Requirement,
    VerificationLevel,
)
from app.models.company import Company, VerificationStatus
from app.models.company_member import CompanyMember, CompanyRole
from app.models.company_social_link import CompanySocialLink
from app.models.user import User
from app.models.verification_document import DocumentStatus, DocumentType, VerificationDocument


@dataclass(frozen=True)
class MissingRequirement:
    key: str
    label: str
    weight: int
    level: VerificationLevel


@dataclass(frozen=True)
class VerificationScore:
    percentage: int
    level: VerificationLevel
    readiness_score: int  # alias of percentage today — see docstring below
    missing_requirements: list[MissingRequirement]
    satisfied_requirement_keys: list[str]

    @property
    def next_level(self) -> VerificationLevel | None:
        idx = LEVEL_ORDER.index(self.level)
        return LEVEL_ORDER[idx + 1] if idx + 1 < len(LEVEL_ORDER) else None


_BUSINESS_REG_TYPES = {DocumentType.BUSINESS_REGISTRATION}
_FACTORY_LICENSE_TYPES = {DocumentType.FACTORY_LICENSE}
_QUALITY_CERT_TYPES = {DocumentType.ISO, DocumentType.CE, DocumentType.BIS}


async def _company_documents(db: AsyncSession, company_id: uuid.UUID) -> list[VerificationDocument]:
    result = await db.execute(
        select(VerificationDocument).where(
            VerificationDocument.company_id == company_id,
            VerificationDocument.is_deleted.is_(False),
        )
    )
    return list(result.scalars().all())


async def _has_document_of_type(
    documents: list[VerificationDocument], types: set[DocumentType]
) -> bool:
    """
    A document counts toward readiness once uploaded (status=pending is
    fine) — this module has no admin-approval workflow yet (see
    docs/adr/0029), so requiring `status == VERIFIED` here would make
    every requirement that depends on a document permanently
    unreachable. Only REJECTED/EXPIRED documents don't count.
    """
    return any(
        d.document_type in types
        and d.status not in (DocumentStatus.REJECTED, DocumentStatus.EXPIRED)
        for d in documents
    )


async def _owner_email_verified(db: AsyncSession, company_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(User.is_email_verified)
        .join(CompanyMember, CompanyMember.user_id == User.id)
        .where(CompanyMember.company_id == company_id, CompanyMember.role == CompanyRole.OWNER)
    )
    return bool(result.scalar_one_or_none())


async def _has_social_link(db: AsyncSession, company_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(func.count())
        .select_from(CompanySocialLink)
        .where(CompanySocialLink.company_id == company_id)
    )
    return int(result.scalar_one()) > 0


async def _check_requirement(
    requirement: Requirement,
    *,
    company: Company,
    documents: list[VerificationDocument],
    owner_email_verified: bool,
    has_social_link: bool,
) -> bool:
    """One branch per requirement key — deliberately explicit (a lookup table of
    lambdas would hide each check's real logic) since there are only 13 of them."""
    match requirement.key:
        case "owner_email_verified":
            return owner_email_verified
        case "legal_entity_type_set":
            return company.legal_entity_type is not None
        case "government_id_set":
            return bool(company.gst_number or company.pan or company.cin)
        case "business_registration_date_set":
            return company.business_registration_date is not None
        case "business_registration_document_uploaded":
            return await _has_document_of_type(documents, _BUSINESS_REG_TYPES)
        case "business_type_set":
            return company.business_type is not None
        case "factory_license_document_uploaded":
            return await _has_document_of_type(documents, _FACTORY_LICENSE_TYPES)
        case "manufacturing_categories_set":
            return bool(company.manufacturing_categories)
        case "logo_uploaded":
            return company.logo_url is not None
        case "cover_image_uploaded":
            return company.cover_image_url is not None
        case "descriptions_complete":
            return bool(company.short_description and company.mission and company.vision)
        case "social_link_added":
            return has_social_link
        case "quality_certificate_uploaded":
            return await _has_document_of_type(documents, _QUALITY_CERT_TYPES)
        case "export_categories_set":
            return bool(company.export_capable and company.export_categories)
        case _:  # pragma: no cover — guards against a Requirement added without a matching branch
            raise AssertionError(f"No check implemented for requirement key: {requirement.key}")


def _level_for_percentage(percentage: int) -> VerificationLevel:
    level = VerificationLevel.UNVERIFIED
    for candidate in LEVEL_ORDER:
        if percentage >= LEVEL_THRESHOLDS[candidate]:
            level = candidate
    return level


async def calculate(db: AsyncSession, company: Company) -> VerificationScore:
    documents = await _company_documents(db, company.id)
    owner_email_verified = await _owner_email_verified(db, company.id)
    has_social_link = await _has_social_link(db, company.id)

    satisfied: list[str] = []
    missing: list[MissingRequirement] = []
    percentage = 0

    for requirement in VERIFICATION_REQUIREMENTS:
        ok = await _check_requirement(
            requirement,
            company=company,
            documents=documents,
            owner_email_verified=owner_email_verified,
            has_social_link=has_social_link,
        )
        if ok:
            percentage += requirement.weight
            satisfied.append(requirement.key)
        else:
            missing.append(
                MissingRequirement(
                    key=requirement.key,
                    label=requirement.label,
                    weight=requirement.weight,
                    level=requirement.level,
                )
            )

    level = _level_for_percentage(percentage)
    return VerificationScore(
        percentage=percentage,
        level=level,
        # "Readiness Score" (module brief) and "percentage" are the same
        # computed value today — kept as a distinct field/name because
        # the brief lists them separately, in case a future module wants
        # them to diverge (e.g. readiness weighted toward *next*-level
        # requirements specifically) without a breaking API-shape change.
        readiness_score=percentage,
        missing_requirements=missing,
        satisfied_requirement_keys=satisfied,
    )


async def sync_legacy_verification_status(
    db: AsyncSession, company: Company, score: VerificationScore
) -> None:
    """
    Best-effort compatibility shim: keeps Module 3A's `Company.verification_status`
    (a coarse unverified/verified boolean-ish field, unmodified schema —
    see docs/adr/0029) meaningfully in sync with the new 5-level score,
    entirely automatically — never manually settable, same as everything
    else this service computes. Called opportunistically wherever a
    company's verification is computed; failing to call it anywhere
    simply means that field lags until the next computation, never that
    it can be set incorrectly.
    """
    target = (
        VerificationStatus.VERIFIED
        if LEVEL_ORDER.index(score.level) >= LEVEL_ORDER.index(VerificationLevel.BUSINESS_VERIFIED)
        else VerificationStatus.UNVERIFIED
    )
    if company.verification_status != target:
        company.verification_status = target
        await db.commit()


def _now() -> (
    datetime
):  # pragma: no cover — trivial, exists only to keep imports tidy for tests to patch
    return datetime.now(UTC)
