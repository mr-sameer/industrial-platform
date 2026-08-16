"""Social links CRUD — Module 3B. Deliberately small; see app.models.company_social_link's docstring."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company_social_link import CompanySocialLink, SocialPlatform


async def list_social_links(db: AsyncSession, company_id: uuid.UUID) -> list[CompanySocialLink]:
    result = await db.execute(
        select(CompanySocialLink)
        .where(CompanySocialLink.company_id == company_id)
        .order_by(CompanySocialLink.platform)
    )
    return list(result.scalars().all())


async def upsert_social_link(
    db: AsyncSession, company_id: uuid.UUID, platform: SocialPlatform, url: str
) -> CompanySocialLink:
    """One row per (company, platform) — see the model's unique constraint. Updates in place if it already exists."""
    result = await db.execute(
        select(CompanySocialLink).where(
            CompanySocialLink.company_id == company_id, CompanySocialLink.platform == platform
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.url = url
        await db.commit()
        await db.refresh(existing)
        return existing

    link = CompanySocialLink(company_id=company_id, platform=platform, url=url)
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return link


async def delete_social_link(
    db: AsyncSession, company_id: uuid.UUID, platform: SocialPlatform
) -> bool:
    result = await db.execute(
        select(CompanySocialLink).where(
            CompanySocialLink.company_id == company_id, CompanySocialLink.platform == platform
        )
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        return False
    await db.delete(existing)
    await db.commit()
    return True
