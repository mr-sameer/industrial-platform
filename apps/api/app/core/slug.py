"""
Slug generation for Company (Module 3A). Deliberately dependency-free
(no python-slugify) — the transformation needed is simple enough that
adding a dependency isn't warranted: lowercase, ASCII-fold accents,
replace anything non-alphanumeric with a single hyphen, trim.
"""

import re
import unicodedata
from collections.abc import Iterator

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = _NON_ALNUM.sub("-", normalized.lower()).strip("-")
    return slug or "company"


def candidate_slugs(base_slug: str) -> Iterator[str]:
    """
    Yields base_slug, then base_slug-2, base_slug-3, ... indefinitely.
    The caller (company_service.create_company) checks each against the
    database and stops at the first unused one — see that function's
    docstring for why this is done as a retry loop rather than a single
    query, and its bounded-attempts guard.
    """
    yield base_slug
    n = 2
    while True:
        yield f"{base_slug}-{n}"
        n += 1
