"""
Company-scoped authorization dependencies — Module 3A. Deliberately
separate from app.core.dependencies (which holds platform-level
`require_role`) per docs/adr/0022-company-role-naming.md: a user's
platform Role and their CompanyRole within a specific company are
independent, and mixing their enforcement into one module would blur
that distinction the ADR exists to prevent.

IDOR prevention: every dependency here resolves membership from
(company_id path param, authenticated user), never trusts a role/company
claimed by the client anywhere else (e.g. a request body) — the only
source of truth for "what can this user do to this company" is the
CompanyMember row looked up here, fresh, per request.
"""

import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser
from app.db.session import get_db
from app.models.company import Company
from app.models.company_member import CompanyMember, CompanyMemberStatus, CompanyRole

# Ordered weakest → strongest. Used so `require_company_role(CompanyRole.ADMIN)`
# means "Admin or anything stronger (Owner)", matching the permission
# matrix's graduated model (docs/domain/09) rather than requiring an exact
# role match at every call site.
_ROLE_ORDER = [CompanyRole.VIEWER, CompanyRole.EDITOR, CompanyRole.ADMIN, CompanyRole.OWNER]


def role_meets_minimum(actual: CompanyRole, minimum: CompanyRole) -> bool:
    """Public helper — reused by app.api.v1.companies for the member-update endpoint's
    conditional authorization (self-accepting an invite vs. an Admin+ acting on someone else)."""
    return _ROLE_ORDER.index(actual) >= _ROLE_ORDER.index(minimum)


def _meets_minimum(actual: CompanyRole, minimum: CompanyRole) -> bool:
    return role_meets_minimum(actual, minimum)


async def get_company_or_404(
    company_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> Company:
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "COMPANY_NOT_FOUND", "message": "No company with that ID exists."},
        )
    return company


CompanyOr404 = Annotated[Company, Depends(get_company_or_404)]


async def get_membership_or_404(
    company_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CompanyMember:
    """
    Resolves the current user's own membership row for this company.
    404s (not 403) if they aren't a member at all — for management
    endpoints, whether a company exists is not information a non-member
    needs distinguished from "you have no access here."
    """
    result = await db.execute(
        select(CompanyMember).where(
            CompanyMember.company_id == company_id,
            CompanyMember.user_id == current_user.id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "COMPANY_NOT_FOUND", "message": "No company with that ID exists."},
        )
    return membership


CurrentMembership = Annotated[CompanyMember, Depends(get_membership_or_404)]


def require_company_role(
    minimum_role: CompanyRole,
) -> Callable[[CompanyMember], Coroutine[Any, Any, CompanyMember]]:
    """
    Usage: `membership: CompanyMember = Depends(require_company_role(CompanyRole.ADMIN))`.
    Requires the caller's membership to be ACTIVE (a pending invite or a
    suspended member cannot act, regardless of the role they'd otherwise
    hold) and at least `minimum_role` per the ordering above.
    """

    async def _check(membership: CurrentMembership) -> CompanyMember:
        if membership.status != CompanyMemberStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "MEMBERSHIP_NOT_ACTIVE",
                    "message": f"Your membership status ({membership.status.value}) does not permit this action.",
                },
            )
        if not _meets_minimum(membership.role, minimum_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "INSUFFICIENT_COMPANY_ROLE",
                    "message": f"Requires at least the '{minimum_role.value}' role in this company.",
                },
            )
        return membership

    return _check
