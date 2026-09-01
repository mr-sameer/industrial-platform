"""
Company Verification & Industrial Identity routes — Module 3B. A
separate router file from app.api.v1.companies (Module 3A), deliberately
— this module's brief says "do not modify previous modules," and adding
these endpoints here means companies.py is untouched byte-for-byte.
Mounted under the same `/companies` prefix so the URL surface reads as
one coherent resource family.

Authorization: document/branding/business-info/social-link mutations
require Editor+ (matching Module 3A's company-profile-edit permission —
see docs/domain/09-permission-matrix.md), except document upload/
delete/replace specifically, which require Admin+ — interpreting the
brief's "ADMIN FEATURES: Company Owner: upload/delete/replace documents"
as "Owner and Admin" (consistent with Module 3A's own Certificate
permission pattern, footnote 6) rather than literally Owner-only, since
an Owner-only restriction would be a stricter reading than Module 3A
established for the conceptually equivalent action. Flagged explicitly
per this module's own documentation practice — see
docs/adr/0029-module-3b-verification-and-identity.md.

Phase 1 addition — admin document review: `review_document` below is
gated by the **platform-level** `app.models.user.Role.ADMIN`
(`app.core.dependencies.require_role`), deliberately not
`CompanyRole.ADMIN` (`app.core.company_authorization.require_company_role`,
used everywhere else in this file). Per
docs/domain/09-permission-matrix.md's Certificates & Verification
table, "Approve/Reject Verification" is Platform Admin only — every
company-scoped role, including a company's own Owner/Admin, is ❌. Using
the company-scoped dependency here would let a company approve its own
documents, defeating the entire point of independent verification —
see docs/adr/0029 decision #3's "future admin-review module" note. This
is why the two dependency modules are imported and used side by side
below rather than one being extended to cover both cases.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.core.company_authorization import CompanyOr404, CurrentMembership, require_company_role
from app.core.config import get_settings
from app.core.dependencies import CurrentUser, require_role
from app.core.file_validation import FileValidationError
from app.core.responses import ApiSuccess, success_response
from app.core.storage import StorageBackend, get_storage_backend
from app.db.session import DbSession
from app.models.company import Company
from app.models.company_member import CompanyMember, CompanyRole
from app.models.company_social_link import SocialPlatform
from app.models.user import Role
from app.models.verification_document import DocumentType
from app.schemas.company_verification import (
    BusinessInfoDetail,
    BusinessInfoUpdate,
    CompanyBrandingPublic,
    DocumentReviewRequest,
    MissingRequirementPublic,
    SocialLinkPublic,
    SocialLinkUpsert,
    VerificationDocumentPublic,
    VerificationScorePublic,
)
from app.services import branding_service, document_service, social_link_service
from app.services import verification_score_service as scoring
from app.services.audit_service import log_event
from app.services.company_service import get_by_slug

RequireAdmin = Annotated[object, Depends(require_role(Role.ADMIN))]

router = APIRouter(prefix="/companies", tags=["company-verification"])
settings = get_settings()


def _get_storage() -> StorageBackend:
    return get_storage_backend()


StorageDep = Annotated[StorageBackend, Depends(_get_storage)]


async def _to_score_public(db: DbSession, company: Company) -> VerificationScorePublic:
    score = await scoring.calculate(db, company)
    await scoring.sync_legacy_verification_status(db, company, score)
    return VerificationScorePublic(
        percentage=score.percentage,
        level=score.level,
        readiness_score=score.readiness_score,
        next_level=score.next_level,
        missing_requirements=[
            MissingRequirementPublic(key=m.key, label=m.label, weight=m.weight, level=m.level)
            for m in score.missing_requirements
        ],
        satisfied_requirement_keys=score.satisfied_requirement_keys,
    )


# --------------------------------------------------------------------------
# Verification score (read-only — see app.services.verification_score_service)
# --------------------------------------------------------------------------


@router.get("/{company_id}/verification", response_model=ApiSuccess[VerificationScorePublic])
async def get_verification(
    db: DbSession, company: CompanyOr404, membership: CurrentMembership
) -> ApiSuccess[VerificationScorePublic]:
    """Full detail, including missing requirements — for the company's own dashboard. Requires membership."""
    return success_response(await _to_score_public(db, company))


@router.get("/slug/{slug}/verification", response_model=ApiSuccess[VerificationScorePublic])
async def get_public_verification(slug: str, db: DbSession) -> ApiSuccess[VerificationScorePublic]:
    """Public verification endpoint — unauthenticated, per this module's brief. Powers the public profile's badge."""
    company = await get_by_slug(db, slug)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "COMPANY_NOT_FOUND", "message": "No company with that slug exists."},
        )
    return success_response(await _to_score_public(db, company))


# --------------------------------------------------------------------------
# Business information
# --------------------------------------------------------------------------


@router.get("/{company_id}/business-info", response_model=ApiSuccess[BusinessInfoDetail])
async def get_business_info(
    db: DbSession, company: CompanyOr404, membership: CurrentMembership
) -> ApiSuccess[BusinessInfoDetail]:
    """Read-side counterpart to update_business_info — see BusinessInfoDetail's docstring."""
    return success_response(BusinessInfoDetail.model_validate(company))


@router.patch("/{company_id}/business-info", response_model=ApiSuccess[dict[str, object]])
async def update_business_info(
    payload: BusinessInfoUpdate,
    db: DbSession,
    company: CompanyOr404,
    membership: Annotated[CompanyMember, Depends(require_company_role(CompanyRole.EDITOR))],
) -> ApiSuccess[dict[str, object]]:
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(company, field, value)
    await db.commit()
    await db.refresh(company)
    await log_event(
        db,
        "company_business_info_updated",
        user_id=str(membership.user_id),
        metadata={"company_id": str(company.id), "fields": list(data)},
    )
    return success_response({"updated_fields": list(data)})


# --------------------------------------------------------------------------
# Branding: logo, cover image
# --------------------------------------------------------------------------


@router.get("/{company_id}/branding", response_model=ApiSuccess[CompanyBrandingPublic])
async def get_branding(
    db: DbSession, company: CompanyOr404, membership: CurrentMembership
) -> ApiSuccess[CompanyBrandingPublic]:
    return success_response(
        CompanyBrandingPublic(
            logo_url=company.logo_url,
            logo_thumbnail_url=company.logo_thumbnail_url,
            cover_image_url=company.cover_image_url,
        )
    )


@router.post("/{company_id}/logo", response_model=ApiSuccess[CompanyBrandingPublic])
async def upload_logo(
    db: DbSession,
    storage: StorageDep,
    company: CompanyOr404,
    membership: Annotated[CompanyMember, Depends(require_company_role(CompanyRole.EDITOR))],
    file: Annotated[UploadFile, File(...)],
) -> ApiSuccess[CompanyBrandingPublic]:
    data = await file.read()
    try:
        updated = await branding_service.upload_logo(
            db,
            storage,
            company=company,
            filename=file.filename or "logo",
            data=data,
            max_size_bytes=settings.upload_max_logo_size_bytes,
        )
    except FileValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    await log_event(
        db,
        "company_logo_uploaded",
        user_id=str(membership.user_id),
        metadata={"company_id": str(company.id)},
    )
    return success_response(
        CompanyBrandingPublic(
            logo_url=updated.logo_url,
            logo_thumbnail_url=updated.logo_thumbnail_url,
            cover_image_url=updated.cover_image_url,
        )
    )


@router.delete("/{company_id}/logo", status_code=status.HTTP_204_NO_CONTENT)
async def delete_logo(
    db: DbSession,
    storage: StorageDep,
    company: CompanyOr404,
    membership: Annotated[CompanyMember, Depends(require_company_role(CompanyRole.EDITOR))],
) -> None:
    await branding_service.delete_logo(db, storage, company=company)
    await log_event(
        db,
        "company_logo_deleted",
        user_id=str(membership.user_id),
        metadata={"company_id": str(company.id)},
    )
    return None


@router.post("/{company_id}/cover-image", response_model=ApiSuccess[CompanyBrandingPublic])
async def upload_cover_image(
    db: DbSession,
    storage: StorageDep,
    company: CompanyOr404,
    membership: Annotated[CompanyMember, Depends(require_company_role(CompanyRole.EDITOR))],
    file: Annotated[UploadFile, File(...)],
) -> ApiSuccess[CompanyBrandingPublic]:
    data = await file.read()
    try:
        updated = await branding_service.upload_cover_image(
            db,
            storage,
            company=company,
            filename=file.filename or "cover",
            data=data,
            max_size_bytes=settings.upload_max_cover_size_bytes,
        )
    except FileValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    await log_event(
        db,
        "company_cover_image_uploaded",
        user_id=str(membership.user_id),
        metadata={"company_id": str(company.id)},
    )
    return success_response(
        CompanyBrandingPublic(
            logo_url=updated.logo_url,
            logo_thumbnail_url=updated.logo_thumbnail_url,
            cover_image_url=updated.cover_image_url,
        )
    )


@router.delete("/{company_id}/cover-image", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cover_image(
    db: DbSession,
    storage: StorageDep,
    company: CompanyOr404,
    membership: Annotated[CompanyMember, Depends(require_company_role(CompanyRole.EDITOR))],
) -> None:
    await branding_service.delete_cover_image(db, storage, company=company)
    await log_event(
        db,
        "company_cover_image_deleted",
        user_id=str(membership.user_id),
        metadata={"company_id": str(company.id)},
    )
    return None


# --------------------------------------------------------------------------
# Social links
# --------------------------------------------------------------------------


@router.get("/{company_id}/social-links", response_model=ApiSuccess[list[SocialLinkPublic]])
async def list_social_links(
    db: DbSession, company: CompanyOr404, membership: CurrentMembership
) -> ApiSuccess[list[SocialLinkPublic]]:
    links = await social_link_service.list_social_links(db, company.id)
    return success_response([SocialLinkPublic.model_validate(link) for link in links])


@router.put("/{company_id}/social-links", response_model=ApiSuccess[SocialLinkPublic])
async def upsert_social_link(
    payload: SocialLinkUpsert,
    db: DbSession,
    company: CompanyOr404,
    membership: Annotated[CompanyMember, Depends(require_company_role(CompanyRole.EDITOR))],
) -> ApiSuccess[SocialLinkPublic]:
    link = await social_link_service.upsert_social_link(
        db, company.id, payload.platform, str(payload.url)
    )
    await log_event(
        db,
        "company_social_link_updated",
        user_id=str(membership.user_id),
        metadata={"company_id": str(company.id), "platform": payload.platform.value},
    )
    return success_response(SocialLinkPublic.model_validate(link))


@router.delete("/{company_id}/social-links/{platform}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_social_link(
    platform: SocialPlatform,
    db: DbSession,
    company: CompanyOr404,
    membership: Annotated[CompanyMember, Depends(require_company_role(CompanyRole.EDITOR))],
) -> None:
    removed = await social_link_service.delete_social_link(db, company.id, platform)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "SOCIAL_LINK_NOT_FOUND",
                "message": "No link for that platform exists.",
            },
        )
    await log_event(
        db,
        "company_social_link_removed",
        user_id=str(membership.user_id),
        metadata={"company_id": str(company.id), "platform": platform.value},
    )
    return None


# --------------------------------------------------------------------------
# Verification documents
# --------------------------------------------------------------------------


@router.post(
    "/{company_id}/documents",
    response_model=ApiSuccess[VerificationDocumentPublic],
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    db: DbSession,
    storage: StorageDep,
    company: CompanyOr404,
    membership: Annotated[CompanyMember, Depends(require_company_role(CompanyRole.ADMIN))],
    document_type: Annotated[DocumentType, Form()],
    file: Annotated[UploadFile, File(...)],
) -> ApiSuccess[VerificationDocumentPublic]:
    data = await file.read()
    try:
        document = await document_service.upload_document(
            db,
            storage,
            company_id=company.id,
            uploaded_by=membership.user_id,
            document_type=document_type,
            filename=file.filename or "document",
            data=data,
            max_size_bytes=settings.upload_max_document_size_bytes,
        )
    except FileValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    await log_event(
        db,
        "company_document_uploaded",
        user_id=str(membership.user_id),
        metadata={
            "company_id": str(company.id),
            "document_id": str(document.id),
            "document_type": document_type.value,
        },
    )
    return success_response(VerificationDocumentPublic.model_validate(document))


@router.get("/{company_id}/documents", response_model=ApiSuccess[list[VerificationDocumentPublic]])
async def list_documents(
    db: DbSession, company: CompanyOr404, membership: CurrentMembership
) -> ApiSuccess[list[VerificationDocumentPublic]]:
    documents = await document_service.list_documents(db, company.id)
    return success_response([VerificationDocumentPublic.model_validate(d) for d in documents])


@router.patch(
    "/{company_id}/documents/{document_id}/replace",
    response_model=ApiSuccess[VerificationDocumentPublic],
)
async def replace_document(
    document_id: uuid.UUID,
    db: DbSession,
    storage: StorageDep,
    company: CompanyOr404,
    membership: Annotated[CompanyMember, Depends(require_company_role(CompanyRole.ADMIN))],
    file: Annotated[UploadFile, File(...)],
) -> ApiSuccess[VerificationDocumentPublic]:
    existing = await document_service.get_document_or_none(db, company.id, document_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "DOCUMENT_NOT_FOUND", "message": "No such document on this company."},
        )
    data = await file.read()
    try:
        new_document = await document_service.replace_document(
            db,
            storage,
            existing=existing,
            uploaded_by=membership.user_id,
            filename=file.filename or "document",
            data=data,
            max_size_bytes=settings.upload_max_document_size_bytes,
        )
    except FileValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    await log_event(
        db,
        "company_document_replaced",
        user_id=str(membership.user_id),
        metadata={
            "company_id": str(company.id),
            "old_document_id": str(document_id),
            "new_document_id": str(new_document.id),
        },
    )
    return success_response(VerificationDocumentPublic.model_validate(new_document))


@router.delete("/{company_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    db: DbSession,
    storage: StorageDep,
    company: CompanyOr404,
    membership: Annotated[CompanyMember, Depends(require_company_role(CompanyRole.ADMIN))],
) -> None:
    existing = await document_service.get_document_or_none(db, company.id, document_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "DOCUMENT_NOT_FOUND", "message": "No such document on this company."},
        )
    await document_service.delete_document(
        db, storage, document=existing, deleted_by=membership.user_id
    )
    await log_event(
        db,
        "company_document_deleted",
        user_id=str(membership.user_id),
        metadata={"company_id": str(company.id), "document_id": str(document_id)},
    )
    return None


# --------------------------------------------------------------------------
# Document review (admin) — Phase 1 of the admin document-verification
# review workflow. See this file's module docstring for why RequireAdmin
# (platform Role.ADMIN) is used here instead of require_company_role.
# --------------------------------------------------------------------------


@router.post(
    "/{company_id}/documents/{document_id}/review",
    response_model=ApiSuccess[VerificationDocumentPublic],
)
async def review_document(
    document_id: uuid.UUID,
    payload: DocumentReviewRequest,
    db: DbSession,
    company: CompanyOr404,
    current_user: CurrentUser,
    _admin: RequireAdmin,
) -> ApiSuccess[VerificationDocumentPublic]:
    """
    Platform-admin-only. Deliberately does not depend on CurrentMembership
    or require_company_role — a platform admin reviewing a document is
    not expected to be a member of the company being reviewed at all.
    The document is still resolved by (company_id, document_id) together
    (document_service.get_document_or_none), so a reviewer cannot act on
    a document belonging to a different company by mismatching the two
    path params — the 404 below is IDOR-safe, matching every other
    document endpoint in this file.
    """
    existing = await document_service.get_document_or_none(db, company.id, document_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "DOCUMENT_NOT_FOUND", "message": "No such document on this company."},
        )
    try:
        reviewed = await document_service.review_document(
            db,
            document=existing,
            reviewer_id=current_user.id,
            decision=payload.decision,
            note=payload.note,
        )
    except document_service.DocumentNotPendingError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "DOCUMENT_NOT_PENDING",
                "message": f"This document is already '{existing.status.value}' and cannot be reviewed again.",
            },
        ) from exc

    event = "company_document_verified" if payload.decision == "approve" else "company_document_rejected"
    await log_event(
        db,
        event,
        user_id=str(current_user.id),
        metadata={
            "company_id": str(company.id),
            "document_id": str(document_id),
            "document_type": existing.document_type.value,
            **({"review_note": payload.note} if payload.decision == "reject" else {}),
        },
    )
    return success_response(VerificationDocumentPublic.model_validate(reviewed))
