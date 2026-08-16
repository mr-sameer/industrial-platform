"""
Shared helper for declaring PostgreSQL-backed enum columns from Python
`(str, enum.Enum)` classes.

CRITICAL: without `values_callable=str_enum_values` (or equivalent),
SQLAlchemy's `Enum(SomeEnumClass, ...)` binds and generates DDL using
each member's **name** (e.g. "VIEWER"), not its **value** (e.g.
"viewer") — even for `class Role(str, enum.Enum)` members, despite them
also being `str` instances whose value equals the lowercase string
everywhere else in this codebase (error messages, JSON serialization,
the `.value` used throughout app/schemas/*.py, and every hand-written
Alembic migration's enum labels, e.g. `sa.Enum("admin", "analyst",
"viewer", name="user_role")`).

This mismatch is silent until the very first INSERT against a database
whose schema was created by an Alembic migration rather than
`Base.metadata.create_all` — it does not raise anywhere the enum type
itself is imported. It was found the hard way while building Module 3A,
after `Base.metadata.create_all` (used by the test suite —
tests/conftest.py — for speed, not full parity with Alembic) had been
masking it since Module 2 by deriving column DDL from the exact same
(buggy-default) mapping it also uses to bind values, making it
internally self-consistent and passing all along in tests despite being
broken end-to-end against every real, migration-created database. See
docs/adr/0025-enum-values-callable-bugfix.md for the full incident
writeup and every column this affected.

Usage:
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="user_role", native_enum=True, values_callable=str_enum_values),
        ...
    )
"""

from collections.abc import Sequence
from enum import Enum
from typing import TypeVar

E = TypeVar("E", bound=Enum)


def str_enum_values(enum_cls: type[E]) -> Sequence[str]:
    return [member.value for member in enum_cls]
