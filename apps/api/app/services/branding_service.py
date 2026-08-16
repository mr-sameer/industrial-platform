"""
Logo/cover image upload — Module 3B. Image processing (Pillow, CPU-
bound) always runs off the event loop via `run_in_threadpool` — never
called directly from an async def, which would block every other
in-flight request for the duration of the resize.
"""

from contextlib import suppress

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.file_validation import scan_for_viruses, validate_image
from app.core.image_processing import (
    COVER_RESPONSIVE_WIDTHS,
    LOGO_THUMBNAIL_SIZE,
    make_responsive_variant,
    make_thumbnail,
)
from app.core.storage import StorageBackend, make_object_key
from app.models.company import Company

settings = get_settings()


async def upload_logo(
    db: AsyncSession,
    storage: StorageBackend,
    *,
    company: Company,
    filename: str,
    data: bytes,
    max_size_bytes: int,
) -> Company:
    content_type = validate_image(data, max_size_bytes=max_size_bytes)
    scan_for_viruses(data)

    original_key = make_object_key(
        company_id=company.id, category="logo", original_filename=filename
    )
    original_url = await storage.save(original_key, data, content_type)

    thumbnail_bytes = await run_in_threadpool(
        make_thumbnail, data, content_type, LOGO_THUMBNAIL_SIZE
    )
    thumb_key = make_object_key(
        company_id=company.id, category="logo", original_filename=f"thumb-{filename}"
    )
    thumbnail_url = await storage.save(thumb_key, thumbnail_bytes, content_type)

    # Replacing a logo: delete the previous files after the new ones are
    # safely stored (never leave the company with no logo if the new
    # upload fails partway) — best-effort, a failed cleanup here doesn't
    # roll back the successful upload.
    old_logo_url, old_thumb_url = company.logo_url, company.logo_thumbnail_url

    company.logo_url = original_url
    company.logo_thumbnail_url = thumbnail_url
    await db.commit()
    await db.refresh(company)

    if old_logo_url and old_logo_url != original_url:
        await _try_delete_by_url(storage, old_logo_url)
    if old_thumb_url and old_thumb_url != thumbnail_url:
        await _try_delete_by_url(storage, old_thumb_url)

    return company


async def delete_logo(db: AsyncSession, storage: StorageBackend, *, company: Company) -> Company:
    old_logo_url, old_thumb_url = company.logo_url, company.logo_thumbnail_url
    company.logo_url = None
    company.logo_thumbnail_url = None
    await db.commit()
    await db.refresh(company)
    if old_logo_url:
        await _try_delete_by_url(storage, old_logo_url)
    if old_thumb_url:
        await _try_delete_by_url(storage, old_thumb_url)
    return company


async def upload_cover_image(
    db: AsyncSession,
    storage: StorageBackend,
    *,
    company: Company,
    filename: str,
    data: bytes,
    max_size_bytes: int,
) -> Company:
    """
    Stores the largest responsive variant's URL as `cover_image_url` —
    the module brief's "Responsive rendering" requirement is satisfied by
    generating every configured width variant (COVER_RESPONSIVE_WIDTHS)
    and storing them all, so a future `srcset`-aware frontend can request
    the right one; `Company.cover_image_url` alone always points at a
    usable image for clients that just want one.
    """
    content_type = validate_image(data, max_size_bytes=max_size_bytes)
    scan_for_viruses(data)

    old_cover_url = company.cover_image_url
    largest_url: str | None = None
    for width in COVER_RESPONSIVE_WIDTHS:
        variant_bytes = await run_in_threadpool(make_responsive_variant, data, content_type, width)
        key = make_object_key(
            company_id=company.id, category="cover", original_filename=f"{width}w-{filename}"
        )
        url = await storage.save(key, variant_bytes, content_type)
        largest_url = (
            url  # COVER_RESPONSIVE_WIDTHS is ascending — last write wins, i.e. the largest
        )

    company.cover_image_url = largest_url
    await db.commit()
    await db.refresh(company)

    if old_cover_url and old_cover_url != largest_url:
        await _try_delete_by_url(storage, old_cover_url)

    return company


async def delete_cover_image(
    db: AsyncSession, storage: StorageBackend, *, company: Company
) -> Company:
    old_cover_url = company.cover_image_url
    company.cover_image_url = None
    await db.commit()
    await db.refresh(company)
    if old_cover_url:
        await _try_delete_by_url(storage, old_cover_url)
    return company


async def _try_delete_by_url(storage: StorageBackend, url: str) -> None:
    """
    Best-effort cleanup of a superseded/removed image. Derives the
    storage key by stripping the storage backend's own base URL prefix —
    safe because every StorageBackend.get_url implementation (see
    app.core.storage) always builds URLs as `<base_url>/<key>`. Never
    raises — a failed cleanup leaves an orphaned file, which is a
    harmless, cheap-to-clean-up-later outcome, not worth breaking the
    request that triggered it over.
    """
    base = settings.upload_public_base_url.rstrip("/") + "/"
    if not url.startswith(base):
        return  # not a URL this backend issued (e.g. already migrated to a different backend) — nothing to do
    key = url[len(base) :]
    with suppress(OSError):
        await storage.delete(key)
