"""
Company Core routes — Module 3A. Thin per docs/standards/coding-standards.md
— business logic lives in app.services.company_service; this module
translates HTTP/Pydantic and maps domain exceptions to the standard error
envelope (docs/standards/api-response-standard.md).

IDOR prevention: every route that acts on a specific company/member
resolves authorization from app.core.company_authorization (which looks
up the CALLER's own CompanyMember row fresh, every request, from the
path's company_id) — never from anything the client claims in the
request body or query string.

Dependency ordering: on every route below that takes both a
CompanyOr404 and an auth-requiring dependency (CurrentMembership, or
require_company_role(...)), the auth-requiring one is declared FIRST.
FastAPI evaluates sibling dependencies in parameter order, and an
unauthenticated request should always get 401 — never a 404 that
depends on whether the company_id happens to exist, which is what
happens if CompanyOr404 (no auth needed) is resolved first.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.company_authorization import (
    CompanyOr404,
    CurrentMembership,
    require_company_role,
    role_meets_minimum,
)
from app.core.dependencies import CurrentUser, VerifiedUser
from app.core.responses import ApiSuccess, success_response
from app.db.session import DbSession
from app.models.company import Company
from app.models.company_member import CompanyMember, CompanyMemberStatus, CompanyRole
from app.schemas.company import (
    CompanyCreate,
    CompanyDetail,
    CompanyMemberCreate,
    CompanyMemberPublic,
    CompanyMemberUpdate,
    CompanyPublic,
    CompanySearchResult,
    CompanyUpdate,
    Page,
)
from app.services import company_service
from app.services.audit_service import log_event

router = APIRouter(prefix="/companies", tags=["companies"])


# --------------------------------------------------------------------------
# Response-shaping helpers
# --------------------------------------------------------------------------


async def _to_detail(db: DbSession, company: Company, my_role: CompanyRole) -> CompanyDetail:
    member_count = await company_service.get_member_count(db, company.id)
    return CompanyDetail(
        id=company.id,
        name=company.name,
        legal_name=company.legal_name,
        slug=company.slug,
        description=company.description,
        industry=company.industry,
        website=company.website,
        email=company.email,
        phone=company.phone,
        year_established=company.year_established,
        company_size=company.company_size,
        gst_number=company.gst_number,
        country=company.country,
        state=company.state,
        city=company.city,
        status=company.status,
        verification_status=company.verification_status,
        member_count=member_count,
        my_role=my_role,
        created_at=company.created_at,
        updated_at=company.updated_at,
    )


async def _to_public(db: DbSession, company: Company) -> CompanyPublic:
    member_count = await company_service.get_member_count(db, company.id)
    return CompanyPublic(
        id=company.id,
        name=company.name,
        slug=company.slug,
        description=company.description,
        industry=company.industry,
        website=company.website,
        country=company.country,
        city=company.city,
        verification_status=company.verification_status,
        member_count=member_count,
        created_at=company.created_at,
    )


async def _to_member_public(db: DbSession, member: CompanyMember) -> CompanyMemberPublic:
    user = await company_service.get_user_by_id_for_member(db, member.user_id)
    assert (
        user is not None
    )  # FK guarantees this; ON DELETE CASCADE removes the member row otherwise
    return CompanyMemberPublic(
        id=member.id,
        user_id=member.user_id,
        full_name=user.full_name,
        email=user.email,
        role=member.role,
        status=member.status,
        joined_at=member.joined_at,
        created_at=member.created_at,
    )


# --------------------------------------------------------------------------
# Company CRUD
# --------------------------------------------------------------------------


@router.post("", response_model=ApiSuccess[CompanyDetail], status_code=status.HTTP_201_CREATED)
async def create_company(
    payload: CompanyCreate, current_user: VerifiedUser, db: DbSession
) -> ApiSuccess[CompanyDetail]:
    """Requires a verified email — see docs/domain/08-business-rules.md / Module 2.5 Phase 4."""
    company = await company_service.create_company(db, current_user.id, payload)
    await log_event(
        db,
        "company_created",
        user_id=str(current_user.id),
        metadata={"company_id": str(company.id)},
    )
    return success_response(await _to_detail(db, company, CompanyRole.OWNER))


@router.get("", response_model=ApiSuccess[list[CompanyPublic]])
async def list_my_companies(
    current_user: CurrentUser, db: DbSession
) -> ApiSuccess[list[CompanyPublic]]:
    """Companies the current user is a member of — the dashboard/company-switcher data source."""
    companies = await company_service.list_my_companies(db, current_user.id)
    return success_response([await _to_public(db, c) for c in companies])


@router.get("/search", response_model=ApiSuccess[Page])
async def search_companies(
    db: DbSession,
    name: str | None = Query(default=None, max_length=255),
    industry: str | None = Query(default=None, max_length=120),
    country: str | None = Query(default=None, max_length=120),
    city: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="created_at", pattern="^(name|created_at|city|country)$"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> ApiSuccess[Page]:
    """
    Public, unauthenticated search over ACTIVE companies only. No current-user
    dependency here deliberately — mirrors docs/domain/12-search-domain.md's
    principle that discovery doesn't require an account. Registered before
    the /{company_id} route so FastAPI doesn't try to parse "search" as a UUID.
    """
    companies, total = await company_service.search_companies(
        db,
        name=name,
        industry=industry,
        country=country,
        city=city,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    page_result = Page(
        items=[CompanySearchResult.model_validate(c) for c in companies],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=company_service.total_pages(total, page_size),
    )
    return success_response(page_result)


@router.get("/slug/{slug}", response_model=ApiSuccess[CompanyPublic])
async def get_company_by_slug(slug: str, db: DbSession) -> ApiSuccess[CompanyPublic]:
    """Public profile — unauthenticated. See docs/domain/03's Company entry, Section 7."""
    company = await company_service.get_by_slug(db, slug)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "COMPANY_NOT_FOUND", "message": "No company with that slug exists."},
        )
    return success_response(await _to_public(db, company))


@router.get("/{company_id}", response_model=ApiSuccess[CompanyDetail])
async def get_company(
    db: DbSession, membership: CurrentMembership, company: CompanyOr404
) -> ApiSuccess[CompanyDetail]:
    """
    Full detail — requires membership (any role, including Viewer).
    404s for non-members (IDOR-safe). `membership` is declared before
    `company` deliberately: FastAPI evaluates sibling dependencies in
    parameter order, and `get_membership_or_404` requires authentication
    as its own sub-dependency — putting it first guarantees an
    unauthenticated caller always gets 401, even for a company_id that
    doesn't exist, rather than the two failure modes racing.
    """
    return success_response(await _to_detail(db, company, membership.role))


@router.patch("/{company_id}", response_model=ApiSuccess[CompanyDetail])
async def update_company(
    payload: CompanyUpdate,
    db: DbSession,
    membership: Annotated[CompanyMember, Depends(require_company_role(CompanyRole.EDITOR))],
    company: CompanyOr404,
) -> ApiSuccess[CompanyDetail]:
    """Editor+ required. Editor cannot change legal_name/gst_number — enforced in the service layer."""
    updated = await company_service.update_company(db, company, payload, actor_role=membership.role)
    await log_event(
        db,
        "company_updated",
        user_id=str(membership.user_id),
        metadata={
            "company_id": str(company.id),
            "fields": list(payload.model_dump(exclude_unset=True)),
        },
    )
    return success_response(await _to_detail(db, updated, membership.role))


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    db: DbSession,
    membership: Annotated[CompanyMember, Depends(require_company_role(CompanyRole.OWNER))],
    company: CompanyOr404,
) -> None:
    """Owner-only. Soft-delete (archive) — see company_service.archive_company's docstring."""
    await company_service.archive_company(db, company)
    await log_event(
        db,
        "company_deleted",
        user_id=str(membership.user_id),
        metadata={"company_id": str(company.id)},
    )
    return None


# --------------------------------------------------------------------------
# Company members
# --------------------------------------------------------------------------


@router.post(
    "/{company_id}/members",
    response_model=ApiSuccess[CompanyMemberPublic],
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    payload: CompanyMemberCreate,
    db: DbSession,
    membership: Annotated[CompanyMember, Depends(require_company_role(CompanyRole.ADMIN))],
    company: CompanyOr404,
) -> ApiSuccess[CompanyMemberPublic]:
    """Admin+ required. Creates a PENDING membership — see docs/adr/0024 for the accept-invite flow."""
    try:
        new_member = await company_service.add_member(db, company.id, payload)
    except company_service.AlreadyMemberError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "ALREADY_MEMBER",
                "message": "This user is already a member of this company.",
            },
        ) from exc
    await log_event(
        db,
        "company_member_invited",
        user_id=str(membership.user_id),
        metadata={"company_id": str(company.id), "invited_user_id": str(payload.user_id)},
    )
    return success_response(await _to_member_public(db, new_member))


@router.get("/{company_id}/members", response_model=ApiSuccess[list[CompanyMemberPublic]])
async def list_members(
    db: DbSession, membership: CurrentMembership, company: CompanyOr404
) -> ApiSuccess[list[CompanyMemberPublic]]:
    """Any active member (Viewer+) can see the roster."""
    members = await company_service.list_members(db, company.id)
    return success_response([await _to_member_public(db, m) for m in members])


@router.patch("/{company_id}/members/{member_id}", response_model=ApiSuccess[CompanyMemberPublic])
async def update_member(
    company_id: uuid.UUID,
    member_id: uuid.UUID,
    payload: CompanyMemberUpdate,
    db: DbSession,
    caller_membership: CurrentMembership,
) -> ApiSuccess[CompanyMemberPublic]:
    """
    Two authorization paths:
      1. Self-service: a PENDING member accepting their own invitation
         (status: pending -> active only — nothing else about themselves).
      2. Admin+ acting on any member: role changes (including ownership
         transfer via role=owner — see docs/adr/0024), status changes,
         suspension.
    """
    target = await company_service.get_member_or_none(db, company_id, member_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "MEMBER_NOT_FOUND", "message": "No such member on this company."},
        )

    is_self_service_accept = (
        target.id == caller_membership.id
        and target.status == CompanyMemberStatus.PENDING
        and payload.role is None
        and payload.status == CompanyMemberStatus.ACTIVE
    )

    if not is_self_service_accept and not role_meets_minimum(
        caller_membership.role, CompanyRole.ADMIN
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "INSUFFICIENT_COMPANY_ROLE",
                "message": "Requires at least the 'admin' role in this company.",
            },
        )

    try:
        updated = await company_service.update_member(
            db, company_id, target, new_role=payload.role, new_status=payload.status
        )
    except company_service.CannotDemoteLastOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CANNOT_DEMOTE_LAST_OWNER",
                "message": "Transfer ownership to another member before changing the Owner's role or status.",
            },
        ) from exc

    event = (
        "company_ownership_transferred"
        if payload.role == CompanyRole.OWNER
        else "company_member_updated"
    )
    await log_event(
        db,
        event,
        user_id=str(caller_membership.user_id),
        metadata={"company_id": str(company_id), "member_id": str(member_id)},
    )
    return success_response(await _to_member_public(db, updated))


@router.delete("/{company_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    company_id: uuid.UUID,
    member_id: uuid.UUID,
    db: DbSession,
    caller_membership: CurrentMembership,
) -> None:
    """Admin+ can remove any non-Owner member. Any member can remove themselves (leave), except the Owner."""
    target = await company_service.get_member_or_none(db, company_id, member_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "MEMBER_NOT_FOUND", "message": "No such member on this company."},
        )

    is_self = target.id == caller_membership.id
    if not is_self and not role_meets_minimum(caller_membership.role, CompanyRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "INSUFFICIENT_COMPANY_ROLE",
                "message": "Requires at least the 'admin' role in this company.",
            },
        )

    try:
        await company_service.remove_member(db, target)
    except company_service.CannotRemoveOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CANNOT_REMOVE_OWNER",
                "message": "Transfer ownership to another member before removing the current Owner.",
            },
        ) from exc

    await log_event(
        db,
        "company_member_removed",
        user_id=str(caller_membership.user_id),
        metadata={"company_id": str(company_id), "member_id": str(member_id)},
    )
    return None
