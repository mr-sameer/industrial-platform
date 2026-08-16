"""
Offering service layer — Phase 4B. Offering is the Company<->Product
bridge (see app.models.offering's docstring and this module's
ABSOLUTE RULE). Nothing here ever writes to Product — an Offering
mutation only ever touches the offerings table.
"""

import math
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.offering import Offering
from app.schemas.product import OfferingCreate, OfferingUpdate


class DuplicateOfferingError(Exception):
    """Same company + product + role already exists — see the
    uq_offering_company_product_role constraint this maps to."""


async def get_offering(db: AsyncSession, offering_id: uuid.UUID) -> Offering | None:
    result = await db.execute(
        select(Offering)
        .where(Offering.id == offering_id)
        .options(selectinload(Offering.company), selectinload(Offering.product))
    )
    return result.scalar_one_or_none()


async def create_offering(
    db: AsyncSession, company_id: uuid.UUID, payload: OfferingCreate
) -> Offering:
    offering = Offering(
        company_id=company_id,
        product_id=payload.product_id,
        role=payload.role,
        moq=payload.moq,
        lead_time=payload.lead_time,
        capacity=payload.capacity,
        country=payload.country,
    )
    db.add(offering)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateOfferingError(
            f"company={company_id} product={payload.product_id} role={payload.role.value}"
        ) from exc

    refreshed = await get_offering(db, offering.id)
    assert refreshed is not None
    return refreshed


async def update_offering(
    db: AsyncSession, offering: Offering, payload: OfferingUpdate
) -> Offering:
    if payload.role is not None:
        offering.role = payload.role
    if payload.moq is not None:
        offering.moq = payload.moq
    if payload.lead_time is not None:
        offering.lead_time = payload.lead_time
    if payload.capacity is not None:
        offering.capacity = payload.capacity
    if payload.country is not None:
        offering.country = payload.country
    if payload.status is not None:
        offering.status = payload.status

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateOfferingError(
            f"company={offering.company_id} product={offering.product_id} role={offering.role.value}"
        ) from exc

    refreshed = await get_offering(db, offering.id)
    assert refreshed is not None
    return refreshed


async def delete_offering(db: AsyncSession, offering: Offering) -> None:
    await db.delete(offering)
    await db.commit()


async def list_offerings_for_product(
    db: AsyncSession, product_id: uuid.UUID, page: int, page_size: int
) -> tuple[list[Offering], int]:
    query = select(Offering).where(Offering.product_id == product_id)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = int(count_result.scalar_one())

    query = (
        query.options(selectinload(Offering.company), selectinload(Offering.product))
        .order_by(Offering.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    return list(result.scalars().all()), total


def total_pages(total: int, page_size: int) -> int:
    return max(1, math.ceil(total / page_size))
