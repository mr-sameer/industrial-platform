"""
SpecificationAlias service — the dedicated ADMIN-only write path the
deterministic specification-extraction milestone's own completion
report identified as missing. The existing specification-authoring
endpoints (app.api.v1.products.create_category_specification and
create_category) require only an authenticated user, not Role.ADMIN;
rather than weaken that existing surface or route alias creation
through it, this is a new, narrower, ADMIN-gated surface — see
app.api.v1.specification_alias's own docstring for the route layer.

Duplicate/validity checking normalizes with the exact same
app.extraction.label_matching.normalize_label function extraction-time
matching itself uses. Those two must never diverge: an alias that
passes creation here but is compared differently at match time could
either silently fail to match, or slip past this module's own
duplicate check.

The stored `alias` value is never modified from what was submitted —
normalization exists only to compare, exactly mirroring how
SpecificationAlias.alias's own docstring already describes this
column's contract.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extraction.label_matching import normalize_label
from app.models.product_specification import ProductSpecification
from app.models.specification_alias import SpecificationAlias

__all__ = [
    "DuplicateAliasError",
    "EmptyAliasError",
    "SpecificationNotFoundForAliasError",
    "create_alias",
    "list_aliases",
]


class SpecificationNotFoundForAliasError(Exception):
    pass


class EmptyAliasError(Exception):
    """Raised for a whitespace-only alias — Pydantic's Field(min_length=1)
    already rejects a literally empty string but not " "."""


class DuplicateAliasError(Exception):
    """Raised when the normalized alias already matches either an
    existing alias for this specification or the specification's own
    name. An alias identical to the name is meaningless (the name
    already matches by itself — see app.extraction.label_matching); a
    repeated alias is a plain duplicate. Either way, nothing is written."""


async def _get_specification(
    db: AsyncSession, specification_id: uuid.UUID
) -> ProductSpecification | None:
    result = await db.execute(
        select(ProductSpecification).where(ProductSpecification.id == specification_id)
    )
    return result.scalar_one_or_none()


async def list_aliases(db: AsyncSession, specification_id: uuid.UUID) -> list[SpecificationAlias]:
    """No existence check on `specification_id` — matches
    product_attribute_evidence_service.list_attribute_evidence's own
    precedent of returning whatever exists (empty, for a specification
    with none) rather than 404ing a read."""
    result = await db.execute(
        select(SpecificationAlias)
        .where(SpecificationAlias.specification_id == specification_id)
        .order_by(SpecificationAlias.created_at)
    )
    return list(result.scalars().all())


async def create_alias(
    db: AsyncSession, specification_id: uuid.UUID, alias: str
) -> SpecificationAlias:
    specification = await _get_specification(db, specification_id)
    if specification is None:
        raise SpecificationNotFoundForAliasError(str(specification_id))

    if not alias.strip():
        raise EmptyAliasError("alias must not be empty or whitespace-only")

    normalized_new = normalize_label(alias)
    if normalized_new == normalize_label(specification.name):
        raise DuplicateAliasError(
            f"{alias!r} is identical to the specification's own name "
            "— an alias must be a genuine synonym, not a restatement of the name."
        )

    existing = await list_aliases(db, specification_id)
    if any(normalize_label(row.alias) == normalized_new for row in existing):
        raise DuplicateAliasError(
            f"{alias!r} is already configured as an alias for this specification."
        )

    alias_row = SpecificationAlias(specification_id=specification_id, alias=alias)
    db.add(alias_row)
    await db.commit()
    await db.refresh(alias_row)
    return alias_row
