"""
Company Core business logic — Module 3A. Keeps app.api.v1.companies thin
per docs/standards/coding-standards.md, matching the layering every prior
module (auth_service, session_service, etc.) already established.
"""

import math
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.slug import candidate_slugs, slugify
from app.models.company import Company, CompanyStatus
from app.models.company_member import CompanyMember, CompanyMemberStatus, CompanyRole
from app.models.user import User
from app.schemas.company import CompanyCreate, CompanyMemberCreate, CompanyUpdate

_MAX_SLUG_ATTEMPTS = 50


class CannotRemoveOwnerError(Exception):
    pass


class CannotDemoteLastOwnerError(Exception):
    pass


class AlreadyMemberError(Exception):
    pass


class MemberNotFoundError(Exception):
    pass


async def _generate_unique_slug(db: AsyncSession, name: str) -> str:
    """
    Tries `slugify(name)`, then `-2`, `-3`, ... until an unused one is
    found. A bounded retry loop (not a single "check and hope") because
    concurrent creation of two companies with the same name is possible
    and must not raise an IntegrityError to the caller — the alternative
    (a single INSERT with an ON CONFLICT retry) was considered and
    rejected as premature: Module 3A's expected creation rate makes the
    race window here negligible, and the slug column's unique constraint
    (migration 0003) is the actual backstop if this loop's assumption
    ever proves wrong.
    """
    base = slugify(name)
    for candidate in candidate_slugs(base):
        result = await db.execute(select(Company.id).where(Company.slug == candidate))
        if result.scalar_one_or_none() is None:
            return candidate
        if candidate.count("-") > _MAX_SLUG_ATTEMPTS:  # pragma: no cover — pathological input guard
            raise RuntimeError("Could not generate a unique slug after many attempts")
    raise AssertionError("unreachable")  # pragma: no cover


async def create_company(
    db: AsyncSession, owner_user_id: uuid.UUID, payload: CompanyCreate
) -> Company:
    """
    Creates a Company and, atomically, its first CompanyMember (the
    creator, as Owner, ACTIVE immediately — no invite step needed for
    the person creating the company). See docs/domain/05-aggregate-roots.md
    ("Company") for why this atomicity matters: a Company must never
    exist even momentarily without an Owner.
    """
    slug = await _generate_unique_slug(db, payload.name)

    company = Company(
        name=payload.name,
        legal_name=payload.legal_name,
        slug=slug,
        description=payload.description,
        industry=payload.industry,
        website=payload.website,
        email=payload.email,
        phone=payload.phone,
        year_established=payload.year_established,
        company_size=payload.company_size,
        gst_number=payload.gst_number,
        country=payload.country,
        state=payload.state,
        city=payload.city,
        status=CompanyStatus.ACTIVE,
    )
    db.add(company)
    await db.flush()  # assigns company.id

    owner_membership = CompanyMember(
        company_id=company.id,
        user_id=owner_user_id,
        role=CompanyRole.OWNER,
        status=CompanyMemberStatus.ACTIVE,
        joined_at=datetime.now(UTC),
    )
    db.add(owner_membership)

    await db.commit()
    await db.refresh(company)
    return company


async def get_member_count(db: AsyncSession, company_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(CompanyMember)
        .where(CompanyMember.company_id == company_id)
    )
    return int(result.scalar_one())


async def get_my_role(
    db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID
) -> CompanyRole | None:
    result = await db.execute(
        select(CompanyMember.role).where(
            CompanyMember.company_id == company_id, CompanyMember.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def get_by_slug(db: AsyncSession, slug: str) -> Company | None:
    result = await db.execute(
        select(Company).where(Company.slug == slug, Company.status == CompanyStatus.ACTIVE)
    )
    return result.scalar_one_or_none()


async def list_my_companies(db: AsyncSession, user_id: uuid.UUID) -> list[Company]:
    result = await db.execute(
        select(Company)
        .join(CompanyMember, CompanyMember.company_id == Company.id)
        .where(CompanyMember.user_id == user_id, Company.status != CompanyStatus.ARCHIVED)
        .order_by(Company.created_at.desc())
    )
    return list(result.scalars().all())


async def update_company(
    db: AsyncSession, company: Company, payload: CompanyUpdate, *, actor_role: CompanyRole
) -> Company:
    """
    Applies only the fields the caller's role is allowed to change — see
    docs/domain/09-permission-matrix.md footnote 2: Editor may update
    descriptive/catalog-adjacent fields but not legal identity fields.
    Owner/Admin (already the minimum required to reach this function via
    require_company_role) may change everything.
    """
    data = payload.model_dump(exclude_unset=True)

    editor_restricted_fields = {"legal_name", "gst_number"}
    if actor_role == CompanyRole.EDITOR:
        for field in editor_restricted_fields:
            data.pop(field, None)

    for field, value in data.items():
        setattr(company, field, value)

    await db.commit()
    await db.refresh(company)
    return company


async def archive_company(db: AsyncSession, company: Company) -> None:
    """
    Module 3A's "delete" is a soft delete (archive), not a physical
    DELETE — consistent with docs/domain/03's Company lifecycle
    (Draft → Active → Suspended/Archived) and with keeping historical
    data available for the AuditLog trail the caller writes alongside
    this call. A hard-delete admin action, if ever needed, is a separate,
    deliberately harder-to-reach future capability, not this endpoint.
    """
    company.status = CompanyStatus.ARCHIVED
    await db.commit()


async def add_member(
    db: AsyncSession, company_id: uuid.UUID, payload: CompanyMemberCreate
) -> CompanyMember:
    existing = await db.execute(
        select(CompanyMember).where(
            CompanyMember.company_id == company_id, CompanyMember.user_id == payload.user_id
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise AlreadyMemberError()

    member = CompanyMember(
        company_id=company_id,
        user_id=payload.user_id,
        role=payload.role,
        status=CompanyMemberStatus.PENDING,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


async def get_member_or_none(
    db: AsyncSession, company_id: uuid.UUID, member_id: uuid.UUID
) -> CompanyMember | None:
    result = await db.execute(
        select(CompanyMember).where(
            CompanyMember.company_id == company_id, CompanyMember.id == member_id
        )
    )
    return result.scalar_one_or_none()


async def accept_invitation(db: AsyncSession, member: CompanyMember) -> CompanyMember:
    """The invited user accepting their own pending invite — see docs/adr/0024."""
    member.status = CompanyMemberStatus.ACTIVE
    member.joined_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(member)
    return member


async def update_member(
    db: AsyncSession,
    company_id: uuid.UUID,
    member: CompanyMember,
    *,
    new_role: CompanyRole | None,
    new_status: CompanyMemberStatus | None,
) -> CompanyMember:
    """
    Handles both ordinary role/status changes and ownership transfer
    (new_role=OWNER). See docs/adr/0024-ownership-transfer-mechanism.md
    for why transfer is modeled as "PATCH this member to role=owner"
    rather than a dedicated endpoint, and docs/domain/08-business-rules.md
    for the single-Owner invariant this function enforces.
    """
    if new_role == CompanyRole.OWNER and member.role != CompanyRole.OWNER:
        current_owner_result = await db.execute(
            select(CompanyMember).where(
                CompanyMember.company_id == company_id, CompanyMember.role == CompanyRole.OWNER
            )
        )
        current_owner = current_owner_result.scalar_one_or_none()
        if current_owner is not None and current_owner.id != member.id:
            current_owner.role = CompanyRole.ADMIN  # demoted, not removed — still a member
            # Must physically execute (and pass the single-Owner partial
            # unique index's constraint check) before promoting the new
            # owner below. SQLAlchemy's unit-of-work batches same-table
            # UPDATEs sharing the same changed columns via executemany
            # for efficiency, and does NOT guarantee that batch's
            # statement order matches the order attributes were set in
            # Python — reproduced directly: without this flush, the
            # promote-to-owner UPDATE sometimes executes first within the
            # batch, transiently leaving two Owner rows and violating
            # uq_company_members_one_owner. See
            # tests/test_company_members.py::test_ownership_transfer_via_role_owner,
            # which failed intermittently (order-dependent on the full
            # suite's flush-batching, not the test itself) before this
            # fix.
            await db.flush()
        member.role = CompanyRole.OWNER
        member.status = CompanyMemberStatus.ACTIVE
        if member.joined_at is None:
            member.joined_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(member)
        return member

    if new_role is not None and member.role == CompanyRole.OWNER and new_role != CompanyRole.OWNER:
        raise CannotDemoteLastOwnerError()
    if (
        member.role == CompanyRole.OWNER
        and new_status is not None
        and new_status != CompanyMemberStatus.ACTIVE
    ):
        # Suspending the sole Owner would leave the company with no one
        # able to act as Owner — the same invariant that blocks
        # demoting/removing them (docs/domain/08) applies here too, not
        # just to the `role` field.
        raise CannotDemoteLastOwnerError()

    if new_status == CompanyMemberStatus.ACTIVE and member.joined_at is None:
        member.joined_at = datetime.now(UTC)
    if new_role is not None:
        member.role = new_role
    if new_status is not None:
        member.status = new_status

    await db.commit()
    await db.refresh(member)
    return member


async def remove_member(db: AsyncSession, member: CompanyMember) -> None:
    if member.role == CompanyRole.OWNER:
        raise CannotRemoveOwnerError()
    await db.delete(member)
    await db.commit()


async def search_companies(
    db: AsyncSession,
    *,
    name: str | None,
    industry: str | None,
    country: str | None,
    city: str | None,
    page: int,
    page_size: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[Company], int]:
    query = select(Company).where(Company.status == CompanyStatus.ACTIVE)

    if name:
        like = f"%{name}%"
        query = query.where(or_(Company.name.ilike(like), Company.slug.ilike(like)))
    if industry:
        query = query.where(Company.industry.ilike(f"%{industry}%"))
    if country:
        query = query.where(Company.country.ilike(f"%{country}%"))
    if city:
        query = query.where(Company.city.ilike(f"%{city}%"))

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = int(count_result.scalar_one())

    sort_column = {
        "name": Company.name,
        "created_at": Company.created_at,
        "city": Company.city,
        "country": Company.country,
    }.get(sort_by, Company.created_at)
    order_clause = sort_column.asc() if sort_order == "asc" else sort_column.desc()

    query = query.order_by(order_clause).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    return list(result.scalars().all()), total


def total_pages(total: int, page_size: int) -> int:
    return max(1, math.ceil(total / page_size))


async def list_members(db: AsyncSession, company_id: uuid.UUID) -> list[CompanyMember]:
    result = await db.execute(select(CompanyMember).where(CompanyMember.company_id == company_id))
    return list(result.scalars().all())


async def get_user_by_id_for_member(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
